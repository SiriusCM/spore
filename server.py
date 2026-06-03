"""
Starfish HTTP Server - Flask 接口服务
提供问答、进化、快照等 RESTful API
"""
import os
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

from core.orchestrator import run as chat_run
from evolver.evolve import evolve
from evolver.snapshot import take_snapshot, list_snapshots, rollback
from settings import init_data_dir, _user_env

# 初始化数据目录
init_data_dir()

# 静态资源目录：
# - WEB_DIST：Vite 构建产物（前端 SPA），由 `cd vue && npm install && npm run build` 生成
# - LEGACY_STATIC：保留给 PyQt 等非前端资源（如 icon.png）
WEB_DIST = os.path.join(os.path.dirname(__file__), "vue", "dist")
LEGACY_STATIC = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(LEGACY_STATIC, exist_ok=True)

# 创建 Flask 应用：静态目录指向 Vite dist
app = Flask(__name__, static_folder=WEB_DIST, static_url_path='/')
CORS(app)  # 允许跨域

# 兼容旧引用
STATIC_DIR = WEB_DIST


@app.route('/')
def root():
    """返回 Web 界面（Vite 构建产物）"""
    index_path = os.path.join(WEB_DIST, 'index.html')
    if not os.path.exists(index_path):
        return (
            "<h2>前端尚未构建</h2>"
            "<p>请先在 <code>vue/</code> 目录执行：</p>"
            "<pre>npm install\nnpm run build</pre>",
            503,
        )
    return send_from_directory(WEB_DIST, 'index.html')


@app.route('/icon.png')
def legacy_icon():
    """PyQt 等使用的图标（不属于前端构建）"""
    return send_from_directory(LEGACY_STATIC, 'icon.png')


@app.route('/api/chat', methods=['POST'])
def chat():
    """发送消息并获取 AI 回复"""
    data = request.get_json()
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({"success": False, "detail": "Message cannot be empty"}), 400
    
    try:
        response = chat_run(message)
        return jsonify({"success": True, "response": response})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Chat error: {str(e)}"}), 500


@app.route('/api/evolve', methods=['POST'])
def api_evolve():
    """触发进化"""
    data = request.get_json() or {}
    apply = data.get('apply', False)
    
    try:
        result = evolve(dry_run=not apply)
        return jsonify({
            "success": True,
            "apply": apply,
            "result": result
        })
    except Exception as e:
        return jsonify({"success": False, "detail": f"Evolve error: {str(e)}"}), 500


@app.route('/api/snapshots', methods=['GET'])
def api_list_snapshots():
    """获取快照列表"""
    try:
        snaps = list_snapshots()
        return jsonify({"success": True, "snapshots": snaps})
    except Exception as e:
        return jsonify({"success": False, "detail": f"List snapshots error: {str(e)}"}), 500


@app.route('/api/snapshot/take', methods=['POST'])
def api_take_snapshot():
    """创建快照"""
    try:
        path = take_snapshot()
        return jsonify({"success": True, "snapshot": os.path.basename(path)})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Take snapshot error: {str(e)}"}), 500


@app.route('/api/rollback', methods=['POST'])
def api_rollback():
    """回滚到指定快照"""
    data = request.get_json() or {}
    tag = data.get('tag', '')
    
    try:
        result = rollback(tag)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Rollback error: {str(e)}"}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({"status": "ok"})


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """获取当前 LLM 设置"""
    from settings import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY
    return jsonify({
        "success": True,
        "settings": {
            "model": LLM_MODEL,
            "base_url": LLM_BASE_URL,
            "api_key": LLM_API_KEY
        }
    })


@app.route('/api/settings', methods=['POST'])
def save_settings():
    """保存 LLM 设置到环境变量文件"""
    data = request.get_json() or {}
    model = data.get('model', '')
    base_url = data.get('base_url', '')
    api_key = data.get('api_key', '')

    try:
        # 写入用户目录下的 env 文件
        lines = []
        if model:
            lines.append(f"LLM_MODEL={model}")
        if base_url:
            lines.append(f"LLM_BASE_URL={base_url}")
        if api_key:
            lines.append(f"LLM_API_KEY={api_key}")

        with open(_user_env, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

        # 重新加载环境变量
        from dotenv import load_dotenv
        load_dotenv(_user_env, override=True)

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Save settings error: {str(e)}"}), 500


# ── MCP 服务端管理 ──────────────────────────────────────
from core import mcp_client
from registry import mcp_registry, prompt_registry, skill_registry, agent_registry as agent_reg


@app.route('/api/mcp/servers', methods=['GET'])
def api_mcp_list():
    """列出所有 MCP 服务端"""
    try:
        return jsonify({"success": True, "servers": mcp_registry.list_servers()})
    except Exception as e:
        return jsonify({"success": False, "detail": f"List error: {e}"}), 500


@app.route('/api/mcp/servers', methods=['POST'])
def api_mcp_add():
    """新增 MCP 服务端"""
    data = request.get_json() or {}
    try:
        sid = mcp_registry.add_server(data)
        _invalidate_tools_cache()
        return jsonify({"success": True, "id": sid})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Add error: {e}"}), 400


@app.route('/api/mcp/servers/<int:sid>', methods=['PUT'])
def api_mcp_update(sid: int):
    """更新 MCP 服务端"""
    data = request.get_json() or {}
    try:
        ok = mcp_registry.update_server(sid, data)
        _invalidate_tools_cache()
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Update error: {e}"}), 400


@app.route('/api/mcp/servers/<int:sid>', methods=['DELETE'])
def api_mcp_delete(sid: int):
    """删除 MCP 服务端"""
    try:
        ok = mcp_registry.delete_server(sid)
        _invalidate_tools_cache()
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Delete error: {e}"}), 500


@app.route('/api/mcp/servers/<int:sid>/toggle', methods=['POST'])
def api_mcp_toggle(sid: int):
    """启停 MCP 服务端"""
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", True))
    try:
        ok = mcp_registry.set_enabled(sid, enabled)
        _invalidate_tools_cache()
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Toggle error: {e}"}), 500


@app.route('/api/mcp/reload', methods=['POST'])
def api_mcp_reload():
    """强制重连所有启用的 MCP server，返回当前 tool 数量"""
    try:
        count = mcp_client.reload()
        _invalidate_tools_cache()
        return jsonify({"success": True, "tools": count})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Reload error: {e}"}), 500


@app.route('/api/mcp/tools', methods=['GET'])
def api_mcp_tools():
    """返回当前已加载的 MCP 工具清单"""
    try:
        tools = mcp_client.get_mcp_tools()
        return jsonify({
            "success": True,
            "tools": [{"name": t.name, "description": t.description} for t in tools],
        })
    except Exception as e:
        return jsonify({"success": False, "detail": f"Tools error: {e}"}), 500


# ── Skill 管理 ─────────────────────────────────────────
@app.route('/api/skills', methods=['GET'])
def api_skill_list():
    """列出所有 skill"""
    try:
        return jsonify({"success": True, "skills": skill_registry.list_skills()})
    except Exception as e:
        return jsonify({"success": False, "detail": f"List error: {e}"}), 500


@app.route('/api/skills', methods=['POST'])
def api_skill_add():
    """新增 skill"""
    data = request.get_json() or {}
    try:
        sid = skill_registry.add_skill(data)
        return jsonify({"success": True, "id": sid})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Add error: {e}"}), 400


@app.route('/api/skills/<int:sid>', methods=['PUT'])
def api_skill_update(sid: int):
    data = request.get_json() or {}
    try:
        ok = skill_registry.update_skill(sid, data)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Update error: {e}"}), 400


@app.route('/api/skills/<int:sid>', methods=['DELETE'])
def api_skill_delete(sid: int):
    try:
        ok = skill_registry.delete_skill(sid)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Delete error: {e}"}), 500


@app.route('/api/skills/<int:sid>/toggle', methods=['POST'])
def api_skill_toggle(sid: int):
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", True))
    try:
        ok = skill_registry.set_enabled(sid, enabled)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Toggle error: {e}"}), 500


@app.route('/api/skills/<int:sid>/export', methods=['GET'])
def api_skill_export(sid: int):
    """下载某个 skill 的 zip 包"""
    try:
        filename, payload = skill_registry.export_skill_zip(sid)
        return Response(
            payload,
            mimetype="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(payload)),
            },
        )
    except Exception as e:
        return jsonify({"success": False, "detail": f"Export error: {e}"}), 400


@app.route('/api/skills/import', methods=['POST'])
def api_skill_import():
    """上传 skill zip 包导入。可选 form 字段 overwrite=1 表示覆盖同名。"""
    if "file" not in request.files:
        return jsonify({"success": False, "detail": "缺少 file 字段"}), 400
    f = request.files["file"]
    overwrite = (request.form.get("overwrite") or "").lower() in ("1", "true", "yes")
    try:
        result = skill_registry.import_skill_zip(f.read(), overwrite=overwrite)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Import error: {e}"}), 400


# ── Agent 管理 ─────────────────────────────────────────
@app.route('/api/agents', methods=['GET'])
def api_agent_list():
    try:
        return jsonify({"success": True, "agents": agent_reg.list_agents()})
    except Exception as e:
        return jsonify({"success": False, "detail": f"List error: {e}"}), 500


@app.route('/api/agents', methods=['POST'])
def api_agent_add():
    data = request.get_json() or {}
    required = ["id", "name", "role", "goal", "backstory"]
    for k in required:
        if not data.get(k):
            return jsonify({"success": False, "detail": f"缺少字段 {k}"}), 400
    if not data.get("domains"):
        data["domains"] = ["*"]
    try:
        ok = agent_reg.add_agent(data)
        return jsonify({"success": ok, "detail": "" if ok else "id 已存在或写入失败"})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Add error: {e}"}), 400


@app.route('/api/agents/<agent_id>', methods=['PUT'])
def api_agent_update(agent_id: str):
    data = request.get_json() or {}
    try:
        ok = agent_reg.update_agent(agent_id, data)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Update error: {e}"}), 400


@app.route('/api/agents/<agent_id>', methods=['DELETE'])
def api_agent_delete(agent_id: str):
    try:
        ok = agent_reg.delete_agent(agent_id)
        return jsonify({"success": ok, "detail": "" if ok else "通用助手不可删除或 id 不存在"})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Delete error: {e}"}), 500


@app.route('/api/agents/<agent_id>/toggle', methods=['POST'])
def api_agent_toggle(agent_id: str):
    data = request.get_json() or {}
    enabled = bool(data.get("enabled", True))
    try:
        ok = agent_reg.set_enabled(agent_id, enabled)
        return jsonify({"success": ok, "detail": "" if ok else "通用助手不可禁用"})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Toggle error: {e}"}), 500


# ── Prompt 常量覆盖 ─────────────────────────────────────
@app.route('/api/prompts', methods=['GET'])
def api_prompt_list():
    """列出所有可覆盖的 prompt 常量及当前覆盖值。
    同时返回 prompts.py 默认值（defaults）方便前端做 placeholder 提示。"""
    try:
        items = prompt_registry.list_overrides()
        # 加入默认值（来自当前 prompts.py + 已应用的 override，前端能看到"实际生效值"）
        from core.orchestrator import _load_prompts
        eff = _load_prompts()
        for it in items:
            it["effective"] = getattr(eff, it["key"], "")
        return jsonify({"success": True, "items": items, "allowed_keys": list(prompt_registry.ALLOWED_KEYS)})
    except Exception as e:
        return jsonify({"success": False, "detail": f"List error: {e}"}), 500


@app.route('/api/prompts/<key>', methods=['PUT'])
def api_prompt_set(key: str):
    data = request.get_json() or {}
    value = data.get("value", "")
    try:
        prompt_registry.set_override(key, value)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "detail": f"{e}"}), 400


@app.route('/api/prompts/<key>', methods=['DELETE'])
def api_prompt_delete(key: str):
    try:
        ok = prompt_registry.delete_override(key)
        return jsonify({"success": ok})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Delete error: {e}"}), 500


# ── 工具列表（只读：内置工具 + MCP 工具合并展示）────────
# 设计：
#   · 内置工具同步加载（仅 import script/tools.py，毫秒级）
#   · MCP 工具异步加载：服务启动后由后台线程预热，前端轮询 /api/tools/mcp 拿状态
#   · 拆分两个端点的目的——MCP server 可能连不上/超时，绝对不能阻塞请求线程
import time as _time
import threading as _threading

# 内置工具的轻量缓存（30s）。重新进化、改 script/tools.py 后无需重启即可看到新工具。
_BUILTIN_CACHE: dict = {"data": None, "ts": 0.0}
_BUILTIN_TTL = 30.0

# MCP 工具状态机：status ∈ {"idle","loading","ready","error"}
_MCP_STATE: dict = {
    "status": "idle",
    "tools": [],
    "error": "",
    "ts": 0.0,
}
_MCP_LOCK = _threading.Lock()


def _invalidate_tools_cache():
    """MCP 配置变动后调用：清空内置 TTL 缓存，并把 MCP 状态重置为 idle，
    下一次请求 /api/tools/mcp 会自动后台重载。"""
    _BUILTIN_CACHE["data"] = None
    _BUILTIN_CACHE["ts"] = 0.0
    with _MCP_LOCK:
        _MCP_STATE["status"] = "idle"
        _MCP_STATE["tools"] = []
        _MCP_STATE["error"] = ""


def _list_builtin_tools() -> list[dict]:
    """同步加载内置工具，毫秒级。"""
    out = []
    try:
        from core.orchestrator import _load_script
        tools_mod = _load_script("tools")
        for t in getattr(tools_mod, "ALL_TOOLS", []):
            out.append({
                "name": getattr(t, "name", t.__class__.__name__),
                "description": getattr(t, "description", "") or "",
                "source": "builtin",
                "server": "",
            })
    except Exception as e:
        out.append({"name": "(builtin load error)", "description": str(e), "source": "error", "server": ""})
    return out


def _mcp_loader_worker():
    """后台线程：实际去拉 MCP 工具，可能很慢/超时/失败。"""
    try:
        items = []
        for t in mcp_client.get_mcp_tools():
            full = getattr(t, "name", "")  # 形如 "mysql.mysql_exec"
            server = full.split(".", 1)[0] if "." in full else ""
            short = full.split(".", 1)[1] if "." in full else full
            items.append({
                "name": short,
                "full_name": full,
                "description": getattr(t, "description", "") or "",
                "source": "mcp",
                "server": server,
            })
        with _MCP_LOCK:
            _MCP_STATE["status"] = "ready"
            _MCP_STATE["tools"] = items
            _MCP_STATE["error"] = ""
            _MCP_STATE["ts"] = _time.time()
    except Exception as e:
        with _MCP_LOCK:
            _MCP_STATE["status"] = "error"
            _MCP_STATE["tools"] = []
            _MCP_STATE["error"] = str(e)
            _MCP_STATE["ts"] = _time.time()


def _ensure_mcp_loading():
    """如果当前不是 loading，则触发后台加载。返回是否真的启动了新任务。"""
    with _MCP_LOCK:
        if _MCP_STATE["status"] == "loading":
            return False
        _MCP_STATE["status"] = "loading"
        _MCP_STATE["error"] = ""
    _threading.Thread(target=_mcp_loader_worker, name="mcp-tools-loader", daemon=True).start()
    return True


@app.route('/api/tools/builtin', methods=['GET'])
def api_tools_builtin():
    """同步返回内置工具，毫秒级。"""
    now = _time.time()
    cached = _BUILTIN_CACHE["data"]
    if cached is None or (now - _BUILTIN_CACHE["ts"] >= _BUILTIN_TTL):
        cached = _list_builtin_tools()
        _BUILTIN_CACHE["data"] = cached
        _BUILTIN_CACHE["ts"] = now
    return jsonify({"success": True, "tools": cached, "count": len(cached)})


@app.route('/api/tools/mcp', methods=['GET'])
def api_tools_mcp():
    """异步加载 MCP 工具：
    - 第一次调用：触发后台拉取，立即返回 status=loading
    - 后续轮询：返回 status=ready/error 与结果
    - ?force=1：强制重新拉
    """
    force = (request.args.get("force") or "").lower() in ("1", "true", "yes")
    if force:
        with _MCP_LOCK:
            _MCP_STATE["status"] = "idle"
    with _MCP_LOCK:
        status = _MCP_STATE["status"]
    if status == "idle":
        _ensure_mcp_loading()
        with _MCP_LOCK:
            status = _MCP_STATE["status"]
    with _MCP_LOCK:
        snapshot = {
            "status": _MCP_STATE["status"],
            "tools": list(_MCP_STATE["tools"]),
            "error": _MCP_STATE["error"],
            "ts": _MCP_STATE["ts"],
        }
    snapshot["success"] = True
    snapshot["count"] = len(snapshot["tools"])
    return jsonify(snapshot)


@app.route('/api/tools', methods=['GET'])
def api_tools_list():
    """聚合接口（向后兼容）：内置同步 + MCP 当前状态。
    MCP 还在加载时不阻塞，前端可以根据 mcp_status 决定是否再轮询。"""
    builtin = _list_builtin_tools()
    with _MCP_LOCK:
        if _MCP_STATE["status"] == "idle":
            _ensure_mcp_loading()
        mcp_status = _MCP_STATE["status"]
        mcp_tools = list(_MCP_STATE["tools"])
        mcp_error = _MCP_STATE["error"]
    items = builtin + mcp_tools
    return jsonify({
        "success": True,
        "tools": items,
        "count": len(items),
        "mcp_status": mcp_status,
        "mcp_error": mcp_error,
    })


# 启动时主动预热一次 MCP 工具加载，让用户首次打开「工具列表」时大概率已就绪
try:
    _ensure_mcp_loading()
except Exception:
    pass


def run_server(host: str = "127.0.0.1", port: int = 8765):
    """启动 HTTP 服务器"""
    app.run(host=host, port=port, debug=False, threaded=True)
