import os
import ast
import subprocess
from datetime import datetime
from .snapshot import take_snapshot, rollback
from settings import SCRIPT_DIR, AGENT_BASE_DIR


def _apply_split_agents(split_proposals):
    """将裂变提案写入数据库。"""
    from registry.agent_registry import add_agent
    for p in split_proposals:
        add_agent({
            "id": p["id"],
            "name": p["name"],
            "description": p.get("description", ""),
            "domains": p["domains"],
            "role": p["role"],
            "goal": p["goal"],
            "backstory": p["backstory"],
            "parent": p.get("parent", "general"),
        })


def _apply_create_skills(skill_proposals):
    """将 create_skill 提案写入 skills 表（重名时更新）。"""
    from registry.skill_registry import add_skill, update_skill
    from database import get_conn
    for p in skill_proposals:
        data = {
            "name": p["name"],
            "summary": p.get("summary", ""),
            "triggers": p.get("triggers", ""),
            "content": p.get("content", ""),
            "domains": p.get("domains") or ["*"],
            "enabled": 1,
        }
        # 重名→更新
        with get_conn() as conn:
            row = conn.execute("SELECT id FROM skills WHERE name=?", (data["name"],)).fetchone()
        if row:
            update_skill(row["id"], data)
        else:
            add_skill(data)


def _apply_rule_updates(rule_proposals):
    from core.user_profile import save_rule, remove_rule
    from registry.agent_registry import add_agent_rule, remove_agent_rule

    for p in rule_proposals:
        agent_id = p.get("agent_id", "")
        if agent_id:
            if p["kind"] == "add_rule":
                add_agent_rule(agent_id, p["rule"])
            elif p["kind"] == "remove_rule":
                remove_agent_rule(agent_id, p["rule"])
        else:
            if p["kind"] == "add_rule":
                save_rule(p["rule"])
            elif p["kind"] == "remove_rule":
                remove_rule(p["rule"])


def _read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def _write(p, text):
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def _apply_edit(src: str, old: str, new: str):
    if src.count(old) == 0:
        return src, "not_found"
    if src.count(old) > 1:
        return src, "ambiguous"
    return src.replace(old, new, 1), "ok"


def _apply_append_preference(src: str, line: str):
    today = datetime.now().strftime("%Y-%m-%d")
    entry = f"- [{today}] {line}"
    if entry in src:
        return src, "duplicate"
    if src.rstrip().endswith("- [初始化]"):
        return src.rstrip() + "\n" + entry + "\n", "ok"
    return src.rstrip() + "\n" + entry + "\n", "ok"


def _render_new_tool(p):
    name = p["name"]
    arg = p["param_name"]
    doc = p["docstring"].replace('"""', "'''")
    body = p["body"].rstrip()
    if not body:
        body = "    return ''"
    lines = ["", "", f'@tool("{name}")', f"def {name}({arg}: str) -> str:", f'    """{doc}"""']
    for ln in body.splitlines():
        if not ln.startswith("    ") and ln.strip():
            ln = "    " + ln
        lines.append(ln)
    return "\n".join(lines) + "\n"


def _apply_create_tool(src: str, p):
    name = p["name"]
    if f"@tool(\"{name}\")" in src or f"def {name}(" in src:
        return src, "duplicate"
    func_block = _render_new_tool(p)
    marker_all = "ALL_TOOLS = ["
    if marker_all not in src:
        return src, "all_tools_not_found"
    pre, post = src.split(marker_all, 1)
    new_src = pre.rstrip() + "\n" + func_block + "\n" + marker_all + post
    end_bracket = new_src.find("]", new_src.find(marker_all))
    if end_bracket == -1:
        return src, "all_tools_bracket_not_found"
    before = new_src[:end_bracket].rstrip()
    if not before.rstrip().endswith(","):
        before = before + ","
    new_src = before + f"\n    {name},\n" + new_src[end_bracket:]
    return new_src, "ok"


def _apply_catalog_desc(src: str, desc: str):
    marker = "TOOL_CATALOG = ("
    if marker not in src:
        return src, "tool_catalog_not_found"
    i = src.find(marker)
    j = src.find(")", i)
    if j == -1:
        return src, "tool_catalog_unclosed"
    block = src[i:j]
    if desc.strip() in block:
        return src, "duplicate"
    extra = f'\n    "{desc.replace(chr(34), chr(39))}"'
    new_src = src[:j].rstrip() + extra + "\n" + src[j:]
    return new_src, "ok"


def _ast_check(path, text):
    try:
        ast.parse(text)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError {path}: {e}"


def _import_smoke(base_dir):
    code = (
        "import importlib, sys;"
        "sys.path.insert(0, r'%s');"
        "from core import prompts, orchestrator, tools;"
        "assert tools.ALL_TOOLS, 'ALL_TOOLS empty';"
        "print('OK', len(tools.ALL_TOOLS))"
    ) % base_dir
    try:
        r = subprocess.run(
            ["python", "-c", code],
            capture_output=True, text=True, timeout=20, cwd=base_dir,
        )
        ok = r.returncode == 0 and "OK" in r.stdout
        msg = (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else ""
        return ok, msg
    except subprocess.TimeoutExpired:
        return False, "import 超时(20s)"
    except Exception as e:
        return False, f"import 检查异常：{e}"


def apply_proposals(proposals, dry_run: bool):
    base_dir = AGENT_BASE_DIR
    files_text = {}
    results = []

    rule_updates = []
    split_updates = []
    skill_updates = []

    for p in proposals:
        f = p.get("file")
        if f and f not in files_text:
            files_text[f] = _read(os.path.join(SCRIPT_DIR, f))

    for p in proposals:
        kind = p["kind"]
        if kind in ("add_rule", "remove_rule"):
            rule_updates.append(p)
            results.append({**p, "status": "ok"})
            continue
        if kind == "split_agent":
            split_updates.append(p)
            results.append({**p, "status": "ok"})
            continue
        if kind == "create_skill":
            skill_updates.append(p)
            results.append({**p, "status": "ok"})
            continue
        f = p["file"]
        if kind == "edit":
            new_text, st = _apply_edit(files_text[f], p["old"], p["new"])
            files_text[f] = new_text if st == "ok" else files_text[f]
            results.append({**p, "status": st})
        elif kind == "append_preference":
            new_text, st = _apply_append_preference(files_text[f], p["line"])
            files_text[f] = new_text if st == "ok" else files_text[f]
            results.append({**p, "status": st})
        elif kind == "create_tool":
            new_text, st = _apply_create_tool(files_text[f], p)
            if st == "ok":
                files_text[f] = new_text
                new_text2, st2 = _apply_catalog_desc(files_text["prompts.py"] if "prompts.py" in files_text else _read(os.path.join(SCRIPT_DIR, "prompts.py")), p["catalog_desc"])
                if "prompts.py" not in files_text:
                    files_text["prompts.py"] = _read(os.path.join(SCRIPT_DIR, "prompts.py"))
                if st2 == "ok":
                    files_text["prompts.py"] = new_text2
            results.append({**p, "status": st})
        else:
            results.append({**p, "status": "unknown_kind"})

    for f, text in files_text.items():
        if not f.endswith(".py"):
            continue
        ok, msg = _ast_check(f, text)
        if not ok:
            return results, {"phase": "syntax", "ok": False, "msg": msg, "applied_to_disk": False, "snapshot": None}

    if dry_run:
        return results, {"phase": "dry-run", "ok": True, "msg": "dry-run，未写盘", "applied_to_disk": False, "snapshot": None}

    snap = take_snapshot()
    for f, text in files_text.items():
        _write(os.path.join(SCRIPT_DIR, f), text)

    if rule_updates:
        _apply_rule_updates(rule_updates)

    if split_updates:
        _apply_split_agents(split_updates)

    if skill_updates:
        _apply_create_skills(skill_updates)

    ok, msg = _import_smoke(base_dir)
    if not ok:
        rollback(os.path.basename(snap))
        return results, {"phase": "smoke", "ok": False, "msg": msg, "applied_to_disk": False, "snapshot": os.path.basename(snap), "rolled_back": True}

    return results, {"phase": "applied", "ok": True, "msg": msg, "applied_to_disk": True, "snapshot": os.path.basename(snap), "rolled_back": False}
