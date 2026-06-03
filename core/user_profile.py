"""
用户规则模块 —— 管理全局规则和智能体专属规则。
数据存储在 SQLite。
"""
from datetime import datetime
from database import get_conn
from registry.agent_registry import get_agent_rules


def load_rules() -> list[str]:
    """加载全局用户规则列表。"""
    conn = get_conn()
    rows = conn.execute("SELECT rule FROM global_rules ORDER BY id").fetchall()
    conn.close()
    return [r["rule"] for r in rows]


def save_rule(rule: str) -> bool:
    """添加一条全局规则（去重）。"""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO global_rules (rule, created_at) VALUES (?, ?)",
            (rule, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def remove_rule(rule: str) -> bool:
    """删除一条全局规则。"""
    conn = get_conn()
    cur = conn.execute("DELETE FROM global_rules WHERE rule = ?", (rule,))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


def rules_context(agent_id: str = "") -> str:
    """将全局规则 + 智能体专属规则合并，格式化为可注入 prompt 的约束文本。"""
    global_rules = load_rules()
    agent_rules = get_agent_rules(agent_id) if agent_id else []

    if not global_rules and not agent_rules:
        return ""

    lines = []
    for i, r in enumerate(global_rules, 1):
        lines.append(f"  {i}. [全局] {r}")
    for i, r in enumerate(agent_rules, len(global_rules) + 1):
        lines.append(f"  {i}. [专属] {r}")

    return (
        "【用户个性化规则 —— 必须严格遵守】\n"
        "以下规则从历史对话中学习而来，代表用户的真实偏好，优先级高于默认行为：\n"
        + "\n".join(lines) + "\n\n"
    )