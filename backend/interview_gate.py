#!/usr/bin/env python3
"""
面试邀约静默闸门 —— HR 面试邀约只记录不回复。

HR 消息进入 AI 回复链路前先过此闸门:
- HR 主动提出"具体可解析时间"的面试邀约 → 解析时间,经冲突校验后写入 interviews 表,
  全程不生成、不发送任何回复(静默)
- 有冲突则不写入,只记日志;无论记录成功与否,调用方都必须静默
- 其余消息(包括不带具体时间的面试意向,如"你哪天有空")放行给正常聊天链路

判定原则: 宁漏勿吞 —— LLM 判定不明确时一律放行,避免把正常聊天静默掉。
闸门自身的任何异常也都放行,绝不阻塞正常聊天。
"""

import json
from datetime import datetime

from backend.logger import get_logger

log = get_logger("interview_gate")

# 检测用 Prompt: 结构化输出,相对时间必须换算成绝对日期
DETECT_PROMPT = """你是检测器。判断下面这条 BOSS直聘 HR 消息是否同时满足两个条件:
1. HR 主动邀约面试或面谈(线下面试、视频面试、电话面试、来公司聊聊等入职前沟通环节)
2. 消息里包含具体可解析的时间点(日期+时刻,如"明天下午2点""周三上午10点半";只有"这周找时间""你哪天有空"这类无具体时刻的不算)

当前时间: {now} ({weekday})

只输出 JSON,不要输出其他任何内容:
{{"is_invite": true或false, "date": "YYYY-MM-DD或null", "time": "HH:MM或null", "type": "offline"或"online", "notes": "面试地址/会议方式等补充信息,没有则空串"}}

规则:
- "明天""后天""周X""X号"等相对时间必须结合当前时间换算成绝对日期
- 视频面试/电话面试算 online,到公司现场算 offline
- 日期或时刻解析不出 → is_invite 必须为 false
- 消息只是在聊工作内容、问简历、闲聊 → is_invite 为 false"""


def handle_interview_invite(conversation_id: int, hr_message: str, matched_conv: dict, job_info: dict) -> bool:
    """
    检测 HR 消息是否为"提出具体面试时间的邀约"。

    返回 True  → 是邀约: 已尝试记录排期(冲突则跳过),调用方必须静默,不发送任何消息
    返回 False → 不是邀约(或闸门关闭/异常),走正常聊天链路
    """
    from backend.state import get_setting

    if get_setting("interview_silent_mode", "true") != "true":
        return False
    if not hr_message or not hr_message.strip():
        return False

    try:
        parsed = _detect_invite(hr_message)
    except Exception as e:
        # 检测失败(如未配 API Key)→ 放行,不影响正常聊天
        log.warning(f"[面试闸门] 检测异常,放行走正常聊天: {e}")
        return False

    if not parsed:
        return False

    _record_interview(conversation_id, parsed, matched_conv, job_info)
    return True


def _detect_invite(hr_message: str) -> dict | None:
    """LLM 判定是否为带具体时间的面试邀约。返回解析结果 dict,不是邀约返回 None。"""
    from backend.interview.llm_client import get_llm, parse_json_from_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    now = datetime.now()
    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    system = DETECT_PROMPT.format(now=now.strftime("%Y-%m-%d %H:%M"), weekday=weekday_cn)

    llm = get_llm(temperature=0)
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=hr_message)])
    data = parse_json_from_llm(resp.content or "")

    if not data or not data.get("is_invite"):
        return None

    date_str = (data.get("date") or "").strip()
    time_str = (data.get("time") or "").strip()
    if not date_str or not time_str:
        return None

    # 二次校验 LLM 给出的时间可解析且在未来 30 天内(防止幻觉出离谱时间)
    try:
        start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    if start_dt < now or (start_dt - now).days > 30:
        log.info(f"[面试闸门] 邀约时间不在有效范围内,放行: {start_dt}")
        return None

    itype = "offline" if data.get("type") == "offline" else "online"
    return {"date": date_str, "time": time_str, "type": itype, "notes": (data.get("notes") or "").strip()}


def _record_interview(conversation_id: int, parsed: dict, matched_conv: dict, job_info: dict):
    """冲突校验后写入排期。有冲突则不写入,只记日志。"""
    from backend.state import validate_and_add_interview

    start_time = f"{parsed['date']} {parsed['time']}"
    notes_parts = []
    if parsed["notes"]:
        notes_parts.append(parsed["notes"])
    notes_parts.append("HR主动提出-静默记录(系统未回复)")
    notes = " | ".join(notes_parts)

    success, err_msg = validate_and_add_interview(conversation_id, parsed["type"], start_time, 60, notes)

    hr_name = (matched_conv or {}).get("hr_name") or "?"
    company = (job_info or {}).get("company") or (matched_conv or {}).get("hr_company") or "?"
    if success:
        log.info(
            f"[面试闸门] HR[{hr_name}] 邀约已静默记录: {start_time} ({parsed['type']}) | {company}"
        )
    else:
        log.info(
            f"[面试闸门] HR[{hr_name}] 邀约时间冲突未记录: {start_time} | {err_msg} | {company}"
        )
