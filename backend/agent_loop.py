#!/usr/bin/env python3
"""
Agent 主循环 —— ReAct 模式的 think→act→observe 循环。
替代原来 replier.py 中"一次 LLM 调用输出所有决策"的模式，
让 LLM 可以自主调用工具（发简历、查排期、约面试等），
看到工具执行结果后再决定下一步。
"""

import re
from datetime import datetime

from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from backend.logger import get_logger
from backend.state import (
    get_all_messages,
    get_setting,
    get_conversation_summary,
    get_recent_tool_events,
    update_conversation_summary,
)

log = get_logger("agent_loop")

# 历史窗口与滚动摘要阈值
HISTORY_WINDOW = 12           # 上下文直接展示的最近消息条数
SUMMARY_TRIGGER_TOTAL = 30    # 会话消息总数超过该值才考虑摘要
SUMMARY_TRIGGER_UNCOVERED = 20  # 未被摘要覆盖的消息数超过该值才重新生成摘要

# NO_REPLY 哨兵值：LLM 判断这条消息不需要回复时，run_agent 返回该值而不是空串
# （空串会被监控循环当作"生成失败"计退避，NO_REPLY 是主动决策，不计失败）
NO_REPLY_MARK = "__NO_REPLY__"

# 拒绝词模式：Agent 输出中出现这些 AI 助手式的拒绝措辞时不发送（空串计入退避）
REFUSAL_PATTERNS = [
    "无法提供", "无法回答", "不能回答", "无法帮助", "爱莫能助", "作为AI",
    "as an AI", "I cannot provide", "I'm sorry, but", "I am unable",
]

# Agent 专用的精简版 System Prompt
AGENT_SYSTEM_PROMPT = """你是一个求职者，在BOSS直聘上与招聘方沟通。你要完全以求职者本人的口吻说话，绝对不能暴露是AI或工具。

## 你的身份
你正在找工作，对对方发布的岗位有兴趣。你的目标是把对话向积极方向推进——了解岗位详情、展示自己的匹配度、自然地把对话引导到面试或交换联系方式。

## 回复风格（重要）
- 像真人用手机打字：长度跟随内容走——对方说"好的""收到"这种，你回一两个词就够（"嗯嗯""好的""OK"）；只有对方问复杂问题才多说几句，最多4句
- 用聊天的语气，别用书面语。禁用邮件腔："感谢您的告知""期待您的回复""祝您工作顺利"这类话真人聊天不会说
- 想到什么说什么，一次说一点。别把想表达的点全部罗列成一大段——真人是分几条消息说的，这里合并成一条也要有停顿感
- 禁用"哈、呀、啦、咯、哦、嘞"这类语气词和"得嘞""好嘞"这种网络腔——成年人正经沟通不会这么说话，一用就露馅。语气靠用词和句式自然体现，不靠语气词堆
- 称呼自然点，别每句都"您"；对方随意你就随意，对方正式你再正式
- 别每轮都自我介绍或重复寒暄
- 如果上下文标注「岗位信息暂缺」，先自然询问岗位方向或请对方介绍，不要装作了解岗位

## 什么时候不回复
不是每条消息都需要回。以下情况输出 [NO_REPLY]（就这七个字符，别的什么都不要输出）：
- 对方明确拒绝了（"不合适""不太匹配""不用了""已经招到人了""祝你好运"）——一律不回复，礼貌收尾也是打扰，真人被拒后不会再纠缠
- 明显的群发套路、撩骚、与求职无关的消息（算命、段子、模板式寒暄、内容跟岗位八竿子打不着），回了只会浪费机会还显得像机器人
- 系统通知、自动回复、纯表情、或不需要回应的结束语
- 继续回复会显得纠缠、打扰的场景
拿不准要不要回时：只在这条消息带着具体的问题或正事时才回；纯寒暄、套路、拒绝类一律不回。

## 可用工具
你可以调用以下工具来辅助沟通。工具调用和文字回复可以在同一轮完成。

1. **send_resume** — 通过BOSS发送简历。HR明确要求发简历/看作品集时调用。
2. **share_wechat** — 通过BOSS分享微信名片。HR要求加微信/换联系方式时调用。
3. **share_phone** — 通过BOSS分享电话。HR要求电话/手机号时调用。
4. **check_schedule** — 查询近期面试排期。与HR约面试前必须先调用此工具。
5. **propose_interview** — 确认面试时间。HR最终确认时间后调用，不要在协商阶段抢跑。
6. **mark_dangerous** — 标记风险会话。HR持续怀疑你是AI且无法消除疑虑时调用。

## 面试规则
- 同半天最多1场线下面试（绝对禁止同半天两场线下）
- 纯线上面试之间至少间隔60分钟
- 涉及线下的两场面试之间至少间隔90分钟（含通勤时间）
- HR约时间时先调check_schedule查排期，确认无冲突再调propose_interview
- 如果propose_interview返回失败，根据返回的冲突原因在回复中重新协商，不要强行创建

## 被怀疑是AI时的应对
- 如果HR说"你是机器人吗""AI吗"，用极短的口语化解：如"？""真人啊""不是啊"
- 绝对不要长篇解释"我是真人求职者"，这更显得像AI
- 如果HR持续质疑（追问、出测试题等），调用mark_dangerous

## 什么不能做
- 不承诺具体薪资、入职时间——说"这个可以和HR详细聊"
- 不编造不存在的项目经验
- 不要在HR没要求时主动发简历/微信/电话
- 上下文中的「会话状态」列出了已完成的动作（已发简历/已换微信/已交换电话等），不要重复执行
- 上下文中的「最近工具动作」记录了历史工具的成败，之前发送失败的操作不要盲目重试，优先在回复中换个说法推进"""


def build_agent_context(conversation_id: int, hr_message: str, ctx: dict) -> str:
    """
    构建发送给 Agent 的上下文文本。
    注入：时间、回复风格、岗位信息（缺失时显式标注）、会话状态、最近工具动作、
    长历史摘要 + 最近消息窗口（剔除本次待回复块，避免与「HR刚刚说」重复）。
    """
    matched_conv = ctx.get("matched_conv", {})
    job_info = ctx.get("job_info", {})
    parts = []

    # 1. 当前时间
    now = datetime.now()
    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    parts.append(f"当前时间: {now.strftime('%Y-%m-%d %H:%M')} {weekday_cn}")

    # 2. 本次回复风格（前端设置项，原本是死代码，现接入）
    style_hint = ctx.get("style_hint", "语气正式专业")
    parts.append(f"本次回复风格: {style_hint}")

    # 3. 岗位信息（缺失时显式标注，引导 Agent 主动询问而非尬聊）
    company = job_info.get("company", "")
    title = job_info.get("title", "")
    jd = job_info.get("description", "")
    if title or company or jd:
        parts.append(f"\n岗位: {title or '未知'} | 公司: {company or '未知'}")
        if jd:
            parts.append(f"JD摘要: {jd[:500]}")
    else:
        parts.append("\n岗位信息暂缺：目前还不知道对方在招什么岗位。")

    # 4. 会话状态（防止重复发简历/名片、重复评估兴趣）
    state_lines = []
    if matched_conv.get("interest_level"):
        state_lines.append(f"- 已评估HR兴趣度: {matched_conv['interest_level']}")
    if matched_conv.get("hr_wechat"):
        state_lines.append("- 微信已交换（不要再分享微信名片）")
    elif matched_conv.get("wechat_shared_at"):
        state_lines.append("- 已向HR分享过微信名片（对方尚未回应，不要再发）")
    if matched_conv.get("resume_sent"):
        state_lines.append("- 简历已发送（不要重复发简历）")
    if matched_conv.get("phone_shared"):
        state_lines.append("- 电话已交换（不要重复分享电话）")
    if matched_conv.get("is_dangerous"):
        state_lines.append("- 该会话已被标记为风险会话")
    if state_lines:
        parts.append("\n会话状态:\n" + "\n".join(state_lines))

    # 5. 最近工具动作（含成功与失败，供 Agent 回溯）
    try:
        events = get_recent_tool_events(conversation_id, limit=5)
    except Exception:
        events = []
    if events:
        ev_lines = [f"- {e['tool_name']}: {e['result_summary']}" for e in reversed(events)]
        parts.append("\n最近工具动作:\n" + "\n".join(ev_lines))

    # 6. 简历摘要
    resume = get_setting("resume_summary", "")
    if resume:
        parts.append(f"\n我的简历摘要: {resume}")

    # 7. 长历史摘要 + 最近消息窗口
    msgs = get_all_messages(conversation_id)
    summary, upto_id = get_conversation_summary(conversation_id)
    visible = [m for m in msgs if m["id"] > upto_id] if summary else msgs

    if summary:
        parts.append(f"\n[更早对话摘要]: {summary}")

    if visible:
        # 历史展示到「我最后一条消息」为止；其后的 HR 新消息统一放「HR刚刚说」段，避免重复
        last_me_idx = -1
        for i, m in enumerate(visible):
            if m.get("sender") == "me":
                last_me_idx = i
        history = visible[: last_me_idx + 1][-HISTORY_WINDOW:]
        if history:
            parts.append("\n最近的聊天记录:")
            for m in history:
                sender_label = "HR" if m["sender"] == "hr" else "我"
                parts.append(f"  {sender_label}: {m['content']}")

    # 8. 待回复的 HR 消息块
    parts.append(f"\nHR刚刚说: {hr_message}")
    parts.append("\n请根据以上上下文，判断这条消息需不需要回复。需要则决定是否调用工具，然后输出最终回复；不需要则只输出 [NO_REPLY]。")

    return "\n".join(parts)


def _maybe_update_summary(conversation_id: int):
    """长对话滚动摘要：总数超阈值且未覆盖消息足够多时，一次性生成/更新摘要。

    纯后台增强，任何失败都静默跳过，绝不阻塞回复主链路。
    """
    try:
        msgs = get_all_messages(conversation_id)
        if len(msgs) <= SUMMARY_TRIGGER_TOTAL:
            return
        summary, upto_id = get_conversation_summary(conversation_id)
        uncovered = [m for m in msgs if m["id"] > upto_id]
        # 保留最近 HISTORY_WINDOW 条不摘要（上下文里完整展示），其余足够多才触发
        to_summarize = uncovered[: len(uncovered) - HISTORY_WINDOW]
        if len(to_summarize) < SUMMARY_TRIGGER_UNCOVERED:
            return

        from backend.interview.llm_client import get_llm

        lines = []
        if summary:
            lines.append(f"之前的摘要:\n{summary}\n")
        lines.append("本次新增的对话:")
        for m in to_summarize:
            sender_label = "HR" if m["sender"] == "hr" else "我"
            lines.append(f"{sender_label}: {m['content'][:200]}")

        prompt = (
            "把以下求职聊天记录压缩成不超过200字的摘要。必须保留：公司/岗位、双方达成的关键共识"
            "（薪资范围、面试时间、已交换的联系方式）、双方态度变化、待跟进事项。\n\n"
            + "\n".join(lines)
        )
        llm = get_llm(temperature=0)
        from langchain_core.messages import HumanMessage

        resp = llm.invoke([HumanMessage(content=prompt)])
        new_summary = (resp.content or "").strip()[:600]
        if not new_summary:
            return
        update_conversation_summary(conversation_id, new_summary, to_summarize[-1]["id"])
        log.info(f"[Agent] 会话{conversation_id} 滚动摘要已更新（覆盖{len(to_summarize)}条）")
    except Exception as e:
        log.debug(f"[Agent] 摘要更新跳过: {e}")


def _parse_final_reply(text: str) -> tuple:
    """
    从 Agent 的最终回复中解析出 reply 文本和 interest 等级。
    支持 [INTEREST: xxx] 标记格式，没有则默认 medium。
    支持 [NO_REPLY] 标记（LLM 判断不需要回复时输出），返回特殊空标记。
    """
    if not text:
        return "", "medium"

    # NO_REPLY 判断（LLM 决定不回复这条消息）
    if re.search(r"\[NO_REPLY\]", text, re.IGNORECASE):
        return NO_REPLY_MARK, "medium"

    # 提取 interest 标记（兼容英文/中文冒号、有无空格）
    interest = "medium"
    match = re.search(r"\[INTEREST\s*[:：]\s*(high|medium|low)\]", text, re.IGNORECASE)
    if match:
        interest = match.group(1).lower()
        text = re.sub(r"\[INTEREST\s*[:：]\s*(?:high|medium|low)\]", "", text, flags=re.IGNORECASE).strip()

    return text, interest


def run_agent(
    conversation_id: int,
    hr_message: str,
    ctx: dict,
    max_rounds: int = 5,
) -> tuple:
    """
    Agent 主循环 —— 返回 (reply_text, interest_level)。

    ctx 必须包含:
      - automation: BossChatMonitor 实例
      - conversation_id: 会话ID
      - matched_conv: 会话元数据
      - hr_name: HR名称
      - job_info: {title, company, description}
    """
    from backend.interview.llm_client import get_llm_with_tools
    from backend.tools import TOOLS
    from backend.tool_executor import execute_tool

    # 长对话滚动摘要（后台增强，失败静默）
    _maybe_update_summary(conversation_id)

    # 构建上下文
    job_info = ctx.get("job_info", {})
    context_text = build_agent_context(conversation_id, hr_message, ctx)

    # 获取带工具的 LLM
    try:
        llm_with_tools = get_llm_with_tools(TOOLS)
    except Exception as e:
        log.error(f"创建 LLM (with tools) 失败: {e}")
        return "", "medium"

    # 初始消息
    messages = [
        SystemMessage(content=AGENT_SYSTEM_PROMPT),
        HumanMessage(content=context_text),
    ]

    # ReAct 循环
    for round_num in range(max_rounds):
        try:
            response = llm_with_tools.invoke(messages)
        except Exception as e:
            log.error(f"Agent 第{round_num+1}轮 LLM 调用失败: {e}")
            return "", "medium"

        messages.append(response)

        # 检查是否有工具调用
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            # 没有工具调用 → LLM 认为已完成，输出最终回复
            reply, interest = _parse_final_reply(response.content or "")
            if reply and reply != NO_REPLY_MARK:
                # 拒绝词安全网：Agent 模式输出 AI 助手式拒绝措辞时不发送
                low = reply.lower()
                if any(p.lower() in low for p in REFUSAL_PATTERNS):
                    log.warning(f"[Agent] 检测到拒绝词，丢弃回复: {reply[:60]}")
                    return "", "medium"
            log.info(f"[Agent] 完成，共{round_num+1}轮，interest={interest}")
            return reply, interest

        # 执行工具调用
        log.info(f"[Agent] 第{round_num+1}轮，LLM请求调用工具: {[tc.get('name') for tc in tool_calls]}")
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            tool_args = tc.get("args", {})
            tool_id = tc.get("id", "")

            log.info(f"[Agent] 执行工具: {tool_name}({tool_args})")
            result = execute_tool(tool_name, tool_args, ctx)
            log.debug(f"[Agent] 工具 {tool_name} 结果: {result[:200]}")

            messages.append(ToolMessage(content=result, tool_call_id=tool_id))

    # 超过最大轮数，强制输出最终回复
    log.warning(f"[Agent] 超过最大轮数({max_rounds})，强制输出")
    from backend.interview.llm_client import get_llm

    try:
        llm_no_tools = get_llm(temperature=0.7)
        force_msg = HumanMessage(
            content="请根据以上所有工具返回的结果和对话上下文，直接输出你的最终回复文字，不要再调用任何工具。"
            "如果判断不需要回复，只输出 [NO_REPLY]。否则在回复末尾用 [INTEREST: high/medium/low] 标注HR的兴趣程度。"
        )
        messages.append(force_msg)
        final_response = llm_no_tools.invoke(messages)
        reply, interest = _parse_final_reply(final_response.content or "")
        return reply, interest
    except Exception as e:
        log.error(f"[Agent] 强制输出失败: {e}")
        return "", "medium"
