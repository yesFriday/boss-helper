#!/usr/bin/env python3
"""
AI 回复生成 —— 使用 LangChain 调用大模型为 BOSS直聘聊天生成自动回复。
每次回复同时由 LLM 根据对话上下文评估 HR 兴趣度 (high/medium/low)。

LangChain 重构要点：
- ChatPromptTemplate   → 替代手工拼接字符串
- PydanticOutputParser → 替代手工 json.loads + 正则兜底
- get_llm()            → 替代手工 httpx.post
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "backend" / "interview"))
from llm_client import get_llm

from backend.state import get_all_messages, get_setting, get_upcoming_interviews
from backend.logger import get_logger

log = get_logger("replier")


# ── Pydantic 输出模型 ──
class ReplyOutput(BaseModel):
    """LLM 回复结构体，PydanticOutputParser 自动校验类型"""

    reply: str = Field(description="回复内容，2-4句话，自然真诚")
    interest: str = Field(description="HR兴趣度评估: high / medium / low")
    interview_action: Optional[str] = Field(None, description="如果要敲定面试，输出 'schedule'，否则为 null")
    interview_type: Optional[str] = Field(None, description="面谈形式，线上输出 'online'，线下输出 'offline'，否则为 null")
    interview_time: Optional[str] = Field(None, description="敲定的面试开始时间，格式 YYYY-MM-DD HH:MM，否则为 null")
    interview_duration: Optional[int] = Field(60, description="面试预计时长（分钟），默认为 60。如HR说是短面试输出30，长面试输出90")
    send_resume_action: Optional[bool] = Field(False, description="当且仅当HR在本次消息中明确要求发送简历、作品集或查看简历，且你同意发送时输出 true，否则输出 false。如果HR没有提出或明确表示不要，必须输出 false。")
    share_wechat_action: Optional[bool] = Field(False, description="当且仅当HR在本次消息中明确要求添加微信、换微信、换联系方式，且你同意交换时输出 true，否则输出 false。如果HR没有提出或明确表示不要，必须输出 false。")
    share_phone_action: Optional[bool] = Field(False, description="当且仅当HR在本次消息中明确要求交换电话或手机号，且你同意交换时输出 true，否则输出 false。如果HR没有提出或明确表示不要，必须输出 false。")


# ── 输出解析器（自动注入 JSON Schema 到 System Prompt，自动解析返回值） ──
output_parser = PydanticOutputParser(pydantic_object=ReplyOutput)

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

## 🤖 应对 HR 怀疑是 AI/机器人的规则（极为重要）
当 HR 的最新消息中包含对你是否是 AI、机器人、自动回复的询问或怀疑（例如问：“你是机器人吗？”、“你是AI吗？”、“自动回复？”、“真人吗？”、“真人在聊吗？”、“怎么像机器人”等）：
- **回复准则**：必须表现得像一个真实的人类，产生困惑或用极短、极自然的口语澄清。**绝对不要**用长篇大论解释，不要用任何“哈哈，我是真人求职者，可能刚才回复太正式...”这类公式化、依然带有明显 AI 感的文字。
- **推荐回复方式**：
  - 用人类感到困惑时习惯发的语气词或标点，如：“？”、“啊？”、“哈？真人啊”、“什么AI？”、“真人啊，怎么了”、“？？不是本人吗”等。
  - 回复长度应控制在 1-10 个字内，且要非常口语化。
- **动作参数**：
  - `interest` 评估为 `medium`。
  - `interview_action` 必须为 `null`，其他所有 action（`send_resume_action`、`share_wechat_action`、`share_phone_action`）必须为 `false`。

## 面试处理与自动协调（重要）
当 HR 发起面试邀请，或者你主动跟 HR 预约面试时，请根据求职者的偏好、已有日程进行严密的合理性判定与人性化沟通：

### 🚨 核心冲突校验与沟通规则
1. **面试形式匹配**：
   - 必须优先满足【我的面试形式偏好】。若求职者“仅接受线上面试”，而HR邀请线下面试，你应当温和说明并引导改成视频面试（例如：“因为时间原因，方便咱们先通过视频简单交流一下吗？”）。
2. **时间轴冲突校验（重点）**：
   - 检查 `【当前系统基准时间】` 和 `【求职者未来3天已有面试日程】`，确保没有时间和通勤冲突。
   - **时间段限制**：任何提议或确认的时间，必须落在【我的期望面试时间段】之内（严禁在期望时段外约面）。
   - **同半天线下互斥**：若当天上午（或下午）已有一场“线下（offline）”面试，绝对不能在同个半天答应或约另一场“线下”面试。
   - **时间缓冲与通勤红线**：
     - 若两场均为“线上（online）”面试，两场面试的开始与结束时间必须相隔 60 分钟以上。
     - 若其中有一场或两场是“线下（offline）”面试，两场之间必须留出至少 90 分钟以上 的通勤与缓冲时间！
3. **主动协调机制**：
   - 如果 HR 提出的时间发生上述任何冲突，严禁答应。你必须：
     - ① 委婉解释该时段已有安排。
     - ② 从你的期望时间段中挑选出 1~2 个完全闲置且无冲突的备选时间段，主动询问 HR 的意见；或者询问是否可以切换成更省时间的“线上面试”。
4. **结构化参数输出（严禁抢跑确认）**：
   - 只有当你和 HR 在对话中最终达成一致（例如你提出了两个备选时间，HR说“那就选明天下午三点吧”；或者HR提了时间你检查不冲突并回复“没问题”）时，才能输出 `"interview_action": "schedule"`。
   - 如果只是单方面提议、正在协商、或 HR 没有作出最终确认，`"interview_action"` 必须为 null。

---

### 🟢 合理约面的正面例子（AI 应该模仿的学习对象）：

* **正面例子一：面对同半天线下冲突 ➔ 委婉协商并提供空闲时段**
  - **当前上下文**：
    - 当前系统时间：2026-06-22 09:30 星期一
    - 已有日程：2026-06-23 10:00 至 11:30 (线下) | 字节跳动
    - 偏好时段：上午(9:00-12:00)，下午(14:00-18:00)
    - HR 消息：“我们想约您明天 (23号) 上午 11:00 来我们公司面谈，您看可以吗？”
  - **AI 内部推理**：
    - 23日上午 11:00 属于上午。而已有日程中 23日上午已经有一场线下（字节跳动）。
    - 规则“同半天线下互斥”，不能接受 23日上午的线下面试。
    - 23日下午是空闲的，24日上午也是空闲的。
  - **AI 生成的回复 JSON**：
    ```json
    {{
      "reply": "您好，非常抱歉，我明天上午正好有一场线下面试，时间上有些冲突。您看明天下午 15:00 或者后天上午 10:00 方便吗？或者咱们也可以先通过视频沟通一下，这样效率更高一些。",
      "interest": "high",
      "interview_action": null,
      "interview_type": null,
      "interview_time": null,
      "interview_duration": 60
    }}
    ```
    *(说明：这里因为是协商阶段，HR 尚未做出最终反馈，所以 action 必须为 null。)*

* **正面例子二：无冲突的合理确认 ➔ 锁定日程并输出参数**
  - **当前上下文**：
    - 当前系统时间：2026-06-22 14:00 星期一
    - 已有日程：2026-06-23 14:00 至 15:00 (线上) | 腾讯
    - 偏好时段：上午(9:00-12:00)，下午(14:00-18:00)
    - HR 消息：“好的，那就明天（23号）下午 16:30 准时在线上视频聊聊。”
  - **AI 内部推理**：
    - 23日 16:30 属于下午偏好时间段。
    - 前一场线上 15:00 结束，这一场线上 16:30 开始，相隔 90 分钟，大于线上 60 分钟间隔红线，安全无冲突。
    - HR 作出了肯定的最终确认。
  - **AI 生成的回复 JSON**：
    ```json
    {{
      "reply": "好的，没问题，那就明天下午 16:30 线上视频面试见，期待和您的深入交流！",
      "interest": "high",
      "interview_action": "schedule",
      "interview_type": "online",
      "interview_time": "2026-06-23 16:30",
      "interview_duration": 60
    }}
    ```

* **正面例子三：应对 HR 对 AI 身份的怀疑 ➔ 极其口语化、人类化的极简回复**
  - **当前上下文**：
    - HR 消息：“你是AI吗？回复这么快。”
  - **AI 内部推理**：
    - HR 怀疑是 AI 在聊天。
    - 规则要求不能长句解释，也不能用公式化的“真人求职者”模板，必须像人类一样用极简的语气词澄清。
  - **AI 生成的回复 JSON**：
    ```json
    {{
      "reply": "？真人啊，怎么了",
      "interest": "medium",
      "interview_action": null,
      "interview_type": null,
      "interview_time": null,
      "interview_duration": 60,
      "send_resume_action": false,
      "share_wechat_action": false,
      "share_phone_action": false
    }}
    ```

---

### 🔴 不合理的反面例子（AI 必须严格规避的错误）：

* **反面典型一：无视通勤时间强行确认线下（❌ 大错特错）**
  - **当前上下文**：
    - 已有日程：2026-06-23 10:00 至 11:30 (线上) | A公司
    - HR 消息：“我们希望约您在 23号中午 12:00 来我们公司见个面（线下面试）。”
  - **AI 犯错表现**：
    ```json
    {{
      "reply": "好的，那我明天中午 12:00 到您公司去面试。",
      "interview_action": "schedule",
      "interview_type": "offline",
      "interview_time": "2026-06-23 12:00",
      "interview_duration": 60
    }}
    ```
  - **错误剖析**：第一场 11:30 结束，第二场 12:00 开始（且是线下）。两场间隔仅仅 30 分钟。规则要求包含线下的两场面试必须相隔 90 分钟以上，因为求职者根本无法在 30 分钟内完成线上挂断、出门、通勤并准时到达对方公司，这会导致面试迟到或时间冲突。

* **反面典型二：过早确认或抢跑输出 action（❌ 大错特错）**
  - **当前上下文**：
    - HR 消息：“我们想约您聊一下，您看您哪天方便？”
  - **AI 犯错表现**：
    ```json
    {{
      "reply": "您好，我明天下午 14:00 方便，您看可以吗？",
      "interview_action": "schedule",
      "interview_type": "online",
      "interview_time": "2026-06-23 14:00",
      "interview_duration": 60
    }}
    ```
  - **错误剖析**：HR 只是在询问求职者的意向时间，求职者单方面提出了建议，但 HR 尚未确认并回复同意。此时绝不能抢跑输出 `"interview_action": "schedule"`，否则会导致系统在后台提前锁死该时间段，而一旦 HR 最终不同意该时间，就会导致数据库中产生错误的预约日程。

* **反面典型三：忽略同半天双线下原则（❌ 大错特错）**
  - **当前上下文**：
    - 已有日程：2026-06-23 10:00 至 11:30 (线下) | 百度
    - HR 消息：“我们想约您明天 (23号) 上午 09:00 来我们公司大楼面谈，刚好我们上午有空。”
  - **AI 犯错表现**：
    ```json
    {{
      "reply": "好的，那明天上午 09:00 我准时去贵司面谈。",
      "interview_action": "schedule",
      "interview_type": "offline",
      "interview_time": "2026-06-23 09:00",
      "interview_duration": 60
    }}
    ```
  - **错误剖析**：忽略了“同半天不能有两场线下”的极严格硬性规定。哪怕前一场 10:00 结束，这一场 09:00 结束，它们在物理时间上看似不冲突，但是求职者必须在同一个上午奔波于两家完全不同的公司大楼，极容易造成奔波劳顿和迟到。

* **反面典型四：当被怀疑是AI时给出长篇模板化解释（❌ 大错特错）**
  - **当前上下文**：
    - HR 消息：“你这回复是自动回复吗？感觉是AI。”
  - **AI 犯错表现**：
    ```json
    {{
      "reply": "哈哈，我是真人求职者，可能刚才回复太正式让您误会了。我对贵司的岗位很感兴趣，希望能深入聊聊。",
      "interest": "medium",
      "interview_action": null,
      "interview_type": null,
      "interview_time": null,
      "interview_duration": 60,
      "send_resume_action": false,
      "share_wechat_action": false,
      "share_phone_action": false
    }}
    ```
  - **错误剖析**：虽然回答了“我是真人”，但这种长篇大论、公式化且过于客套的辩解是极其典型的大模型回复风格，HR 一眼就能看出依然是 AI，完全违背了“接近真实人类回复方式”的原则。应该直接回复“？”或“不是啊，怎么了”。

## 触发发送与交换规则（重要）
你可以通过在输出的 JSON 中将 `send_resume_action`、`share_wechat_action`、`share_phone_action` 设为 `true` 来主动控制系统点击发送相关卡片。

### 📄 简历发送 (`send_resume_action`):
- **触发条件**：当且仅当 HR 明确提出要查看简历、作品集或发送简历（如“发份简历吧”、“看看CV”、“作品集发下”），且你同意发送时，输出 `send_resume_action: true`。
- **否定/拒绝判定**：如果 HR 消息中包含否定语义（如“先不要发简历”、“我这里有你简历了，不用再发”），你必须输出 `send_resume_action: false`。
- **文字回复配合**：输出 true 时，在 `reply` 文本中写明 “已通过BOSS把简历发给您了，请查收” 等类似话语。

### 💬 微信交换 (`share_wechat_action`):
- **触发条件**：当且仅当 HR 明确提出想加微信、换微信、换联系方式时（如“加个微信吧”、“换个V”），且你同意交换时，输出 `share_wechat_action: true`。
- **否定/拒绝判定**：如果 HR 表达了否定意图（如“先在BOSS聊，别发微信”、“先不加V”），你必须输出 `share_wechat_action: false`。
- **文字回复配合**：输出 true 时，在 `reply` 文本中说明“我把联系方式通过BOSS发您了”之类的话。**注意：绝对不要在 `reply` 文本里出现 "微信"、"WeChat"、"VX"、"微信号" 这些词，否则BOSS会过滤整条消息。**

### 📞 电话交换 (`share_phone_action`):
- **触发条件**：当且仅当 HR 明确提出需要电话或手机号时（如“电话多少”、“发下手机号”），且你同意交换时，输出 `share_phone_action: true`。
- **否定/拒绝判定**：如果 HR 表示不要或暂不交换电话，输出 `share_phone_action: false`。
- **文字回复配合**：输出 true 时，在 `reply` 文本中说明“我把电话通过BOSS发您了”即可。

### ⚠️ 重要防错准则：
- **不主动、不抢跑**：不要在 HR 没有提出要求、或你没有决定发送的情况下主动将这些 action 设为 true。
- **防重复**：如果通过聊天上下文得知已经完成过交换（例如上一轮刚交换过，或者数据库标志已是已发送），则输出 false，不要重复触发。

{format_instructions}

interest 评估标准（根据完整对话判断HR当前兴趣程度）：
- high: HR问了技术细节、项目经历、面试时间、薪资期望、要了微信、表达了明确合作意向
- medium: HR配合沟通、说"方便""可以""好的""聊聊"、发了JD、问了基本情况
- low: 简单打招呼、摸底试探、回复敷衍、未表现出进一步了解的意愿"""


def _encode_wechat(wechat_id: str) -> str:
    """把微信号编码，绕开 BOSS 直聘的聊天内容过滤。"""
    if not wechat_id:
        return ""
    return wechat_id.replace("--", "一一").replace("-", "一")


def build_reply_context(
    conversation_id: int, hr_message: str, job_info: dict, resume_summary: str, wechat_id: str = ""
) -> str:
    """构建发送给 LLM 的上下文文本，注入系统基准时间及现有面试冲突日程"""
    from datetime import datetime
    
    parts = []

    # 1. 注入当前系统时间与星期几
    now = datetime.now()
    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()]
    time_str = now.strftime("%Y-%m-%d %H:%M")
    parts.append(f"【当前系统基准时间】: {time_str} {weekday_cn}")

    # 2. 注入用户的面试设置偏好
    pref_format = get_setting("interview_format", "both")
    format_cn = {"online": "仅接受线上面试", "offline": "仅接受线下面试", "both": "线上线下均可"}.get(pref_format, "线上线下均可")
    parts.append(f"【我的面试形式偏好】: {format_cn}")
    
    pref_slots_raw = get_setting("interview_time_slots", "上午(9:00-12:00)，下午(14:00-18:00)")
    pref_slots = pref_slots_raw
    try:
        import json
        parsed = json.loads(pref_slots_raw)
        if isinstance(parsed, list):
            formatted = []
            for slot in parsed:
                label = slot.get("label", "").strip()
                start = slot.get("start", "").strip()
                end = slot.get("end", "").strip()
                if start and end:
                    if label:
                        formatted.append(f"{label}({start}-{end})")
                    else:
                        formatted.append(f"{start}-{end}")
            if formatted:
                pref_slots = "，".join(formatted)
    except Exception:
        pass
    parts.append(f"【我的期望面试时间段】: {pref_slots}")

    # 3. 注入未来3天的日程安排
    upcoming = get_upcoming_interviews(days=3)
    parts.append("\n【求职者未来3天已有面试日程（请严格避开冲突）】:")
    if not upcoming:
        parts.append("  (目前未来3天没有任何面试安排，全部时间均为空闲)")
    else:
        for item in upcoming:
            t_type = "线上" if item["interview_type"] == "online" else "线下"
            parts.append(
                f"  - {item['start_time']} 至 {item['end_time']} ({t_type}) | 公司: {item['company']} | 岗位: {item['job_title']}"
            )
            
    parts.append("\n【岗位基本信息】")
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

    msgs = get_all_messages(conversation_id)
    if msgs:
        parts.append("\n最近的对话记录:")
        for m in msgs:
            sender_label = "HR" if m["sender"] == "hr" else "我"
            ai_tag = " [AI代发]" if m.get("ai_generated") else ""
            parts.append(f"  {sender_label}{ai_tag}: {m['content']}")

    parts.append(f"\nHR刚刚说: {hr_message}")

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

    使用 LangChain 输出解析器自动校验 JSON 格式，
    解析失败时降级到正则兜底。
    """
    if not hr_message or len(hr_message.strip()) < 1:
        return "", ""

    hr_lower = hr_message.strip().lower()
    if hr_lower in (
        "你好", "您好", "hi", "hello", "嗨", "在吗", "在吗？", "在不在", "在不在？",
    ):
        company = job_info.get("company", "贵公司")
        title = job_info.get("title", "相关岗位")
        desc_hint = ""
        if job_info.get("description"):
            desc_hint = "，看了下要求感觉挺对口的"
        return (
            f"您好！我对贵司招聘的{title}很感兴趣{desc_hint}，请问方便详细聊聊吗？",
            "low",
            {}
        )

    try:
        context = build_reply_context(conversation_id, hr_message, job_info, resume_summary, wechat_id)

        style_hint = {
            "professional": "语气正式专业",
            "casual": "语气轻松友好",
            "enthusiastic": "语气热情积极",
        }.get(style, "语气正式专业")

        system_content = (
            SYSTEM_PROMPT.format(format_instructions=output_parser.get_format_instructions())
            + f"\n\n本次回复风格: {style_hint}"
        )

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=context),
        ]

        llm = get_llm(temperature=0.7)
        raw = llm.invoke(messages).content

        # ── 使用 PydanticOutputParser 解析 ──
        try:
            parsed = output_parser.parse(raw)
            reply = parsed.reply.strip()
            interest = parsed.interest.strip().lower()
            interview_action = parsed.interview_action.strip().lower() if parsed.interview_action else None
            interview_type = parsed.interview_type.strip().lower() if parsed.interview_type else None
            interview_time = parsed.interview_time.strip() if parsed.interview_time else None
            interview_duration = parsed.interview_duration if parsed.interview_duration else 60
        except Exception:
            # 解析失败 → 正则兜底
            reply = ""
            interest = ""
            interview_action = None
            interview_type = None
            interview_time = None
            interview_duration = 60
            
            m = re.search(r'"reply"\s*:\s*"([^"]*)"', raw)
            if m:
                reply = m.group(1).strip()
            m2 = re.search(r'"interest"\s*:\s*"(\w+)"', raw)
            if m2:
                interest = m2.group(1).strip().lower()
            m3 = re.search(r'"interview_action"\s*:\s*"(\w+)"', raw)
            if m3:
                interview_action = m3.group(1).strip().lower()
            m4 = re.search(r'"interview_type"\s*:\s*"(\w+)"', raw)
            if m4:
                interview_type = m4.group(1).strip().lower()
            m5 = re.search(r'"interview_time"\s*:\s*"([^"]*)"', raw)
            if m5:
                interview_time = m5.group(1).strip()
            m6 = re.search(r'"interview_duration"\s*:\s*(\d+)', raw)
            if m6:
                interview_duration = int(m6.group(1))

        if interest not in ("high", "medium", "low"):
            interest = ""

        if not reply or len(reply) < 2:
            if not reply:
                reply = raw
            if len(reply) < 2:
                return "", "", {}

        if len(reply) > 300:
            reply = reply[:300] + "..."

        # ── 安全检查 ──
        refusal_patterns = [
            "无法提供", "无法回答", "不能回答", "无法帮助", "爱莫能助",
            "as an AI, I cannot", "I cannot provide",
        ]
        for pattern in refusal_patterns:
            if pattern.lower() in reply.lower():
                return "", "", {}

        extra_data = {
            "interview_action": interview_action,
            "interview_type": interview_type,
            "interview_time": interview_time,
            "interview_duration": interview_duration,
        }
        return reply, interest, extra_data

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