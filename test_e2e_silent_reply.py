# -*- coding: utf-8 -*-
"""
端到端静默验证 —— 走 monitor._generate_one 真实链路(LLM 判定真实调用):

A 组(邀约,应静默): reply 必须为空 + generate_reply 一次都不被调
                    (链路上 reply 为空则 _send_one 永不触发,HR 收不到任何消息)
B 组(闲聊对照,应放行): generate_reply 被正常调用
C 组: 排期入库/冲突表登记校验
"""
import os
import sys
from datetime import datetime, timedelta

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "backend"))

from backend.state import init_db, get_db, set_setting

init_db()
set_setting("interview_silent_mode", "true")
set_setting("auto_reply_enabled", "true")

import backend.boss_chat_monitor as bcm
from backend.boss_chat_monitor import BossChatMonitor
from backend.interview.llm_client import get_llm  # noqa: 提前确认 LLM 可用

# mock: 今日回复计数清零,避免上限干扰
bcm.get_today_auto_reply_count = lambda: 0

# spy: 记录 generate_reply 是否被调(= 走了正常回复链路)
import backend.replier as replier_mod

gen_calls = []
def _spy_generate_reply(conv_id, hr_message, *a, **k):
    gen_calls.append(hr_message)
    return "这是AI的正常聊天回复", "medium", {}
replier_mod.generate_reply = _spy_generate_reply

# 跳过浏览器初始化,只测纯 LLM 链路
m = BossChatMonitor.__new__(BossChatMonitor)
m._reply_failures = {}

CONV_ID = 99002
now = datetime.now()
tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
day_after = (now + timedelta(days=2)).strftime("%Y-%m-%d")
next_monday = (now + timedelta(days=(7 - now.weekday()) % 7 or 7)).strftime("%Y-%m-%d")
next_wed = (now + timedelta(days=(2 - now.weekday()) % 7 or 7)).strftime("%Y-%m-%d")

matched_conv = {"hr_name": "端到端HR", "hr_company": "端到端公司"}
job_info = {"title": "店长助理", "company": "端到端公司", "description": "餐饮门店管理"}

# 独立日期: 与明天/后天错开,避免脚本自身日期算错导致误判冲突
d_plus3 = (now + timedelta(days=3)).strftime("%Y-%m-%d")
d_plus4 = (now + timedelta(days=4)).strftime("%Y-%m-%d")


def make_task(msg):
    return {
        "conv_id": CONV_ID, "matched_conv": matched_conv, "hr_name": "端到端HR",
        "hr_message": msg, "job_info": job_info, "last_me": "",
    }


def run_one(msg):
    """跑一条消息,返回 (reply, generate_reply是否被调)"""
    before = len(gen_calls)
    task = m._generate_one(make_task(msg))
    return task.get("reply", ""), len(gen_calls) > before


def counts():
    db = get_db()
    n = db.execute("SELECT COUNT(*) c FROM interviews WHERE conversation_id=?", (CONV_ID,)).fetchone()["c"]
    c = db.execute("SELECT COUNT(*) c FROM conflicted_interviews WHERE conversation_id=?", (CONV_ID,)).fetchone()["c"]
    return n, c


def clear():
    db = get_db()
    db.execute("DELETE FROM interviews WHERE conversation_id=?", (CONV_ID,))
    db.execute("DELETE FROM conflicted_interviews WHERE conversation_id=?", (CONV_ID,))
    db.commit()


passed, failed = 0, []


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}  {detail}")


clear()
print("=" * 60)
print("A组: 面试邀约(8个话术变体) → 必须全程零回复")
print("=" * 60)

invites = [
    (f"明天下午2点方便来公司线下面试吗？", f"{tomorrow} 14:00"),
    (f"明天上午10点半来面试一下吧", f"{tomorrow} 10:30"),
    (f"后天下午3点我们视频面试", f"{day_after} 15:00"),
    (f"9月10号上午11点来公司聊聊", "2026-09-10 11:00"),
    (f"{d_plus3}上午9点初试，记得带上简历", f"{d_plus3} 09:00"),
    (f"{d_plus4}下午4点电话面试方便吗", f"{d_plus4} 16:00"),
    (f"明天14:30可以过来复试吗", None),  # 与第一场同天下午 → 冲突
    (f"那就明天下午2点，不见不散", None),  # 同天下午 → 冲突
    (f"简历看过了很合适，{d_plus4}上午10点半来面试吧", None),  # 9月10号上午已有线下 → 冲突
    (f"{d_plus3}下午2点半线上面聊一下", f"{d_plus3} 14:30"),
]

for i, (msg, expect_time) in enumerate(invites, 1):
    n_before, c_before = counts()
    reply, gen_called = run_one(msg)
    n_after, c_after = counts()
    tag = f"邀约{i}"
    check(f"{tag} 零回复(reply为空)", reply == "", f"实际回复: {reply[:60]!r}")
    check(f"{tag} 未走聊天链路", not gen_called, "generate_reply 被调用了!")
    if expect_time:
        check(f"{tag} 排期+1", n_after == n_before + 1, f"{n_before}->{n_after}")
        if n_after > n_before:
            row = get_db().execute(
                "SELECT start_time FROM interviews WHERE conversation_id=? ORDER BY id DESC LIMIT 1", (CONV_ID,)
            ).fetchone()
            check(f"{tag} 时间={expect_time}", row["start_time"].startswith(expect_time), f"实际 {row['start_time']}")
    else:
        check(f"{tag} 冲突表+1(排期不加)", c_after == c_before + 1 and n_after == n_before,
              f"排期{n_before}->{n_after}, 冲突{c_before}->{c_after}")
    print()

print("=" * 60)
print("B组: 闲聊对照(3条) → 必须正常走聊天链路")
print("=" * 60)
chats = [
    "你好，看了你的简历想聊一下，你目前还在找工作吗？",
    "这个岗位需要经常早晚班轮换，你能接受吗？",
    "你之前门店的日营业额大概做到多少？",
]
for i, msg in enumerate(chats, 1):
    reply, gen_called = run_one(msg)
    check(f"闲聊{i} 正常生成回复", gen_called and reply == "这是AI的正常聊天回复",
          f"gen_called={gen_called}, reply={reply[:30]!r}")

print()
print("=" * 60)
print("C组: 数据终态")
print("=" * 60)
n, c = counts()
print(f"  排期表: {n} 条 | 冲突表: {c} 条 | 聊天链路被调: {len(gen_calls)} 次(应=3)")
check("排期共 7 条", n == 7, f"实际 {n}")
check("冲突共 3 条", c == 3, f"实际 {c}")
check("聊天链路仅闲聊 3 次", len(gen_calls) == 3, f"实际 {len(gen_calls)}")

clear()
print(f"\n结果: {passed} 通过, {len(failed)} 失败 {failed if failed else ''}")
sys.exit(1 if failed else 0)
