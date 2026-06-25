#!/usr/bin/env python3
"""
BossChatMonitor — 专门负责聊天会话同步、AI 回复决策和消息发送交互。
"""

import json
import random
import re
import time
from typing import List, Optional

from backend.boss_applier import BossApplier
from backend.firefox import pause
from backend.logger import get_logger
from backend.boss_selectors import SELECTORS
from backend.state import (
    list_active_conversations,
    get_or_create_conversation,
    get_conversation,
    replace_conversation_messages,
    update_conversation_last_message,
    update_conversation_wechat,
    get_today_auto_reply_count,
    get_setting,
    get_application,
    add_message,
    increment_daily_stat,
    update_conversation_interest,
)

log = get_logger("boss_chat_monitor")

MAX_AUTO_REPLY_PER_DAY = 200


class BossChatMonitor(BossApplier):
    """聊天监控与自动回复业务类"""

    def navigate_to_chat(self) -> bool:
        """导航到 BOSS 聊天页，切到「未读」标签，只显示有未读消息的会话。"""
        try:
            self.page.goto("https://www.zhipin.com/web/geek/chat", wait_until="load", timeout=45000)
            pause(2, 3)
            # 点击「未读」标签，只显示有未读的会话
            for sel in ['span.label-name:has-text("未读")', 'li:has-text("未读")', '.label-name:has-text("未读")']:
                try:
                    unread_tab = self.page.locator(sel).first
                    if unread_tab.is_visible():
                        unread_tab.click()
                        pause(1, 2)
                        break
                except Exception:
                    pass
            return self.check_page_safety()
        except Exception:
            return False

    def poll_conversation_list(self) -> List[dict]:
        """从 BOSS 聊天页 DOM 获取会话列表。DOM 失败用 body text 正则兜底。"""
        conversations = []

        # 方式1: DOM 选择器
        conv_els = self._find_all_elements(SELECTORS["conversation_items"])
        if conv_els:
            for el in conv_els:
                try:
                    text = el.inner_text().strip()
                    if not text or len(text) < 3:
                        continue
                    # 从 BOSS 真实结构提取 HR 名字: .name-text
                    try:
                        hr_name = el.locator(".name-text").first.inner_text().strip()
                    except Exception:
                        hr_name = ""
                    if not hr_name:
                        # 兜底：从 body_text 行中提取
                        hr_name = (
                            el.evaluate("""(el) => {
                            const lines = (el.innerText||'').split('\\n').map(l=>l.trim()).filter(Boolean);
                            for (const l of lines) {
                                if (/^\\d{1,2}:\\d{2}$/.test(l)) continue;
                                if (/^\\[.+\\]$/.test(l)) continue;
                                const ch = l.replace(/[^\\u4e00-\\u9fff]/g,'');
                                if (ch.length>=2 && ch.length<=5) return l.split(/[\\s|·]/)[0].trim();
                            }
                            return '';
                        }""")
                            or ""
                        )
                    has_unread = False
                    try:
                        badge = el.locator('.red-dot, [class*="unread"]').first
                        has_unread = badge.is_visible()
                    except Exception:
                        pass
                    conversations.append(
                        {
                            "text": text,
                            "has_unread": has_unread,
                            "element": el,
                            "hr_name": hr_name,
                        }
                    )
                except Exception:
                    continue

        # 方式2: body text 正则兜底
        if not conversations:
            try:
                body = self.page.inner_text("body") or ""
                pattern = r"(\d{1,2}:\d{2})\s+([\u4e00-\u9fff\w·]+?)\s+(\[\s*\S+\s*\])\s+(.+?)(?=\s*\d{1,2}:\d{2}\s+|没有更多了|\Z)"
                for m in re.findall(pattern, body):
                    time_str, name_block, status, msg = m
                    # 提取纯名字：从 name_block 中去掉公司后缀
                    hr_name = re.sub(
                        r"[\u4e00-\u9fff]{2,}(?:有限|集团|科技|网络|信息|文化|教育|医疗|能源|贸易|实业|发展|控股|投资).*|经理.*|主管.*|专员.*|总监.*|[\[\]].*",
                        "",
                        name_block,
                    ).strip()
                    if not hr_name or len(hr_name) < 2:
                        m2 = re.match(r"^[\u4e00-\u9fff]{2,4}", name_block)
                        hr_name = m2.group(0) if m2 else name_block[:6]
                    hr_name = hr_name.strip()
                    if not hr_name or len(hr_name) < 2:
                        continue
                    conversations.append(
                        {
                            "text": f"{time_str}\n{name_block}\n{status}\n{msg}".strip(),
                            "has_unread": "未读" in status,
                            "element": None,
                            "hr_name": hr_name,
                        }
                    )
            except Exception:
                pass

        return conversations

    def read_visible_messages(self) -> List[dict]:
        """读取当前右侧聊天窗口中的可见消息，避免把左侧会话列表误当聊天内容。"""
        try:
            raw = self.page.evaluate("""() => {
                const result = [];
                const vw = window.innerWidth || 1200;
                const visible = el => {
                    const r = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                };
                const clean = text => (text || '')
                    .replace(/^(已读|未读|送达|发送失败|已发送)\\s*/g, '')
                    .replace(/\\n?(已读|未读|送达|发送失败|已发送)$/g, '')
                    .trim();
                const pickStatus = text => {
                    const m = (text || '').match(/(^|\\n)\\s*(已读|未读|送达|发送失败|已发送)\\s*(\\n|$)/);
                    return m ? m[2] : '';
                };
                const push = (el, contentEl) => {
                    if (!visible(el)) return;
                    const r = el.getBoundingClientRect();
                    if (r.left + r.width / 2 < vw * 0.35) return;
                    const textNode = contentEl || el.querySelector('.text p, .text span:last-child, .text, [class*="bubble"], [class*="content"]');
                    const fullText = el.innerText || '';
                    const content = clean(textNode ? textNode.innerText : el.innerText);
                    if (!content || /^(已读|未读|送达|发送失败|已发送)$/.test(content)) return;
                    if (content.length > 1000) return;
                    const cls = el.className || '';
                    const sender = cls.includes('item-myself') || cls.includes('myself') || cls.includes('self') || r.left > vw * 0.52 ? 'me' : 'hr';
                    const status = sender === 'me' ? pickStatus(fullText) : '';
                    result.push({sender: sender, content: content, status: status});
                };

                document.querySelectorAll('li.message-item, li[class*="message-item"]').forEach(el => push(el));
                if (result.length === 0) {
                    document.querySelectorAll('[class*="message"] [class*="bubble"], [class*="msg"] [class*="bubble"], [class*="chat"] [class*="text"]').forEach(el => push(el, el));
                }
                return result;
            }""")
            return raw or []
        except Exception:
            return []

    def open_conversation_by_name(self, hr_name: str) -> bool:
        """在聊天页中按 HR 名字定位并打开对应会话。"""
        try:
            current_url = self.page.url
            if "/web/geek/chat" not in current_url:
                self.page.goto("https://www.zhipin.com/web/geek/chat", wait_until="load", timeout=45000)
                pause(2, 3)

            # 优先用 Playwright 文本选择器点击列表项。BOSS 的左栏布局会随宽度变化，不能强依赖元素在屏幕左半边。
            for sel in [
                f'li[role="listitem"]:has-text("{hr_name}")',
                f'.user-list li:has-text("{hr_name}")',
                f'[class*="friend"]:has-text("{hr_name}")',
                f'text="{hr_name}"',
            ]:
                try:
                    loc = self.page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        loc.click(force=True, timeout=3000)
                        pause(1, 2)
                        return True
                except Exception:
                    pass

            # 兜底：在 DOM 中找包含 HR 名的最小可点击会话容器并触发点击。
            clicked = self.page.evaluate(
                """(name) => {
                    const visible = el => {
                        const r = el.getBoundingClientRect();
                        const s = getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                    };
                    const candidates = [];
                    const selectors = [
                        '.user-list li', 'li[role="listitem"]', '.friend-content',
                        '[class*="friend"]', '[class*="conversation"]', '[class*="chat-item"]'
                    ];
                    document.querySelectorAll(selectors.join(',')).forEach(el => {
                        const text = (el.innerText || '');
                        if (text.length < 3 || text.length > 200) return;
                        if (!text.includes(name)) return;
                        if (!visible(el)) return;
                        const rect = el.getBoundingClientRect();
                        const nameEl = el.querySelector('.name-text, [class*="name"]');
                        const nameText = (nameEl && nameEl.innerText || '').trim();
                        const exact = nameText === name || text.split('\\n').some(line => line.trim() === name);
                        candidates.push({el: el, exact: exact ? 1 : 0, area: rect.width * rect.height, top: rect.top});
                    });
                    candidates.sort((a,b) => b.exact - a.exact || a.area - b.area || a.top - b.top);
                    for (const c of candidates) {
                        try {
                            c.el.scrollIntoView({block: 'center'});
                            const r = c.el.getBoundingClientRect();
                            const opts = {bubbles: true, cancelable: true, view: window, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2};
                            c.el.dispatchEvent(new MouseEvent('mousedown', opts));
                            c.el.dispatchEvent(new MouseEvent('mouseup', opts));
                            c.el.dispatchEvent(new MouseEvent('click', opts));
                            return true;
                        } catch(e) {}
                    }
                    return false;
                }""",
                hr_name,
            )
            if clicked:
                pause(1, 2)
                return True
            return False
        except Exception as e:
            log.error(f"打开会话失败 ({hr_name}): {e}", exc_info=True)
            return False

    def send_message(self, text: str, fast: bool = True) -> bool:
        """逐字模拟键盘输入 + Enter 发送，确保 BOSS 检测到输入事件。"""
        try:
            # 点击输入框激活
            try:
                self.page.locator("#chat-input").first.click()
                time.sleep(0.15)
            except Exception:
                try:
                    self.page.locator('[contenteditable="true"]').first.click()
                    time.sleep(0.15)
                except Exception:
                    pass

            # 清除已有内容
            try:
                self.page.keyboard.press("Control+a")
                time.sleep(0.05)
                self.page.keyboard.press("Backspace")
                time.sleep(0.05)
            except Exception:
                pass

            # 逐字键入，模拟真人打字
            delay = 20 if fast else 40
            self.page.keyboard.type(text, delay=delay)
            pause(0.3, 0.6)

            # 按 Enter 发送
            self.page.keyboard.press("Enter")
            pause(0.5, 1)

            # 验证：消息区出现了刚发的文本
            body = self.page.inner_text("body")
            check = text[:8] if len(text) >= 8 else text[:4]
            if check in body:
                return True

            # 再试一次 Enter
            try:
                self.page.keyboard.press("Enter")
                pause(0.3, 0.5)
                return True
            except Exception:
                pass

            return False
        except Exception as e:
            log.error(f"send_message 失败: {e}", exc_info=True)
            return False

    def _get_chat_security_id(self, hr_name: str = "") -> str:
        """从 BOSS API 或页面提取对方 securityId。"""
        for attempt in range(3):  # 重试3次
            try:
                # 方式1: 页面 HTML 正则搜
                html = self.page.content()
                m = re.search(r'securityId["\']?\s*[:=]\s*["\']([A-Za-z0-9_~+/=-]{30,})["\']', html)
                if m:
                    return m.group(1)

                # 方式2: JS 全局对象
                sid = self.page.evaluate("""() => {
                    for (const key of Object.keys(window)) {
                        try {
                            const v = window[key];
                            if (!v || typeof v !== 'object') continue;
                            if (v.securityId) return v.securityId;
                        } catch(e) {}
                    }
                    return '';
                }""")
                if sid:
                    return sid

                # 方式3: BOSS API 获取会话列表, 按 HR 名匹配
                encrypt_id = ""
                try:
                    encrypt_id = self.page.evaluate("""() => {
                        for (const key of Object.keys(window)) {
                            try { if (window[key] && window[key].encryptSystemId) return window[key].encryptSystemId; } catch(e) {}
                        }
                        return '';
                    }""")
                except Exception:
                    pass

                if encrypt_id and hr_name:
                    url = f"https://www.zhipin.com/wapi/zprelation/friend/geekFilterByLabel?labelId=0&encryptSystemId={encrypt_id}"
                    data = self.page.evaluate(
                        """async (url) => {
                        const r = await fetch(url, {headers:{'Accept':'application/json','x-requested-with':'XMLHttpRequest'}, credentials:'include'});
                        return await r.json();
                    }""",
                        url,
                    )
                    friends = (data or {}).get("zpData", {}).get("friends", [])
                    for f in friends:
                        fn = (f.get("bossName") or f.get("realName") or "").strip()
                        if fn == hr_name:
                            return f.get("securityId", "")

                if attempt < 2:
                    log.debug(f"[securityId] 第{attempt + 1}次获取失败，重试...")
                    pause(1, 2)

            except Exception as e:
                log.error(f"[securityId] 获取异常: {e}", exc_info=True)
                if attempt < 2:
                    pause(1, 2)

        log.warning(f"securityId 获取失败（3次重试），HR: {hr_name}")
        return ""

    def send_wechat(self, hr_name: str = "") -> bool:
        """通过 BOSS API 发起交换，等弹窗出现后点「确定」。"""
        try:
            sid = self._get_chat_security_id(hr_name)

            if sid:
                self.page.evaluate(
                    """
                    async (sid) => {
                        await fetch('https://www.zhipin.com/wapi/zpchat/exchange/test', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/x-www-form-urlencoded', 'x-requested-with': 'XMLHttpRequest'},
                            body: 'securityId=' + encodeURIComponent(sid) + '&type=2&friendSource=0',
                            credentials: 'include',
                        });
                    }
                """,
                    sid,
                )
                log.info("[换微信] API /exchange/test 已调用")
            else:
                btn = self._find_element(SELECTORS["wechat_share_btn"], timeout_ms=5000)
                if not btn:
                    log.warning("send_wechat: 无法获取 securityId 且未找到按钮")
                    return False
                btn.click()
                log.info("[换微信] 已点击换微信按钮")

            # 等弹窗 → 点「确定」
            confirm_clicked = self.page.evaluate("""() => {
                return new Promise((resolve) => {
                    let tries = 0;
                    const check = () => {
                        // 先找「确定与对方交换微信吗？」弹窗里的确定按钮
                        const btns = document.querySelectorAll('span');
                        for (const b of btns) {
                            if (b.innerText.trim() === '确定' && b.offsetParent !== null) {
                                const parent = b.closest('.secure-exchange, .sentence-popover, [class*="exchange"], [class*="popover"]');
                                if (parent) {
                                    b.click();
                                    resolve(true);
                                    return;
                                }
                            }
                        }
                        // 兜底：任何可见的"确定"按钮
                        const all = document.querySelectorAll('.btn-sure-v2, span');
                        for (const el of all) {
                            if (el.innerText.trim() === '确定' && el.offsetParent !== null && !el.closest('.btn-outline-v2')) {
                                el.click();
                                resolve(true);
                                return;
                            }
                        }
                        if (++tries < 30) setTimeout(check, 300);
                        else resolve(false);
                    };
                    check();
                });
            }""")
            if confirm_clicked:
                pause(0.5, 1)
                log.info("[换微信] 已点确定按钮")
                return True

            log.warning("[换微信] 超时: 未找到确定按钮")
            return False

        except Exception as e:
            log.error(f"send_wechat 失败: {e}", exc_info=True)
            return False

    def send_phone(self, hr_name: str = "") -> bool:
        """通过 BOSS API 交换手机号（type=1），等弹窗出现后点「确定」。"""
        try:
            sid = self._get_chat_security_id(hr_name)

            if sid:
                self.page.evaluate(
                    """
                    async (sid) => {
                        await fetch('https://www.zhipin.com/wapi/zpchat/exchange/test', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/x-www-form-urlencoded', 'x-requested-with': 'XMLHttpRequest'},
                            body: 'securityId=' + encodeURIComponent(sid) + '&type=1&friendSource=0',
                            credentials: 'include',
                        });
                    }
                """,
                    sid,
                )
                log.info("[换电话] API /exchange/test (type=1) 已调用")
            else:
                btn = self._find_element(SELECTORS["phone_share_btn"], timeout_ms=5000)
                if not btn:
                    log.warning("send_phone: 无法获取 securityId 且未找到按钮")
                    return False
                btn.click()
                log.info("[换电话] 已点击换电话按钮")

            # 等弹窗 → 点「确定」
            confirm_clicked = self.page.evaluate("""() => {
                return new Promise((resolve) => {
                    let tries = 0;
                    const check = () => {
                        const btns = document.querySelectorAll('span');
                        for (const b of btns) {
                            if (b.innerText.trim() === '确定' && b.offsetParent !== null) {
                                const parent = b.closest('.secure-exchange, .sentence-popover, .panel-contact, [class*="exchange"], [class*="popover"]');
                                if (parent) {
                                    b.click();
                                    resolve(true);
                                    return;
                                }
                            }
                        }
                        const all = document.querySelectorAll('.btn-sure-v2, span');
                        for (const el of all) {
                            if (el.innerText.trim() === '确定' && el.offsetParent !== null && !el.closest('.btn-outline-v2')) {
                                el.click();
                                resolve(true);
                                return;
                            }
                        }
                        if (++tries < 30) setTimeout(check, 300);
                        else resolve(false);
                    };
                    check();
                });
            }""")
            if confirm_clicked:
                pause(0.5, 1)
                log.info("[换电话] 已点确定按钮")
                return True

            log.warning("[换电话] 超时: 未找到确定按钮")
            return False

        except Exception as e:
            log.error(f"send_phone 失败: {e}", exc_info=True)
            return False

    def send_resume(self) -> bool:
        """点击「发简历」按钮，等弹窗后点「发送」确认。"""
        try:
            btn = self._find_element(SELECTORS["resume_attach_btn"], timeout_ms=5000)
            if not btn:
                log.warning("send_resume: 未找到发简历按钮")
                return False
            btn.click()
            log.info("[发简历] 已点击发简历按钮")
            pause(1, 2)

            # 等弹窗出现 → 点「发送」按钮
            confirm = self._find_element(SELECTORS["resume_confirm_btn"], timeout_ms=5000)
            if confirm:
                confirm.click()
                pause(0.5, 1)
                log.info("[发简历] 已点发送按钮")
                return True

            # 兜底：无弹窗但已点击
            log.info("[发简历] 无弹窗，直接完成")
            return True
        except Exception as e:
            log.error(f"send_resume 失败: {e}", exc_info=True)
            return False

    # ══════════════════════════════════════
    #  监控周期（供后台循环调用）
    # ══════════════════════════════════════

    def run_chat_monitor_cycle(self) -> dict:
        """
        一个完整的监控周期:
        1. 导航到聊天页
        2. 扫描未读会话
        3. 对每个未读会话: 打开→读消息→存库→AI回复
        """
        result = {"checked": 0, "new_messages": 0, "replies_sent": 0}

        # 只在不在聊天页时才导航（避免每轮刷新页面，触发 BOSS 登录检查）
        current_url = self.page.url
        need_nav = "/web/geek/chat" not in current_url
        if need_nav:
            if not self.navigate_to_chat():
                log.info("[监控] 导航到聊天页失败")
                return result
        else:
            # 已在聊天页，轻量点击「未读」Tab 即可
            for sel in ['span.label-name:has-text("未读")', '.label-name:has-text("未读")']:
                try:
                    tab = self.page.locator(sel).first
                    if tab.is_visible():
                        tab.click()
                        pause(0.5, 1)
                        break
                except Exception:
                    pass

        if not self.check_page_safety():
            log.warning("[监控] 安全检查未通过（登录过期/验证码等）")
            return result

        conversations = self.poll_conversation_list()
        result["checked"] = len(conversations)
        log.info(f"[监控] 扫描到 {len(conversations)} 个会话")
        # 始终打印 body 内容用于调试
        try:
            preview = (self.page.inner_text("body") or "")[:800].replace("\n", " | ")
            log.debug(f"[监控] Body: {preview}")
        except Exception:
            pass

        known_convs = list_active_conversations()
        log.info(f"[监控] 数据库已知活跃会话: {len(known_convs)}")

        # 已在导航时切到「未读」Tab，当前列表都是未读。每轮上限 3 个
        if not conversations:
            log.info("[监控] 无未读消息，跳过本轮")
            return result
        if len(conversations) > 3:
            log.info(f"[监控] 未读会话: {len(conversations)} 个，本轮只处理前3个")
            conversations = conversations[:3]

        for conv_data in conversations:
            text = conv_data.get("text", "")
            has_unread = conv_data.get("has_unread", False)
            element = conv_data.get("element")

            if not text:
                continue

            # 尝试匹配已知会话：用提取的 HR 名字精确匹配
            matched_conv = None
            extracted_name = conv_data.get("hr_name", "")
            for kc in known_convs:
                kc_name = kc.get("hr_name", "")
                if kc_name and extracted_name and kc_name == extracted_name:
                    matched_conv = kc
                    break

            if not matched_conv:
                for kc in known_convs:
                    kc_name = kc.get("hr_name", "")
                    if kc_name and len(kc_name) >= 3 and kc_name in text:
                        matched_conv = kc
                        break

            if not matched_conv:
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                hr_name = conv_data.get("hr_name", "") or lines[0] if lines else ""
                hr_name = hr_name[:20] if len(hr_name) > 20 else hr_name

                # 过滤无效名称
                skip_keywords = [
                    "消息",
                    "联系人",
                    "沟通",
                    "设置",
                    "搜索",
                    "我的",
                    "首页",
                    "已沟通",
                    "继续沟通",
                    "新对话",
                    "系统",
                    "通知",
                    "BOSS",
                    "在线",
                    "离线",
                    "刚刚",
                    "分钟",
                    "小时",
                    "昨天",
                    "简历",
                    "附件",
                    "上传",
                    "制作",
                    "更新",
                    "AI",
                ]
                is_valid = (
                    hr_name
                    and len(hr_name) >= 2
                    and not hr_name.isdigit()
                    and not any(kw == hr_name for kw in skip_keywords)
                    and not any(kw in hr_name and len(hr_name) <= len(kw) + 1 for kw in skip_keywords)
                )
                if not is_valid:
                    log.debug(f"[监控] 跳过无效会话名: '{hr_name}' (原文: {text[:50]})")
                    continue

                conv_id = get_or_create_conversation(
                    None, hr_name, conv_data.get("company", ""), conv_data.get("job_title", "")
                )
                known_convs = list_active_conversations()
                matched_conv = get_conversation(conv_id)
                if not matched_conv:
                    continue
                log.info(f"[监控] 新建会话: {hr_name}")
                # 标记用于 WebSocket 广播
                result.setdefault("new_conversations", []).append(hr_name)
            else:
                conv_id = matched_conv["id"]
                # 提取的名字比 DB 更精确时自动修正
                if extracted_name and len(extracted_name) >= 2:
                    old_name = matched_conv.get("hr_name", "")
                    if old_name != extracted_name and (
                        old_name in extracted_name or extracted_name in old_name or len(extracted_name) < len(old_name)
                    ):
                        try:
                            from backend.state import get_db as _gdb2

                            _gdb2().execute("UPDATE conversations SET hr_name=? WHERE id=?", (extracted_name, conv_id))
                            _gdb2().commit()
                            matched_conv["hr_name"] = extracted_name
                        except Exception:
                            pass

            # 从会话文本里提取公司名（格式：HR名+公司名+岗位）
            if not matched_conv.get("hr_company"):
                company_info = text.split("\n")[0] if "\n" in text else text
                import re as _re3

                hr_name_part = matched_conv.get("hr_name", "")
                if hr_name_part and len(hr_name_part) >= 2:
                    company_info = company_info.replace(hr_name_part, "", 1)
                # 去掉时间/状态/括号等
                company_info = _re3.sub(r"\d{1,2}:\d{2}|\[.*?\]|送达|已读|未读", "", company_info)
                # 提取公司名（纯中文 4-12字）
                m = _re3.search(r"[\u4e00-\u9fa5]{4,12}", company_info)
                if m:
                    company = m.group()
                    try:
                        from backend.state import get_db as _gdb3

                        _gdb3().execute("UPDATE conversations SET hr_company=? WHERE id=?", (company, conv_id))
                        _gdb3().commit()
                        matched_conv["hr_company"] = company
                        log.info(f"[监控] 提取公司名: {company}")
                    except Exception:
                        pass

            if matched_conv.get("status") != "active":
                continue
            if not matched_conv.get("auto_reply_enabled"):
                continue
            if matched_conv.get("is_dangerous"):
                log.info(f"[监控] 会话 {matched_conv.get('hr_name')} 已标记为风险会话，跳过")
                continue

            # 读取消息：打开会话从 DOM 提取
            hr_name_to_open = matched_conv["hr_name"]
            opened = self.open_conversation_by_name(hr_name_to_open)
            if not opened and len(hr_name_to_open) > 4:
                short = re.match(r"^[\u4e00-\u9fff]{2,3}", hr_name_to_open)
                if short:
                    opened = self.open_conversation_by_name(short.group(0))
            if not opened:
                log.info(f"[监控] 无法打开会话: {hr_name_to_open}")
                continue
            pause(1, 2)
            msgs = self.read_visible_messages()
            log.info(f"[监控] 会话 {matched_conv.get('hr_name')}: 读到 {len(msgs)} 条消息")

            new_count = 0
            clean_msgs = []
            for msg in msgs:
                sender = msg.get("sender", "hr")
                content = (msg.get("content") or "").strip()
                if not content:
                    continue
                clean_msgs.append({"sender": sender, "content": content, "status": msg.get("status", "")})

            if clean_msgs:
                replace_conversation_messages(conv_id, clean_msgs)
                last_msg = clean_msgs[-1]
                update_conversation_last_message(conv_id, last_msg["content"], last_msg["sender"], 0)

                # 从 HR 消息里提取微信号
                if not matched_conv.get("hr_wechat"):
                    import re as _re

                    for m in clean_msgs:
                        if m["sender"] == "hr":
                            patterns = [
                                # wxid_xxxxxxxx 格式
                                r"(?:wxid|WXID)[_\-]?\s*[:：]?\s*([a-zA-Z0-9_-]{6,30})",
                                # 微信/VX/WeChat：xxx 格式
                                r"(?:微信|VX|vx|wechat|WeChat)[号：:]*\s*[:：]?\s*([a-zA-Z0-9_-]{4,30})",
                                # 加我/加V -> xxx
                                r"(?:加我|加V|找V|加个V)\s*[:：]?\s*([a-zA-Z0-9_-]{4,30})",
                                # 微信号 xxx（纯中文前缀）
                                r"\u5fae\u4fe1\u53f7\s+([a-zA-Z0-9_-]{4,30})",
                            ]
                            for pat in patterns:
                                match = _re.search(pat, m["content"])
                                if match:
                                    wx_id = match.group(1).strip()
                                    if wx_id and len(wx_id) >= 5:
                                        update_conversation_wechat(conv_id, wx_id)
                                        matched_conv["hr_wechat"] = wx_id
                                        result["wechat_exchanged"] = True
                                        log.info(f"[监控] 提取HR微信: {wx_id}")
                                        break

            # 检测需要回复的 HR 消息：仅跳过纯 BOSS 系统通知（<80字且以系统模式开头）
            def _is_system_notification(content):
                content = content.strip()
                if len(content) > 80:
                    return False
                patterns = (
                    "你与该职位竞争者PK情况",
                    "竞争力分析",
                    "BOSS安全提示",
                    "系统消息",
                    "沟通分析",
                    "今日推荐",
                    "该Boss已查看了你的简历",
                )
                return any(content.startswith(p) for p in patterns)

            unreplied_hr_msg = None
            for i in range(len(clean_msgs) - 1, -1, -1):
                m = clean_msgs[i]
                if m["sender"] == "me":
                    continue
                if _is_system_notification(m["content"]):
                    continue
                # HR 消息
                has_reply_after = any(clean_msgs[j]["sender"] == "me" for j in range(i + 1, len(clean_msgs)))
                if not has_reply_after:
                    unreplied_hr_msg = m["content"]
                    new_count = 1
                    log.info(f"[监控] 待回复HR消息: {m['content'][:60]}...")
                break

            if unreplied_hr_msg:
                result["new_messages"] += 1

            # 自动回复
            auto_reply_enabled = get_setting("auto_reply_enabled", "true") == "true"
            if unreplied_hr_msg and auto_reply_enabled:
                today_replies = get_today_auto_reply_count()
                if today_replies >= MAX_AUTO_REPLY_PER_DAY:
                    continue

                try:
                    from backend.replier import generate_reply

                    job_title = matched_conv.get("job_title", "")
                    job_company = matched_conv.get("hr_company", "")
                    job_desc = ""
                    app_id = matched_conv.get("application_id")
                    if app_id:
                        app = get_application(app_id)
                        if app:
                            job_desc = app.get("description") or ""
                            job_title = job_title or app.get("job_title", "")
                            job_company = job_company or app.get("company", "")

                    job_info = {
                        "title": job_title,
                        "company": job_company,
                        "description": job_desc,
                    }
                    style = get_setting("ai_reply_style", "professional")
                    resume = get_setting("resume_summary", "")
                    wechat = get_setting("wechat_id", "")

                    reply, interest, extra_data = generate_reply(conv_id, unreplied_hr_msg, job_info, style, resume, wechat)
                    if reply:
                        # 🆕 面试自动排程与冲突校验引擎 🆕
                        if extra_data.get("interview_action") == "schedule":
                            itype = extra_data.get("interview_type")
                            itime = extra_data.get("interview_time")
                            idur = extra_data.get("interview_duration", 60)
                            
                            from backend.state import validate_and_add_interview
                            success, err_msg = validate_and_add_interview(conv_id, itype, itime, idur)
                            
                            if not success:
                                log.warning(f"[排程] 拟约定面试 ({itype}, {itime}) 规则校验失败: {err_msg}。发起自动二次协商重算...")
                                re_prompt = (
                                    f"【面试排程冲突】你刚才向HR提议或确认在 {itime} 进行 {itype} 面试，"
                                    f"但由于时间冲突未能成功预约，原因为: {err_msg}。\n"
                                    f"请重新生成一条回复，并避开这个时间段，另外挑选一个完全符合偏好且闲置的时间段推荐给HR。"
                                )
                                # 调用 AI 进行回炉重构
                                reply, interest, extra_data = generate_reply(conv_id, re_prompt, job_info, style, resume, wechat)
                                
                                # 二次校验（仅尝试协商一次，避免死循环）
                                if extra_data.get("interview_action") == "schedule":
                                    itype = extra_data.get("interview_type")
                                    itime = extra_data.get("interview_time")
                                    idur = extra_data.get("interview_duration", 60)
                                    success, err_msg = validate_and_add_interview(conv_id, itype, itime, idur)
                                    if not success:
                                        log.warning(f"[排程] 二次排程校验依然失败: {err_msg}。本次取消自动建单，仅发送聊天内容。")
                                        extra_data["interview_action"] = None
                            
                            # 如果最终校验通过，向前端广播通知
                            if extra_data.get("interview_action") == "schedule" and success:
                                log.info(f"[排程] 恭喜！已自动为您约好一场面试 ({itype}, {itime})。")
                                try:
                                    from backend.app import broadcast_ws
                                    import asyncio
                                    asyncio.create_task(broadcast_ws({
                                        "type": "interview_scheduled",
                                        "company": job_company or matched_conv.get("hr_company", "未知"),
                                        "job_title": job_title or matched_conv.get("job_title", "未知"),
                                        "time": itime,
                                        "format": "线上" if itype == "online" else "线下"
                                    }))
                                except Exception as be:
                                    log.error(f"WebSocket 广播面试通知失败: {be}")

                        # 先执行发送操作（简历/微信/电话），根据 AI 大模型决策的意图执行
                        
                        # 发简历
                        if extra_data.get("send_resume_action") is True:
                            if not matched_conv.get("resume_sent"):
                                log.info("[监控] AI 决定发送简历，正在发送...")
                                if self.send_resume():
                                    from backend.state import mark_resume_sent

                                    mark_resume_sent(conv_id)
                                    pause(1, 2)

                        # 换微信
                        if extra_data.get("share_wechat_action") is True:
                            if not matched_conv.get("hr_wechat"):
                                log.info("[监控] AI 决定分享微信，正在发送...")
                                self.send_wechat(hr_name_to_open)
                                pause(1, 2)

                        # 换电话
                        if extra_data.get("share_phone_action") is True:
                            if not matched_conv.get("phone_shared"):
                                log.info("[监控] AI 决定分享电话，正在发送...")
                                if self.send_phone(hr_name_to_open):
                                    from backend.state import mark_phone_shared

                                    mark_phone_shared(conv_id)
                                    pause(1, 2)

                        # 然后再发送AI回复
                        log.info(f"[监控] AI回复: {reply[:60]}...")
                        if self.send_message(reply):
                            add_message(conv_id, "me", reply, ai_generated=True)
                            update_conversation_last_message(conv_id, reply, "me", 0)
                            increment_daily_stat("auto_replies_sent")
                            result["replies_sent"] += 1
                            if interest:
                                update_conversation_interest(conv_id, interest)
                                log.info(f"[监控] HR兴趣度: {interest}")
                            log.info("[监控] 回复已发送")
                            # 风险会话检测：AI判定为危险则标记并永久停止后续监控
                            if extra_data.get("danger_flag"):
                                log.warning(f"[监控] ⚠️ 检测到风险会话: {matched_conv.get('hr_name')}，AI回复已发送，后续将永久跳过")
                                from backend.state import mark_conversation_dangerous
                                mark_conversation_dangerous(conv_id)
                        else:
                            log.warning("[监控] 回复发送失败!")
                        pause(5, 15)
                except Exception as e:
                    log.error(f"AI回复生成失败: {e}", exc_info=True)
            elif unreplied_hr_msg and not auto_reply_enabled:
                log.info("[监控] 自动回复已关闭，跳过")

            # 下一个会话前确保输入框已清空，避免残留文字
            try:
                input_el = self.page.locator("#chat-input").first
                text = input_el.inner_text().strip()
                if text:
                    log.debug(f"[监控] 输入框残留文字「{text[:30]}...」，正在清空")
                    input_el.click()
                    self.page.keyboard.press("Control+a")
                    self.page.keyboard.press("Backspace")
                    pause(0.3, 0.5)
            except Exception:
                pass
            # 重新切「未读」Tab，刷新侧边栏列表（BOSS 可能已把刚才的会话标记为已读移出列表）
            for sel in ['span.label-name:has-text("未读")', '.label-name:has-text("未读")']:
                try:
                    tab = self.page.locator(sel).first
                    if tab.is_visible():
                        tab.click()
                        pause(0.5, 1)
                        break
                except Exception:
                    pass
            pause(0.5, 1)

        log.info(f"[监控] 本轮完成: 消息 {result['new_messages']}, 回复 {result['replies_sent']}")
        return result
