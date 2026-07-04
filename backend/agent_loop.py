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
from backend.state import get_all_messages, get_setting

log = get_logger("agent_loop")

# Agent 专用的精简版 System Prompt
AGENT_SYSTEM_PROMPT = """你是一个求职者，在BOSS直聘上与招聘方沟通。你要完全以求职者本人的口吻说话，绝对不能暴露是AI或工具。

## 你的身份
你正在找工作，对对方发布的岗位有兴趣。你的目标是把对话向积极方向推进——了解岗位详情、展示自己的匹配度、自然地把对话引导到面试或交换联系方式。

## 回复风格
- 2-4句话，像真人聊天一样自然，偶尔用口语词（呢、嘛、吧、哈），但不要每句都用
- 围绕对方岗位信息（公司、岗位名、JD内容）来聊
- HR问技术就答技术，HR闲聊就闲聊，灵活应对
- 不要每轮都做自我介绍，不要重复寒暄
- 不要用"哈哈，我是真人求职者"这种模板化解释——太假了

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
- 不要在HR没要求时主动发简历/微信/电话"""


def build_agent_context(conversation_id: int, hr_message: str, job_info: dict) -> str:
    """
    构建发送给 Agent 的上下文文本。
    精简版——排期、JD详情等由 Agent 通过工具按需获取。
    """
    parts = []

    # 1. 当前时间
    now = datetime.now()
    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    parts.append(f"当前时间: {now.strftime('%Y-%m-%d %H:%M')} {weekday_cn}")

    # 2. 岗位基本信息
    company = job_info.get("company", "未知")
    title = job_info.get("title", "未知")
    parts.append(f"\n岗位: {title} | 公司: {company}")
    jd = job_info.get("description", "")
    if jd:
        parts.append(f"JD摘要: {jd[:500]}")

    # 3. 简历摘要
    resume = get_setting("resume_summary", "")
    if resume:
        parts.append(f"\n我的简历摘要: {resume}")

    # 4. 聊天历史
    msgs = get_all_messages(conversation_id)
    if msgs:
        parts.append("\n最近的聊天记录:")
        for m in msgs[-10:]:
            sender_label = "HR" if m["sender"] == "hr" else "我"
            parts.append(f"  {sender_label}: {m['content']}")

    # 5. HR 最新消息
    parts.append(f"\nHR刚刚说: {hr_message}")

    parts.append("\n请根据以上上下文，决定是否需要调用工具，然后输出你的最终回复。")

    return "\n".join(parts)


def _parse_final_reply(text: str) -> tuple:
    """
    从 Agent 的最终回复中解析出 reply 文本和 interest 等级。
    支持 [INTEREST: xxx] 标记格式，没有则默认 medium。
    """
    if not text:
        return "", "medium"

    # 提取 interest 标记
    interest = "medium"
    match = re.search(r"\[INTEREST\s*:\s*(high|medium|low)\]", text, re.IGNORECASE)
    if match:
        interest = match.group(1).lower()
        text = re.sub(r"\[INTEREST\s*:\s*(?:high|medium|low)\]", "", text, flags=re.IGNORECASE).strip()

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

    # 构建上下文
    job_info = ctx.get("job_info", {})
    context_text = build_agent_context(conversation_id, hr_message, job_info)

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
            "在回复末尾用 [INTEREST: high/medium/low] 标注HR的兴趣程度。"
        )
        messages.append(force_msg)
        final_response = llm_no_tools.invoke(messages)
        reply, interest = _parse_final_reply(final_response.content or "")
        return reply, interest
    except Exception as e:
        log.error(f"[Agent] 强制输出失败: {e}")
        return "", "medium"
