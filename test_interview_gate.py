# -*- coding: utf-8 -*-
"""面试邀约静默闸门离线测试 —— 5 用例:

1. 具体时间邀约        → 静默(handle=True)  + 写入排期
2. 冲突时间邀约        → 静默(handle=True)  + 不写入(冲突跳过)
3. 重复邀约(同会话同时间) → 静默(handle=True) + 不重复入库
4. 模糊面试意向(无具体时间)→ 放行(handle=False) 走正常聊天
5. 非面试闲聊           → 放行(handle=False) 走正常聊天

另验证: interview_silent_mode=false 时全部放行。
"""
import os
import sys
from datetime import datetime, timedelta

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "backend"))

from backend.state import get_db, init_db

init_db()

from backend.interview_gate import handle_interview_invite

CONV_ID = 99001  # 临时测试会话 ID(不污染真实数据)
now = datetime.now()
tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
day_after = (now + timedelta(days=2)).strftime("%Y-%m-%d")

matched_conv = {"hr_name": "测试HR", "hr_company": "测试公司"}
job_info = {"title": "店长助理", "company": "测试公司", "description": ""}


def count_interviews() -> int:
    row = get_db().execute(
        "SELECT COUNT(*) AS c FROM interviews WHERE conversation_id=?", (CONV_ID,)
    ).fetchone()
    return row["c"]


def count_conflicts() -> int:
    row = get_db().execute(
        "SELECT COUNT(*) AS c FROM conflicted_interviews WHERE conversation_id=?", (CONV_ID,)
    ).fetchone()
    return row["c"]


def clear():
    get_db().execute("DELETE FROM interviews WHERE conversation_id=?", (CONV_ID,))
    get_db().execute("DELETE FROM conflicted_interviews WHERE conversation_id=?", (CONV_ID,))
    get_db().commit()


passed, failed = 0, []


def check(name: str, cond: bool, detail: str = ""):
    global passed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}  {detail}")


print("=== 用例 1: 具体时间邀约 → 静默 + 入库 ===")
clear()
handled = handle_interview_invite(CONV_ID, f"明天下午2点方便来公司线下面试吗？地址是科技园A座", matched_conv, job_info)
check("返回 True(静默)", handled is True)
check("排期已写入 1 条", count_interviews() == 1, f"实际 {count_interviews()} 条")
row = get_db().execute("SELECT start_time, interview_type FROM interviews WHERE conversation_id=?", (CONV_ID,)).fetchone()
check(f"时间正确 {tomorrow} 14:00 offline", row and row["start_time"].startswith(f"{tomorrow} 14:00") and row["interview_type"] == "offline",
      f"实际 {dict(row) if row else '无'}")

print("=== 用例 2: 冲突时间邀约(同天同时段) → 静默 + 不重复写入 + 冲突表留档 ===")
before = count_interviews()
conflicts_before = count_conflicts()
handled = handle_interview_invite(CONV_ID, f"那明天下午2点过来聊聊吧", matched_conv, job_info)
check("返回 True(静默)", handled is True)
check("未新增排期(同会话同时间不重复)", count_interviews() == before, f"实际 {count_interviews()} 条")
check("冲突表已登记", count_conflicts() == conflicts_before + 1, f"实际 {count_conflicts()} 条")
row = get_db().execute(
    "SELECT conflict_reason, hr_message FROM conflicted_interviews WHERE conversation_id=? ORDER BY id DESC LIMIT 1", (CONV_ID,)
).fetchone()
check("冲突原因与HR原话已存", row and "同半天" in (row["conflict_reason"] or "") and "明天下午2点" in (row["hr_message"] or ""),
      f"实际 {dict(row) if row else '无'}")

print("=== 用例 3: 模糊面试意向(无具体时间) → 放行 ===")
handled = handle_interview_invite(CONV_ID, "这周找时间来面谈一下吧，你哪天方便？", matched_conv, job_info)
check("返回 False(放行走正常聊天)", handled is False)

print("=== 用例 4: 非面试闲聊 → 放行 ===")
handled = handle_interview_invite(CONV_ID, "你好，看了你的简历，想了解下你之前门店的日营业额大概多少？", matched_conv, job_info)
check("返回 False(放行)", handled is False)

print("=== 用例 5: 第二个HR不同时间邀约 → 静默 + 入库 ===")
handled = handle_interview_invite(CONV_ID, f"{day_after}上午10点来视频面试一下吧", matched_conv, job_info)
check("返回 True(静默)", handled is True)
row = get_db().execute(
    "SELECT start_time, interview_type FROM interviews WHERE conversation_id=? ORDER BY id DESC LIMIT 1", (CONV_ID,)
).fetchone()
check(f"时间正确 {day_after} 10:00 online", row and row["start_time"].startswith(f"{day_after} 10:00") and row["interview_type"] == "online",
      f"实际 {dict(row) if row else '无'}")

print("=== 用例 6: 开关关闭 → 全部放行 ===")
from backend.state import set_setting
set_setting("interview_silent_mode", "false")
handled = handle_interview_invite(CONV_ID, f"后天下午3点来面试吧", matched_conv, job_info)
check("返回 False(放行)", handled is False)
set_setting("interview_silent_mode", "true")

clear()
print(f"\n结果: {passed} 通过, {len(failed)} 失败 {failed if failed else ''}")
sys.exit(1 if failed else 0)
