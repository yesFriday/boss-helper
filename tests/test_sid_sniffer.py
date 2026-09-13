"""securityId 旁听方案单元测试。

覆盖:好友身份记录合并(去重/同名保留多条)、列表条目 sid 解析
(唯一名字直接用/同名靠最后消息预览关联/无法区分返回空)。

运行: pytest tests/test_sid_sniffer.py -v
"""

import os
import sys
import tempfile
from pathlib import Path

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="boss_sid_test_")
os.environ["BOSS_DATA_DIR"] = _TEST_DATA_DIR

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import backend.state as st

st.init_db()

from backend.boss_chat_monitor import merge_friend_records, resolve_item_sid  # noqa: E402


class TestMergeFriendRecords:
    def test_merge_basic(self):
        store = {}
        n = merge_friend_records(
            store,
            [
                {"name": "张女士", "securityId": "AAA", "lastMsg": "考虑新机会吗"},
                {"name": "郭刚", "securityId": "BBB", "lastMsg": "来面试吧"},
            ],
        )
        assert n == 2
        assert store["张女士"] == [{"sid": "AAA", "last_msg": "考虑新机会吗"}]

    def test_dedup_same_sid(self):
        store = {}
        merge_friend_records(store, [{"name": "张女士", "securityId": "AAA", "lastMsg": "hi"}])
        n = merge_friend_records(store, [{"name": "张女士", "securityId": "AAA", "lastMsg": "hi"}])
        assert n == 0
        assert len(store["张女士"]) == 1

    def test_same_name_two_people(self):
        store = {}
        merge_friend_records(
            store,
            [
                {"name": "张女士", "securityId": "AAA", "lastMsg": "京东客服考虑吗"},
                {"name": "张女士", "securityId": "BBB", "lastMsg": "理货员考虑吗"},
            ],
        )
        assert len(store["张女士"]) == 2

    def test_alternative_name_fields(self):
        store = {}
        merge_friend_records(
            store,
            [
                {"bossName": "李先生", "securityId": "CCC"},
                {"realName": "王女士", "securityId": "DDD"},
            ],
        )
        assert store["李先生"][0]["sid"] == "CCC"
        assert store["王女士"][0]["sid"] == "DDD"

    def test_skip_invalid(self):
        store = {}
        assert merge_friend_records(store, [{"name": "", "securityId": "X"}, {"name": "Y", "securityId": ""}, None]) == 0
        assert store == {}


class TestResolveItemSid:
    def test_unique_name(self):
        records = {"郭刚": [{"sid": "BBB", "last_msg": "来面试吧"}]}
        assert resolve_item_sid({"hr_name": "郭刚", "text": "郭刚\n丹鸟速递\n来面试吧"}, records) == "BBB"

    def test_same_name_resolved_by_last_msg(self):
        records = {
            "张女士": [
                {"sid": "AAA", "last_msg": "京东客服考虑吗"},
                {"sid": "BBB", "last_msg": "理货员考虑吗"},
            ]
        }
        item = {"hr_name": "张女士", "text": "张女士 朴朴超市 理货员考虑吗 08:51"}
        assert resolve_item_sid(item, records) == "BBB"
        item2 = {"hr_name": "张女士", "text": "张女士 京东 客服 京东客服考虑吗 09:00"}
        assert resolve_item_sid(item2, records) == "AAA"

    def test_same_name_ambiguous_returns_empty(self):
        records = {
            "张女士": [
                {"sid": "AAA", "last_msg": "京东客服考虑吗"},
                {"sid": "BBB", "last_msg": "理货员考虑吗"},
            ]
        }
        # 预览消息和两条记录都对不上 → 宁可不给 sid(退回名字匹配)也不错绑
        assert resolve_item_sid({"hr_name": "张女士", "text": "张女士 在吗"}, records) == ""

    def test_unknown_name(self):
        assert resolve_item_sid({"hr_name": "陌生人", "text": ""}, {"张女士": [{"sid": "A", "last_msg": "x"}]}) == ""

    def test_empty_inputs(self):
        assert resolve_item_sid({}, {}) == ""
