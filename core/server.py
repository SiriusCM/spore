"""
Starfish HTTP Server - Flask 接口服务
提供问答、进化、快照等 RESTful API
"""
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from core.orchestrator import run as chat_run
from evolver.evolve import evolve
from evolver.snapshot import take_snapshot, list_snapshots, rollback
from settings import DATA_DIR, init_data_dir, _user_env

# 初始化数据目录
init_data_dir()

# 创建 Flask 应用
app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)  # 允许跨域

# 静态文件目录
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)


@app.route('/')
def root():
    """返回 Web 界面"""
    return send_from_directory(STATIC_DIR, 'index.html')


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


def run_server(host: str = "127.0.0.1", port: int = 8765):
    """启动 HTTP 服务器"""
    app.run(host=host, port=port, debug=False, threaded=True)