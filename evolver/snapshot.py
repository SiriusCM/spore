"""
单快照管理 —— 只保留上一次版本，每次写盘前自动覆盖。
内部使用，不对外暴露 API。
"""
import os
import shutil
from settings import SCRIPT_DIR, DATA_DIR

SNAP_DIR = os.path.join(DATA_DIR, ".snapshots")


def _snapshot_targets():
    """返回 script/ 目录下需要备份的文件列表"""
    files = []
    for name in os.listdir(SCRIPT_DIR):
        if name.startswith(".") or name == "__pycache__":
            continue
        p = os.path.join(SCRIPT_DIR, name)
        if os.path.isfile(p) and (name.endswith(".py") or name.endswith(".md")):
            files.append(name)
    return files


def take_snapshot() -> str:
    """创建单快照（覆盖上次）"""
    os.makedirs(SNAP_DIR, exist_ok=True)

    # 清理旧快照
    if os.path.exists(SNAP_DIR):
        shutil.rmtree(SNAP_DIR)
    os.makedirs(SNAP_DIR, exist_ok=True)

    dst = os.path.join(SNAP_DIR, "last")
    os.makedirs(dst, exist_ok=True)

    for name in _snapshot_targets():
        shutil.copy2(os.path.join(SCRIPT_DIR, name), os.path.join(dst, name))
    return dst


def _rollback():
    """内部回滚（仅 evolver/applier.py 调用）"""
    src_dir = os.path.join(SNAP_DIR, "last")
    if not os.path.isdir(src_dir):
        return False
    for name in os.listdir(src_dir):
        shutil.copy2(os.path.join(src_dir, name), os.path.join(SCRIPT_DIR, name))
    return True