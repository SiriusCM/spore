import os
import re
import importlib.util
from crewai import Agent, Task, Crew, Process, LLM
from settings import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY, SCRIPT_DIR
from .chat_log import append_history, write_chat_log, write_evolve_hint, history_context
from .user_profile import rules_context
from .agent_registry import list_agents, route, record_hit
from . import mcp_client, mcp_registry, skill_registry


# (mtime, module) cache —— 文件未变则复用已加载模块，避免重复 exec
_SCRIPT_CACHE: dict = {}


def _script_path(name: str) -> str:
    return os.path.join(SCRIPT_DIR, f"{name}.py")


def _script_mtime(name: str) -> float:
    try:
        return os.path.getmtime(_script_path(name))
    except OSError:
        return 0.0


def _load_script(name):
    """从用户 script 目录动态加载模块；按 mtime 缓存，文件变更自动失效。"""
    path = _script_path(name)
    mtime = os.path.getmtime(path)
    cached = _SCRIPT_CACHE.get(name)
    if cached and cached[0] == mtime:
        return cached[1]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _SCRIPT_CACHE[name] = (mtime, mod)
    return mod


_HINT_RE = re.compile(r'\[EVOLVE_HINT\](.*?)\[/EVOLVE_HINT\]', re.DOTALL)
_DOMAIN_RE = re.compile(r'\[DOMAIN\](.*?)\[/DOMAIN\]', re.DOTALL)
_SKILL_RE = re.compile(r'\[SKILL\](.*?)\[/SKILL\]', re.DOTALL)

_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = LLM(model=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    return _llm


# planner 单例：role/goal/backstory 全来自常量，无需每次重建
_planner_cache: dict = {}  # {"mtime": float, "agent": Agent}


def _get_planner() -> Agent:
    P = _load_script("prompts")
    mtime = _script_mtime("prompts")
    cached = _planner_cache.get("agent")
    if cached is not None and _planner_cache.get("mtime") == mtime:
        return cached
    agent = Agent(
        role=P.PLANNER_ROLE,
        goal=P.PLANNER_GOAL,
        backstory=P.PLANNER_BACKSTORY,
        tools=[],
        verbose=False,
        tracing=False,
        allow_delegation=False,
        llm=_get_llm(),
    )
    _planner_cache["agent"] = agent
    _planner_cache["mtime"] = mtime
    return agent


# executor 缓存：按 agent_id 区分；tools.py 或 MCP 注册表变更则整体失效
_executor_cache: dict = {}  # {agent_id: Agent}
_executor_tools_mtime: float = 0.0
_executor_mcp_version: float = -1.0


def _build_agent_list() -> str:
    """构建智能体列表文本供 planner 选择领域。"""
    agents = list_agents()
    if not agents:
        return "- general(通用助手): 处理所有问题, domains=[*]"
    lines = []
    for a in agents:
        domains = ", ".join(a.get("domains", ["*"]))
        lines.append(f"- {a['id']}({a['name']}): {a.get('description', '')}, domains=[{domains}]")
    return "\n".join(lines)


def _build_executor(agent_def: dict) -> Agent:
    """根据智能体定义动态构建 executor Agent；按 agent_id 缓存。
    tools.py 变更或 MCP 注册表版本变更时整体失效。"""
    global _executor_tools_mtime, _executor_mcp_version
    tools_mtime = _script_mtime("tools")
    mcp_version = mcp_registry.current_version()
    if tools_mtime != _executor_tools_mtime or mcp_version != _executor_mcp_version:
        _executor_cache.clear()
        _executor_tools_mtime = tools_mtime
        _executor_mcp_version = mcp_version

    agent_id = agent_def.get("id", "general")
    cached = _executor_cache.get(agent_id)
    if cached is not None:
        return cached

    tools_mod = _load_script("tools")
    all_tools = list(tools_mod.ALL_TOOLS) + mcp_client.get_mcp_tools()
    agent = Agent(
        role=agent_def.get("role", "智能助手"),
        goal=agent_def.get("goal", "帮助用户完成任务。"),
        backstory=agent_def.get("backstory", "你是一个智能助手。"),
        tools=all_tools,
        verbose=False,
        tracing=False,
        allow_delegation=False,
        llm=_get_llm(),
    )
    _executor_cache[agent_id] = agent
    return agent


def _format_plan_template(P, **kwargs) -> str:
    """兼容老/新 prompts.py：新模板包含 skill_section 占位，老模板没有。"""
    template = P.PLAN_TASK_TEMPLATE
    if "{skill_section}" not in template:
        kwargs.pop("skill_section", None)
    return template.format(**kwargs)


def _format_exec_template(P, **kwargs) -> str:
    """兼容老/新 prompts.py：新模板包含 skill_content/skill_obey 占位。"""
    template = P.EXEC_TASK_TEMPLATE
    if "{skill_content}" not in template:
        kwargs.pop("skill_content", None)
    if "{skill_obey}" not in template:
        kwargs.pop("skill_obey", None)
    return template.format(**kwargs)


def _build_skill_section(agent_id: str) -> str:
    """给 planner 看的 Skill 列表块；为空时返回空串。"""
    body = skill_registry.render_for_planner(agent_id)
    if not body:
        return ""
    return (
        "【可用 Skill 列表】\n"
        + body
        + "\n（若任务确实匹配某个 Skill，请通过 [SKILL]name[/SKILL] 激活；不匹配则保持 [SKILL][/SKILL] 空标签）\n\n"
    )


def _resolve_skill_content(plan_result: str, agent_id: str) -> tuple[str, list[str]]:
    """从 planner 输出中提取 [SKILL]...[/SKILL]，返回 (拼接好的注入文本, 激活名列表)。"""
    m = _SKILL_RE.search(plan_result)
    if not m:
        return "", []
    names = [n.strip() for n in m.group(1).split(",") if n.strip()]
    if not names:
        return "", []
    blocks: list[str] = []
    activated: list[str] = []
    for name in names:
        sk = skill_registry.get_by_name(name)
        if not sk:
            continue
        domains = sk.get("domains") or ["*"]
        if agent_id and agent_id not in domains and "*" not in domains:
            continue
        blocks.append(f"## Skill：{sk['name']}\n{sk.get('content', '').strip()}")
        activated.append(sk["name"])
        skill_registry.record_hit(sk["name"])
    if not blocks:
        return "", []
    body = "\n\n".join(blocks)
    return f"【已激活的 Skill —— 必须严格遵循其指引完成本次任务】\n{body}\n\n", activated


def run(user_input: str) -> str:
    P = _load_script("prompts")
    ctx = history_context()
    global_rules = rules_context()
    agent_list = _build_agent_list()
    skill_section = _build_skill_section("")  # planner 阶段还不知道 agent，先列全部

    planner = _get_planner()

    plan_task = Task(
        description=_format_plan_template(
            P,
            user_rules=global_rules, history_context=ctx,
            user_input=user_input, tool_catalog=P.TOOL_CATALOG,
            agent_list=agent_list, skill_section=skill_section,
        ),
        expected_output=P.PLAN_TASK_EXPECTED,
        agent=planner,
    )

    plan_crew = Crew(
        agents=[planner], tasks=[plan_task],
        process=Process.sequential, verbose=False, tracing=False,
    )
    plan_result = str(plan_crew.kickoff()).strip()

    # 解析领域标签
    domain_match = _DOMAIN_RE.search(plan_result)
    domain = domain_match.group(1).strip() if domain_match else "general"

    # 路由到对应智能体
    agent_def = route(domain)
    executor = _build_executor(agent_def)
    record_hit(domain, agent_def["id"])

    # 解析 Skill 激活
    skill_content, activated = _resolve_skill_content(plan_result, agent_def["id"])
    skill_obey = "，并严格遵循上方激活的 Skill 指引" if activated else ""

    # executor 阶段合并全局规则 + 智能体专属规则
    merged_rules = rules_context(agent_def["id"])

    exec_task = Task(
        description=_format_exec_template(
            P,
            user_rules=merged_rules, user_input=user_input,
            agent_name=agent_def.get("name", "通用助手"),
            domain=domain,
            skill_content=skill_content,
            skill_obey=skill_obey,
        ),
        expected_output=P.EXEC_TASK_EXPECTED,
        agent=executor,
        context=[plan_task],
    )

    exec_crew = Crew(
        agents=[executor], tasks=[exec_task],
        process=Process.sequential, verbose=False, tracing=False,
    )

    try:
        result = exec_crew.kickoff()
        raw = str(result)
        hint_match = _HINT_RE.search(raw)
        if hint_match:
            hint = hint_match.group(1).strip()
            answer = _HINT_RE.sub('', raw).strip()
            write_evolve_hint(user_input, hint)
        else:
            answer = raw.strip()
        append_history(user_input, answer)
        write_chat_log(user_input, answer)
        return answer
    except Exception as e:
        err = f"执行出错：{type(e).__name__}: {e}"
        write_chat_log(user_input, err, error=True)
        raise
