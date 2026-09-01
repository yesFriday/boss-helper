#!/usr/bin/env python3
"""
AI 回复生成 —— 已改造为 Agent 模式。
generate_reply() 内部调用 agent_loop.run_agent()，
LLM 可以自主决定调用工具（发简历、查排期、约面试等）。
"""

import random
import re
import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "backend" / "interview"))
from llm_client import get_llm

from backend.state import get_all_messages, get_setting
from backend.logger import get_logger

log = get_logger("replier")


# ── Pydantic 输出模型（简化版，Agent 改造后只保留 reply + interest）──
class ReplyOutput(BaseModel):
    """LLM 回复结构体，仅保留核心字段。工具调用由 Agent 循环自主完成。"""

    reply: str = Field(description="回复内容，2-4句话，自然真诚")
    interest: str = Field(description="HR兴趣度评估: high / medium / low")


# ── 输出解析器 ──
output_parser = PydanticOutputParser(pydantic_object=ReplyOutput)

# ── System Prompt（精简版，工具调用逻辑已移至 agent_loop.AGENT_SYSTEM_PROMPT）──
SYSTEM_PROMPT = """你是一个求职者，在BOSS直聘上与招聘方沟通。你要完全以求职者本人的口吻说话。

## 回复原则
- 像真人用手机打字：长度跟随内容——对方说"好的"这种，回一两个词就够；复杂问题最多4句
- 禁用邮件腔："感谢您的告知""期待您的回复""祝您工作顺利"这类话不要出现
- 围绕对方岗位信息来聊，HR问技术就答技术，HR闲聊就闲聊
- 不承诺具体薪资、入职时间
- 不编造不存在的项目经验
- 不要每轮自我介绍，不要重复寒暄
- 如果这条消息不需要回复（对方明确拒绝、纯结束语、再回会显得纠缠），把 reply 字段设为 NO_REPLY

## 被怀疑是AI时
- 用极短口语化解：如"？""真人啊""不是啊"
- 绝对不要长篇解释"我是真人求职者"

{format_instructions}

interest 评估标准：
- high: HR问了技术细节、项目经历、面试时间、要了微信
- medium: HR配合沟通、说"方便""可以""好的""聊聊"
- low: 简单打招呼、敷衍回复、未表现出进一步了解意愿"""


def _encode_wechat(wechat_id: str) -> str:
    """把微信号编码，绕开 BOSS 直聘的聊天内容过滤。"""
    if not wechat_id:
        return ""
    return wechat_id.replace("--", "一一").replace("-", "一")


def build_reply_context(
    conversation_id: int, hr_message: str, job_info: dict, resume_summary: str, wechat_id: str = ""
) -> str:
    """构建发送给 LLM 的上下文文本（简化版，排程等数据由 Agent 按需查询）"""
    from datetime import datetime
    
    parts = []

    # 当前时间
    now = datetime.now()
    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    parts.append(f"当前时间: {now.strftime('%Y-%m-%d %H:%M')} {weekday_cn}")

    # 岗位信息
    parts.append(f"\n岗位: {job_info.get('title', '未知')} | 公司: {job_info.get('company', '未知')}")
    jd = job_info.get("description", "")
    if jd:
        parts.append(f"JD摘要: {jd[:500]}")

    # 简历
    if resume_summary:
        parts.append(f"\n我的简历摘要: {resume_summary}")

    # 聊天记录（展示到「我最后一条消息」为止，待回复块单独放下面，避免重复）
    msgs = get_all_messages(conversation_id)
    if msgs:
        last_me_idx = -1
        for i, m in enumerate(msgs):
            if m["sender"] == "me":
                last_me_idx = i
        history = msgs[: last_me_idx + 1][-10:]
        if history:
            parts.append("\n最近的聊天记录:")
            for m in history:
                sender_label = "HR" if m["sender"] == "hr" else "我"
                parts.append(f"  {sender_label}: {m['content']}")

    parts.append(f"\nHR刚刚说: {hr_message}")

    return "\n".join(parts)


# 简单问候快速回复模板池（不走 LLM）：口语化、不暴露 AI 身份、带变量差异化，
# 避免"所有 HR 收到同一句开场白"的机器人指纹
GREETING_TEMPLATES = [
    "您好，看到贵司在招{title}，正好是我方向的，方便聊聊嘛？",
    "您好呀，{company}的{title}我还挺感兴趣的，可以详细了解下嘛？",
    "hi，刷到{company}这个{title}，感觉挺对口的，想了解下~",
    "您好！{title}这个岗位我看了下，跟我背景挺匹配的，方便沟通一下嘛？",
    "您好，我这边正在看{title}方向的机会，贵司这个岗位还在招嘛？",
    "您好呀，看到{title}这个职位，想深入了解一下，方便的话聊聊呗~",
    "您好，{company}的{title}吸引到我了，方便的话想跟您聊几句。",
    "嗨，您好！对这个{title}岗位挺感兴趣的，看了下要求也比较对口，可以聊聊嘛？",
]


def _quick_greeting(job_info: dict) -> str:
    """从模板池随机挑一条，填入岗位/公司变量做差异化。"""
    title = job_info.get("title") or "这个"
    company = job_info.get("company") or "贵司"
    template = random.choice(GREETING_TEMPLATES)
    return template.format(title=title, company=company)


def generate_reply(
    conversation_id: int,
    hr_message: str,
    job_info: dict,
    style: str = "professional",
    resume_summary: str = "",
    wechat_id: str = "",
    agent_ctx: dict = None,
) -> tuple:
    """
    根据 HR 消息生成 AI 回复和兴趣度评估。
    返回 (reply_text, interest_level, extra_data) 元组。
    
    优先使用 Agent 模式（调用 agent_loop.run_agent），
    当 agent_ctx 未提供时降级为传统 LLM 直接生成模式。
    extra_data 始终为空 dict（Agent 模式下工具调用已在内部完成）。
    """
    if not hr_message or len(hr_message.strip()) < 1:
        return "", "", {}

    # 简单问候 → 模板池快速回复，不走 LLM
    hr_lower = hr_message.strip().lower()
    if hr_lower in (
        "你好", "您好", "hi", "hello", "嗨", "在吗", "在吗？", "在不在", "在不在？",
    ):
        return (_quick_greeting(job_info), "low", {})

    # ── Agent 模式 ──
    if agent_ctx is not None:
        try:
            from backend.agent_loop import run_agent

            style_map = {
                "professional": "自然干练，像同事间发工作消息：直接说事，不客套不啰嗦",
                "casual": "轻松随意，像朋友聊天",
                "enthusiastic": "热情但不夸张，像对机会很感兴趣的正常人",
            }
            agent_ctx["style_hint"] = style_map.get(style, "自然干练，像同事间发工作消息：直接说事，不客套不啰嗦")

            reply, interest = run_agent(conversation_id, hr_message, agent_ctx)
            return reply, interest, {}
        except Exception as e:
            log.error(f"Agent 模式失败，降级到传统模式: {e}", exc_info=True)
            # 继续往下走传统模式

    # ── 传统模式（降级兜底）──
    try:
        context = build_reply_context(conversation_id, hr_message, job_info, resume_summary, wechat_id)

        style_hint = {
            "professional": "自然干练，像同事间发工作消息：直接说事，不客套不啰嗦",
            "casual": "轻松随意，像朋友聊天",
            "enthusiastic": "热情但不夸张，像对机会很感兴趣的正常人",
        }.get(style, "自然干练，像同事间发工作消息：直接说事，不客套不啰嗦")

        system_content = (
            SYSTEM_PROMPT.format(format_instructions=output_parser.get_format_instructions())
            + f"\n\n本次回复风格: {style_hint}"
        )

        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=context),
        ]

        llm = get_llm(temperature=0.7)
        raw = llm.invoke(messages).content

        # 使用 PydanticOutputParser 解析
        try:
            parsed = output_parser.parse(raw)
            reply = parsed.reply.strip()
            interest = parsed.interest.strip().lower()
        except Exception:
            # 正则兜底
            reply = ""
            interest = ""
            m = re.search(r'"reply"\s*:\s*"([^"]*)"', raw)
            if m:
                reply = m.group(1).strip()
            m2 = re.search(r'"interest"\s*:\s*"(\w+)"', raw)
            if m2:
                interest = m2.group(1).strip().lower()

        if interest not in ("high", "medium", "low"):
            interest = "medium"

        # NO_REPLY 透传（LLM 判断不需要回复）
        if reply.strip().upper() == "NO_REPLY":
            from backend.agent_loop import NO_REPLY_MARK

            return NO_REPLY_MARK, interest or "medium", {}

        if not reply or len(reply) < 2:
            if not reply:
                # 原始输出疑似结构化内容(JSON/代码块/思考标记)时绝不能直接发给HR
                stripped = (raw or "").strip()
                looks_structured = (
                    stripped.startswith("{")
                    or stripped.startswith("```")
                    or stripped.startswith("[")
                    or '"reply"' in stripped
                    or "[INTEREST" in stripped
                )
                if looks_structured:
                    log.warning(f"传统模式输出疑似结构化内容，丢弃: {stripped[:80]}")
                    return "", "", {}
                reply = stripped
            if len(reply) < 2:
                return "", "", {}

        if len(reply) > 300:
            reply = reply[:300] + "..."

        # 安全检查
        refusal_patterns = [
            "无法提供", "无法回答", "不能回答", "无法帮助", "爱莫能助",
            "as an AI, I cannot", "I cannot provide",
        ]
        for pattern in refusal_patterns:
            if pattern.lower() in reply.lower():
                return "", "", {}

        return reply, interest, {}

    except Exception as e:
        log.error(f"generate_reply error: {e}", exc_info=True)
        return "", "", {}


def generate_greeting(
    job_title: str, company: str, template: str = "", style: str = "professional"
) -> str:
    """生成打招呼语，支持模板变量替换"""
    if not template:
        template = get_setting(
            "greeting_template",
            "您好，我对贵公司的{job_title}岗位很感兴趣，请问可以详细了解一下吗？",
        )

    greeting = template.replace("{job_title}", job_title).replace("{company}", company)

    if "{job_title}" in greeting or "{company}" in greeting:
        greeting = f"您好，我对贵公司的{job_title}岗位很感兴趣，请问可以详细了解一下吗？"

    return greeting
