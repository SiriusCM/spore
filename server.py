"""
Starfish HTTP Server - Flask 入口
所有 API 路由拆分到 api/ 目录下，api.py 只做应用初始化和蓝图注册。
"""
import os
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from settings import init_data_dir

# 初始化数据目录
init_data_dir()

# ── Flask 应用 ──────────────────────────────────────
WEB_DIST = os.path.join(os.path.dirname(__file__), "view", "dist")
LEGACY_STATIC = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(LEGACY_STATIC, exist_ok=True)

app = Flask(__name__, static_folder=WEB_DIST, static_url_path="/")
CORS(app)


# ── 静态 / 健康检查路由 ─────────────────────────────
@app.route("/")
def root():
    """返回 Vite 构建的 Web 界面"""
    index_path = os.path.join(WEB_DIST, "index.html")
    if not os.path.exists(index_path):
        return (
            "<h2>前端尚未构建</h2>"
            "<p>请先在 <code>view/</code> 目录执行：</p>"
            "<pre>npm install\nnpm run build</pre>",
            503,
        )
    return send_from_directory(WEB_DIST, "index.html")


@app.route("/icon.png")
def legacy_icon():
    """PyQt 桌面应用窗口图标"""
    return send_from_directory(LEGACY_STATIC, "icon.png")


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})


# ── 注册蓝图 ────────────────────────────────────────
from api.chat import bp as chat_bp
import api.mcp as mcp_module
from api.settings import bp as settings_bp
from api.skills import bp as skills_bp
from api.agents import bp as agents_bp
from api.evolve import bp as evolve_bp

app.register_blueprint(chat_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(mcp_module.bp)
app.register_blueprint(mcp_module._tools_bp)   # /api/tools/* 独立蓝图
app.register_blueprint(skills_bp)
app.register_blueprint(agents_bp)
app.register_blueprint(evolve_bp)


# ── MCP 预热 + 启动入口 ─────────────────────────────
try:
    from api.state import ensure_mcp_loading
    ensure_mcp_loading()
except Exception:
    pass


def run_server(host: str = "127.0.0.1", port: int = 8765):
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    run_server()