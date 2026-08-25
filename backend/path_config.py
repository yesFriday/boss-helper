"""
数据与日志路径统一管理配置
"""

import os
from pathlib import Path

def get_boss_data_dir() -> Path:
    env_dir = os.environ.get("BOSS_DATA_DIR")
    if env_dir:
        d = Path(env_dir)
    else:
        d = Path(__file__).parent.parent / ".boss_profile"
    d.mkdir(parents=True, exist_ok=True)
    return d
