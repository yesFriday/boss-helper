"""冲突改期引导回复单元测试。

覆盖:空闲半时段计算(排除已约时段)、两段式回复构造(冲突说明+真实空闲+问句收尾,
无确认性措辞)。全部使用 monkeypatch 隔离,不写共享数据库。

运行: pytest tests/test_conflict_reply.py -v
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="boss_conflict_test_")
os.environ["BOSS_DATA_DIR"] = _TEST_DATA_DIR

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import backend.state as st

st.init_db()

import pytest  # noqa: E402

import backend.interview_gate as ig  # noqa: E402
from backend.interview_gate import _build_conflict_reply, get_free_halfday_slots  # noqa: E402


def _mk_upcoming(days_ahead: int, hour: int):
    """构造 get_upcoming_interviews 返回结构的排期记录。"""
    start = datetime.now() + timedelta(days=days_ahead)
    start = start.replace(hour=hour, minute=0, second=0, microsecond=0)
    return {"start_time": start.strftime("%Y-%m-%d %H:%M:%S"), "interview_type": "offline"}


class TestFreeHalfdaySlots:
    def test_all_free_when_no_interviews(self, monkeypatch):
        monkeypatch.setattr("backend.state.get_upcoming_interviews", lambda days=5: [])
        slots = get_free_halfday_slots(days=3)
        assert len(slots) >= 2
        # 标签为 今天/明天/周X，粒度为 全天/上午/下午
        assert all(s.startswith(("今天", "明天", "周一", "周二", "周三", "周四", "周五", "周六", "周日")) for s in slots)
        assert all(("全天" in s or "上午" in s or "下午" in s) for s in slots)
        # 同一天不会同时出现上午和下午（已合并为全天）
        days_seen = [s.replace("全天", "").replace("上午", "").replace("下午", "") for s in slots]
        assert len(days_seen) == len(set(days_seen))

    def test_booked_halfday_excluded(self, monkeypatch):
        booked = [_mk_upcoming(1, 15)]  # 明天下午一场
        monkeypatch.setattr("backend.state.get_upcoming_interviews", lambda days=5: booked)
        slots = get_free_halfday_slots(days=3)
        assert "明天下午" not in slots
        assert "明天上午" in slots  # 上午仍空闲（独立半场不合并）

    def test_today_elapsed_halfdays_excluded(self, monkeypatch):
        """今天的上午/下午过了时间点后不应再对外报。"""
        from datetime import datetime as dt
        monkeypatch.setattr("backend.state.get_upcoming_interviews", lambda days=5: [])
        monkeypatch.setattr(ig, "datetime", _FixedNow)
        slots = get_free_halfday_slots(days=3)
        assert not any(s.startswith("今天") for s in slots)  # 20点后今天全天已过
        assert slots[0] == "明天全天"

    def test_max_slots(self, monkeypatch):
        monkeypatch.setattr("backend.state.get_upcoming_interviews", lambda days=5: [])
        assert len(get_free_halfday_slots(days=5, max_slots=3)) <= 3


class _FixedNow:
    """替换模块内 datetime，让 now() 返回固定时刻（20:00）。"""
    @staticmethod
    def now(tz=None):
        return datetime(2026, 9, 12, 20, 0)


class TestConflictReply:
    def test_two_segment_template(self, monkeypatch):
        monkeypatch.setattr(ig, "get_free_halfday_slots", lambda *a, **k: ["周四上午", "周四下午", "周五上午"])
        reply = _build_conflict_reply()
        assert "已经有安排" in reply  # 第一段: 说明冲突
        assert "周四上午、周四下午、周五上午" in reply  # 第二段: 报真实空闲
        assert "您看哪个时间方便" in reply  # 问句收尾

    def test_no_confirmation_wording(self, monkeypatch):
        monkeypatch.setattr(ig, "get_free_halfday_slots", lambda *a, **k: ["周五下午"])
        reply = _build_conflict_reply()
        for banned in ("就这么定", "准时", "没问题", "一定到", "确认时间", "定在"):
            assert banned not in reply, f"出现确认性措辞: {banned}"

    def test_reply_mentions_real_slots(self, monkeypatch):
        slots = ["周一上午", "周二下午"]
        monkeypatch.setattr(ig, "get_free_halfday_slots", lambda *a, **k: slots)
        reply = _build_conflict_reply()
        assert slots[0] in reply and slots[1] in reply

    def test_no_schedule_generic_reply(self, monkeypatch):
        monkeypatch.setattr(ig, "get_free_halfday_slots", lambda *a, **k: [])
        reply = _build_conflict_reply()
        assert "已经有安排" in reply
        assert "下周" in reply  # 近期排满 → 引导到下周
