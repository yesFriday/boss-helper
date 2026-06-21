#!/usr/bin/env python3
"""
BossAutomation — 继承 BossScraper，增加点击/输入/聊天等交互能力。
（重构说明：本文件已作为兼容层门面，其真实实现在 automation_base.py, boss_applier.py, boss_chat_monitor.py 中）
"""

# 导入选择器配置以保持兼容性
from backend.boss_selectors import SELECTORS
from backend.boss_chat_monitor import BossChatMonitor, MAX_AUTO_REPLY_PER_DAY
from backend.boss_applier import MAX_APPLY_PER_DAY

# 核心类的转发映射，app.py 可完全不做改动地继续导入和使用 BossAutomation
BossAutomation = BossChatMonitor
