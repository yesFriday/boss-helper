"""会话定位与回复链路设计缺陷修复的单元测试(D1 securityId 身份/D2 孤儿扫描/D3 三阶段)。

覆盖:securityId 归并建会话、match_conversation_item 匹配优先级、身份校验、
stale 会话查询(UTC 时间窗)、发送失败计入退避、三阶段编排契约。

运行: pytest tests/test_conversation_identity.py -v
"""

import asyncio
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

# 必须在导入 backend.state 之前设置,保证测试 DB 隔离
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="boss_identity_test_")
os.environ["BOSS_DATA_DIR"] = _TEST_DATA_DIR

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest

import backend.state as st

st.init_db()


@pytest.fixture(autouse=True)
def fresh_db():
    """每个测试用全新数据库。"""
    conn = getattr(st._local, "conn", None)
    if conn is not None:
        conn.close()
        st._local.conn = None
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(st.DB_PATH) + suffix)
        if p.exists():
            p.unlink()
    st.init_db()
    yield
    conn = getattr(st._local, "conn", None)
    if conn is not None:
        conn.close()
        st._local.conn = None


def _make_conv(name="张三", sid="", **kwargs):
    return st.get_or_create_conversation(None, name, kwargs.pop("company", ""), "", sid)


# ── D1: securityId 作为会话身份 ──


def test_same_security_id_returns_same_conversation():
    cid1 = _make_conv("张三", sid="sid_abc123")
    cid2 = _make_conv("张三", sid="sid_abc123")
    assert cid1 == cid2


def test_security_id_merges_name_variants():
    """名字变了但 sid 相同 → 同一会话,并更新名字。"""
    cid1 = _make_conv("张三", sid="sid_abc123")
    cid2 = _make_conv("张三丰", sid="sid_abc123")
    assert cid1 == cid2
    conv = st.get_conversation(cid1)
    assert conv["hr_name"] == "张三丰"


def test_same_name_different_sid_creates_separate():
    """同名不同 HR(不同 sid)→ 拆成两个会话,不再错误归并。"""
    cid1 = _make_conv("张伟", sid="sid_AAA111")
    cid2 = _make_conv("张伟", sid="sid_BBB222")
    assert cid1 != cid2
    assert st.get_conversation_by_security_id("sid_AAA111")["id"] == cid1
    assert st.get_conversation_by_security_id("sid_BBB222")["id"] == cid2


def test_no_sid_falls_back_to_name_merge():
    """无 sid(存量数据/接口失败)时保持原名归并行为。"""
    cid1 = _make_conv("李四")
    cid2 = _make_conv("李四")
    assert cid1 == cid2


def test_update_conversation_security_id_learns_once():
    """存量会话学习 sid;已有 sid 时不覆盖(防误学)。"""
    cid = _make_conv("王五")
    st.update_conversation_security_id(cid, "sid_learned_1")
    assert st.get_conversation(cid)["security_id"] == "sid_learned_1"
    st.update_conversation_security_id(cid, "sid_other_2")
    assert st.get_conversation(cid)["security_id"] == "sid_learned_1"


def test_application_id_backfills_sid():
    app_id = st.add_application({"title": "后端开发", "company": "字节", "hr_name": "赵六", "salary": "20k", "city": "北京", "description": "JD"})
    cid = st.get_or_create_conversation(app_id, "赵六", "", "", "sid_app_123")
    assert st.get_conversation(cid)["security_id"] == "sid_app_123"
    # 再用同 sid 访问(名字不同) → 归并回同一会话
    cid2 = st.get_or_create_conversation(None, "赵六六", "", "", "sid_app_123")
    assert cid2 == cid


# ── match_conversation_item 匹配优先级 ──


def _kc(name, sid=""):
    return {"hr_name": name, "security_id": sid}


def test_match_by_security_id_exact():
    known = [_kc("张三", "sid_zs"), _kc("李四", "sid_ls")]
    item = {"hr_name": "张三", "text": "张三 字节 后端", "security_id": "sid_ls"}
    m = __import__("backend.boss_chat_monitor", fromlist=["match_conversation_item"]).match_conversation_item
    assert m(item, known)["hr_name"] == "李四"  # sid 优先于名字


def test_match_sid_no_hit_name_fallback():
    """条目 sid 在已知会话里没有 → 不再按名字归并(可能同名不同人),返回 None 由建会话处理。"""
    m = __import__("backend.boss_chat_monitor", fromlist=["match_conversation_item"]).match_conversation_item
    known = [_kc("张三", "sid_zs")]
    item = {"hr_name": "张三", "text": "张三 腾讯 前端", "security_id": "sid_unknown"}
    assert m(item, known) is None


def test_match_no_sid_by_exact_name():
    m = __import__("backend.boss_chat_monitor", fromlist=["match_conversation_item"]).match_conversation_item
    known = [_kc("张三")]
    item = {"hr_name": "张三", "text": "张三 字节 后端", "security_id": ""}
    assert m(item, known)["hr_name"] == "张三"


def test_match_legacy_known_without_sid_item_with_sid():
    """老会话无 sid,条目带 sid 且名字相同 → 命中(后续回填 sid)。"""
    m = __import__("backend.boss_chat_monitor", fromlist=["match_conversation_item"]).match_conversation_item
    known = [_kc("王五")]
    item = {"hr_name": "王五", "text": "王五 美团 测试", "security_id": "sid_ww"}
    assert m(item, known)["hr_name"] == "王五"


def test_match_by_substring_fallback():
    m = __import__("backend.boss_chat_monitor", fromlist=["match_conversation_item"]).match_conversation_item
    known = [_kc("欧阳娜娜")]
    item = {"hr_name": "", "text": "欧阳娜娜 网易 运营", "security_id": ""}
    assert m(item, known)["hr_name"] == "欧阳娜娜"


# ── D2: 孤儿消息兜底扫描 ──


def _seed_stale(hr_name="陈七", minutes_ago=30, **kwargs):
    cid = _make_conv(hr_name, **kwargs)
    st.update_conversation_last_message(cid, "你好，方便聊聊吗", "hr")
    # last_message_at 已是 CURRENT_TIMESTAMP,手动调到 N 分钟前模拟超时
    st.get_db().execute(
        "UPDATE conversations SET last_message_at = datetime('now', ?) WHERE id=?",
        (f"-{minutes_ago} minutes", cid),
    )
    st.get_db().commit()
    return cid


def test_stale_query_finds_unreplied_hr():
    cid = _seed_stale(minutes_ago=30)
    stale = st.get_stale_hr_conversations(10, 5)
    assert [s["id"] for s in stale] == [cid]


def test_stale_query_ignores_recent():
    _seed_stale(minutes_ago=2)  # 2分钟前,未到10分钟窗口
    assert st.get_stale_hr_conversations(10, 5) == []


def test_stale_query_gates():
    # auto_reply 关闭
    cid1 = _seed_stale(hr_name="甲", minutes_ago=30)
    st.get_db().execute("UPDATE conversations SET auto_reply_enabled=0 WHERE id=?", (cid1,))
    # 风险会话
    cid2 = _seed_stale(hr_name="乙", minutes_ago=30)
    st.get_db().execute("UPDATE conversations SET is_dangerous=1 WHERE id=?", (cid2,))
    # 已关闭
    cid3 = _seed_stale(hr_name="丙", minutes_ago=30)
    st.update_conversation_status(cid3, "closed")
    # 我方最后一条(等待HR回复)不算孤儿
    cid4 = _seed_stale(hr_name="丁", minutes_ago=30)
    st.update_conversation_last_message(cid4, "好的谢谢", "me")
    st.get_db().commit()
    assert st.get_stale_hr_conversations(10, 10) == []


def test_stale_query_limit_and_order():
    for i, name in enumerate(["会话一", "会话二", "会话三"]):
        _seed_stale(hr_name=name, minutes_ago=30 + i * 10)
    stale = st.get_stale_hr_conversations(10, 2)
    assert len(stale) == 2
    # 等待最久的(消息最老)优先
    assert stale[0]["hr_name"] == "会话三"
    assert stale[1]["hr_name"] == "会话二"


def test_stale_conv_closed_via_sid_seed():
    """会话关闭后不再被 sweep 找回。"""
    cid = _seed_stale(minutes_ago=60)
    st.update_conversation_status(cid, "closed")
    assert st.get_stale_hr_conversations(10, 5) == []


# ── D3: 三阶段编排与退避 ──


def _make_monitor():
    mod = __import__("backend.boss_chat_monitor", fromlist=["BossChatMonitor"])
    mon = mod.BossChatMonitor.__new__(mod.BossChatMonitor)  # 跳过浏览器初始化
    mon.page = MagicMock()
    return mon


@contextmanager
def patch_pause():
    import backend.boss_chat_monitor as m

    original = m.pause
    m.pause = lambda *a, **k: None
    try:
        yield
    finally:
        m.pause = original


def test_send_failure_bumps_backoff():
    mon = _make_monitor()
    task = {
        "conv_id": 1,
        "matched_conv": {"hr_name": "测试", "is_dangerous": False},
        "hr_name": "测试",
        "hr_message": "在吗",
        "reply": "你好",
        "job_info": {},
    }
    mon.open_conversation_by_name = MagicMock(return_value=True)
    mon.send_message = MagicMock(return_value=False)  # 发送失败
    mon._clear_input_box = MagicMock()

    with patch_pause():
        mon._send_one(task, {"replies_sent": 0})
    fail_key = (1, hash("在吗"))
    assert mon._reply_failures[fail_key]["count"] == 1  # 发送失败计入退避


def test_generate_one_backoff_skips_after_limit():
    mon = _make_monitor()
    mon._reply_failures = {(1, hash("你好")): {"count": 3, "last_ts": time.time()}}
    task = {
        "conv_id": 1,
        "matched_conv": {"hr_name": "测试"},
        "hr_name": "测试",
        "hr_message": "你好",
        "job_info": {},
        "last_me": "",
    }
    st.set_setting("auto_reply_enabled", "true")
    result = mon._generate_one(task)
    assert result["reply"] == ""  # 冷却期内跳过,不调 LLM


def test_generate_one_daily_limit_skips(monkeypatch):
    mon = _make_monitor()
    monkeypatch.setattr("backend.boss_chat_monitor.get_today_auto_reply_count", lambda: 999)
    task = {
        "conv_id": 1,
        "matched_conv": {"hr_name": "测试"},
        "hr_name": "测试",
        "hr_message": "你好",
        "job_info": {},
        "last_me": "",
    }
    st.set_setting("auto_reply_enabled", "true")
    result = mon._generate_one(task)
    assert result["reply"] == ""


def test_run_cycle_scan_failure_returns_empty():
    """_scan_list 失败(导航失败)时返回空结果,不抛异常。"""
    mon = _make_monitor()
    mon._scan_list = MagicMock(return_value=None)

    async def run():
        return await mon.run_chat_monitor_cycle()

    result = asyncio.run(run())
    assert result == {"checked": 0, "new_messages": 0, "replies_sent": 0}


def test_run_cycle_orchestration_phases():
    """三阶段契约:open_and_read → generate_one → send_one 按序执行,
    generate 阶段不碰 page(_generate_one 内部无浏览器调用)。"""
    mon = _make_monitor()
    order = []
    task = {
        "conv_id": 1,
        "matched_conv": {"hr_name": "测试"},
        "hr_name": "测试",
        "hr_message": "你好，看了你的简历",
        "job_info": {},
        "last_me": "",
        "reply": "",
    }
    mon._scan_list = MagicMock(return_value=[{"text": "测试 字节 后端", "hr_name": "测试"}])
    mon._open_and_read = MagicMock(
        side_effect=lambda item, handled, result: order.append("open") or task
    )
    mon._generate_one = MagicMock(
        side_effect=lambda t: order.append("generate") or {**t, "reply": "你好，我在"}
    )
    mon._send_one = MagicMock(
        side_effect=lambda t, r: order.append("send") or r.__setitem__(
            "replies_sent", r.get("replies_sent", 0) + 1
        )
    )
    mon._refresh_after_cycle = MagicMock()

    async def run():
        return await mon.run_chat_monitor_cycle()

    result = asyncio.run(run())
    assert order == ["open", "generate", "send"]
    assert result["new_messages"] == 1
    assert result["replies_sent"] == 1


def test_run_cycle_no_reply_skips_send():
    mon = _make_monitor()
    task = {"conv_id": 1, "hr_name": "测试", "hr_message": "你好", "reply": "", "job_info": {}}
    mon._scan_list = MagicMock(return_value=[{"text": "x", "hr_name": "测试"}])
    mon._open_and_read = MagicMock(return_value=task)
    mon._generate_one = MagicMock(side_effect=lambda t: t)  # 生成失败,reply 为空
    mon._send_one = MagicMock()
    mon._refresh_after_cycle = MagicMock()

    async def run():
        return await mon.run_chat_monitor_cycle()

    result = asyncio.run(run())
    mon._send_one.assert_not_called()
    assert result["replies_sent"] == 0


def test_run_cycle_lock_serializes():
    """并发两个 cycle 经 run_chat_monitor_cycle 的锁串行执行,不重叠。"""
    mon = _make_monitor()
    mon._scan_list = MagicMock(return_value=[])
    mon._refresh_after_cycle = MagicMock()
    active, peaks = [], []

    async def fake_locked():
        active.append(1)
        peaks.append(len(active))
        await asyncio.sleep(0.05)
        active.pop()
        return {"checked": 0, "new_messages": 0, "replies_sent": 0}

    mon._run_cycle_locked = fake_locked

    async def run():
        return await asyncio.gather(
            mon.run_chat_monitor_cycle(), mon.run_chat_monitor_cycle()
        )

    results = asyncio.run(run())
    assert max(peaks) == 1  # 任意时刻只有一个周期在跑
    assert all(r["checked"] == 0 for r in results)


# ── tool_executor hop 契约 ──


def test_tool_executor_uses_run_pw_hop():
    te = __import__("backend.tool_executor", fromlist=["execute_tool"])
    calls = []

    class FakeAutomation:
        def send_resume(self):
            calls.append("method")
            return True

    # 提供 run_pw → 工具先经 hop(记录),再在 hop 内调用实际方法
    ctx = {
        "automation": FakeAutomation(),
        "conversation_id": 1,
        "matched_conv": {},
        "hr_name": "测试",
        "job_info": {},
        "run_pw": lambda fn, *a: calls.append("hop") or fn(),
    }
    result = te.execute_tool("send_resume", {}, ctx)
    assert "成功" in result
    assert calls == ["hop", "method"]  # hop 先于方法调用,顺序证明走了包装器


def test_tool_executor_without_hop_direct_call():
    te = __import__("backend.tool_executor", fromlist=["execute_tool"])
    calls = []

    class FakeAutomation:
        def send_resume(self):
            calls.append(1)
            return True

    ctx = {
        "automation": FakeAutomation(),
        "conversation_id": 1,
        "matched_conv": {},
        "hr_name": "测试",
        "job_info": {},
    }
    result = te.execute_tool("send_resume", {}, ctx)
    assert "成功" in result
    assert calls == [1]


def test_runtime_run_in_pw_rejects_event_loop_thread():
    rt = __import__("backend.runtime", fromlist=["run_in_pw"])

    async def call_in_loop():
        return rt.run_in_pw(lambda: 1)  # 在事件循环线程内同步调用 → 拒绝

    with pytest.raises(RuntimeError):
        asyncio.run(call_in_loop())
