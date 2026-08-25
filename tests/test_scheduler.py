"""Scheduler 单元测试:全部依赖 mock,不依赖 FastAPI / Playwright / SQLite。

运行: pytest tests/test_scheduler.py -v
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.scheduler import (
    APPLY_CHUNK,
    LOG_MAX,
    NO_PROGRESS_LIMIT,
    Scheduler,
    SchedulerDeps,
    match_time_range,
)


class FakeAutomation:
    def __init__(self):
        self.page = MagicMock()
        self.check_page_safety = MagicMock(return_value=True)
        self.apply_batch = MagicMock(return_value=[{"success": True}] * 3)


def make_deps(tmp_settings=None, **overrides):
    """构造一套可编程的假依赖。"""
    store = tmp_settings if tmp_settings is not None else {}
    events = {"broadcasts": [], "paused": False, "applied_calls": [], "chat_cycles": 0}

    async def run_pw(fn, *args):
        return fn(*args)

    async def broadcast(msg):
        events["broadcasts"].append(msg)

    async def save_jobs(keyword, city_code):
        return 10, 5

    def pending_jobs(limit, hr_filter):
        return [{"job_url": f"https://zhipin.com/job/{i}"} for i in range(limit)]

    async def run_chat_cycle():
        events["chat_cycles"] += 1
        return {"new_messages": 0, "replies_sent": 0}

    d = SchedulerDeps(
        get_setting=lambda k, default="": store.get(k, default),
        set_setting=lambda k, v: store.__setitem__(k, v),
        run_pw=run_pw,
        get_automation=lambda: overrides.get("automation"),
        broadcast=broadcast,
        city_code=lambda city: "101280100",
        save_jobs=overrides.get("save_jobs", save_jobs),
        pending_jobs=overrides.get("pending_jobs", pending_jobs),
        today_count=overrides.get("today_count", lambda: 0),
        set_monitor_paused=lambda v: events.__setitem__("paused", v),
        get_monitor_paused=lambda: events["paused"],
        monitor_alive=overrides.get("monitor_alive", lambda: True),
        run_chat_cycle=overrides.get("run_chat_cycle", run_chat_cycle),
    )
    return d, store, events


def in_window_config():
    now = datetime.now()
    start = (now.replace(minute=max(now.minute - 5, 0))).strftime("%H:%M")
    end = (now.replace(minute=min(now.minute + 5, 59))).strftime("%H:%M")
    if start > end:
        start, end = "00:00", "23:59"
    return {
        "days": list(range(1, 8)),
        "time_ranges": [{"start": start, "end": end}],
        "auto_apply": {"keyword": "AI Agent", "city": "广州", "daily_limit": 30, "hr_active_filter": "all"},
    }


# ── 时间窗匹配 ──


def test_match_time_range_hit():
    cfg = {"days": [3], "time_ranges": [{"start": "09:00", "end": "12:00"}]}
    now = datetime(2026, 8, 26, 10, 30)  # 周三
    assert match_time_range(cfg, now) == "09:00~12:00"


def test_match_time_range_wrong_day():
    cfg = {"days": [1], "time_ranges": [{"start": "09:00", "end": "12:00"}]}
    now = datetime(2026, 8, 26, 10, 30)  # 周三,配置只允许周一
    assert match_time_range(cfg, now) is None


def test_match_time_range_out_of_window():
    cfg = {"days": [3], "time_ranges": [{"start": "09:00", "end": "12:00"}]}
    now = datetime(2026, 8, 26, 14, 0)
    assert match_time_range(cfg, now) is None


def test_match_time_range_boundary_inclusive():
    cfg = {"days": [3], "time_ranges": [{"start": "09:00", "end": "12:00"}]}
    assert match_time_range(cfg, datetime(2026, 8, 26, 9, 0)) is not None
    assert match_time_range(cfg, datetime(2026, 8, 26, 12, 0)) is not None


# ── 状态持久化 ──


def test_enabled_restored_from_persistence():
    d, store, _ = make_deps({"scheduler_enabled": "true"})
    s = Scheduler(d)
    assert s.enabled is True
    assert s.get_config()["enabled"] is True


def test_disabled_by_default():
    d, _, _ = make_deps()
    s = Scheduler(d)
    assert s.enabled is False


def test_set_enabled_persists():
    d, store, _ = make_deps()
    s = Scheduler(d)
    asyncio.run(s.set_enabled(True))
    assert store["scheduler_enabled"] == "true"
    # 模拟重启:用同一 store 重建
    s2 = Scheduler(make_deps(store)[0])
    assert s2.enabled is True


def test_log_persisted_and_capped():
    d, store, _ = make_deps()
    s = Scheduler(d)

    async def _many():
        for i in range(LOG_MAX + 10):
            await s._report([f"事件{i}"])

    asyncio.run(_many())
    persisted = json.loads(store["scheduler_log"])
    assert len(persisted) == LOG_MAX
    assert persisted[-1]["tasks"] == [f"事件{LOG_MAX + 9}"]
    # 模拟重启:日志可恢复
    s2 = Scheduler(make_deps(store)[0])
    assert len(s2.log_entries) == LOG_MAX


# ── 配置 ──


def test_get_config_merges_defaults():
    d, store, _ = make_deps({"scheduler_config": json.dumps({"days": [1]})})
    s = Scheduler(d)
    cfg = s.get_config()
    assert cfg["days"] == [1]
    assert "auto_apply" in cfg and "auto_reply" in cfg
    assert cfg["enabled"] is False


def test_update_config_roundtrip():
    d, store, _ = make_deps()
    s = Scheduler(d)
    payload = in_window_config() | {"enabled": True}
    result = asyncio.run(s.update_config(payload))
    assert result["enabled"] is True
    # enabled 不应混入持久化的 config
    db_cfg = json.loads(store["scheduler_config"])
    assert "enabled" not in db_cfg


# ── tick 行为 ──


def test_tick_disabled_does_nothing():
    d, _, events = make_deps()
    s = Scheduler(d)
    asyncio.run(s._tick())
    assert events["chat_cycles"] == 0
    assert s.phase == "idle"


def test_tick_paused_outside_window():
    auto = FakeAutomation()
    d, store, events = make_deps(
        automation=auto,
        today_count=lambda: 0,
        monitor_alive=lambda: True,
    )
    store["scheduler_config"] = json.dumps({"days": [1], "time_ranges": []})
    s = Scheduler(d)
    asyncio.run(s.set_enabled(True))
    asyncio.run(s._tick())
    assert s.phase == "paused"


def test_tick_no_browser_skips_apply():
    d, store, _ = make_deps(automation=None)
    store["scheduler_config"] = json.dumps(in_window_config())
    s = Scheduler(d)
    asyncio.run(s.set_enabled(True))
    asyncio.run(s._tick())  # 不应抛异常


def test_chat_fallback_only_when_monitor_dead():
    auto = FakeAutomation()
    chat = AsyncMock(return_value={"new_messages": 2, "replies_sent": 1})
    d_alive, _, _ = make_deps(automation=auto, monitor_alive=lambda: True, run_chat_cycle=chat)
    d_dead, _, ev_dead = make_deps(automation=auto, monitor_alive=lambda: False, run_chat_cycle=chat)
    s1, s2 = Scheduler(d_alive), Scheduler(d_dead)
    asyncio.run(s1.set_enabled(True))
    asyncio.run(s2.set_enabled(True))
    asyncio.run(s1._tick())
    assert chat.await_count == 0  # monitor 存活时不重复跑
    asyncio.run(s2._tick())
    assert chat.await_count == 1  # monitor 死了才兜底
    assert ev_dead["paused"] is False  # 兜底路径不碰 monitor 暂停状态


# ── 投递会话 ──


def test_apply_session_respects_daily_limit():
    auto = FakeAutomation()
    d, _, events = make_deps(automation=auto, today_count=lambda: 30)
    s = Scheduler(d)
    cfg = in_window_config()
    cfg["auto_apply"]["daily_limit"] = 30
    asyncio.run(s.set_enabled(True))
    asyncio.run(s._apply_session(cfg))
    auto.apply_batch.assert_not_called()
    assert any("达到上限" in t for e in s.log_entries for t in e["tasks"])


def test_apply_session_chunks_and_interleaves_chat():
    auto = FakeAutomation()
    auto.apply_batch = MagicMock(return_value=[{"success": True}] * APPLY_CHUNK)
    call_state = {"count": 0}

    def today_count():
        return call_state["count"]

    def apply_batch(urls, greeting, limit):
        call_state["count"] += len(urls)  # 每块投完即计入
        return [{"success": True}] * len(urls)

    auto.apply_batch = MagicMock(side_effect=apply_batch)
    d, _, events = make_deps(automation=auto, today_count=today_count)
    s = Scheduler(d)
    cfg = in_window_config()
    cfg["auto_apply"]["daily_limit"] = 12  # 12 条 = 3 块(5+5+2)
    asyncio.run(s.set_enabled(True))
    asyncio.run(s._apply_session(cfg))

    chunks = [c.args[0] for c in auto.apply_batch.call_args_list]
    assert [len(c) for c in chunks] == [APPLY_CHUNK, APPLY_CHUNK, 2]
    # 每块之间跑了一轮聊天:12 条投递后应至少有 2 轮块间聊天
    assert events["chat_cycles"] >= 2
    assert call_state["count"] == 12
    assert s.phase == "idle"
    assert events["paused"] is False  # 会话结束恢复未暂停


def test_apply_session_monitor_pause_restored():
    auto = FakeAutomation()
    d, _, events = make_deps(automation=auto, today_count=lambda: 30)  # 直达上限
    events["paused"] = True  # 用户此前手动暂停
    s = Scheduler(d)
    asyncio.run(s._apply_session(in_window_config()))
    assert events["paused"] is True  # 恢复为用户先前的暂停状态


def test_apply_session_safety_stop_disables():
    auto = FakeAutomation()
    auto.check_page_safety = MagicMock(return_value=False)
    d, store, events = make_deps(automation=auto, today_count=lambda: 0)
    s = Scheduler(d)
    asyncio.run(s.set_enabled(True))
    asyncio.run(s._apply_session(in_window_config()))
    assert s.enabled is False
    assert store["scheduler_enabled"] == "false"  # 停止也持久化
    auto.apply_batch.assert_not_called()
    assert any(m["type"] == "safety_warning" for m in events["broadcasts"])
    assert events["paused"] is False


def test_apply_session_searches_when_empty():
    auto = FakeAutomation()
    empty_then_jobs = {"first": True}
    state = {"applied": 0}

    def pending_jobs(limit, hr_filter):
        if empty_then_jobs["first"]:
            empty_then_jobs["first"] = False
            return []
        return [{"job_url": f"https://zhipin.com/job/{i}"} for i in range(3)]

    def apply_batch(urls, greeting, limit):
        state["applied"] += len(urls)
        return [{"success": True}] * len(urls)

    auto.apply_batch = MagicMock(side_effect=apply_batch)
    d, _, _ = make_deps(
        automation=auto,
        pending_jobs=pending_jobs,
        today_count=lambda: state["applied"],
    )
    s = Scheduler(d)
    cfg = in_window_config()
    cfg["auto_apply"]["daily_limit"] = 3
    asyncio.run(s.set_enabled(True))
    asyncio.run(s._apply_session(cfg))
    assert any("搜索" in t for e in s.log_entries for t in e["tasks"])
    assert state["applied"] == 3


def test_apply_session_fuse_on_no_progress():
    """today_count 恒不推进(如账号被限流)时熔断,不得无限重投。"""
    auto = FakeAutomation()
    d, _, _ = make_deps(automation=auto, today_count=lambda: 0)
    s = Scheduler(d)
    cfg = in_window_config()
    cfg["auto_apply"]["daily_limit"] = 100
    asyncio.run(s.set_enabled(True))
    asyncio.run(s._apply_session(cfg))
    assert auto.apply_batch.call_count == NO_PROGRESS_LIMIT
    assert any("熔断" in t for e in s.log_entries for t in e["tasks"])
    assert s.phase == "idle"


def test_status_contract():
    d, store, _ = make_deps({"scheduler_config": json.dumps(in_window_config())})
    s = Scheduler(d)
    status = s.get_status()
    assert set(status.keys()) == {"active", "phase", "today_count", "daily_limit", "execution_log"}
    assert status["daily_limit"] == 30
    assert isinstance(status["execution_log"], list)
