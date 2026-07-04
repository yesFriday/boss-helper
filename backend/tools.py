#!/usr/bin/env python3
"""
Agent 工具定义 —— OpenAI function-calling 格式的工具 schema。
供 get_llm_with_tools() 绑定到 LLM，实现 Agent 自主决策调用工具。
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "send_resume",
            "description": "通过BOSS直聘发送附件简历给HR。仅在HR明确要求查看简历、作品集或发简历时调用。如果HR说'先不要发''不用发''已经有了'则不要调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "share_wechat",
            "description": "通过BOSS直聘分享求职者的微信名片给HR。仅在HR明确要求加微信、换联系方式、加个V时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "share_phone",
            "description": "通过BOSS直聘分享求职者的电话号码给HR。仅在HR明确要求电话、手机号时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_schedule",
            "description": "查询求职者未来几天的面试排期，返回已占用的时间段、面试形式偏好、可用的空位建议。在与HR约定面试时间时必须先调用此工具检查冲突。",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "查询未来多少天，默认3天",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_interview",
            "description": "与HR最终确认面试时间后，创建面试日程记录。会自动校验：同半天线下互斥、面试间隔、时间偏好等。如果校验失败会返回具体冲突原因和备选时间。仅在HR明确确认了具体时间后调用，不要在协商阶段抢跑。",
            "parameters": {
                "type": "object",
                "properties": {
                    "interview_type": {
                        "type": "string",
                        "enum": ["online", "offline"],
                        "description": "面试形式",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "面试开始时间，格式YYYY-MM-DD HH:MM",
                    },
                    "duration_min": {
                        "type": "integer",
                        "default": 60,
                        "description": "面试预计时长（分钟），默认60",
                    },
                    "notes": {
                        "type": "string",
                        "description": "备注，如面试地址、联系人等",
                    },
                },
                "required": ["interview_type", "start_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_dangerous",
            "description": "当HR持续怀疑你是AI/机器人且无法消除疑虑时，标记当前会话为风险会话。标记后将永久停止该会话的AI自动回复。仅在HR表达了明确怀疑且你的解释无效时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
