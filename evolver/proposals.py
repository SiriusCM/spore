import os
import json
from crewai.tools import tool
from settings import SCRIPT_DIR

WRITABLE_FILES = {"prompts.py", "tools.py"}
PROTECTED_FILES = set()

_proposals = []


def reset_proposals():
    _proposals.clear()


def get_proposals():
    return list(_proposals)


def _norm_filename(name: str) -> str:
    name = (name or "").strip().lstrip("/")
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"非法路径：{name}（只接受 core/ 下的纯文件名）")
    return name


@tool("list_script_files")
def list_script_files(_: str = "") -> str:
    """列出 script/ 目录下可修改的文件。无需输入参数。"""
    items = []
    for n in sorted(os.listdir(SCRIPT_DIR)):
        if n.startswith(".") or n == "__pycache__":
            continue
        p = os.path.join(SCRIPT_DIR, n)
        if os.path.isfile(p):
            size = os.path.getsize(p)
            items.append(f"{n} ({size}B)")
    return "\n".join(items) if items else "(空)"


@tool("read_script_file")
def read_script_file(filename: str) -> str:
    """读取 script/ 下某文件的完整内容。参数 filename 为纯文件名，如 'prompts.py' 'tools.py'。"""
    try:
        name = _norm_filename(filename)
    except ValueError as e:
        return f"失败：{e}"
    fp = os.path.join(SCRIPT_DIR, name)
    if not os.path.isfile(fp):
        return f"失败：文件不存在 {name}"
    with open(fp, "r", encoding="utf-8") as f:
        return f.read()




@tool("read_today_log")
def read_today_log(_: str = "") -> str:
    """读取今日的进化摘要（已脱敏，不含原始对话）。无需输入参数。"""
    from core.chat_log import get_today_hints
    return get_today_hints()


@tool("read_recent_evolve_reports")
def read_recent_evolve_reports(n: str = "3") -> str:
    """读取最近 N 份进化报告。参数 n 默认 '3'。"""
    from database import get_conn
    try:
        k = int(str(n).strip() or 3)
    except Exception:
        k = 3
    conn = get_conn()
    rows = conn.execute(
        "SELECT report, created_at FROM evolve_reports ORDER BY id DESC LIMIT ?", (k,)
    ).fetchall()
    conn.close()
    if not rows:
        return "(无报告)"
    parts = []
    for r in rows:
        parts.append(f"========== {r['created_at'][:10]} ==========\n{r['report']}")
    return "\n\n".join(parts)


@tool("propose_edit")
def propose_edit(payload: str) -> str:
    """提交一条修改提案（不立即写盘，由框架统一应用）。
    payload 为 JSON 字符串，结构：
    {"file": "prompts.py | orchestrator.py | chat_log.py | tools.py", "old": "原文片段（必须在文件中精确存在）", "new": "替换为", "reason": "为何这么改"}
    file 不允许是 CONSTITUTION.md（受保护）。
    """
    try:
        data = json.loads(payload)
    except Exception as e:
        return f"失败：payload 非合法 JSON：{e}"
    f = (data.get("file") or "").strip()
    if f not in WRITABLE_FILES:
        return f"失败：file 必须是 {sorted(WRITABLE_FILES - PROTECTED_FILES)} 之一，收到 {f!r}"
    if f in PROTECTED_FILES:
        return f"失败：{f} 是受保护文件，evolver 不可修改"
    if not data.get("old") or not data.get("new"):
        return "失败：old/new 不能为空"
    _proposals.append({
        "kind": "edit",
        "file": f,
        "old": data["old"],
        "new": data["new"],
        "reason": data.get("reason", ""),
    })
    return f"OK：提案已记录（edit {f}，当前共 {len(_proposals)} 条）"


@tool("propose_add_rule")
def propose_add_rule(payload: str) -> str:
    """从对话中提炼一条用户行为规则并添加。
    payload 为 JSON：{"rule": "规则内容", "agent_id": "目标智能体ID（可选，不填则为全局规则）", "reason": "从哪条对话推断出的"}
    规则必须是一句直接可执行的指令，例如：
    - 全局规则（所有智能体遵守）：{"rule": "回答要简洁，不超过3句话", "reason": "..."}
    - 专属规则（仅特定智能体）：{"rule": "代码不加注释", "agent_id": "programming", "reason": "..."}
    不要写笼统的描述如"用户喜欢简洁"，要写成"回答不超过3句话"这样Agent能直接执行的指令。
    """
    try:
        data = json.loads(payload)
    except Exception as e:
        return f"失败：payload 非合法 JSON：{e}"
    rule = (data.get("rule") or "").strip()
    if not rule:
        return "失败：rule 不能为空"
    if len(rule) > 200:
        return "失败：rule 过长（>200字），请精炼"
    agent_id = (data.get("agent_id") or "").strip()
    _proposals.append({
        "kind": "add_rule",
        "rule": rule,
        "agent_id": agent_id,  # 空字符串表示全局规则
        "reason": data.get("reason", ""),
    })
    scope = f"智能体 {agent_id}" if agent_id else "全局"
    return f"OK：{scope}规则提案已记录（当前共 {len(_proposals)} 条）"


@tool("propose_remove_rule")
def propose_remove_rule(payload: str) -> str:
    """删除一条已过时或被用户否定的规则。
    payload 为 JSON：{"rule": "要删除的规则原文（必须精确匹配）", "agent_id": "目标智能体ID（可选，不填则删全局规则）", "reason": "为何删除"}
    """
    try:
        data = json.loads(payload)
    except Exception as e:
        return f"失败：payload 非合法 JSON：{e}"
    rule = (data.get("rule") or "").strip()
    if not rule:
        return "失败：rule 不能为空"
    agent_id = (data.get("agent_id") or "").strip()
    _proposals.append({
        "kind": "remove_rule",
        "rule": rule,
        "agent_id": agent_id,
        "reason": data.get("reason", ""),
    })
    scope = f"智能体 {agent_id}" if agent_id else "全局"
    return f"OK：删除{scope}规则提案已记录（当前共 {len(_proposals)} 条）"


@tool("propose_create_tool")
def propose_create_tool(payload: str) -> str:
    """新增一个 @tool 函数到 core/tools.py 并登记到 ALL_TOOLS。
    payload 为 JSON：
    {"name": "snake_case_name", "param_name": "arg", "docstring": "...", "body": "Python 函数体源码(不含 def 行，缩进 4 空格)", "catalog_desc": "在 TOOL_CATALOG 中追加的描述", "reason": "为何需要"}
    """
    try:
        data = json.loads(payload)
    except Exception as e:
        return f"失败：payload 非合法 JSON：{e}"
    for k in ("name", "param_name", "docstring", "body", "catalog_desc"):
        if not str(data.get(k, "")).strip():
            return f"失败：缺少字段 {k}"
    name = data["name"].strip()
    if not name.isidentifier() or not name.islower():
        return f"失败：name 必须是小写蛇形合法标识符，收到 {name!r}"
    _proposals.append({
        "kind": "create_tool",
        "file": "tools.py",
        "name": name,
        "param_name": data["param_name"].strip(),
        "docstring": data["docstring"].strip(),
        "body": data["body"],
        "catalog_desc": data["catalog_desc"].strip(),
        "reason": data.get("reason", ""),
    })
    return f"OK：新增工具提案已记录（{name}，当前共 {len(_proposals)} 条）"


@tool("read_user_rules")
def read_user_rules(_: str = "") -> str:
    """读取当前已学到的用户规则列表（全局+各智能体专属）。无需输入参数。"""
    from core.user_profile import load_rules
    from registry.agent_registry import list_agents, get_agent_rules
    lines = []
    global_rules = load_rules()
    if global_rules:
        lines.append("【全局规则】")
        for i, r in enumerate(global_rules, 1):
            lines.append(f"  {i}. {r}")
    agents = list_agents()
    for a in agents:
        agent_rules = get_agent_rules(a["id"])
        if agent_rules:
            lines.append(f"【{a['name']}({a['id']}) 专属规则】")
            for i, r in enumerate(agent_rules, 1):
                lines.append(f"  {i}. {r}")
    return "\n".join(lines) if lines else "(暂无用户规则)"


@tool("read_agents")
def read_agents(_: str = "") -> str:
    """读取当前已注册的智能体列表和领域统计数据。无需输入参数。用于判断是否需要裂变。"""
    from registry.agent_registry import list_agents, get_domain_stats, get_split_threshold
    agents = list_agents()
    stats = get_domain_stats()
    threshold = get_split_threshold()
    lines = [f"裂变阈值: {threshold}", f"领域统计: {json.dumps(stats, ensure_ascii=False)}", ""]
    for a in agents:
        lines.append(f"- {a['id']}({a['name']}): domains={a.get('domains')}, hit={a.get('hit_count', 0)}, parent={a.get('parent')}")
    return "\n".join(lines)


@tool("propose_split_agent")
def propose_split_agent(payload: str) -> str:
    """提交一条智能体裂变提案。当某个领域的命中次数超过阈值时，从父智能体中裂变出专业子智能体。
    payload 为 JSON：
    {
        "id": "snake_case_id（如 cooking、programming、geography）",
        "name": "智能体名称（如 编程助手、美食助手）",
        "description": "一句话描述该智能体的专长",
        "domains": ["该智能体负责的领域标签列表"],
        "role": "智能体角色（如 编程专家）",
        "goal": "智能体目标",
        "backstory": "智能体背景故事，描述其专业能力",
        "parent": "父智能体 ID（通常是 general）",
        "reason": "为何需要裂变（基于领域统计数据）"
    }
    裂变约束：
    - 某领域命中次数必须 >= split_threshold 才允许裂变
    - 不可重复创建已有 ID 的智能体
    - domains 标签必须具体，不能是 "*"
    """
    try:
        data = json.loads(payload)
    except Exception as e:
        return f"失败：payload 非合法 JSON：{e}"
    for k in ("id", "name", "domains", "role", "goal", "backstory"):
        if not data.get(k):
            return f"失败：缺少字段 {k}"
    agent_id = data["id"].strip()
    if not agent_id.replace("_", "").isalnum():
        return f"失败：id 必须是 snake_case 标识符，收到 {agent_id!r}"
    domains = data["domains"]
    if not isinstance(domains, list) or "*" in domains:
        return "失败：domains 必须是具体领域列表，不能包含 '*'"
    _proposals.append({
        "kind": "split_agent",
        "id": agent_id,
        "name": data["name"].strip(),
        "description": data.get("description", "").strip(),
        "domains": domains,
        "role": data["role"].strip(),
        "goal": data["goal"].strip(),
        "backstory": data["backstory"].strip(),
        "parent": data.get("parent", "general"),
        "reason": data.get("reason", ""),
    })
    return f"OK：裂变提案已记录（{agent_id}，当前共 {len(_proposals)} 条）"


@tool("propose_create_skill")
def propose_create_skill(payload: str) -> str:
    """新增一条 Skill（按需激活的"任务剧本"）。
    Skill 是优先于 split_agent 的轻量手段：
    - 同领域出现可复用的步骤模板（如"周报生成"、"日志分析"）→ 用 skill
    - 仅当该领域需要全新工具集 / 与既有 agent 性格相左 → 才考虑 split_agent
    payload 为 JSON：
    {
        "name": "snake_case_name（唯一）",
        "summary": "一句话简介，planner 用它判断是否激活",
        "triggers": "触发关键词，逗号分隔（可选）",
        "content": "完整指引（Markdown 也可），命中后将注入 executor prompt",
        "domains": ["适用领域列表，* 表示全部"],
        "reason": "为何需要这条 skill"
    }
    """
    try:
        data = json.loads(payload)
    except Exception as e:
        return f"失败：payload 非合法 JSON：{e}"
    for k in ("name", "summary", "content"):
        if not str(data.get(k, "")).strip():
            return f"失败：缺少字段 {k}"
    name = data["name"].strip()
    if not name.replace("_", "").isalnum():
        return f"失败：name 必须是合法标识符，收到 {name!r}"
    domains = data.get("domains") or ["*"]
    if not isinstance(domains, list):
        return "失败：domains 必须是列表"
    _proposals.append({
        "kind": "create_skill",
        "name": name,
        "summary": data["summary"].strip(),
        "triggers": (data.get("triggers") or "").strip(),
        "content": data["content"],
        "domains": domains,
        "reason": data.get("reason", ""),
    })
    return f"OK：新增 Skill 提案已记录（{name}，当前共 {len(_proposals)} 条）"


@tool("read_skills")
def read_skills(_: str = "") -> str:
    """读取当前已注册的 Skill 列表（含命中次数）。无需输入参数。
    用于判断某领域是否已有覆盖的 skill，避免重复创建。"""
    from registry.skill_registry import list_skills
    items = list_skills(only_enabled=False)
    if not items:
        return "(暂无 Skill)"
    lines = []
    for s in items:
        flag = "" if s.get("enabled") else "[禁用]"
        lines.append(
            f"- {s['name']} {flag} (命中{s.get('hit_count', 0)}): {s.get('summary', '')} | domains={s.get('domains')}"
        )
    return "\n".join(lines)


@tool("finalize")
def finalize(summary: str = "") -> str:
    """声明已完成所有提案。参数 summary 是对今日改动的一句话总结。调用此工具后请结束任务。"""
    return f"FINALIZED：共 {len(_proposals)} 条提案待框架应用。总结：{summary or '(无)'}"


EVOLVER_TOOLS = [
    list_script_files,
    read_script_file,
    read_today_log,
    read_recent_evolve_reports,
    read_user_rules,
    read_agents,
    read_skills,
    propose_edit,
    propose_add_rule,
    propose_remove_rule,
    propose_create_tool,
    propose_create_skill,
    propose_split_agent,
    finalize,
]
