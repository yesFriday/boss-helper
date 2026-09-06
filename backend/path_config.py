"""
数据与日志路径统一管理配置
"""

import sys
import os
from pathlib import Path

def get_boss_data_dir() -> Path:
    env_dir = os.environ.get("BOSS_DATA_DIR")
    if env_dir:
        d = Path(env_dir).resolve()
    elif getattr(sys, "frozen", False):
        # PyInstaller 打包环境下，通过 sys.executable 或 工作目录 追溯项目根目录
        exe_path = Path(sys.executable).resolve()
        cwd = Path.cwd().resolve()
        
        # 候选根目录优先级: 当前工作目录 -> 可执行文件的各级父目录
        candidates = [
            cwd,
            exe_path.parent,
            exe_path.parent.parent,
            exe_path.parent.parent.parent,
            exe_path.parent.parent.parent.parent,
        ]
        
        target_dir = None
        for candidate in candidates:
            if (candidate / ".boss_profile").exists() or (candidate / "package.json").exists() or (candidate / "backend").exists():
                target_dir = candidate / ".boss_profile"
                break
        
        if not target_dir:
            target_dir = cwd / ".boss_profile"
            
        d = target_dir
    else:
        d = Path(__file__).resolve().parent.parent / ".boss_profile"
        
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_log_dir() -> Path:
    """日志目录: 与 bossHelper 项目根平级的 logs 文件夹。"""
    env_dir = os.environ.get("BOSS_LOG_DIR")
    if env_dir:
        d = Path(env_dir).resolve()
    else:
        # 项目根 = bossHelper 目录(backend 的上一级),日志与其平级
        d = Path(__file__).resolve().parent.parent.parent / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d
