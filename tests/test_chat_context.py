"""AI 对话上下文修复的单元测试。

覆盖:系统通知过滤、历史对齐防重、连续未回复块提取、Agent 上下文注入、
工具事件持久化、滚动摘要触发、interest 解析、问候模板池。

运行: pytest tests/test_chat_context.py -v
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# 必须在导入 backend.state 之前设置,保证测试 DB 隔离
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="boss_chat_test_")
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


# ── 系统通知过滤 ──


def test_is_system_notification():
    assert st.is_system_notification("该Boss已查看了你的简历") is True
    assert st.is_system_notification("BOSS安全提示：请勿轻信") is True
    assert st.is_system_notification("你好，我们看了你的简历觉得很匹配") is False
    assert st.is_system_notification("") is False
    # 超过80字的长文本即使是系统前缀也不是通知（保守策略）
    assert st.is_system_notification("系统消息" + "x" * 100) is False


def test_purge_system_notifications():
    conv_id = st.get_or_create_conversation(None, "张三", "某科技", "AI工程师")
    st.add_message(conv_id, "hr", "该Boss已查看了你的简历")
    st.add_message(conv_id, "hr", "你好，看了你的简历")
    st.add_message(conv_id, "me", "您好！")
    st.add_message(conv_id, "hr", "BOSS安全提示：谨防诈骗")
    deleted = st.purge_system_notifications()
    assert deleted == 2
    msgs = st.get_all_messages(conv_id)
    contents = [m["content"] for m in msgs]
    assert contents == ["你好，看了你的简历", "您好！"]
    # 幂等
    assert st.purge_system_notifications() == 0


# ── 历史对齐防重 ──


def test_replace_normal_overlap_appends_new_only():
    conv_id = st.get_or_create_conversation(None, "张三", "某科技", "AI工程师")
    st.replace_conversation_messages(
        conv_id, [{"sender": "hr", "content": "你好"}, {"sender": "me", "content": "您好！"}]
    )
    st.replace_conversation_messages(
        conv_id,
        [
            {"sender": "hr", "content": "你好"},
            {"sender": "me", "content": "您好！"},
            {"sender": "hr", "content": "方便发简历吗"},
        ],
    )
    msgs = st.get_all_messages(conv_id)
    assert len(msgs) == 3
    assert msgs[-1]["content"] == "方便发简历吗"


def test_replace_set_dedup_when_window_mismatch():
    """滑动窗口失配(如历史中有系统通知被过滤)时,集合去重防止整段重复追加。"""
    conv_id = st.get_or_create_conversation(None, "李四", "某网络", "后端")
    # 模拟旧数据:中间夹了一条系统通知
    st.replace_conversation_messages(
        conv_id,
        [
            {"sender": "hr", "content": "你好"},
            {"sender": "hr", "content": "BOSS安全提示：谨防诈骗"},
            {"sender": "hr", "content": "看了你简历，聊聊？"},
        ],
    )
    # 新一轮读取:系统通知已被前置过滤掉
    st.replace_conversation_messages(
        conv_id,
        [
            {"sender": "hr", "content": "你好"},
            {"sender": "hr", "content": "看了你简历，聊聊？"},
            {"sender": "hr", "content": "还在吗"},
        ],
    )
    msgs = st.get_all_messages(conv_id)
    contents = [m["content"] for m in msgs]
    # 不应出现重复的"你好"/"看了你简历"，只追加真正的新消息"还在吗"
    assert contents.count("你好") == 1
    assert contents.count("看了你简历，聊聊？") == 1
    assert contents[-1] == "还在吗"


def test_replace_empty_db_appends_all():
    conv_id = st.get_or_create_conversation(None, "王五", "某教育", "前端")
    st.replace_conversation_messages(
        conv_id, [{"sender": "hr", "content": "你好"}, {"sender": "me", "content": "您好"}]
    )
    assert len(st.get_all_messages(conv_id)) == 2


# ── 连续未回复块 ──


def test_extract_unreplied_block_multiple_messages():
    from backend.boss_chat_monitor import extract_unreplied_block

    msgs = [
        {"sender": "hr", "content": "你好"},
        {"sender": "me", "content": "您好！"},
        {"sender": "hr", "content": "看了你简历"},
        {"sender": "hr", "content": "我们是做AI Agent的"},
        {"sender": "hr", "content": "方便聊聊吗"},
    ]
    assert extract_unreplied_block(msgs) == "看了你简历\n我们是做AI Agent的\n方便聊聊吗"


def test_extract_unreplied_block_all_replied():
    from backend.boss_chat_monitor import extract_unreplied_block

    msgs = [
        {"sender": "hr", "content": "你好"},
        {"sender": "me", "content": "您好！"},
    ]
    assert extract_unreplied_block(msgs) is None


def test_extract_unreplied_block_skips_system_notifications():
    from backend.boss_chat_monitor import extract_unreplied_block

    msgs = [
        {"sender": "me", "content": "您好！"},
        {"sender": "hr", "content": "该Boss已查看了你的简历"},
        {"sender": "hr", "content": "聊聊？"},
    ]
    assert extract_unreplied_block(msgs) == "聊聊？"


def test_extract_unreplied_block_no_me_messages():
    from backend.boss_chat_monitor import extract_unreplied_block

    msgs = [{"sender": "hr", "content": "你好"}]
    assert extract_unreplied_block(msgs) == "你好"


# ── Agent 上下文 ──


def _setup_conversation_with_msgs():
    conv_id = st.get_or_create_conversation(None, "赵六", "某智能", "AI应用工程师")
    st.add_message(conv_id, "hr", "你好，看了你的简历")
    st.add_message(conv_id, "me", "您好！谢谢关注")
    st.add_message(conv_id, "hr", "方便发下简历吗")
    return conv_id


def test_build_agent_context_injects_state_and_style():
    from backend.agent_loop import build_agent_context

    conv_id = _setup_conversation_with_msgs()
    ctx = {
        "matched_conv": {
            "interest_level": "high",
            "hr_wechat": "wxid_abc123",
            "resume_sent": 1,
            "phone_shared": 0,
        },
        "job_info": {"title": "AI工程师", "company": "某智能", "description": "负责Agent开发"},
        "style_hint": "语气轻松友好",
    }
    text = build_agent_context(conv_id, "方便发下简历吗", ctx)
    assert "语气轻松友好" in text
    assert "已评估HR兴趣度: high" in text
    assert "微信已交换" in text
    assert "简历已发送" in text
    assert "电话已交换" not in text
    assert "JD摘要" in text


def test_build_agent_context_marks_missing_job_info():
    from backend.agent_loop import build_agent_context

    conv_id = _setup_conversation_with_msgs()
    ctx = {"matched_conv": {}, "job_info": {"title": "", "company": "", "description": ""}}
    text = build_agent_context(conv_id, "聊聊？", ctx)
    assert "岗位信息暂缺" in text


def test_build_agent_context_no_duplication_of_hr_block():
    from backend.agent_loop import build_agent_context

    conv_id = _setup_conversation_with_msgs()
    hr_msg = "方便发下简历吗"
    ctx = {"matched_conv": {}, "job_info": {"title": "AI工程师", "company": "某智能", "description": ""}}
    text = build_agent_context(conv_id, hr_msg, ctx)
    # 待回复块只出现在「HR刚刚说」段一次,历史展示到「我最后一条消息」为止
    assert text.count(hr_msg) == 1
    assert "您好！谢谢关注" in text  # 我方最后回复仍在历史里


def test_build_agent_context_injects_tool_events():
    from backend.agent_loop import build_agent_context

    conv_id = _setup_conversation_with_msgs()
    st.record_tool_event(conv_id, "send_resume", "简历发送成功")
    st.record_tool_event(conv_id, "share_wechat", "微信名片分享失败")
    ctx = {"matched_conv": {}, "job_info": {"title": "AI工程师", "company": "某智能", "description": ""}}
    text = build_agent_context(conv_id, "聊聊？", ctx)
    assert "最近工具动作" in text
    assert "send_resume" in text
    assert "简历发送成功" in text


def test_build_agent_context_injects_summary():
    from backend.agent_loop import build_agent_context

    conv_id = _setup_conversation_with_msgs()
    st.update_conversation_summary(conv_id, "已与HR约定周三下午面试", 1)
    ctx = {"matched_conv": {}, "job_info": {"title": "AI工程师", "company": "某智能", "description": ""}}
    text = build_agent_context(conv_id, "聊聊？", ctx)
    assert "[更早对话摘要]" in text
    assert "已与HR约定周三下午面试" in text
    # 摘要覆盖到 id=1,其后的消息仍然完整展示
    assert "您好！谢谢关注" in text


# ── 工具事件 / 岗位回填 ──


def test_tool_events_roundtrip_order_and_limit():
    conv_id = st.get_or_create_conversation(None, "钱七", "某云", "SRE")
    for i in range(7):
        st.record_tool_event(conv_id, "send_resume", f"第{i}次")
    events = st.get_recent_tool_events(conv_id, limit=5)
    assert len(events) == 5
    assert events[0]["result_summary"] == "第6次"  # 倒序,最新在前
    assert events[-1]["result_summary"] == "第2次"


def test_get_application_by_hr_name():
    from backend.state import add_application

    add_application(
        {
            "title": "AI Agent开发",
            "company": "某智能科技",
            "url": "https://zhipin.com/job/1001",
            "hr_name": "张经理",
            "description": "负责多Agent系统",
        }
    )
    app = st.get_application_by_hr_name("张经理")
    assert app is not None
    assert app["job_title"] == "AI Agent开发"
    assert st.get_application_by_hr_name("不存在的HR") is None
    assert st.get_application_by_hr_name("") is None


# ── 摘要触发 ──


def test_maybe_update_summary_skips_short_conversations(monkeypatch):
    from backend import agent_loop

    conv_id = _setup_conversation_with_msgs()
    called = MagicMock()
    monkeypatch.setattr("backend.interview.llm_client.get_llm", lambda **kw: called)
    agent_loop._maybe_update_summary(conv_id)
    called.assert_not_called()


def test_maybe_update_summary_triggers_and_persists(monkeypatch):
    from backend import agent_loop

    conv_id = st.get_or_create_conversation(None, "孙八", "某大厂", "算法")
    for i in range(35):
        st.add_message(conv_id, "hr" if i % 2 == 0 else "me", f"消息{i}")
    llm = MagicMock()
    llm.invoke = MagicMock(return_value=MagicMock(content="双方聊了薪资范围15-25K，约定下周面试"))
    monkeypatch.setattr("backend.interview.llm_client.get_llm", lambda **kw: llm)
    agent_loop._maybe_update_summary(conv_id)
    summary, upto_id = st.get_conversation_summary(conv_id)
    assert "15-25K" in summary
    assert upto_id > 0
    llm.invoke.assert_called_once()


def test_maybe_update_summary_silent_failure(monkeypatch):
    from backend import agent_loop

    conv_id = st.get_or_create_conversation(None, "周九", "某厂", "测试")
    for i in range(35):
        st.add_message(conv_id, "hr" if i % 2 == 0 else "me", f"消息{i}")

    def boom(**kw):
        raise RuntimeError("LLM 不可用")

    monkeypatch.setattr("backend.interview.llm_client.get_llm", boom)
    agent_loop._maybe_update_summary(conv_id)  # 不应抛异常
    summary, _ = st.get_conversation_summary(conv_id)
    assert summary == ""


# ── interest 解析 ──


def test_parse_final_reply_variants():
    from backend.agent_loop import _parse_final_reply

    assert _parse_final_reply("好的，明天见 [INTEREST: high]") == ("好的，明天见", "high")
    assert _parse_final_reply("好的[INTEREST:high]") == ("好的", "high")
    assert _parse_final_reply("好的[INTEREST：high]") == ("好的", "high")
    assert _parse_final_reply("没有标记") == ("没有标记", "medium")
    assert _parse_final_reply("") == ("", "medium")


# ── 问候模板池 ──


def test_quick_greeting_variety():
    from backend.replier import GREETING_TEMPLATES, _quick_greeting

    assert len(GREETING_TEMPLATES) >= 8
    job = {"title": "AI工程师", "company": "某智能"}
    seen = {_quick_greeting(job) for _ in range(30)}
    assert len(seen) >= 2  # 30 次抽样必然出现不同模板
    # 模板变量正确填充
    for g in seen:
        assert "{" not in g and "}" not in g


def test_quick_greeting_fills_placeholders():
    from backend.replier import _quick_greeting

    g = _quick_greeting({"title": "AI工程师", "company": "某智能"})
    # 30次抽样中至少一条同时包含岗位与公司（含两种变量的模板占多数）
    gs = [_quick_greeting({"title": "AI工程师", "company": "某智能"}) for _ in range(30)]
    assert any("AI工程师" in x for x in gs)
