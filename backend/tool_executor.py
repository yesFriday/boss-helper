#!/usr/bin/env python3
"""
工具执行器 —— 将 Agent 的工具调用映射到实际的浏览器操作和数据库操作。
每个工具函数接收 ctx 上下文，返回字符串结果给 LLM。
"""

import json
from datetime import datetime, timedelta
from backend.logger import get_logger
from backend.state import record_tool_event

log = get_logger("tool_executor")


def _record(ctx: dict, tool_name: str, result_summary: str):
    """记录有副作用的工具调用结果（成功与失败都记），供后续轮次上下文回溯。"""
    try:
        record_tool_event(ctx.get("conversation_id"), tool_name, result_summary)
    except Exception as e:
        log.debug(f"工具事件记录失败: {e}")


def _call_automation(ctx: dict, method_name: str, *args):
    """调用 automation 的浏览器方法。ctx 提供 run_pw(llm线程场景)时 hop 回 pw 线程,
    否则直调(CLI/测试场景,调用方本身就在浏览器线程或无浏览器)。"""
    automation = ctx.get("automation")
    if not automation:
        return None
    method = getattr(automation, method_name, None)
    if method is None:
        return None
    run_pw = ctx.get("run_pw")
    if run_pw is not None:
        return run_pw(method, *args)
    return method(*args)


def execute_tool(tool_name: str, tool_args: dict, ctx: dict) -> str:
    """
    根据工具名分发执行，返回给 LLM 的结果字符串。
    ctx 必须包含:
      - automation: BossChatMonitor 实例（提供 send_resume/send_wechat/send_phone/send_message 等方法）
      - conversation_id: 数据库会话ID
      - matched_conv: 会话元数据 dict
      - hr_name: HR名称（用于打开会话）
      - job_info: {title, company, description}
    """
    tool_name = (tool_name or "").strip()
    tool_args = tool_args or {}

    try:
        if tool_name == "send_resume":
            return _exec_send_resume(ctx)
        elif tool_name == "share_wechat":
            return _exec_share_wechat(ctx)
        elif tool_name == "share_phone":
            return _exec_share_phone(ctx)
        elif tool_name == "check_schedule":
            return _exec_check_schedule(tool_args, ctx)
        elif tool_name == "propose_interview":
            return _exec_propose_interview(tool_args, ctx)
        elif tool_name == "mark_dangerous":
            return _exec_mark_dangerous(ctx)
        else:
            return f"未知工具: {tool_name}"
    except Exception as e:
        log.error(f"工具 {tool_name} 执行失败: {e}", exc_info=True)
        return f"工具执行失败: {str(e)}"


def _exec_send_resume(ctx: dict) -> str:
    """通过 BOSS 发简历"""
    conv_id = ctx.get("conversation_id")
    matched_conv = ctx.get("matched_conv", {})
    automation = ctx.get("automation")

    if matched_conv.get("resume_sent"):
        return "简历之前已经发送过了，无需重复发送。"

    if not automation:
        return "错误: 浏览器自动化实例不可用"

    success = _call_automation(ctx, "send_resume")
    if success:
        from backend.state import mark_resume_sent
        mark_resume_sent(conv_id)
        matched_conv["resume_sent"] = True
        _record(ctx, "send_resume", "简历发送成功")
        return "【系统事件】简历发送成功。请在回复中自然告知HR已发即可。"
    else:
        _record(ctx, "send_resume", "简历发送失败（未找到按钮或确认弹窗）")
        return "【系统事件】简历发送失败（页面未出现确认弹窗）。回复HR时切勿声称已发，可以说稍后发或直接不回复。"


def _exec_share_wechat(ctx: dict) -> str:
    """通过 BOSS 分享微信"""
    matched_conv = ctx.get("matched_conv", {})
    automation = ctx.get("automation")
    hr_name = ctx.get("hr_name", "")

    if matched_conv.get("hr_wechat"):
        return "微信名片之前已经分享过了，无需重复发送。"

    if not automation:
        return "错误: 浏览器自动化实例不可用"

    success = _call_automation(ctx, "send_wechat", hr_name)
    if success:
        _record(ctx, "share_wechat", "微信名片分享成功")
        return "【系统事件】名片分享成功。请在回复中自然告知HR已发，注意切勿出现'微信'两字。"
    else:
        _record(ctx, "share_wechat", "微信名片分享失败")
        return "【系统事件】名片分享失败。回复HR时切勿声称已发。"


def _exec_share_phone(ctx: dict) -> str:
    """通过 BOSS 分享电话"""
    conv_id = ctx.get("conversation_id")
    matched_conv = ctx.get("matched_conv", {})
    automation = ctx.get("automation")
    hr_name = ctx.get("hr_name", "")

    if matched_conv.get("phone_shared"):
        return "电话之前已经交换过了，无需重复发送。"

    if not automation:
        return "错误: 浏览器自动化实例不可用"

    success = _call_automation(ctx, "send_phone", hr_name)
    if success:
        from backend.state import mark_phone_shared
        mark_phone_shared(conv_id)
        matched_conv["phone_shared"] = True
        _record(ctx, "share_phone", "电话分享成功")
        return "【系统事件】电话分享成功。请在回复中自然告知HR已发即可。"
    else:
        _record(ctx, "share_phone", "电话分享失败")
        return "【系统事件】电话分享失败。回复HR时切勿声称已发。"


def _exec_check_schedule(tool_args: dict, ctx: dict) -> str:
    """查询排期并返回格式化结果"""
    days = tool_args.get("days", 3)
    from backend.state import get_upcoming_interviews, get_setting

    # 面试偏好
    pref_format = get_setting("interview_format", "both")
    format_map = {"online": "仅接受线上", "offline": "仅接受线下", "both": "线上线下均可"}
    format_desc = format_map.get(pref_format, "线上线下均可")

    pref_slots = get_setting("interview_time_slots", "上午(9:00-12:00)，下午(14:00-18:00)")

    # 已有面试
    upcoming = get_upcoming_interviews(days=days)
    now = datetime.now()

    lines = []
    lines.append(f"## 面试偏好")
    lines.append(f"- 形式: {format_desc}")
    lines.append(f"- 期望时段: {pref_slots}")
    lines.append("")

    if not upcoming:
        lines.append(f"未来{days}天无面试安排，全部空闲。")
        lines.append("")
        # 生成简单的空位建议
        for d in range(days):
            dt = now + timedelta(days=d)
            date_str = dt.strftime("%Y-%m-%d")
            wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
            can_offline = dt.weekday() < 5  # 工作日
            tip = "可约线上/线下" if can_offline else "建议仅线上"
            lines.append(f"- {date_str} ({wd}): 全天空闲，{tip}")
    else:
        lines.append(f"## 未来{days}天已有面试:")
        for item in upcoming:
            t_type = "线上" if item["interview_type"] == "online" else "线下"
            lines.append(f"  - {item['start_time'][:16]} → {item['end_time'][:16]} ({t_type}) | {item['company']} - {item['job_title']}")

        # 分析空位
        lines.append("")
        lines.append("## 可用空位分析:")
        for d in range(days):
            dt = now + timedelta(days=d)
            date_str = dt.strftime("%Y-%m-%d")
            day_upcoming = [u for u in upcoming if u["start_time"].startswith(date_str)]

            if not day_upcoming:
                lines.append(f"- {date_str}: 全天空闲")
                continue

            morning_booked = any(
                datetime.strptime(u["start_time"][:16], "%Y-%m-%d %H:%M").hour < 12
                for u in day_upcoming
            )
            afternoon_booked = any(
                12 <= datetime.strptime(u["start_time"][:16], "%Y-%m-%d %H:%M").hour < 18
                for u in day_upcoming
            )

            # 检查线下互斥
            has_offline_am = any(
                u["interview_type"] == "offline"
                and datetime.strptime(u["start_time"][:16], "%Y-%m-%d %H:%M").hour < 12
                for u in day_upcoming
            )
            has_offline_pm = any(
                u["interview_type"] == "offline"
                and 12 <= datetime.strptime(u["start_time"][:16], "%Y-%m-%d %H:%M").hour < 18
                for u in day_upcoming
            )

            am_status = "上午已占（线下）" if has_offline_am else ("上午已占" if morning_booked else "上午空闲")
            pm_status = "下午已占（线下）" if has_offline_pm else ("下午已占" if afternoon_booked else "下午空闲")

            lines.append(f"- {date_str}: {am_status} | {pm_status}")

        # 规则提示
        lines.append("")
        lines.append("## 面试规则（务必遵守）:")
        lines.append("- 同半天最多1场线下面试（绝对禁止同半天两场线下）")
        lines.append("- 两场纯线上面试之间至少间隔60分钟")
        lines.append("- 涉及线下的两场面试之间至少间隔90分钟（含通勤）")
        lines.append("- 不要约在期望时段之外的时间")

    return "\n".join(lines)


def _exec_propose_interview(tool_args: dict, ctx: dict) -> str:
    """创建面试记录，校验时间冲突"""
    conv_id = ctx.get("conversation_id")
    interview_type = tool_args.get("interview_type", "online")
    start_time = tool_args.get("start_time", "")
    duration_min = tool_args.get("duration_min", 60)
    notes = tool_args.get("notes", "")

    from backend.state import validate_and_add_interview
    success, err_msg = validate_and_add_interview(conv_id, interview_type, start_time, duration_min, notes)

    if success:
        _record(ctx, "propose_interview", f"面试创建成功: {start_time} ({interview_type})")
        return f"面试时间已确认: {start_time} ({interview_type})，时长{duration_min}分钟。用自然的话跟HR确认这个时间（如'那咱们就定X号X点，到时候见'）。"
    else:
        _record(ctx, "propose_interview", f"面试创建失败: {err_msg[:80]}")
        # 构建失败回复，附带备选建议
        return f"**面试时间创建失败**: {err_msg}\n请根据此冲突原因，在回复中重新与HR协商备选时间。不要再尝试创建这个时间。"


def _exec_mark_dangerous(ctx: dict) -> str:
    """标记风险会话"""
    conv_id = ctx.get("conversation_id")
    matched_conv = ctx.get("matched_conv", {})

    from backend.state import mark_conversation_dangerous
    mark_conversation_dangerous(conv_id)
    matched_conv["is_dangerous"] = True

    hr_name = matched_conv.get("hr_name", "未知")
    _record(ctx, "mark_dangerous", f"会话已被标记为风险会话")
    return f"已将会话「{hr_name}」标记为风险会话，后续不再自动回复。你的本轮回复正常发送即可。"
