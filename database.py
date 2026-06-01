"""
SQLite 数据库统一管理模块。
所有数据存储在 ~/.starfish/starfish.db
"""
import os
import sqlite3
from settings import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "starfish.db")


def get_conn() -> sqlite3.Connection:
    """获取数据库连接（自动创建目录和文件）。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库表结构，幂等操作。"""
    conn = get_conn()
    conn.executescript("""
        -- 智能体注册表
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            domains TEXT NOT NULL DEFAULT '["*"]',
            role TEXT NOT NULL,
            goal TEXT NOT NULL,
            backstory TEXT NOT NULL,
            hit_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            parent TEXT
        );

        -- 领域命中统计
        CREATE TABLE IF NOT EXISTS domain_stats (
            domain TEXT PRIMARY KEY,
            hit_count INTEGER DEFAULT 0
        );

        -- 全局用户规则
        CREATE TABLE IF NOT EXISTS global_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

        -- 智能体专属规则
        CREATE TABLE IF NOT EXISTS agent_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            rule TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(agent_id, rule)
        );

        -- 对话日志
        CREATE TABLE IF NOT EXISTS chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_input TEXT NOT NULL,
            answer TEXT NOT NULL,
            is_error INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        -- 进化摘要
        CREATE TABLE IF NOT EXISTS evolve_hints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_input TEXT NOT NULL,
            hint TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        -- 进化报告
        CREATE TABLE IF NOT EXISTS evolve_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        -- 系统配置（如裂变阈值等）
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        -- MCP 服务端配置（用户可在 UI 增删改启停）
        -- transport: stdio | sse
        -- command/args: stdio 模式下的启动命令与参数（JSON 数组）
        -- env: 注入子进程的环境变量（JSON 对象）
        -- url: sse 模式下的服务地址
        CREATE TABLE IF NOT EXISTS mcp_servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            transport TEXT NOT NULL DEFAULT 'stdio',
            command TEXT DEFAULT '',
            args TEXT DEFAULT '[]',
            env TEXT DEFAULT '{}',
            url TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        -- Skill 配置（用户可在 UI 增删改启停）
        -- name        : 唯一名称，作为 [SKILL]name[/SKILL] 的标识
        -- summary     : 简短一句话描述，给 planner 看，用于决定是否激活
        -- triggers    : 触发关键词（逗号分隔），辅助 planner 匹配
        -- content     : 激活时注入到 executor prompt 的完整内容（Markdown）
        -- domains     : 适用领域（JSON 数组），便于按 agent 范围过滤
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            summary TEXT NOT NULL DEFAULT '',
            triggers TEXT DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            domains TEXT NOT NULL DEFAULT '["*"]',
            enabled INTEGER DEFAULT 1,
            hit_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );
    """)

    # 插入默认配置
    conn.execute(
        "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
        ("split_threshold", "10")
    )

    # 插入默认通用助手（如果不存在）
    conn.execute("""
        INSERT OR IGNORE INTO agents (id, name, description, domains, role, goal, backstory, hit_count, created_at, parent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "general", "通用助手", "处理所有未被专业助手覆盖的通用问题",
        '["*"]', "智能助手",
        "严格按照规划师给出的步骤计划，调用合适的工具完成任务，并返回真实结果。必须遵守用户个性化规则。",
        "你是一个智能助手，拥有读写文件、删除文件、抓取网页、执行Shell命令等能力，能帮用户高效完成各种任务。",
        0, "2026-05-19", None
    ))

    conn.commit()
    conn.close()