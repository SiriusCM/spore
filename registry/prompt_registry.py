"""
Prompt 常量覆盖注册表
─────────────────────
作用：让用户在 UI 上覆盖 script/prompts.py 里**纯文本常量**的值，
而不必直接编辑文件。模板字符串（带 {xxx} 占位）不开放，因为它们与
orchestrator 里的 str.format 调用是代码契约，改错会运行时崩溃。

存储：SQLite 的 prompt_overrides 表（database.py 中定义）

读取流程：
    P = _load_script("prompts")       # 文件默认值
    P = apply_overrides_to_module(P)  # SQLite 覆盖（仅在白名单内）
    使用 P.PLANNER_ROLE、P.TOOL_CATALOG ...

CUD 后调 _bump_version()，orchestrator 的 planner 单例据此失效重建。
"""
import time
from datetime import datetime
from types import SimpleNamespace
from database import get_conn


# 仅这些字段允许被 SQLite 覆盖；带 {xxx} 占位符的模板不在内
ALLOWED_KEYS: tuple[str, ...] = (
    "PLANNER_ROLE",
    "PLANNER_GOAL",
    "PLANNER_BACKSTORY",
    "TOOL_CATALOG",
    "PLAN_TASK_EXPECTED",
    "EXEC_TASK_EXPECTED",
)


# ── CRUD ───────────────────────────────────────────────
def list_overrides() -> list[dict]:
    """返回所有覆盖项；同时把白名单里没覆盖的 key 也列出（value 为空）方便 UI 渲染。"""
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value, updated_at FROM prompt_overrides").fetchall()
    overrides = {r["key"]: dict(r) for r in rows}
    out: list[dict] = []
    for k in ALLOWED_KEYS:
        item = overrides.get(k)
        out.append({
            "key": k,
            "value": item["value"] if item else "",
            "overridden": item is not None,
            "updated_at": item["updated_at"] if item else "",
        })
    return out


def get_override(key: str) -> str | None:
    if key not in ALLOWED_KEYS:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM prompt_overrides WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_override(key: str, value: str) -> bool:
    if key not in ALLOWED_KEYS:
        raise ValueError(f"不允许覆盖的 key：{key}")
    if not isinstance(value, str):
        raise ValueError("value 必须是字符串")
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO prompt_overrides (key, value, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now),
        )
        conn.commit()
    _bump_version()
    return True


def delete_override(key: str) -> bool:
    """删除单条覆盖（恢复使用 prompts.py 默认值）。"""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM prompt_overrides WHERE key=?", (key,))
        conn.commit()
    if cur.rowcount:
        _bump_version()
    return cur.rowcount > 0


# ── 应用：把 SQLite 中的覆盖注入到一个 prompts 模块对象上 ───
def apply_overrides_to_module(P):
    """返回一个新的 namespace，把 ALLOWED_KEYS 中已覆盖的字段替换为数据库值；
    没覆盖的字段透传 P 上的原值。模板字符串不在 ALLOWED_KEYS，必然透传。
    """
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM prompt_overrides").fetchall()
    overrides = {r["key"]: r["value"] for r in rows}

    # 拷一份 P 的属性到 SimpleNamespace；orchestrator 用属性访问，不依赖具体类型
    data: dict = {}
    for name in dir(P):
        if name.startswith("_"):
            continue
        try:
            data[name] = getattr(P, name)
        except Exception:
            continue
    for k, v in overrides.items():
        if k in ALLOWED_KEYS:
            data[k] = v
    return SimpleNamespace(**data)


# ── 版本号（CUD 后变化，供 orchestrator 让 planner 单例失效）──
_version: float = 0.0


def _bump_version() -> None:
    global _version
    _version = time.time()


def current_version() -> float:
    return _version