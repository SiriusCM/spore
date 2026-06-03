"""
Skill 注册表 —— SQLite 中 skills 表的 CRUD，以及供 orchestrator 使用的：
  · list_for_planner(agent_id)  : 返回 [{name, summary, triggers}] 用于喂给 planner
  · get_by_name(name)           : planner 命中后取出完整 content 注入 executor
  · record_hit(name)            : 命中计数

设计上跟 mcp_registry 同构：CUD 改 _bump_version()，便于上层做缓存失效。
"""
import json
import sqlite3
import time
from datetime import datetime
from typing import Any

from database import get_conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    try:
        d["domains"] = json.loads(d.get("domains") or '["*"]')
    except Exception:
        d["domains"] = ["*"]
    d["enabled"] = bool(d.get("enabled"))
    return d


# ── CRUD ───────────────────────────────────────────────
def list_skills(only_enabled: bool = False) -> list[dict]:
    sql = "SELECT * FROM skills"
    if only_enabled:
        sql += " WHERE enabled=1"
    sql += " ORDER BY id ASC"
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_skill(skill_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
    return _row_to_dict(row) if row else None


def get_by_name(name: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM skills WHERE name=? AND enabled=1", (name,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def add_skill(data: dict) -> int:
    payload = _normalize(data)
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO skills
               (name, summary, triggers, content, domains, enabled, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                payload["name"], payload["summary"], payload["triggers"],
                payload["content"], payload["domains"], payload["enabled"],
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        _bump_version()
        return cur.lastrowid


def update_skill(skill_id: int, data: dict) -> bool:
    payload = _normalize(data, partial=True)
    if not payload:
        return False
    sets = ", ".join(f"{k}=?" for k in payload.keys())
    values = list(payload.values()) + [skill_id]
    with get_conn() as conn:
        cur = conn.execute(f"UPDATE skills SET {sets} WHERE id=?", values)
        conn.commit()
        if cur.rowcount:
            _bump_version()
        return cur.rowcount > 0


def delete_skill(skill_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM skills WHERE id=?", (skill_id,))
        conn.commit()
        if cur.rowcount:
            _bump_version()
        return cur.rowcount > 0


def set_enabled(skill_id: int, enabled: bool) -> bool:
    return update_skill(skill_id, {"enabled": 1 if enabled else 0})


def record_hit(name: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE skills SET hit_count = hit_count + 1 WHERE name=?",
            (name,),
        )
        conn.commit()


# ── 字段规范化 ─────────────────────────────────────────
def _normalize(data: dict, partial: bool = False) -> dict:
    out: dict[str, Any] = {}
    keys = {"name", "summary", "triggers", "content", "domains", "enabled"}
    for k in keys:
        if k not in data:
            if partial:
                continue
            defaults = {
                "summary": "", "triggers": "", "content": "",
                "domains": ["*"], "enabled": 1,
            }
            if k == "name":
                raise ValueError("name 不能为空")
            out[k] = defaults[k]
            continue
        v = data[k]
        if k == "domains":
            out[k] = json.dumps(v if isinstance(v, list) else ["*"], ensure_ascii=False)
        elif k == "enabled":
            out[k] = 1 if v else 0
        else:
            out[k] = str(v or "")
    if not partial and isinstance(out.get("domains"), list):
        out["domains"] = json.dumps(out["domains"], ensure_ascii=False)
    return out


# ── 版本号（CUD 后变化，供 orchestrator 缓存失效用）────
_version: float = 0.0


def _bump_version() -> None:
    global _version
    _version = time.time()


def current_version() -> float:
    return _version


# ── 给 planner 用的精简列表 ───────────────────────────
def list_for_planner(agent_id: str = "") -> list[dict]:
    """返回启用且适用于该 agent 的 skill 摘要列表。
    每项仅含 name/summary/triggers，不含完整 content（节省 prompt token）。"""
    skills = list_skills(only_enabled=True)
    out = []
    for s in skills:
        domains = s.get("domains") or ["*"]
        if agent_id and agent_id not in domains and "*" not in domains:
            continue
        out.append({
            "name": s["name"],
            "summary": s.get("summary", ""),
            "triggers": s.get("triggers", ""),
        })
    return out


def render_for_planner(agent_id: str = "") -> str:
    """格式化成给 planner 看的文本块；为空时返回空串。"""
    items = list_for_planner(agent_id)
    if not items:
        return ""
    lines = []
    for it in items:
        trig = f"  关键词: {it['triggers']}" if it["triggers"] else ""
        lines.append(f"- {it['name']}: {it['summary']}{trig}")
    return "\n".join(lines)


# ── 导入导出（ZIP，每个 skill 一个 SKILL.md + frontmatter）──
import io
import re
import zipfile


_FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def _build_skill_md(skill: dict) -> str:
    """根据一条 skill 生成 SKILL.md 文本（YAML-ish frontmatter + 正文）。"""
    domains = skill.get("domains") or ["*"]
    lines = [
        "---",
        f"name: {skill['name']}",
        f"summary: {skill.get('summary', '')}",
        f"triggers: {skill.get('triggers', '')}",
        f"domains: {json.dumps(domains, ensure_ascii=False)}",
        f"enabled: {'true' if skill.get('enabled', True) else 'false'}",
        "---",
        "",
        skill.get("content", "").rstrip() + "\n",
    ]
    return "\n".join(lines)


def _parse_skill_md(text: str) -> dict:
    """解析 SKILL.md，返回 add_skill 可直接吃的 dict。frontmatter 里支持 name/summary/triggers/domains/enabled。"""
    m = _FRONT_RE.match(text.lstrip("\ufeff"))
    if not m:
        raise ValueError("SKILL.md 缺少 frontmatter（--- 包裹的元数据块）")
    front_text, body = m.group(1), m.group(2)

    meta: dict = {}
    for line in front_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()

    if "name" not in meta or not meta["name"]:
        raise ValueError("frontmatter 必须包含 name")

    domains_raw = meta.get("domains", '["*"]')
    try:
        domains = json.loads(domains_raw)
        if not isinstance(domains, list):
            domains = ["*"]
    except Exception:
        domains = [s.strip() for s in domains_raw.strip("[]").split(",") if s.strip()] or ["*"]

    enabled_raw = meta.get("enabled", "true").lower()
    enabled = 1 if enabled_raw in ("1", "true", "yes", "y") else 0

    return {
        "name": meta["name"],
        "summary": meta.get("summary", ""),
        "triggers": meta.get("triggers", ""),
        "domains": domains,
        "enabled": enabled,
        "content": body.strip() + "\n",
    }


def export_skill_zip(skill_id: int) -> tuple[str, bytes]:
    """导出单个 skill 为 zip 字节流，返回 (filename, bytes)。"""
    sk = get_skill(skill_id)
    if not sk:
        raise ValueError(f"skill id={skill_id} 不存在")
    md = _build_skill_md(sk)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", md)
    return f"{sk['name']}.zip", buf.getvalue()


def import_skill_zip(zip_bytes: bytes, overwrite: bool = False) -> dict:
    """从 zip 字节流导入一个 skill。
    - 找到第一个 SKILL.md（不区分大小写、容许位于子目录）
    - 解析后 add_skill；若已存在同名 skill，根据 overwrite 决定覆盖或失败
    返回结果 dict：{action: 'created'|'updated', id, name}
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        skill_md_name = None
        for n in zf.namelist():
            if n.lower().endswith("skill.md") and not n.endswith("/"):
                skill_md_name = n
                break
        if not skill_md_name:
            raise ValueError("zip 中找不到 SKILL.md")
        text = zf.read(skill_md_name).decode("utf-8", errors="replace")

    data = _parse_skill_md(text)

    with get_conn() as conn:
        row = conn.execute("SELECT id FROM skills WHERE name=?", (data["name"],)).fetchone()
    if row:
        if not overwrite:
            raise ValueError(f"skill '{data['name']}' 已存在，未覆盖（请勾选覆盖选项）")
        update_skill(row["id"], data)
        return {"action": "updated", "id": row["id"], "name": data["name"]}
    new_id = add_skill(data)
    return {"action": "created", "id": new_id, "name": data["name"]}