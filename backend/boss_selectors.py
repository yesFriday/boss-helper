#!/usr/bin/env python3
"""
boss_selectors.py — 包含 BOSS 直聘的 UI 元素选择器及合并覆盖逻辑。
"""

SELECTORS = {
    "apply_button": [
        'button:has-text("立即沟通")',
        'a:has-text("立即沟通")',
        '[class*="btn-chat"]',
        '[class*="start-chat"]',
        'span:has-text("立即沟通")',
        'div:has-text("立即沟通")',
    ],
    "chat_input": [
        "#chat-input",
        'div[contenteditable="true"]',
        '[class*="chat-input"]',
        '[placeholder*="请输入"]',
        'div.chat-editor',
        'div.boss-chat-editor',
        'textarea[class*="chat"]',
        'textarea[placeholder*="输入"]',
        'div[class*="input-area"]',
    ],
    "chat_send_button": [
        'button[type="send"]',
        ".btn-send",
        'button:has-text("发送")',
        'button[class*="send"]',
    ],
    "conversation_items": [
        'li[role="listitem"]',
        ".friend-content",
        '[class*="chat-item"]',
    ],
    "message_items_in_chat": [
        "li.message-item",
        'li[class*="message-item"]',
        '[class*="message-item"]',
    ],
    "unread_badge": [
        '[class*="unread"]',
        '[class*="badge"]',
        ".red-dot",
    ],
    "greeting_dialog_close": [
        'button[class*="close"]',
        '[class*="dialog-close"]',
        'span:has-text("×")',
        '[class*="modal-close"]',
        'svg[class*="close"]',
    ],
    "resume_attach_btn": [
        # 只匹配工具栏按钮,禁止裸 div/span 文本匹配——否则会点中聊天气泡里的"发简历"字样
        'div.toolbar-btn:has-text("发简历")',
        '[class*="toolbar"] button:has-text("发简历")',
        '.chat-input-area button:has-text("发简历")',
    ],
    "resume_confirm_btn": [
        # 真实 DOM:点「发简历」后,确认 popover 渲染在发简历按钮所在的
        # toolbar-btn-content 容器内,按钮是 <span class="btn-v2 btn-sure-v2">确定</span>
        # (文字是「确定」不是「发送」)。必须限定容器——否则会误中换电话 popover
        # 的「确定」或聊天输入框的「发送」按钮(btn-sure-v2 同名)
        'div.toolbar-btn-content:has(.toolbar-btn:has-text("发简历")) span.btn-sure-v2',
        'div.toolbar-btn-content:has(.toolbar-btn:has-text("发简历")) .btn-v2:not(.btn-outline-v2)',
        # 旧版全局弹窗结构兜底
        ".btn-sure-v2.btn-confirm",
        ".choose-resume-dialog .btn-confirm",
    ],
    "resume_online_option": [
        # 两阶段弹窗(无默认简历/首次发送):先在 select-box 里选「发送在线简历」,
        # 自动流程无法上传附件文件,只能走在线简历
        '.select-box .select-one:has-text("发送在线简历")',
    ],
    "wechat_share_btn": [
        ".btn-weixin",
        'div:has-text("换微信")',
        'span:has-text("换微信")',
        '[class*="btn-weixin"]',
    ],
    "phone_share_btn": [
        ".btn-contact",
        'div:has-text("换电话")',
        'span:has-text("换电话")',
        '[class*="btn-contact"]',
    ],
    "back_to_list": [
        '[class*="back"]',
        'span:has-text("返回")',
        'button:has-text("返回")',
        'a[href*="/chat"]',
    ],
}


def _merge_selectors():
    """合并 settings 表中的选择器覆盖。"""
    try:
        from backend.state import get_setting
        import json as _json

        raw = get_setting("selector_overrides", "")
        if raw:
            overrides = _json.loads(raw)
            for k, v in overrides.items():
                if k in SELECTORS and isinstance(v, list) and len(v) > 0:
                    SELECTORS[k] = v
    except Exception:
        pass


_merge_selectors()
