"""虚构动作防线（fabrication guard）单元测试。

背景：AI 只能通过BOSS平台内工具（发简历/名片/电话）行动，但曾大量生成
"我这就加""刚申请了""点了同意"等微信侧/电话侧虚构动作话术，导致 HR
反复等待不会发生的动作（见 9/11 会话1071/1140/1195）。

覆盖：模式命中真实案例、合法话术不误伤、run_agent 出站防线（重生成/丢弃/直通）。

运行: pytest tests/test_fabrication_guard.py -v
"""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

# 必须在导入 backend.state 之前设置,保证测试 DB 隔离
_TEST_DATA_DIR = tempfile.mkdtemp(prefix="boss_fabrication_test_")
os.environ["BOSS_DATA_DIR"] = _TEST_DATA_DIR

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import backend.state as st

st.init_db()

from backend.agent_loop import (
    NO_REPLY_MARK,
    has_fabricated_action_claim,
    run_agent,
)


class TestFabricatedPatterns:
    def test_real_log_cases_caught(self):
        """9/11 日志里实际出现过的虚构动作话术必须全部命中。"""
        cases = [
            "可能我微信设置了防打扰，您发下您的微信，我来加您。",
            "被屏蔽了，我直接加您上面留的133手机号。",
            "好的，我这就加。",
            "刚申请了，您看下微信新的朋友。",
            "点了同意，您刷新看下。",
            "好的，我现在加。",
            "看到微信号了，这就加你。",
            "好，我重新加一下。",
            "不好意思，刚才手滑按掉了。",
            "方便发下微信号吗？我直接加您。",
            "微信我通过一下。",
            "行，您微信号多少？我加您。",
            "好的，我这就去加。",
            "我打给您，您注意接听。",
            "电话我没接到，我回拨过去。",
        ]
        for text in cases:
            assert has_fabricated_action_claim(text), f"漏检: {text}"

    def test_legit_replies_pass(self):
        """合法话术（平台内动作/请对方操作/真人代加）不得误伤。"""
        legit = [
            "好的，名片发您了。",
            "好的，名片发过去了，加上聊。",
            "电话发您了，随时方便沟通。",
            "方便加个微信吗？",
            "您把微信号发我，我让家里这边加您",
            "我过去很方便，您把具体地址发我一下。",
            "我愿意加入贵司。",
            "分拣的排班时间和薪资构成具体是怎样的？",
            "我对理货员比较感兴趣，之前做过门店盘点和库存管理。",
            "骑手暂时不考虑，我主要在看门店运营相关的岗位。",
            "简历已经发了，您看一下。",
            "电话名片发您了，您方便的时候联系我。",
        ]
        for text in legit:
            assert has_fabricated_action_claim(text) is None, f"误伤: {text}"

    def test_empty_and_none(self):
        assert has_fabricated_action_claim("") is None
        assert has_fabricated_action_claim(None) is None


def _patch_llm(monkeypatch, first_reply, corrected_reply):
    """把 run_agent 用到的两个 LLM 入口替换为可控的假对象。"""
    import backend.interview.llm_client as llm_client

    first_resp = SimpleNamespace(content=first_reply, tool_calls=[])
    llm_with_tools = MagicMock()
    llm_with_tools.invoke.return_value = first_resp

    corrected_resp = SimpleNamespace(content=corrected_reply)
    plain_llm = MagicMock()
    plain_llm.invoke.return_value = corrected_resp

    monkeypatch.setattr(llm_client, "get_llm_with_tools", lambda *a, **k: llm_with_tools)
    monkeypatch.setattr(llm_client, "get_llm", lambda *a, **k: plain_llm)
    return plain_llm


class TestRunAgentGuard:
    def _ctx(self):
        return {"matched_conv": {}, "job_info": {}, "conversation_id": 1, "hr_name": "测试HR"}

    def test_fabricated_reply_regenerated(self, monkeypatch):
        """虚构动作回复触发纠正重生成，采用纠正后的回复。"""
        plain_llm = _patch_llm(monkeypatch, "好的，我这就加。", "名片发您了，您看一下。")
        reply, interest = run_agent(1, "你加我微信吧", self._ctx())
        assert reply == "名片发您了，您看一下。"
        assert interest == "medium"
        plain_llm.invoke.assert_called_once()

    def test_fabricated_reply_dropped_if_repeat(self, monkeypatch):
        """纠正重生成后仍然虚构动作 → 丢弃（空串计入退避）。"""
        _patch_llm(monkeypatch, "好的，我这就加。", "好，我马上加您。")
        reply, _ = run_agent(1, "你加我微信吧", self._ctx())
        assert reply == ""

    def test_clean_reply_passthrough(self, monkeypatch):
        """正常回复不触发防线，也不调用纠正 LLM。"""
        plain_llm = _patch_llm(monkeypatch, "好的，名片发您了。", "unused")
        reply, _ = run_agent(1, "你加我微信吧", self._ctx())
        assert reply == "好的，名片发您了。"
        plain_llm.invoke.assert_not_called()

    def test_no_reply_passthrough(self, monkeypatch):
        """[NO_REPLY] 不经过防线直接透传。"""
        _patch_llm(monkeypatch, NO_REPLY_MARK, "unused")
        reply, _ = run_agent(1, "祝你好运", self._ctx())
        assert reply == NO_REPLY_MARK
