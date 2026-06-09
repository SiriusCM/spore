import sys
from core.orchestrator import run


HELP = (
    "🌟 spore CLI — 可自我进化的智能助手\n"
    "\n"
    "用法：\n"
    "  spore                 启动桌面应用\n"
    "  spore cli             进入控制台对话模式\n"
    "  spore evolve          触发进化（dry-run 预览，不写盘）\n"
    "  spore evolve --apply  触发进化并写盘生效\n"
    "  spore reports         查看进化报告列表\n"
    "  spore api             启动 Web 界面（浏览器访问）\n"
    "\n"
    "对话模式中：\n"
    "  直接输入 → 与 AI 对话\n"
    "  exit / quit → 退出\n"
)


def chat_loop():
    print(HELP)
    while True:
        try:
            q = input("👤 你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见")
            break
        if not q:
            continue
        if q.lower() in ("exit", "quit"):
            print("👋 再见")
            break
        print("⏳ 处理中...")
        try:
            print(f"\n✨ AI：\n{run(q)}\n" + "-" * 50)
        except Exception as e:
            print(f"\n❌ 执行出错：{type(e).__name__}: {e}\n" + "-" * 50)


def main():
    from settings import init_data_dir
    init_data_dir()

    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        chat_loop()
        return

    if len(sys.argv) > 1 and sys.argv[1] == "web":
        from server import run_server
        print("🌐 启动 Web 服务: http://localhost:8765")
        print("   按 Ctrl+C 停止服务")
        run_server(host="0.0.0.0", port=8765)
        return

    if len(sys.argv) > 1 and sys.argv[1] == "evolve":
        from evolver.evolve import evolve
        evolve(dry_run="--apply" not in sys.argv)
        return

    if len(sys.argv) > 1 and sys.argv[1] == "reports":
        from database import get_conn
        conn = get_conn()
        rows = conn.execute(
            """SELECT id, created_at, state, proposals_count,
                      applied_count, failed_count, phase, result_msg
               FROM evolve_reports ORDER BY id DESC LIMIT 20"""
        ).fetchall()
        conn.close()
        if not rows:
            print("（无进化报告）")
            return
        print("📋 进化报告（新 → 旧）：")
        for r in rows:
            tag = {"preview": "[预览]", "applied": "[已应用]", "failed": "[失败]"}.get(r["state"], "[?]")
            print(f"  #{r['id']} {tag} {r['created_at'][:19]} | {r['phase']} | 提案:{r['proposals_count']} 成功:{r['applied_count']} 失败:{r['failed_count']}")
        return

    # 默认启动桌面版
    from desktop import run_desktop
    print("🖥️ 启动桌面应用...")
    sys.exit(run_desktop())


if __name__ == "__main__":
    main()