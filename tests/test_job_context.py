"""岗位上下文提取链路单元测试。

覆盖:conversations/interviews 的 job_url 列迁移、update_conversation_job_context 回写、
validate_and_add_interview / add_conflicted_interview 的 job_url 落库、
interview_gate 的 get_job_url 回调时序(确认为邀约才调用)。

运行: pytest tests/test_job_context.py -v
"""

import os
import sys
import tempfile
from pathlib import Path

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="boss_jobctx_test_")
os.environ["BOSS_DATA_DIR"] = _TEST_DATA_DIR

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import backend.state as st

st.init_db()

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    db = st.get_db()
    yield
    db.rollback()


from backend.interview_gate import handle_interview_invite  # noqa: E402
from backend.state import (  # noqa: E402
    add_conflicted_interview,
    get_conversation,
    get_or_create_conversation,
    update_conversation_job_context,
    validate_and_add_interview,
)


def _mk_conv(name="测试HR"):
    return get_or_create_conversation(None, name, "", "", "")


class TestJobContextMigration:
    def test_columns_exist(self):
        db = st.get_db()
        for table in ("conversations", "interviews", "conflicted_interviews"):
            cols = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            assert "job_url" in cols, f"{table} 缺少 job_url 列"


class TestUpdateConversationJobContext:
    def test_write_and_overwrite(self):
        conv_id = _mk_conv("上下文HR")
        update_conversation_job_context(conv_id, hr_company="链家公司", job_title="置业顾问")
        conv = get_conversation(conv_id)
        assert conv["hr_company"] == "链家公司"
        assert conv["job_title"] == "置业顾问"

        # 非空才覆盖:传空串不冲掉已有值
        update_conversation_job_context(conv_id, hr_company="", job_title="店长")
        conv = get_conversation(conv_id)
        assert conv["hr_company"] == "链家公司"
        assert conv["job_title"] == "店长"

    def test_job_url_write(self):
        conv_id = _mk_conv("链接HR")
        update_conversation_job_context(conv_id, job_url="https://www.zhipin.com/job_detail/abc.html")
        assert get_conversation(conv_id)["job_url"] == "https://www.zhipin.com/job_detail/abc.html"


class TestInterviewJobUrl:
    @pytest.fixture(autouse=True)
    def clear_interviews(self):
        # 避免其他用例写入的排期造成时间冲突
        db = st.get_db()
        db.execute("DELETE FROM interviews")
        db.commit()
        yield

    def test_validate_and_add_uses_conversation_url(self):
        conv_id = _mk_conv("排期HR")
        update_conversation_job_context(conv_id, hr_company="盒马", job_title="拣货员", job_url="https://www.zhipin.com/job_detail/box.html")
        from datetime import datetime, timedelta

        start = (datetime.now() + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        ok, msg = validate_and_add_interview(conv_id, "offline", start.strftime("%Y-%m-%d %H:%M"), 60, "测试")
        assert ok, msg
        row = st.get_db().execute(
            "SELECT company, job_title, job_url FROM interviews WHERE conversation_id=?", (str(conv_id),)
        ).fetchone()
        assert row["company"] == "盒马"
        assert row["job_title"] == "拣货员"
        assert row["job_url"] == "https://www.zhipin.com/job_detail/box.html"

    def test_explicit_url_overrides(self):
        conv_id = _mk_conv("显式HR")
        from datetime import datetime, timedelta

        start = (datetime.now() + timedelta(days=3)).replace(hour=15, minute=0, second=0, microsecond=0)
        ok, msg = validate_and_add_interview(
            conv_id, "online", start.strftime("%Y-%m-%d %H:%M"), 60, "测试", job_url="https://www.zhipin.com/job_detail/explicit.html"
        )
        assert ok, msg
        row = st.get_db().execute(
            "SELECT job_url FROM interviews WHERE conversation_id=?", (str(conv_id),)
        ).fetchone()
        assert row["job_url"] == "https://www.zhipin.com/job_detail/explicit.html"

    def test_conflicted_interview_saves_url(self):
        conv_id = _mk_conv("冲突HR")
        # 先占掉一个当天下午线下
        from datetime import datetime, timedelta

        day = datetime.now() + timedelta(days=4)
        start1 = day.replace(hour=15, minute=0, second=0, microsecond=0)
        validate_and_add_interview(conv_id, "offline", start1.strftime("%Y-%m-%d %H:%M"), 60, "占用")
        cid = add_conflicted_interview(
            conv_id, "offline", (day.replace(hour=16, minute=0)).strftime("%Y-%m-%d %H:%M"),
            60, "时间冲突", hr_message="来面试吧", job_url="https://www.zhipin.com/job_detail/c.html",
        )
        row = st.get_db().execute("SELECT job_url FROM conflicted_interviews WHERE id=?", (cid,)).fetchone()
        assert row["job_url"] == "https://www.zhipin.com/job_detail/c.html"


class TestGateJobUrlCallback:
    def test_callback_not_called_for_non_invite(self):
        conv_id = _mk_conv("普通消息HR")
        called = []

        def _cb():
            called.append(1)
            return "https://x/job_detail/1.html"

        handled = handle_interview_invite(conv_id, "你好，考虑新机会吗？", {"hr_name": "测试"}, {}, get_job_url=_cb)
        assert handled is None  # 非邀约 → None，走正常聊天链路
        assert called == []

    def test_callback_called_for_invite(self):
        # 用真实未来时间构造邀约消息,LLM 检测依赖外部 API → 不可用时闸门放行,回调也不应调用
        conv_id = _mk_conv("邀约HR")
        called = []

        def _cb():
            called.append(1)
            return "https://x/job_detail/2.html"

        msg = "明天下午3点来我们公司面试"
        handled = handle_interview_invite(conv_id, msg, {"hr_name": "邀约HR"}, {}, get_job_url=_cb)
        if handled is not None:  # LLM 可用时:是邀约 → 回调必须被调用且URL落库
            assert called == [1]
            assert get_conversation(conv_id)["job_url"] == "https://x/job_detail/2.html"
        else:  # 测试环境无 LLM → 闸门放行,回调不应被调用
            assert called == []
