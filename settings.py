import os
import shutil
from dotenv import load_dotenv

# ── 目录划分 ──────────────────────────────────────────
# PKG_DIR  : 包安装位置（只读，存放代码和默认模板）
# DATA_DIR : 用户数据目录（可写，存放运行时配置、日志、可进化脚本）
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.expanduser("~"), ".spore")

# env 加载：用户目录 ~/.spore/config/env
_user_config_dir = os.path.join(DATA_DIR, "config")
_user_env = os.path.join(_user_config_dir, "env")
_pkg_env = os.path.join(PKG_DIR, "config", "env")
if os.path.exists(_user_env):
    load_dotenv(_user_env)

LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")

SHELL_BLACKLIST = ["rm -rf /", "sudo rm", "mkfs", ":(){:|:&};:", "shutdown", "reboot", "dd if="]

MEMORY_ENABLED = True
MAX_HISTORY = 20

# ── 运行时可写目录（全部在 ~/.spore/ 下）──────────
SCRIPT_DIR = os.path.join(DATA_DIR, "script")       # prompts.py, tools.py（可被 evolver 修改）

# ── 包内只读目录 ────────────────────────────────────
CORE_DIR = os.path.join(PKG_DIR, "core")            # 框架代码（不可被 evolver 修改）
EVOLVER_DIR = os.path.join(PKG_DIR, "evolver")      # 进化引擎代码

# 兼容旧代码
AGENT_BASE_DIR = PKG_DIR


def init_data_dir():
    """首次运行时初始化用户数据目录、数据库和可进化脚本。"""
    os.makedirs(SCRIPT_DIR, exist_ok=True)

    # 初始化 SQLite 数据库（建表 + 插入默认数据）
    from database import init_db
    init_db()

    # 从包内 script/ 拷贝可进化脚本（仅当目标不存在时，保留用户已进化的版本）
    pkg_script = os.path.join(PKG_DIR, "script")
    if os.path.isdir(pkg_script):
        for name in os.listdir(pkg_script):
            src = os.path.join(pkg_script, name)
            dst = os.path.join(SCRIPT_DIR, name)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)

    # 拷贝 config/env 到用户目录
    os.makedirs(_user_config_dir, exist_ok=True)
    if os.path.exists(_pkg_env) and not os.path.exists(_user_env):
        shutil.copy2(_pkg_env, _user_env)