"""
MCP 客户端管理器
─────────────────
职责：
  1. 启动一个常驻后台事件循环线程（loop_thread）
  2. 为 mcp_registry.active_configs() 里每个启用的 server 建立 stdio 会话
  3. list_tools() 后把每个工具包成 crewai 的 BaseTool 实例
  4. 同步 .run() 内部把调用桥接到后台事件循环，等待结果
  5. 注册表版本号变化时自动重建（懒重建：调用 get_tools() 时检查）

异常容忍：单个 server 启动失败不会影响其它 server。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from concurrent.futures import Future
from contextlib import AsyncExitStack
from typing import Any

from pydantic import BaseModel, Field, create_model

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamablehttp_client
except ImportError as e:
    raise SystemExit("缺少依赖 mcp，请先安装：pip install mcp") from e

from crewai.tools import BaseTool

from registry import mcp_registry


# ── 后台事件循环线程 ──────────────────────────────────────
class _LoopThread:
    """单例：在后台线程跑一个永不停止的事件循环。"""

    _instance: "_LoopThread | None" = None
    _lock = threading.Lock()

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run, name="mcp-loop", daemon=True
        )
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    @classmethod
    def get(cls) -> "_LoopThread":
        with cls._lock:
            if cls._instance is None:
                cls._instance = _LoopThread()
            return cls._instance

    def run_coro(self, coro, timeout: float | None = None) -> Any:
        fut: Future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return fut.result(timeout=timeout)


# ── 单个 MCP 会话的包装 ─────────────────────────────────
class _Session:
    """一个 MCP server 子进程 + ClientSession 的封装，跑在后台 loop 上。"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.name = cfg["name"]
        self._stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None
        self.tool_specs: list[dict] = []  # [{name, description, input_schema}, ...]

    async def start(self) -> None:
        stack = AsyncExitStack()
        try:
            transport = (self.cfg.get("transport") or "stdio").lower()

            if transport == "stdio":
                command = self.cfg.get("command") or sys.executable
                args = self.cfg.get("args") or []
                env = {**os.environ, **(self.cfg.get("env") or {})}
                params = StdioServerParameters(command=command, args=args, env=env)
                read, write = await stack.enter_async_context(stdio_client(params))
            elif transport in ("http", "streamable-http", "streamable_http"):
                url = self.cfg.get("url") or ""
                if not url:
                    raise ValueError("HTTP MCP server 必须提供 url")
                # streamablehttp_client 返回 (read, write, get_session_id)
                ctx = await stack.enter_async_context(streamablehttp_client(url))
                read, write = ctx[0], ctx[1]
            else:
                raise NotImplementedError(f"暂不支持的 transport: {transport}")

            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            listed = await session.list_tools()
            self.tool_specs = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema or {"type": "object", "properties": {}},
                }
                for t in listed.tools
            ]
            self.session = session
            self._stack = stack
        except Exception:
            await stack.aclose()
            raise

    async def stop(self) -> None:
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:
                pass
            self._stack = None
            self.session = None

    async def call(self, tool_name: str, arguments: dict) -> str:
        assert self.session is not None, "session 未启动"
        result = await self.session.call_tool(tool_name, arguments or {})
        # 把多段 content 拼成字符串
        parts: list[str] = []
        for c in result.content or []:
            text = getattr(c, "text", None)
            if text:
                parts.append(text)
            else:
                parts.append(str(c))
        return "\n".join(parts) if parts else ""


# ── crewai BaseTool 包装器 ──────────────────────────────
def _build_args_model(name: str, schema: dict) -> type[BaseModel]:
    """根据 MCP 的 inputSchema 动态生成 pydantic 模型。"""
    properties = (schema or {}).get("properties") or {}
    required = set((schema or {}).get("required") or [])
    type_map = {
        "string": str, "integer": int, "number": float,
        "boolean": bool, "array": list, "object": dict,
    }
    fields: dict[str, tuple] = {}
    for fname, fspec in properties.items():
        ftype = type_map.get((fspec or {}).get("type"), str)
        default = ... if fname in required else (fspec or {}).get("default", None)
        fields[fname] = (
            ftype if fname in required else (ftype | None),
            Field(default=default, description=(fspec or {}).get("description", "")),
        )
    if not fields:
        fields["__noop__"] = (str | None, Field(default=None, description="(无参数)"))
    return create_model(f"{name}_Args", **fields)


class _McpTool(BaseTool):
    """把一个 MCP tool 暴露成 crewai 的同步 BaseTool。"""

    name: str
    description: str
    args_schema: type[BaseModel]
    _session: _Session
    _tool_name: str
    _timeout: float

    def __init__(self, session: _Session, spec: dict, timeout: float):
        full_name = f"{session.name}.{spec['name']}"
        args_model = _build_args_model(full_name.replace(".", "_"), spec["input_schema"])
        super().__init__(
            name=full_name,
            description=spec["description"] or f"MCP tool {full_name}",
            args_schema=args_model,
        )
        # BaseTool 用 pydantic，私有属性绕过校验
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_tool_name", spec["name"])
        object.__setattr__(self, "_timeout", timeout)

    def _run(self, **kwargs) -> str:
        kwargs.pop("__noop__", None)
        loop = _LoopThread.get()
        try:
            return loop.run_coro(
                self._session.call(self._tool_name, kwargs),
                timeout=self._timeout,
            )
        except Exception as e:
            return json.dumps(
                {"error": f"MCP 调用失败: {type(e).__name__}: {e}"},
                ensure_ascii=False,
            )


# ── 客户端管理器（懒重建） ─────────────────────────────
class _Manager:
    def __init__(self):
        self._version: float = -1.0
        self._sessions: list[_Session] = []
        self._tools: list[BaseTool] = []
        self._lock = threading.Lock()
        self._timeout = float(getattr(mcp_registry, "DEFAULT_TIMEOUT", 30))

    def _rebuild_locked(self) -> None:
        loop = _LoopThread.get()
        # 关闭旧会话
        for s in self._sessions:
            try:
                loop.run_coro(s.stop(), timeout=10)
            except Exception:
                pass
        self._sessions = []
        self._tools = []

        configs = mcp_registry.active_configs()
        for cfg in configs:
            session = _Session(cfg)
            try:
                loop.run_coro(session.start(), timeout=self._timeout)
            except Exception as e:
                print(f"[mcp] 启动 server '{cfg.get('name')}' 失败：{e}", file=sys.stderr)
                continue
            self._sessions.append(session)
            for spec in session.tool_specs:
                self._tools.append(_McpTool(session, spec, self._timeout))

        self._version = mcp_registry.current_version()

    def get_tools(self) -> list[BaseTool]:
        cur_ver = mcp_registry.current_version()
        if cur_ver != self._version:
            with self._lock:
                if cur_ver != self._version:
                    self._rebuild_locked()
        return list(self._tools)

    def shutdown(self) -> None:
        with self._lock:
            loop = _LoopThread.get()
            for s in self._sessions:
                try:
                    loop.run_coro(s.stop(), timeout=5)
                except Exception:
                    pass
            self._sessions = []
            self._tools = []


_manager = _Manager()


# ── 对外 API ───────────────────────────────────────────
def get_mcp_tools() -> list[BaseTool]:
    """返回当前所有启用的 MCP server 暴露的 crewai 工具列表。"""
    return _manager.get_tools()


def reload() -> int:
    """强制重建所有 MCP 连接，返回当前 tool 数量。"""
    with _manager._lock:
        _manager._version = -1.0
        _manager._rebuild_locked()
    return len(_manager._tools)


def shutdown() -> None:
    """关闭所有 MCP 会话（一般进程退出时调用）。"""
    _manager.shutdown()
