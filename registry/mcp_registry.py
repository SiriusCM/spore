"""
MCP 服务端注册表 —— 负责 mcp_servers 表的 CRUD，以及按 mtime/版本号
向上层（mcp_client）暴露最新的"启用配置列表"。

数据表见 database.py 的 mcp_servers 定义。
"""
import json
import sqlite3
import time
from datetime import datetime
from typing import Any

from database import get_conn


_DEFAULT_TIMEOUT = 30


# ── 行 ↔ dict 转换 ──────────────────────────────────────
def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    # JSON 字段反序列化
    for k in ("args", "env"):
        try:
            d[k] = json.loads(d.get(k) or ("[]" if k == "args" else "{}"))
        except Exception:
            d[k] = [] if k == "args" else {}
    d["enabled"] = bool(d.get("enabled"))
    return d


# ── CRUD ───────────────────────────────────────────────
def list_servers(only_enabled: bool = False) -> list[dict]:
    sql = "SELECT * FROM mcp_servers"
    if only_enabled:
        sql += " WHERE enabled=1"
    sql += " ORDER BY id ASC"
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_server(server_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM mcp_servers WHERE id=?", (server_id,)).fetchone()
    return _row_to_dict(row) if row else None


def add_server(data: dict) -> int:
    """新增 MCP server。data 字段：name, transport, command, args, env, url, enabled, description"""
    payload = _normalize(data)
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO mcp_servers
               (name, transport, command, args, env, url, enabled, description, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                payload["name"], payload["transport"], payload["command"],
                payload["args"], payload["env"], payload["url"],
                payload["enabled"], payload["description"],
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        _bump_version()
        return cur.lastrowid


def update_server(server_id: int, data: dict) -> bool:
    payload = _normalize(data, partial=True)
    if not payload:
        return False
    sets = ", ".join(f"{k}=?" for k in payload.keys())
    values = list(payload.values()) + [server_id]
    with get_conn() as conn:
        cur = conn.execute(f"UPDATE mcp_servers SET {sets} WHERE id=?", values)
        conn.commit()
        if cur.rowcount:
            _bump_version()
        return cur.rowcount > 0


def delete_server(server_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM mcp_servers WHERE id=?", (server_id,))
        conn.commit()
        if cur.rowcount:
            _bump_version()
        return cur.rowcount > 0


def set_enabled(server_id: int, enabled: bool) -> bool:
    return update_server(server_id, {"enabled": 1 if enabled else 0})


# ── 字段规范化 ─────────────────────────────────────────
def _normalize(data: dict, partial: bool = False) -> dict:
    out: dict[str, Any] = {}
    keys = {"name", "transport", "command", "args", "env", "url", "enabled", "description"}
    for k in keys:
        if k not in data:
            if partial:
                continue
            # 全量新增时给默认值
            defaults = {
                "transport": "stdio", "command": "", "args": [], "env": {},
                "url": "", "enabled": 1, "description": "",
            }
            if k == "name":
                raise ValueError("name 不能为空")
            out[k] = defaults[k]
            continue
        v = data[k]
        if k == "args":
            out[k] = json.dumps(v if isinstance(v, list) else [], ensure_ascii=False)
        elif k == "env":
            out[k] = json.dumps(v if isinstance(v, dict) else {}, ensure_ascii=False)
        elif k == "enabled":
            out[k] = 1 if v else 0
        else:
            out[k] = str(v or "")
    # 序列化 args/env 在全量场景下也需要
    if not partial:
        if isinstance(out.get("args"), list):
            out["args"] = json.dumps(out["args"], ensure_ascii=False)
        if isinstance(out.get("env"), dict):
            out["env"] = json.dumps(out["env"], ensure_ascii=False)
    return out


# ── "版本号" 用于 mcp_client 判断是否需要重建连接池 ────────
_version: float = 0.0


def _bump_version() -> None:
    global _version
    _version = time.time()


def current_version() -> float:
    """返回当前注册表版本号；任何 CUD 操作后会变化。"""
    return _version


# ── 便利方法：返回 list[dict]（已反序列化）供 mcp_client 启动 ────
def active_configs() -> list[dict]:
    """返回启用的 MCP server 配置列表（字段已反序列化）。"""
    return list_servers(only_enabled=True)


DEFAULT_TIMEOUT = _DEFAULT_TIMEOUT