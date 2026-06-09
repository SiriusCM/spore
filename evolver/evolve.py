import os
from datetime import datetime
from crewai import Agent, Task, Crew, Process, LLM
from settings import LLM_MODEL, LLM_BASE_URL, LLM_API_KEY
from . import prompts as EP
from .proposals import EVOLVER_TOOLS, get_proposals, reset_proposals
from .applier import apply_proposals


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _build_evolver_agent():
    llm = LLM(model=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
    return Agent(
        role=EP.EVOLVER_ROLE,
        goal=EP.EVOLVER_GOAL,
        backstory=EP.EVOLVER_BACKSTORY,
        tools=EVOLVER_TOOLS,
        verbose=False,
        tracing=False,
        allow_delegation=False,
        llm=llm,
        max_iter=20,
    )


def _render_proposals_md(results):
    if not results:
        return "_无_"
    lines = []
    for i, p in enumerate(results, 1):
        kind = p.get("kind")
        st = p.get("status", "")
        reason = p.get("reason", "")
        if kind == "edit":
            lines.append(f"{i}. **edit** `{p['file']}`  状态：`{st}`\n   原因：{reason}\n   old: `{(p.get('old','') or '')[:80]}...`\n   new: `{(p.get('new','') or '')[:80]}...`")
        elif kind == "append_preference":
            lines.append(f"{i}. **append_preference** `CONSTITUTION.md`  状态：`{st}`\n   行：{p.get('line','')}")
        elif kind == "create_tool":
            lines.append(f"{i}. **create_tool** `{p['name']}`  状态：`{st}`\n   原因：{reason}\n   catalog_desc：{p.get('catalog_desc','')}")
        elif kind == "add_rule":
            lines.append(f"{i}. **add_rule**  状态：`{st}`\n   规则：{p.get('rule','')}\n   原因：{reason}")
        elif kind == "remove_rule":
            lines.append(f"{i}. **remove_rule**  状态：`{st}`\n   规则：{p.get('rule','')}\n   原因：{reason}")
        elif kind == "split_agent":
            lines.append(f"{i}. **split_agent** `{p.get('id','')}`({p.get('name','')})  状态：`{st}`\n   domains：{p.get('domains','')}\n   parent：{p.get('parent','')}\n   原因：{reason}")
        elif kind == "create_skill":
            lines.append(f"{i}. **create_skill** `{p.get('name','')}`  状态：`{st}`\n   summary：{p.get('summary','')}\n   domains：{p.get('domains','')}\n   原因：{reason}")
        else:
            lines.append(f"{i}. **{kind}**  状态：`{st}`")
    return "\n".join(lines)


def _get_evolver_context() -> str:
    """生成当前系统状态摘要（工具/技能/智能体），注入到 evolver 任务模板。"""
    from core.registry.tool_catalog_registry import build_tool_catalog_text
    from core.registry.skill_registry import list_skills
    from core.registry.agent_registry import list_agents

    tools_text = build_tool_catalog_text()
    skills = list_skills(only_enabled=False)
    agents = list_agents()

    skill_lines = []
    if skills:
        for s in skills:
            flag = "[禁用]" if not s.get("enabled") else ""
            skill_lines.append(f"  - {s['name']} {flag}: {s.get('summary','')}")
    else:
        skill_lines.append("  (无)")

    agent_lines = []
    for a in agents:
        agent_lines.append(
            f"  - {a['id']}({a['name']}): {a.get('description','')}, hit={a.get('hit_count',0)}"
        )

    return f"""【当前系统状态】

### 内置工具
{tools_text}

### 已有 Skill
{chr(10).join(skill_lines)}

### 已有智能体
{chr(10).join(agent_lines)}
"""


def evolve(dry_run: bool = True) -> dict:
    """
    触发一次进化。
    dry_run=True 时：仅模拟，报告内容会返回给前端展示
    dry_run=False 时：实际应用，报告存库后返回路径
    返回 dict：{
        "report_path": str,
        "report": str,            # 完整 Markdown 报告内容
        "proposals": int,
        "applied": int,
        "failed": int,
        "applied_to_disk": bool,
        "snapshot": str|None,
        "msg": str,
    }
    """
    from core.chat_log import get_all_hints, clear_all_hints
    today = _today()
    reset_proposals()
    evolver = _build_evolver_agent()
    context = _get_evolver_context()
    task = Task(
        description=EP.EVOLVER_TASK_TEMPLATE.format(context=context),
        expected_output="调用 finalize 工具后，返回其结果字符串作为总结。",
        agent=evolver,
    )
    crew = Crew(agents=[evolver], tasks=[task], process=Process.sequential, verbose=False, tracing=False)
    print("🧠 evolver Agent 正在阅读与反思（这可能需要 30~90 秒）...")
    summary = ""
    notes = ""
    try:
        summary = str(crew.kickoff()).strip()
    except Exception as e:
        notes = f"Agent 运行异常：{type(e).__name__}: {e}"

    proposals = get_proposals()
    if not proposals:
        decision = {"phase": "no-op", "ok": True, "msg": "evolver 未提交任何提案", "applied_to_disk": False, "snapshot": None, "rolled_back": False}
        results = []
    else:
        results, decision = apply_proposals(proposals, dry_run=dry_run)
        # 执行模式：应用后清空所有摘要
        if not dry_run and decision.get("applied_to_disk"):
            clear_all_hints()

    # 生成报告内容（无论 dry_run 还是 apply 都生成）
    md = EP.REPORT_TEMPLATE.format(
        today=today,
        summary=summary or "(无)",
        proposals_md=_render_proposals_md(results),
        phase=decision.get("phase", ""),
        result_msg=decision.get("msg", ""),
        applied_to_disk=str(decision.get("applied_to_disk", False)),
        snapshot=decision.get("snapshot") or "(无)",
        rolled_back=str(decision.get("rolled_back", False)),
        notes=notes or "(无)",
    )

    n = len(results)
    applied = sum(1 for p in results if p.get("status") == "ok")
    failed = n - applied
    print(f"✅ 进化完成 [{'DRY-RUN' if dry_run else 'APPLY'}]")
    print(f"   提案 : {n} 条（ok {applied} / 其他 {failed}）")
    print(f"   阶段 : {decision.get('phase')}  写盘 : {decision.get('applied_to_disk')}  快照 : {decision.get('snapshot') or '-'}  回滚 : {decision.get('rolled_back')}")
    if decision.get("msg"):
        print(f"   说明 : {decision.get('msg')}")
    if dry_run and n > 0:
        print("👉 确认无误后执行：spore evolve --apply")

    # 保存报告到数据库
    from database import get_conn
    conn = get_conn()
    # 确定状态：preview=预览/未应用, applied=已应用, failed=失败
    if dry_run:
        state = "preview"
    elif decision.get("rolled_back"):
        state = "failed"
    else:
        state = "applied"
    conn.execute(
        """INSERT INTO evolve_reports
           (created_at, state, proposals_count, applied_count, failed_count, snapshot_tag, phase, result_msg, report_content)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(),
            state,
            n,
            applied,
            failed,
            decision.get("snapshot"),
            decision.get("phase", ""),
            decision.get("msg", ""),
            md,
        )
    )
    conn.commit()
    conn.close()

    return {
        "report": md,
        "proposals": n,
        "applied": applied,
        "failed": failed,
        "state": state,
        "applied_to_disk": decision.get("applied_to_disk", False),
        "snapshot": decision.get("snapshot"),
        "msg": decision.get("msg", ""),
    }