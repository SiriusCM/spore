"""
智能体注册表 —— 管理多智能体的加载、领域路由、命中统计。
数据存储在 SQLite（~/.starfish/starfish.db）。

跟 mcp_registry / skill_registry 同构：CUD 操作会 _bump_version()，
便于 orchestrator 做缓存失效。
"""
import json
import time
from datetime import datetime
from typing import Any
from database import get_conn

_DEFAULT_AGENT = {
    "id": "general", "name": "通用助手",
    "role": "智能助手", "goal": "帮助用户完成任务。",
    "backstory": "你是一个智能助手。", "domains": ["*"]
}

PROTECTED_AGENT_IDS = {"general"}  # 不允许删除或禁用的兜底 agent


def _row_to_dict(row) -> dict:
    """将数据库行转为字典，domains 从 JSON 字符串还原为列表。"""
    d = dict(row)
    try:
        d["domains"] = json.loads(d.get("domains") or '["*"]')
    except Exception:
        d["domains"] = ["*"]
    # enabled 字段在老库可能不存在
    if "enabled" in d:
        d["enabled"] = bool(d.get("enabled"))
    else:
        d["enabled"] = True
    return d


def list_agents(only_enabled: bool = False) -> list[dict]:
    sql = "SELECT * FROM agents"
    if only_enabled:
        sql += " WHERE enabled=1"
    sql += " ORDER BY created_at"
    conn = get_conn()
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_agent_by_id(agent_id: str) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def route(domain: str) -> dict:
    """根据领域标签路由到最匹配的智能体（仅在启用的 agent 中挑选）。"""
    agents = list_agents(only_enabled=True)
    for a in agents:
        if domain in a.get("domains", []):
            return a
    for a in agents:
        if "*" in a.get("domains", []):
            return a
    # 兜底：所有 enabled agent 都不匹配时，强制返回 general
    fallback = get_agent_by_id("general")
    return fallback or _DEFAULT_AGENT


def record_hit(domain: str, agent_id: str):
    """记录一次领域命中。"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO domain_stats (domain, hit_count) VALUES (?, 1) "
        "ON CONFLICT(domain) DO UPDATE SET hit_count = hit_count + 1",
        (domain,)
    )
    conn.execute(
        "UPDATE agents SET hit_count = hit_count + 1 WHERE id = ?",
        (agent_id,)
    )
    conn.commit()
    conn.close()


def get_domain_stats() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT domain, hit_count FROM domain_stats ORDER BY hit_count DESC").fetchall()
    conn.close()
    return {r["domain"]: r["hit_count"] for r in rows}


def get_split_threshold() -> int:
    conn = get_conn()
    row = conn.execute("SELECT value FROM config WHERE key = 'split_threshold'").fetchone()
    conn.close()
    return int(row["value"]) if row else 10


def add_agent(agent_def: dict) -> bool:
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO agents (id, name, description, domains, role, goal, backstory, hit_count, created_at, parent, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """, (
            agent_def["id"], agent_def["name"], agent_def.get("description", ""),
            json.dumps(agent_def["domains"], ensure_ascii=False),
            agent_def["role"], agent_def["goal"], agent_def["backstory"],
            agent_def.get("created_at", datetime.now().strftime("%Y-%m-%d")),
            agent_def.get("parent"),
            1 if agent_def.get("enabled", True) else 0,
        ))
        conn.commit()
        conn.close()
        _bump_version()
        return True
    except Exception:
        conn.close()
        return False


def update_agent(agent_id: str, data: dict) -> bool:
    """更新 agent 字段。允许的字段：name/description/domains/role/goal/backstory/enabled。
    id 不可修改（要改请删除后重建）。general 始终保持 enabled=1。"""
    allowed = {"name", "description", "domains", "role", "goal", "backstory", "enabled"}
    payload: dict[str, Any] = {}
    for k, v in data.items():
        if k not in allowed:
            continue
        if k == "domains":
            payload[k] = json.dumps(v if isinstance(v, list) else ["*"], ensure_ascii=False)
        elif k == "enabled":
            payload[k] = 1 if v else 0
        else:
            payload[k] = str(v or "")
    if agent_id in PROTECTED_AGENT_IDS:
        payload["enabled"] = 1  # 强制保持启用
    if not payload:
        return False
    sets = ", ".join(f"{k}=?" for k in payload.keys())
    values = list(payload.values()) + [agent_id]
    conn = get_conn()
    cur = conn.execute(f"UPDATE agents SET {sets} WHERE id=?", values)
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    if ok:
        _bump_version()
    return ok


def delete_agent(agent_id: str) -> bool:
    if agent_id in PROTECTED_AGENT_IDS:
        return False
    conn = get_conn()
    # 一并清理 agent_rules
    conn.execute("DELETE FROM agent_rules WHERE agent_id=?", (agent_id,))
    cur = conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    if ok:
        _bump_version()
    return ok


def set_enabled(agent_id: str, enabled: bool) -> bool:
    if agent_id in PROTECTED_AGENT_IDS:
        return False
    return update_agent(agent_id, {"enabled": enabled})


def get_agent_rules(agent_id: str) -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT rule FROM agent_rules WHERE agent_id = ? ORDER BY id", (agent_id,)
    ).fetchall()
    conn.close()
    return [r["rule"] for r in rows]


def add_agent_rule(agent_id: str, rule: str) -> bool:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO agent_rules (agent_id, rule, created_at) VALUES (?, ?, ?)",
            (agent_id, rule, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        conn.close()
        return False


def remove_agent_rule(agent_id: str, rule: str) -> bool:
    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM agent_rules WHERE agent_id = ? AND rule = ?", (agent_id, rule)
    )
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed


# ── 版本号：CUD 后变化，供 orchestrator 做 executor 缓存失效 ──
_version: float = 0.0


def _bump_version() -> None:
    global _version
    _version = time.time()


def current_version() -> float:
    return _version