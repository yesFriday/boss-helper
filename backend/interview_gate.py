#!/usr/bin/env python3
"""
面试邀约静默闸门 —— HR 面试邀约只记录不回复。

HR 消息进入 AI 回复链路前先过此闸门:
- HR 主动提出"具体可解析时间"的面试邀约 → 解析时间,经冲突校验后写入 interviews 表,
  全程静默不回复
- 时间冲突 → 不入排期,转存冲突留档表,并回复"两段式改期引导"(说明冲突+报真实
  空闲时段+以问句收尾);绝不代表本人确认任何时间,最终拍板由求职者本人完成
- 其余消息(包括不带具体时间的面试意向,如"你哪天有空")放行给正常聊天链路

判定原则: 宁漏勿吞 —— LLM 判定不明确时一律放行,避免把正常聊天静默掉。
闸门自身的任何异常也都放行,绝不阻塞正常聊天。
"""

import json
from datetime import datetime
from typing import Optional

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


def handle_interview_invite(
    conversation_id: int,
    hr_message: str,
    matched_conv: dict,
    job_info: dict,
    get_job_url=None,
) -> Optional[str]:
    """
    检测 HR 消息是否为"提出具体面试时间的邀约"。

    get_job_url: 可选回调，确认是邀约后调用以获取岗位详情页URL（如点开页面捕获）。
    只在确认为邀约时才调用，避免对每条消息都执行浏览器动作。

    返回 None    → 不是邀约(或闸门关闭/异常),走正常聊天链路
    返回 ""      → 是邀约且已静默入排期,调用方必须静默,不发送任何消息
    返回 非空文本 → 邀约与已有安排冲突,已转存留档;文本为"两段式改期引导回复",
                    调用方应将其发送给 HR
    """
    from backend.state import get_setting

    if get_setting("interview_silent_mode", "true") != "true":
        return None
    if not hr_message or not hr_message.strip():
        return None

    try:
        parsed = _detect_invite(hr_message)
    except Exception as e:
        # 检测失败(如未配 API Key)→ 放行,不影响正常聊天
        log.warning(f"[面试闸门] 检测异常,放行走正常聊天: {e}")
        return None

    if not parsed:
        return None

    job_url = ""
    if get_job_url is not None:
        try:
            job_url = get_job_url() or ""
        except Exception as e:
            log.debug(f"[面试闸门] 获取岗位链接失败: {e}")
    if job_url:
        try:
            from backend.state import update_conversation_job_context

            update_conversation_job_context(conversation_id, job_url=job_url)
            matched_conv["job_url"] = job_url
        except Exception:
            pass

    success, err_msg, conflict_id = _record_interview(
        conversation_id, parsed, matched_conv, job_info, hr_message, job_url
    )
    if success:
        return ""  # 已入排期 → 静默
    return _build_conflict_reply()  # 冲突 → 两段式改期引导


def _record_interview(
    conversation_id: int,
    parsed: dict,
    matched_conv: dict,
    job_info: dict,
    hr_message: str = None,
    job_url: str = "",
) -> tuple:
    """冲突校验后写入排期。有冲突则转存冲突登记表(conflicted_interviews),不写排期。

    返回 (success, err_msg, conflict_id)。
    """
    from backend.state import validate_and_add_interview, add_conflicted_interview

    start_time = f"{parsed['date']} {parsed['time']}"
    notes_parts = []
    if parsed["notes"]:
        notes_parts.append(parsed["notes"])
    notes_parts.append("HR主动提出-静默记录(系统未回复)")
    notes = " | ".join(notes_parts)

    success, err_msg = validate_and_add_interview(
        conversation_id, parsed["type"], start_time, 60, notes, job_url=job_url
    )

    hr_name = (matched_conv or {}).get("hr_name") or "?"
    company = (job_info or {}).get("company") or (matched_conv or {}).get("hr_company") or "?"
    if success:
        log.info(
            f"[面试闸门] HR[{hr_name}] 邀约已静默记录: {start_time} ({parsed['type']}) | {company} | 岗位链接={'有' if job_url else '无'}"
        )
        return True, "", None
    # 冲突: 转存冲突登记表留档(便于后续人工跟进),排期表不写入
    conflict_id = add_conflicted_interview(
        conversation_id, parsed["type"], start_time, 60, err_msg,
        hr_message=hr_message, notes="HR主动提出-静默记录(冲突未入排期)", job_url=job_url,
    )
    log.info(
        f"[面试闸门] HR[{hr_name}] 邀约时间冲突未记录: {start_time} | {err_msg} | "
        f"{company} | 已登记冲突表#{conflict_id}"
    )
    return False, err_msg, conflict_id


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def get_free_halfday_slots(days: int = 5, max_slots: int = 3) -> list:
    """计算未来 N 天的空闲半时段（如"明天上午""周六全天"），已约/已过去的时段自动排除。

    - 今天的上午过了 12 点、下午过了 18 点后不再对外报（已来不及安排）
    - 同一天上下午都空闲时合并为"全天"，避免"周六上午、周六下午"这种机械表达
    - 标签用 今天/明天/周X，贴近真人说话
    """
    from datetime import datetime, timedelta

    from backend.state import get_upcoming_interviews

    now = datetime.now()
    upcoming = get_upcoming_interviews(days=days)
    slots = []
    for offset in range(days):
        day = now + timedelta(days=offset)
        date_str = day.strftime("%Y-%m-%d")
        if offset == 0:
            label = "今天"
        elif offset == 1:
            label = "明天"
        else:
            label = WEEKDAY_CN[day.weekday()]
        day_interviews = [u for u in upcoming if (u["start_time"] or "")[:10] == date_str]

        def _hour(u):
            try:
                return datetime.strptime((u["start_time"] or "")[:16], "%Y-%m-%d %H:%M").hour
            except Exception:
                return 10  # 解析失败按上午占用处理，宁可少报时段

        morning_busy = any(_hour(u) < 12 for u in day_interviews)
        afternoon_busy = any(12 <= _hour(u) < 18 for u in day_interviews)
        # 已过去的半场不再对外报
        if offset == 0 and now.hour >= 12:
            morning_busy = True
        if offset == 0 and now.hour >= 18:
            afternoon_busy = True

        if not morning_busy and not afternoon_busy:
            slots.append(f"{label}全天")
        else:
            if not morning_busy:
                slots.append(f"{label}上午")
            if not afternoon_busy:
                slots.append(f"{label}下午")
        if len(slots) >= max_slots:
            break
    return slots[:max_slots]


def _build_conflict_reply() -> str:
    """两段式改期引导：说明冲突 + 报真实空闲时段 + 问句收尾。

    确定性模板(不走 LLM)，空闲时段来自真实排期，绝不编造；
    不出现任何确认性措辞，最终时间由 HR 选择、求职者本人拍板。
    """
    slots = get_free_halfday_slots()
    if slots:
        return f"不好意思，这个时间我这边已经有安排了。{'、'.join(slots)}我都有空，您看哪个时间方便？"
    return "不好意思，这个时间我这边已经有安排了。您看下周什么时间方便？我这边时间好协调。"


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
