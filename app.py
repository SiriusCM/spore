import sys
from core.orchestrator import run


HELP = (
    "🌟 Starfish CLI — 可自我进化的智能助手\n"
    "\n"
    "用法：\n"
    "  starfish                 启动桌面应用\n"
    "  starfish cli             进入控制台对话模式\n"
    "  starfish evolve          触发进化（dry-run 预览，不写盘）\n"
    "  starfish evolve --apply  触发进化并写盘生效\n"
    "  starfish snapshots       查看已有快照列表\n"
    "  starfish rollback [tag]  回滚到指定快照（默认最近一次）\n"
    "  starfish reset           重置 script 为初始版本\n"
    "  starfish web             启动 Web 界面（浏览器访问）\n"
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
        from core.server import run_server
        print("🌐 启动 Web 服务: http://localhost:8765")
        print("   按 Ctrl+C 停止服务")
        run_server(host="0.0.0.0", port=8765)
        return

    if len(sys.argv) > 1 and sys.argv[1] == "evolve":
        from evolver.evolve import evolve
        evolve(dry_run="--apply" not in sys.argv)
        return

    if len(sys.argv) > 1 and sys.argv[1] == "snapshots":
        from evolver.snapshot import list_snapshots
        snaps = list_snapshots()
        if not snaps:
            print("（无快照）")
        else:
            print("📦 已有快照（新 → 旧）：")
            for s in snaps:
                print(f"  - {s}")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        from evolver.snapshot import rollback
        tag = sys.argv[2] if len(sys.argv) > 2 else ""
        print(f"↩️  {rollback(tag)}")
        return

    if len(sys.argv) > 1 and sys.argv[1] == "reset":
        import os
        import shutil
        from settings import DATA_DIR, PKG_DIR, SCRIPT_DIR
        pkg_script = os.path.join(PKG_DIR, "script")
        if os.path.isdir(SCRIPT_DIR):
            shutil.rmtree(SCRIPT_DIR)
        shutil.copytree(pkg_script, SCRIPT_DIR)
        print("✅ script/ 已从源码重新拷贝（恢复出厂设置）")
        return

    # 默认启动桌面版
    from core.desktop import run_desktop
    print("🖥️ 启动桌面应用...")
    sys.exit(run_desktop())


if __name__ == "__main__":
    main()