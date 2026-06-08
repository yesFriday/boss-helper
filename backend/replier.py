#!/usr/bin/env python3
"""
AI 回复生成 —— 调用 DeepSeek API 为 BOSS直聘聊天生成自动回复。
每次回复同时由 DeepSeek 根据对话上下文评估 HR 兴趣度 (high/medium/low)。
"""

import json
import sys
from pathlib import Path

# 复用 interview/llm_client.py
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "backend" / "interview"))
from llm_client import llm_chat_deepseek

from backend.state import get_recent_messages, get_setting
from backend.logger import get_logger

log = get_logger("replier")

SYSTEM_PROMPT = """你是一个求职者开发的AI助手，在BOSS直聘上帮他自动与招聘方沟通。

## 核心身份
-带入求职者的身份与hr进行交流，约面试

## 求职者背景（动态适配）
- 根据对方发布的招聘岗位来匹配你的回复侧重点
- 不要硬套一个万能模板：如果对方招的是AI产品经理，就围绕AI产品方向聊；如果招的是大模型开发，就围绕模型/工程方向聊
- 绝不要编造岗位不存在的信息，也不要提到与对方招聘岗位无关的技术领域

## 回复原则
- 2-4句话，自然真诚，不许生硬
- 围绕对方发布的岗位信息（岗位名、公司、JD）来回复
- 主动了解对方岗位的具体要求、技术栈、团队情况
- 回答技术问题时给出专业、具体的内容
- 不承诺薪资、入职时间——"这些可以后续和本人详细聊"
- 不要重复寒暄，不要每一轮都自我介绍

## 面试处理（重要）
- 绝对不要直接同意面试或答应面试时间
- 当HR说"来面试""方便面试吗""什么时候过来"等邀请时，先引导加微信：
  "感谢邀请！方便的话可以先加微信聊聊，让求职者本人跟您沟通会更好，面试的事你们微信上直接定"
- 不要替求职者承诺面试、不要给具体时间

## 触发发送规则（重要）
系统会根据HR的消息内容自动执行以下操作，你只需要在回复中适当提及即可：

### 简历发送
- 当HR明确要求"发简历""看看简历""CV""作品集"时，系统会自动通过BOSS官方「发简历」按钮发送附件简历
- 你只需要回复"已通过BOSS把简历发给您了，请查收"即可
- 绝对不要说"我这边不存储简历""没有简历文件"之类的话

### 微信交换
- 当HR说"加微信""微信聊""加个v""换微信"时，系统会自动通过BOSS官方「换微信」按钮分享求职者微信
- 你只需要回复"我把联系方式通过BOSS发您了"这类话即可
- 绝对不要在文字回复里出现"微信""WeChat""VX""微信号"这些词，BOSS会过滤掉整条消息

### 电话交换
- 当HR说"电话""手机号"时，系统会自动通过BOSS官方「换电话」按钮分享求职者电话
- 你只需要回复"我把电话通过BOSS发您了"即可

### 重要提醒
- 不要在HR没有要求的情况下主动说"已发送"
- 不要重复说"已发送"，如果之前已经发过，就不再提
- 这些操作会在你回复之前执行，所以你说"已发送"时东西确实已经发出去了

## 输出格式（严格JSON）
{"reply": "你的回复内容", "interest": "high/medium/low"}

interest 评估标准（根据完整对话判断HR当前兴趣程度）：
- high: HR问了技术细节、项目经历、面试时间、薪资期望、要了微信、表达了明确合作意向
- medium: HR配合沟通、说"方便""可以""好的""聊聊"、发了JD、问了基本情况
- low: 简单打招呼、摸底试探、回复敷衍、未表现出进一步了解的意愿"""


def _encode_wechat(wechat_id: str) -> str:
    """把微信号编码，绕开 BOSS 直聘的聊天内容过滤。"""
    if not wechat_id:
        return ""
    result = wechat_id
    result = result.replace("--", "一一")
    result = result.replace("-", "一")
    return result


def build_reply_context(
    conversation_id: int, hr_message: str, job_info: dict, resume_summary: str, wechat_id: str = ""
) -> str:
    parts = []

    parts.append(f"招聘方公司: {job_info.get('company', '未知')}")
    parts.append(f"应聘岗位: {job_info.get('title', '未知')}")

    job_desc = job_info.get("description", "")
    if job_desc:
        parts.append(f"岗位描述: {job_desc[:500]}")

    if resume_summary:
        parts.append(f"我的简历摘要: {resume_summary}")

    if wechat_id:
        encoded = _encode_wechat(wechat_id)
        parts.append(f"求职者微信: {wechat_id}（BOSS会过滤微信号，实际发送时请用编码形式: {encoded}，不要发原始形式）")
    else:
        parts.append("求职者微信: 未设置")

    msgs = get_recent_messages(conversation_id, 5)
    if msgs:
        parts.append("\n最近的对话记录:")
        for m in reversed(msgs):
            sender_label = "HR" if m["sender"] == "hr" else "我"
            ai_tag = " [AI代发]" if m.get("ai_generated") else ""
            parts.append(f"  {sender_label}{ai_tag}: {m['content'][:200]}")

    parts.append(f"\nHR刚刚说: {hr_message}")
    parts.append("\n请以JSON格式输出回复和兴趣度: {\"reply\": \"...\", \"interest\": \"high/medium/low\"}")

    return "\n".join(parts)


def generate_reply(
    conversation_id: int,
    hr_message: str,
    job_info: dict,
    style: str = "professional",
    resume_summary: str = "",
    wechat_id: str = "",
) -> tuple:
    """
    根据 HR 消息生成 AI 回复和兴趣度评估。
    返回 (reply_text, interest_level) 元组，失败时返回 ("", "").
    """
    if not hr_message or len(hr_message.strip()) < 1:
        return "", ""

    hr_lower = hr_message.strip().lower()
    if hr_lower in ("你好", "您好", "hi", "hello", "嗨", "在吗", "在吗？", "在不在", "在不在？"):
        company = job_info.get("company", "贵公司")
        title = job_info.get("title", "相关岗位")
        desc_hint = ""
        if job_info.get("description"):
            desc_hint = f"，看了JD感觉挺对口的"
        return (
            f"您好！看到贵司在招{title}，挺感兴趣的{desc_hint}。PS：正在和你聊的这个AI是我自己开发的，算是我的技术名片～",
            "low",
        )

    try:
        context = build_reply_context(conversation_id, hr_message, job_info, resume_summary, wechat_id)

        style_hint = {
            "professional": "语气正式专业",
            "casual": "语气轻松友好",
            "enthusiastic": "语气热情积极",
        }.get(style, "语气正式专业")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + f"\n\n本次回复风格: {style_hint}"},
            {"role": "user", "content": context},
        ]

        raw = llm_chat_deepseek(messages, temperature=0.7)
        raw = raw.strip().strip('"').strip("'").strip()

        reply = ""
        interest = ""
        try:
            parsed = json.loads(raw)
            reply = (parsed.get("reply") or parsed.get("content") or "").strip()
            interest = (parsed.get("interest") or parsed.get("level") or "").strip().lower()
        except json.JSONDecodeError:
            import re
            m = re.search(r'"reply"\s*:\s*"([^"]*)"', raw)
            if m:
                reply = m.group(1).strip()
            m2 = re.search(r'"interest"\s*:\s*"(\w+)"', raw)
            if m2:
                interest = m2.group(1).strip().lower()

        if interest not in ("high", "medium", "low"):
            interest = ""

        if not reply or len(reply) < 2:
            if not reply:
                reply = raw
            if len(reply) < 2:
                return "", ""

        if len(reply) > 300:
            reply = reply[:300] + "..."

        refusal_patterns = [
            "无法提供", "无法回答", "不能回答", "无法帮助", "爱莫能助",
            "as an AI, I cannot", "I cannot provide",
        ]
        for pattern in refusal_patterns:
            if pattern.lower() in reply.lower():
                return "", ""

        return reply, interest

    except Exception as e:
        log.error(f"generate_reply error: {e}", exc_info=True)
        return "", ""


def generate_greeting(
    job_title: str, company: str, template: str = "", style: str = "professional"
) -> str:
    if not template:
        template = get_setting(
            "greeting_template",
            "您好，我对贵公司的{job_title}岗位很感兴趣，请问可以详细了解一下吗？",
        )

    greeting = template.replace("{job_title}", job_title).replace("{company}", company)

    if "{job_title}" in greeting or "{company}" in greeting:
        greeting = f"您好，我对贵公司的{job_title}岗位很感兴趣，请问可以详细了解一下吗？"

    return greeting
