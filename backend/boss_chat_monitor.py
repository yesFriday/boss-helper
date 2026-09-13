#!/usr/bin/env python3
"""
BossChatMonitor — 专门负责聊天会话同步、AI 回复决策和消息发送交互。
"""

import json
import random
import asyncio
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
    get_conversation_by_security_id,
    update_conversation_security_id,
    get_stale_hr_conversations,
    get_last_hr_message,
    get_recent_hr_messages,
    replace_conversation_messages,
    update_conversation_last_message,
    update_conversation_wechat,
    get_today_auto_reply_count,
    get_setting,
    get_application,
    get_application_by_hr_name,
    is_system_notification,
    add_message,
    increment_daily_stat,
    update_conversation_interest,
)
from backend import runtime, browser_ops

log = get_logger("boss_chat_monitor")

MAX_AUTO_REPLY_PER_DAY = 200  # 默认值，可在前端设置页动态调整（settings key: max_auto_reply_per_day）


def get_max_auto_reply_per_day() -> int:
    try:
        return max(1, int(get_setting("max_auto_reply_per_day", str(MAX_AUTO_REPLY_PER_DAY))))
    except (TypeError, ValueError):
        return MAX_AUTO_REPLY_PER_DAY

# 失败退避：同一条 HR 消息连续生成失败 N 次后，M 秒内不再重试
REPLY_FAILURE_LIMIT = 3
REPLY_BACKOFF_SECONDS = 1800

# 孤儿消息兜底扫描：HR 最后一条消息超过 N 分钟未回复的会话从 DB 侧找回
SWEEP_LIMIT_PER_CYCLE = 2


def extract_unreplied_block(msgs: List[dict]) -> Optional[str]:
    """提取尾部连续未回复的 HR 消息块（系统通知已过滤）。

    从最后一条消息向前找到最近一条我方消息，其后所有 HR 消息按序合并；
    没有未回复 HR 消息时返回 None。HR 连发多条时整块作为待回复内容。
    """
    hr_block = []
    for m in reversed(msgs):
        if m.get("sender") == "me":
            break
        content = (m.get("content") or "").strip()
        if not content or is_system_notification(content):
            continue
        hr_block.append(content)
    if not hr_block:
        return None
    return "\n".join(reversed(hr_block))


def match_conversation_item(item: dict, known_convs: List[dict]) -> Optional[dict]:
    """把页面会话条目匹配到 DB 会话。securityId 精确优先,其次名字精确,最后名字子串。

    securityId 是 BOSS 会话的唯一身份,名字撞车不再归并(同名不同 HR 拆分会话)。
    """
    sid = (item.get("security_id") or "").strip()
    if sid:
        for kc in known_convs:
            if (kc.get("security_id") or "").strip() == sid:
                return kc
    extracted_name = (item.get("hr_name") or "").strip()
    text = item.get("text", "")
    if extracted_name:
        for kc in known_convs:
            kc_name = kc.get("hr_name", "")
            if kc_name and kc_name == extracted_name and not (sid and (kc.get("security_id") or "").strip()):
                # 条目带 sid 而已知会话没有 sid 且名字相同 → 命中(老数据,后续回填)
                return kc
    for kc in known_convs:
        kc_name = kc.get("hr_name", "")
        if kc_name and len(kc_name) >= 3 and kc_name in text:
            return kc
    return None


def merge_friend_records(store: dict, friends: list) -> int:
    """合并好友身份记录到 store(名字→[{sid, last_msg}])，返回新增条数。

    数据源是旁听/主动拉取的 BOSS 好友接口(字段: name/bossName + securityId + lastMsg)。
    同名 HR 各自保留独立记录，靠 last_msg 与会话列表预览做二次关联。
    """
    merged = 0
    for f in friends or []:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or f.get("bossName") or f.get("realName") or "").strip()
        sid = str(f.get("securityId") or "").strip()
        if not name or not sid:
            continue
        rec = {"sid": sid, "last_msg": str(f.get("lastMsg") or "").strip()}
        bucket = store.setdefault(name, [])
        if any(r["sid"] == sid for r in bucket):
            continue
        bucket.append(rec)
        merged += 1
    return merged


def resolve_item_sid(item: dict, friend_records: dict) -> str:
    """为会话列表条目解析 securityId。

    名字唯一 → 直接用；同名多条 → 用最后消息预览与好友记录的 last_msg 关联；
    仍无法区分 → 返回空串（宁可退回名字匹配，也不错绑身份）。
    """
    name = (item.get("hr_name") or "").strip()
    recs = friend_records.get(name) or []
    if not recs:
        return ""
    if len(recs) == 1:
        return recs[0]["sid"]
    text = (item.get("text") or "").replace("\n", " ")
    for r in recs:
        lm = (r.get("last_msg") or "")[:40]
        if lm and lm in text:
            return r["sid"]
    return ""


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

        return self._attach_security_ids(conversations)

    def _install_sniffer(self):
        """挂网络监听(每个页面对象一次): 被动收割好友身份记录与 encryptSystemId。

        BOSS 前端加载聊天页时会自己调 getGeekFriendList.json(响应含全部好友的
        securityId+名字+最后消息)和带 encryptSystemId 的请求——旁听即可，无需
        访问 window 全局变量(旧方案的死路)。
        """
        page_key = id(self.page)
        if getattr(self, "_sniffer_page_id", None) == page_key:
            return
        self._sniffer_page_id = page_key
        if not hasattr(self, "_friend_records"):
            self._friend_records = {}
        if not hasattr(self, "_geek_encrypt_id"):
            self._geek_encrypt_id = ""

        def on_request(req):
            try:
                if not self._geek_encrypt_id:
                    m = re.search(r"[?&]encryptSystemId=([A-Za-z0-9]{10,})", req.url)
                    if m:
                        self._geek_encrypt_id = m.group(1)
                        log.info(f"[Sniffer] 收割 encryptSystemId: {self._geek_encrypt_id[:12]}...")
            except Exception:
                pass

        def on_response(resp):
            try:
                url = resp.url
                if "getGeekFriendList" in url or "geekFilterByLabel" in url:
                    data = resp.json()
                    zp = (data or {}).get("zpData") or {}
                    merged = merge_friend_records(
                        self._friend_records, zp.get("result") or zp.get("friends") or []
                    )
                    if merged:
                        total = sum(len(v) for v in self._friend_records.values())
                        log.info(f"[Sniffer] 被动捕获好友身份 +{merged}，累计 {total} 人")
            except Exception:
                pass

        self.page.on("request", on_request)
        self.page.on("response", on_response)
        log.debug("[Sniffer] 网络监听已挂载")

    def _fetch_friend_list_active(self) -> bool:
        """主动分页拉取好友身份列表(同源GET、cookie自动携带，与页面自身行为一致)。

        被动监听是机遇型的(BOSS 前端没刷新列表就没有响应可听)，主动补拉保证
        每个监控周期都能建立全量映射。翻页参数未官方文档化，用"首页重复即停"
        防死循环。
        """
        try:
            seen_first_sids = set()
            for page_no in range(1, 16):
                data = self.page.evaluate(
                    """async (pageNo) => {
                        const r = await fetch(`/wapi/zprelation/friend/getGeekFriendList.json?page=${pageNo}`, {
                            headers: {'Accept': 'application/json'}, credentials: 'include'
                        });
                        return await r.json();
                    }""",
                    page_no,
                )
                zp = (data or {}).get("zpData") or {}
                result = zp.get("result") or []
                if not result:
                    break
                merge_friend_records(self._friend_records, result)
                first_sid = str(result[0].get("securityId") or "")
                if first_sid in seen_first_sids:
                    break
                seen_first_sids.add(first_sid)
                if len(result) < 20:
                    break
                pause(0.3, 0.8)
            if self._friend_records:
                total = sum(len(v) for v in self._friend_records.values())
                log.info(f"[Sniffer] 主动拉取好友身份列表: 累计 {total} 人")
                return True
            return False
        except Exception as e:
            log.debug(f"[Sniffer] 主动拉取好友列表失败: {e}")
            return False

    def _attach_security_ids(self, conversations: List[dict]) -> List[dict]:
        """给会话条目附加 securityId(BOSS 会话唯一身份)。

        优先用网络监听积累的好友身份记录(支持同名 HR 按最后消息关联)；
        记录为空时主动拉取一次；再不行退化到旧 friends API；全失败则静默
        返回(条目无 sid,匹配退回名字路径)。
        """
        if not conversations:
            return conversations
        try:
            if not self._friend_records:
                self._fetch_friend_list_active()
            if not self._friend_records:
                sid_map = self._fetch_friend_sid_map()
                if sid_map:
                    for c in conversations:
                        name = (c.get("hr_name") or "").strip()
                        if name and name in sid_map and not c.get("security_id"):
                            c["security_id"] = sid_map[name]
                return conversations
            resolved = 0
            for c in conversations:
                if c.get("security_id"):
                    continue
                sid = resolve_item_sid(c, self._friend_records)
                if sid:
                    c["security_id"] = sid
                    resolved += 1
            if resolved:
                log.debug(
                    f"[Sniffer] 身份解析: {resolved}/{len(conversations)} 个条目获得 sid"
                    f"（映射库 {sum(len(v) for v in self._friend_records.values())} 人）"
                )
        except Exception as e:
            log.debug(f"[监控] securityId 映射获取失败(退化用名字匹配): {e}")
        return conversations

    def _fetch_friend_sid_map(self) -> dict:
        """调 BOSS friends API 拿 name→securityId 映射。失败返回空 dict。"""
        try:
            encrypt_id = self.page.evaluate("""() => {
                for (const key of Object.keys(window)) {
                    try { if (window[key] && window[key].encryptSystemId) return window[key].encryptSystemId; } catch(e) {}
                }
                return '';
            }""")
            if not encrypt_id:
                return {}
            url = f"https://www.zhipin.com/wapi/zprelation/friend/geekFilterByLabel?labelId=0&encryptSystemId={encrypt_id}"
            data = self.page.evaluate(
                """async (url) => {
                    const r = await fetch(url, {headers:{'Accept':'application/json','x-requested-with':'XMLHttpRequest'}, credentials:'include'});
                    return await r.json();
                }""",
                url,
            )
            friends = (data or {}).get("zpData", {}).get("friends", []) or []
            return {
                ((f.get("bossName") or f.get("realName") or "").strip()): f.get("securityId", "")
                for f in friends
                if (f.get("bossName") or f.get("realName") or "").strip() and f.get("securityId")
            }
        except Exception:
            return {}

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

    def _verify_window_identity(self, conv_id: int) -> bool:
        """内容指纹身份校验：窗口里应能看到该会话库中已知的最后一条 HR 消息。

        原理：不同 HR 的聊天内容几乎不可能恰好相同，"窗口可见的最后 HR 消息
        包含数据库记录的那条"即可高度确信点开的是同一个人的窗口。
        HR 在上次同步之后又发了新消息也算通过（旧消息仍在窗口历史里可见）。
        任何无法比对的情况一律放行（不阻塞正常流程）。
        """
        try:
            # 拿库中最近几条 HR 消息做指纹集合（HR 在同步后又发新消息时，
            # 旧消息可能被顶出可视区，单比最后一条会误伤）
            needles = [
                str(c).strip()[:40]
                for c in get_recent_hr_messages(conv_id, limit=5)
                if c and len(str(c).strip()) >= 2
            ]
            if not needles:
                return True  # 无历史可比（新会话等）
            msgs = self.read_visible_messages()
            win_hr_texts = [
                (m.get("content") or "").strip()
                for m in msgs
                if m.get("sender") == "hr" and (m.get("content") or "").strip()
            ]
            if not win_hr_texts:
                return True  # 窗口还没有 HR 消息可比
            return any(n in t for n in needles for t in win_hr_texts)
        except Exception as e:
            log.debug(f"[监控] 内容指纹校验异常(放行): {e}")
            return True

    def _get_chat_security_id(self, hr_name: str = "") -> str:
        """从 BOSS API 或页面提取对方 securityId。"""
        # 熔断: 连续失败太多次说明三条提取路径在当前页面上都失效(Vue SPA 不暴露),
        # 冷却期内直接返回空,避免每个会话浪费 6 秒重试。恢复靠网络监听方案的
        # attach/回填路径,不靠这里。
        if time.time() < getattr(self, "_sid_cb_until", 0):
            return ""
        for attempt in range(3):  # 重试3次
            try:
                # 方式1: 页面 HTML 正则搜
                html = self.page.content()
                m = re.search(r'securityId["\']?\s*[:=]\s*["\']([A-Za-z0-9_~+/=-]{30,})["\']', html)
                if m:
                    self._mark_sid_success()
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
                    self._mark_sid_success()
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
                            self._mark_sid_success()
                            return f.get("securityId", "")

                if attempt < 2:
                    log.debug(f"[securityId] 第{attempt + 1}次获取失败，重试...")
                    pause(1, 2)

            except Exception as e:
                log.error(f"[securityId] 获取异常: {e}", exc_info=True)
                if attempt < 2:
                    pause(1, 2)

        # 失败计数熔断: 连续 15 次全失败 → 冷却 10 分钟,期间直接返回空
        streak = getattr(self, "_sid_fail_streak", 0) + 1
        self._sid_fail_streak = streak
        if streak >= 15:
            self._sid_cb_until = time.time() + 600
            self._sid_fail_streak = 0
            log.warning("[securityId] 连续失败 15 次，三条提取路径失效，熔断 10 分钟")
        else:
            log.warning(f"securityId 获取失败（3次重试），HR: {hr_name}")
        return ""

    def _mark_sid_success(self):
        """sid 获取成功时清零失败计数。"""
        self._sid_fail_streak = 0

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
        """点击「发简历」按钮，等弹窗后点「确定」确认发送。
        确认弹窗未出现视为失败——绝不能在没有确认发送的情况下返回成功,
        否则会向HR谎称"简历已发"。"""
        try:
            btn = self._find_element(SELECTORS["resume_attach_btn"], timeout_ms=5000)
            if not btn:
                log.warning("send_resume: 未找到发简历按钮")
                return False
            btn.click()
            log.info("[发简历] 已点击发简历按钮")
            pause(1, 2)

            # 两阶段弹窗(首次发送/无默认简历):先选「发送在线简历」。
            # 自动流程无法上传附件文件,只能走在线简历路径
            online = self._find_element(SELECTORS["resume_online_option"], timeout_ms=2000)
            if online:
                online.click()
                log.info("[发简历] 已选择「发送在线简历」")
                pause(1, 2)

            # 等弹窗出现 → 点「确定」按钮(注意:按钮文字是「确定」不是「发送」)
            confirm = self._find_element(SELECTORS["resume_confirm_btn"], timeout_ms=5000)
            if not confirm:
                # 弹窗未出现 → 发送未完成,必须返回失败并尝试关闭可能残留的弹窗
                log.warning("[发简历] 未出现确认弹窗,简历未发送")
                try:
                    self.page.keyboard.press("Escape")
                    pause(0.5, 1)
                except Exception:
                    pass
                return False

            confirm.click()
            pause(1, 2)

            # 校验:点击后确认弹窗应关闭(该 popover 对 Esc 无响应,点「取消」无效场景不存在)。
            # 弹窗仍在说明点击未生效,重点一次;仍未关闭则如实返回失败
            for _ in range(2):
                try:
                    if not confirm.is_visible():
                        log.info("[发简历] 已点确定按钮,简历已发送")
                        return True
                except Exception:
                    log.info("[发简历] 已点确定按钮,简历已发送")
                    return True
                log.warning("[发简历] 点确定后弹窗未关闭,重点一次")
                try:
                    confirm.click()
                except Exception:
                    pass
                pause(1, 2)

            log.warning("[发简历] 确认弹窗始终未关闭,简历未发送")
            return False
        except Exception as e:
            log.error(f"send_resume 失败: {e}", exc_info=True)
            return False

    # ══════════════════════════════════════
    #  监控周期（供后台循环调用）
    # ══════════════════════════════════════

    def _click_unread_tab(self):
        """轻量点击「未读」Tab,刷新侧边栏列表(不整页刷新,避免触发登录检查)。"""
        for sel in ['span.label-name:has-text("未读")', '.label-name:has-text("未读")']:
            try:
                tab = self.page.locator(sel).first
                if tab.is_visible():
                    tab.click()
                    pause(0.5, 1)
                    break
            except Exception:
                pass

    def _scan_list(self) -> Optional[List[dict]]:
        """[pw线程] 导航+安全检查+扫描未读列表+孤儿sweep合并。失败返回 None。"""
        # 挂网络监听(幂等): 被动收割好友身份映射(securityId 数据源)
        self._install_sniffer()
        # 只在不在聊天页时才导航（避免每轮刷新页面，触发 BOSS 登录检查）
        current_url = self.page.url
        if "/web/geek/chat" not in current_url:
            if not self.navigate_to_chat():
                log.info("[监控] 导航到聊天页失败")
                return None
        else:
            self._click_unread_tab()

        if not self.check_page_safety():
            log.warning("[监控] 安全检查未通过（登录过期/验证码等）")
            return None

        conversations = self.poll_conversation_list()
        log.info(f"[监控] 扫描到 {len(conversations)} 个会话")
        try:
            preview = (self.page.inner_text("body") or "")[:800].replace("\n", " | ")
            log.debug(f"[监控] Body: {preview}")
        except Exception:
            pass

        if not conversations:
            log.info("[监控] 无未读消息")
        if len(conversations) > 3:
            log.info(f"[监控] 未读会话: {len(conversations)} 个，本轮只处理前3个")
            conversations = conversations[:3]

        # 孤儿消息兜底(D2):未读红点被打开即消失,回复失败的消息"已读未回"永不再试;
        # 从 DB 侧找回 HR 最后消息超时未回的会话,与未读条目合并处理
        items = list(conversations)
        try:
            sweep_min = int(get_setting("sweep_after_minutes", "10"))
            stale = get_stale_hr_conversations(sweep_min, SWEEP_LIMIT_PER_CYCLE)
            for sc in stale:
                items.append(
                    {
                        "text": sc.get("hr_name", ""),
                        "hr_name": sc.get("hr_name", ""),
                        "has_unread": False,
                        "element": None,
                        "security_id": sc.get("security_id") or "",
                        "stale_conv": sc,
                    }
                )
            if stale:
                log.info(
                    f"[监控] 孤儿扫描: 找回 {len(stale)} 个超时未回会话: "
                    f"{[s.get('hr_name') for s in stale]}"
                )
        except Exception as e:
            log.debug(f"[监控] 孤儿扫描失败: {e}")
        return items

    async def run_chat_monitor_cycle(self) -> dict:
        """
        一个完整的监控周期(三阶段编排,LLM 不占浏览器线程):
        [pw]  _scan_list     — 导航/安全检查/扫列表/孤儿sweep合并
        [pw]  _open_and_read — 逐会话: 打开+身份校验+读DOM+存库+提块(纯 DOM/DB)
        [llm] _generate_one  — 生成回复(快速问候/Agent/降级)+退避/去重闸门(无浏览器,
                               Agent 工具经 run_pw hop 回 pw 线程)
        [pw]  _send_one      — 重新定位会话+发送+落库+统计(发送失败计退避)
        """
        # monitor 循环与定时调度器可能同时触发(调度块间聊天兜底),串行化避免
        # 同一会话被两个周期并发处理导致重复回复
        if not hasattr(self, "_cycle_lock"):
            self._cycle_lock = asyncio.Lock()
        async with self._cycle_lock:
            # 前端独占操作(搜索/投递/手动发消息)进行中:让路,本轮不跑,
            # 避免与其共用 page 抢导航导致标签页来回切换
            if browser_ops.is_busy():
                log.debug("[监控] 浏览器被独占操作占用,本轮跳过")
                return {"checked": 0, "new_messages": 0, "replies_sent": 0}
            return await self._run_cycle_locked()

    async def _run_cycle_locked(self) -> dict:
        result = {"checked": 0, "new_messages": 0, "replies_sent": 0}
        items = await runtime.aio_run_pw(self._scan_list)
        if items is None:
            return result
        result["checked"] = len(items)

        handled = set()
        for item in items:
            task = await runtime.aio_run_pw(self._open_and_read, item, handled, result)
            if task is None or not task.get("hr_message"):
                continue
            result["new_messages"] += 1
            task = await runtime.aio_run_llm(self._generate_one, task)
            if task.get("reply"):
                await runtime.aio_run_pw(self._send_one, task, result)

        # 收尾:清输入框残留 + 刷新未读Tab,为下一轮做准备
        await runtime.aio_run_pw(self._refresh_after_cycle)
        log.info(f"[监控] 本轮完成: 消息 {result['new_messages']}, 回复 {result['replies_sent']}")
        return result

    def _refresh_after_cycle(self):
        self._clear_input_box()
        self._click_unread_tab()
        pause(0.5, 1)

    def _clear_input_box(self):
        """清空输入框残留文字,避免污染下一个会话。"""
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

    def _open_and_read(self, item: dict, handled: set, result: dict) -> Optional[dict]:
        """[pw线程] 定位/创建会话 → 门卫检查 → 打开+身份校验 → 读消息存库 → 提待回复块。"""
        text = item.get("text", "")
        stale_conv = item.get("stale_conv")
        if not text and not stale_conv:
            return None

        known_convs = list_active_conversations()
        log.debug(f"[监控] 数据库已知活跃会话: {len(known_convs)}")

        # ── 定位/创建会话记录 ──
        if stale_conv:
            # 孤儿扫描找回的会话,DB 记录已知,跳过匹配
            conv_id = stale_conv["id"]
            if conv_id in handled:
                return None
            matched_conv = get_conversation(conv_id) or stale_conv
        else:
            matched_conv = match_conversation_item(item, known_convs)
            if matched_conv is not None:
                # 条目已解析出 sid 且会话还没有 → 回填，之后每轮都能精确匹配
                item_sid = (item.get("security_id") or "").strip()
                if item_sid and not (matched_conv.get("security_id") or "").strip():
                    try:
                        update_conversation_security_id(matched_conv["id"], item_sid)
                        matched_conv["security_id"] = item_sid
                        log.info(
                            f"[Sniffer] 回填会话 securityId: {matched_conv.get('hr_name')}"
                            f" -> {item_sid[:12]}..."
                        )
                    except Exception:
                        pass
            if matched_conv is None:
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                hr_name = item.get("hr_name", "") or lines[0] if lines else ""
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
                    return None

                conv_id = get_or_create_conversation(
                    None,
                    hr_name,
                    item.get("company", ""),
                    item.get("job_title", ""),
                    item.get("security_id", ""),
                )
                matched_conv = get_conversation(conv_id)
                if not matched_conv:
                    return None
                log.info(f"[监控] 新建会话: {hr_name}")
                # 标记用于 WebSocket 广播
                result.setdefault("new_conversations", []).append(hr_name)
            else:
                conv_id = matched_conv["id"]
                # 提取的名字比 DB 更精确时自动修正(仅无 securityId 的名字匹配路径;
                # sid 命中的会话身份已确定,不再用名字启发式改名)
                extracted_name = (item.get("hr_name") or "").strip()
                if extracted_name and len(extracted_name) >= 2 and not (
                    item.get("security_id") and matched_conv.get("security_id")
                ):
                    old_name = matched_conv.get("hr_name", "")
                    if old_name != extracted_name and (
                        old_name in extracted_name
                        or extracted_name in old_name
                        or len(extracted_name) < len(old_name)
                    ):
                        try:
                            from backend.state import get_db as _gdb2

                            _gdb2().execute(
                                "UPDATE conversations SET hr_name=? WHERE id=?", (extracted_name, conv_id)
                            )
                            _gdb2().commit()
                            matched_conv["hr_name"] = extracted_name
                        except Exception:
                            pass

        if conv_id in handled:
            return None
        handled.add(conv_id)

        # 公司/岗位信息不再从会话列表文本猜测(旧正则基本提不准)，
        # 统一改由打开会话后从聊天页头部提取，见 _extract_chat_context

        if matched_conv.get("status") != "active":
            return None
        if not matched_conv.get("auto_reply_enabled"):
            return None
        if matched_conv.get("is_dangerous"):
            log.info(f"[监控] 会话 {matched_conv.get('hr_name')} 已标记为风险会话，跳过")
            return None

        # ── 打开会话 ──
        hr_name_to_open = matched_conv["hr_name"]
        opened = self.open_conversation_by_name(hr_name_to_open)
        if not opened and len(hr_name_to_open) > 4:
            short = re.match(r"^[\u4e00-\u9fff]{2,3}", hr_name_to_open)
            if short:
                opened = self.open_conversation_by_name(short.group(0))
        if not opened:
            log.info(f"[监控] 无法打开会话: {hr_name_to_open}")
            return None
        pause(1, 2)

        # ── 身份校验(D1 安全网):当前页面 securityId 必须与期望一致 ──
        # 期望 sid:条目携带的(来自 friends API)优先,退回 DB 记录的
        expected_sid = (item.get("security_id") or "").strip() or (
            matched_conv.get("security_id") or ""
        ).strip()
        page_sid = ""
        if expected_sid:
            page_sid = self._get_chat_security_id(hr_name_to_open)
            if page_sid and page_sid != expected_sid:
                log.warning(
                    f"[监控] ⚠️ 身份校验失败: 期望会话 {hr_name_to_open}"
                    f"(sid={expected_sid[:10]}...) 实际打开 sid={page_sid[:10]}...，"
                    "跳过回复防止回错人"
                )
                return None
            if page_sid:
                log.debug(f"[监控] 身份校验通过: {hr_name_to_open}")
        else:
            # 存量会话首次带 sid 打开 → 学习回填,后续轮次可精确校验
            page_sid = self._get_chat_security_id(hr_name_to_open)
            if page_sid:
                update_conversation_security_id(conv_id, page_sid)
                matched_conv["security_id"] = page_sid
                log.debug(f"[监控] 学习会话 securityId: {hr_name_to_open} -> {page_sid[:10]}...")

        # ── 内容指纹校验(sid 没能确认时的兜底安全网) ──
        # 窗口内应能看到该会话已知的最后一条 HR 消息;看不到说明点开的窗口
        # 属于别人(典型:同名 HR 点错行)。
        if not page_sid and not self._verify_window_identity(conv_id):
            log.warning(
                f"[监控] ⚠️ 内容指纹校验失败: 窗口内找不到会话 {hr_name_to_open} 的已知消息，"
                "疑似打开了同名会话，跳过防止回错人"
            )
            return None

        # ── 读取消息 ──
        # 先从聊天页头部提取公司/岗位（比会话列表文本可靠，覆盖旧正则提取不到的场景）
        self._extract_chat_context(conv_id, matched_conv)
        msgs = self.read_visible_messages()
        log.info(f"[监控] 会话 {matched_conv.get('hr_name')}: 读到 {len(msgs)} 条消息")

        clean_msgs = []
        for msg in msgs:
            sender = msg.get("sender", "hr")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            # 系统通知不入库，避免污染 AI 上下文
            if is_system_notification(content):
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

        # ── 提取待回复块 + 岗位信息,组装任务(不做任何 LLM 调用) ──
        unreplied_hr_msg = extract_unreplied_block(clean_msgs)
        if unreplied_hr_msg:
            log.info(f"[监控] 待回复HR消息: {unreplied_hr_msg[:60]}...")

        last_me = next((m["content"] for m in reversed(clean_msgs) if m["sender"] == "me"), "")
        job_info = self._resolve_job_info(matched_conv, conv_id, hr_name_to_open)

        return {
            "conv_id": conv_id,
            "matched_conv": matched_conv,
            "hr_name": hr_name_to_open,
            "hr_message": unreplied_hr_msg,
            "job_info": job_info,
            "last_me": last_me,
        }

    # 聊天页头部结构（BOSS 前端更新时只需改这里）:
    # .base-info: [.name-content .name-text]=HR名, 无class的span=公司名, .base-title=HR头衔
    # .chat-position-content .position-content: .position-name=岗位名, .salary, .city
    # 公司名偶尔不在头部 → 兜底读左侧列表中同名会话行的 name-box 第二个span
    EXTRACT_CHAT_CONTEXT_JS = """(expectedName) => {
        const trim = s => (s || '').trim();
        const base = document.querySelector('.chat-conversation .base-info, .top-info-content .base-info');
        let hr_name = '', company = '', hr_title = '';
        if (base) {
            hr_name = trim((base.querySelector('.name-content .name-text') || {}).textContent);
            hr_title = trim((base.querySelector('.base-title') || {}).textContent);
            const compSpan = [...base.querySelectorAll(':scope > span')].find(
                s => !s.className && trim(s.textContent)
            );
            company = compSpan ? trim(compSpan.textContent) : '';
        }
        const bar = document.querySelector('.chat-position-content .position-content, [ka="geek_chat_job_detail"]');
        let job_title = '';
        if (bar) {
            job_title = trim((bar.querySelector('.position-name') || {}).textContent);
        }
        if (!company && expectedName) {
            // 兜底: 头部没有公司名时,从左侧列表同名会话行取(结构: .name-text=HR名, span=公司名, i.vline, span=头衔)
            for (const nb of document.querySelectorAll('li[role="listitem"] .name-box')) {
                const nameEl = nb.querySelector('.name-text');
                if (!nameEl || trim(nameEl.textContent) !== expectedName) continue;
                const spans = [...nb.querySelectorAll(':scope > span')].filter(
                    s => !s.className && s !== nameEl && trim(s.textContent)
                );
                if (spans.length) company = trim(spans[0].textContent);
                if (!hr_name) hr_name = expectedName;
                break;
            }
        }
        return {hr_name, company, hr_title, job_title};
    }"""

    def _extract_chat_context(self, conv_id: int, matched_conv: dict):
        """会话已打开时，从聊天页头部提取公司/岗位信息并回写会话(PW线程内调用)。"""
        try:
            info = (
                self.page.evaluate(self.EXTRACT_CHAT_CONTEXT_JS, matched_conv.get("hr_name") or "")
                or {}
            )
        except Exception as e:
            log.debug(f"[监控] 提取聊天上下文失败: {e}")
            return
        company = (info.get("company") or "").strip()
        job_title = (info.get("job_title") or "").strip()
        if not company and not job_title:
            return
        changed = []
        if company and company != (matched_conv.get("hr_company") or ""):
            changed.append(("hr_company", company))
        if job_title and job_title != (matched_conv.get("job_title") or ""):
            changed.append(("job_title", job_title))
        if not changed:
            return
        try:
            from backend.state import update_conversation_job_context

            update_conversation_job_context(
                conv_id,
                hr_company=company or None,
                job_title=job_title or None,
            )
            for k, v in changed:
                matched_conv[k] = v
            log.info(f"[监控] 提取岗位上下文: {matched_conv.get('hr_name')} | 公司={company or '-'} 岗位={job_title or '-'}")
        except Exception as e:
            log.debug(f"[监控] 岗位上下文回写失败: {e}")

    def capture_job_url(self) -> str:
        """点击聊天头部岗位条(查看职位)，捕获岗位详情页URL(PW线程内调用)。

        BOSS 岗位条不是 <a>，链接由 JS 点击后打开；且点击常先经过安全验证中转页
        (/web/passport/zp/security.html)，真实岗位地址在该页 URL 的 callbackUrl 参数里。
        优先捕获新标签页，兜底处理同标签页跳转。失败返回空串，绝不抛异常。
        """
        try:
            loc = self.page.locator(
                '.chat-position-content .position-content, [ka="geek_chat_job_detail"]'
            ).first
            if loc.count() == 0:
                return ""
            before_url = self.page.url
            url = ""
            try:
                with self.page.context.expect_page(timeout=6000) as popup_info:
                    loc.click(timeout=5000)
                popup = popup_info.value
                # 安全检查可能自动通过并跳转到岗位页，先等一拍
                try:
                    popup.wait_for_url("**/job_detail/**", timeout=4000)
                except Exception:
                    try:
                        popup.wait_for_load_state("domcontentloaded", timeout=6000)
                    except Exception:
                        pass
                url = self._resolve_job_url(popup.url or "")
                try:
                    popup.close()
                except Exception:
                    pass
            except Exception:
                url = ""
            if not url:
                cur = self.page.url
                if cur != before_url:
                    url = self._resolve_job_url(cur)
                    try:
                        self.page.go_back(timeout=20000)
                        pause(1, 2)
                    except Exception:
                        pass
            return url
        except Exception as e:
            log.debug(f"[监控] 捕获岗位链接失败: {e}")
            return ""

    @staticmethod
    def _resolve_job_url(url: str) -> str:
        """从最终/中转 URL 解析岗位详情地址；解析不出返回空串。"""
        from urllib.parse import unquote, urlparse, parse_qs

        url = (url or "").strip()
        if not url:
            return ""
        # 安全验证中转页: 真实地址在 callbackUrl 参数
        if "/web/passport/zp/security.html" in url:
            try:
                qs = parse_qs(urlparse(url).query)
                callback = (qs.get("callbackUrl") or [""])[0]
                callback = unquote(callback)
                if "/job_detail/" in callback:
                    path = callback.split("?")[0]
                    return f"https://www.zhipin.com{path}" if path.startswith("/") else path
            except Exception:
                pass
            return ""
        if "/job_detail/" in url:
            return url.split("?")[0].strip()
        return ""

    def _resolve_job_info(self, matched_conv: dict, conv_id: int, hr_name: str) -> dict:
        """解析岗位信息:会话关联的投递记录优先,无关联时按 HR 名反查回填。"""
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

        # 会话未关联投递记录时，按 HR 名反查回填岗位信息
        if not (job_desc and job_title and job_company):
            app2 = get_application_by_hr_name(hr_name) or get_application_by_hr_name(
                matched_conv.get("hr_name", "")
            )
            if app2:
                job_desc = job_desc or (app2.get("description") or "")
                job_title = job_title or app2.get("job_title", "")
                job_company = job_company or app2.get("company", "")
                if app2.get("id") and not matched_conv.get("application_id"):
                    try:
                        from backend.state import get_db as _gdb

                        _gdb().execute(
                            "UPDATE conversations SET application_id=? WHERE id=?",
                            (app2["id"], conv_id),
                        )
                        _gdb().commit()
                        matched_conv["application_id"] = app2["id"]
                        log.info(f"[监控] 会话已关联岗位: {app2.get('job_title')}")
                    except Exception:
                        pass

        return {"title": job_title, "company": job_company, "description": job_desc}

    def _bump_failure(self, fail_key):
        """失败计数(生成失败/发送失败共用),触发退避冷却。"""
        if not hasattr(self, "_reply_failures"):
            self._reply_failures = {}
        prev = self._reply_failures.get(fail_key, {"count": 0, "last_ts": 0})
        prev["count"] += 1
        prev["last_ts"] = time.time()
        self._reply_failures[fail_key] = prev
        return prev

    def _generate_one(self, task: dict) -> dict:
        """[llm线程] 生成回复:快速问候/Agent/降级三路 + 退避/去重闸门。不碰浏览器,
        Agent 工具经 ctx["run_pw"] hop 回 pw 线程。"""
        task["reply"] = ""
        task["interest"] = ""
        conv_id = task["conv_id"]
        matched_conv = task["matched_conv"]
        hr_message = task.get("hr_message") or ""

        if not hr_message:
            return task
        if get_setting("auto_reply_enabled", "true") != "true":
            log.info("[监控] 自动回复已关闭，跳过")
            return task
        max_auto_reply = get_max_auto_reply_per_day()
        if get_today_auto_reply_count() >= max_auto_reply:
            log.info(f"[监控] 今日自动回复已达上限 {max_auto_reply}，跳过")
            return task

        # 失败退避：同一条消息连续失败次数超限 → 冷却期内跳过
        if not hasattr(self, "_reply_failures"):
            self._reply_failures = {}
        fail_key = (conv_id, hash(hr_message))
        fail_state = self._reply_failures.get(fail_key)
        if (
            fail_state
            and fail_state["count"] >= REPLY_FAILURE_LIMIT
            and time.time() - fail_state["last_ts"] < REPLY_BACKOFF_SECONDS
        ):
            log.info(
                f"[监控] 会话 {matched_conv.get('hr_name')} 该消息连续失败 {fail_state['count']} 次，"
                "冷却中，本轮跳过"
            )
            return task

        try:
            # 面试邀约闸门: HR 提出具体面试时间的邀约 → 成功入排期则静默;
            # 时间冲突则回复"两段式改期引导"(说明冲突+报真实空闲时段,不代表本人确认)
            # 确认邀约后才捕获岗位链接(llm线程 → hop回pw线程点击查看职位),避免对每条消息都动浏览器
            from backend.interview_gate import handle_interview_invite

            def _get_job_url():
                return runtime.run_in_pw(self.capture_job_url)

            gate_reply = handle_interview_invite(
                conv_id, hr_message, matched_conv, task.get("job_info") or {}, get_job_url=_get_job_url
            )
            if gate_reply is not None:
                task["reply"] = gate_reply
                task["interest"] = "high"  # 主动约面试的 HR 是高意向
                if gate_reply:
                    log.info(f"[监控] 面试邀约冲突,回复改期引导: {matched_conv.get('hr_name')}")
                else:
                    log.info(f"[监控] 面试邀约静默处理(不回复): {matched_conv.get('hr_name')}")
                return task

            from backend.replier import generate_reply

            job_info = task["job_info"]
            style = get_setting("ai_reply_style", "professional")
            resume = get_setting("resume_summary", "")
            wechat = get_setting("wechat_id", "")

            # 构建 Agent 上下文（工具调用在 Agent 循环内部完成;
            # run_pw: llm 线程内浏览器操作 hop 回 pw 线程）
            agent_ctx = {
                "automation": self,
                "run_pw": runtime.run_in_pw,
                "conversation_id": conv_id,
                "matched_conv": matched_conv,
                "hr_name": task["hr_name"],
                "job_info": job_info,
            }

            reply, interest, _extra = generate_reply(
                conv_id, hr_message, job_info, style, resume, wechat, agent_ctx=agent_ctx
            )

            # NO_REPLY：LLM 主动判断这条消息不需要回复——不计失败、不发送
            from backend.agent_loop import NO_REPLY_MARK

            if reply == NO_REPLY_MARK:
                log.info(f"[监控] LLM判断无需回复，跳过: {matched_conv.get('hr_name')}")
                task["reply"] = ""
                return task

            # 回复去重：与我方最后一条消息完全相同则重新生成一次，仍相同则跳过本轮
            last_me = task.get("last_me", "")
            if reply and reply == last_me:
                log.info("[监控] 生成的回复与上一条重复，重新生成一次")
                reply, interest, _extra = generate_reply(
                    conv_id, hr_message, job_info, style, resume, wechat, agent_ctx=agent_ctx
                )
                if reply == NO_REPLY_MARK:
                    log.info(f"[监控] 重新生成判断无需回复，跳过: {matched_conv.get('hr_name')}")
                    task["reply"] = ""
                    return task
                if reply and reply == last_me:
                    log.warning("[监控] 重新生成后仍与上一条重复，跳过本轮发送")
                    reply = ""

            if reply:
                task["reply"] = reply
                task["interest"] = interest or ""
            else:
                prev = self._bump_failure(fail_key)
                log.warning(
                    f"[监控] 回复生成为空（第{prev['count']}次失败）: {matched_conv.get('hr_name')}"
                )
        except Exception as e:
            self._bump_failure(fail_key)
            log.error(f"AI回复生成失败: {e}", exc_info=True)
        return task

    def _send_one(self, task: dict, result: dict):
        """[pw线程] 重新定位会话(生成期间页面可能被手动操作/调度器导航) → 发送 → 落库 → 统计。"""
        conv_id = task["conv_id"]
        matched_conv = task["matched_conv"]
        reply = task["reply"]
        hr_name = task["hr_name"]
        fail_key = (conv_id, hash(task.get("hr_message") or ""))

        # 重新定位会话再发送;定位失败则放弃本轮(避免把回复发到错误会话)
        opened = self.open_conversation_by_name(hr_name)
        if not opened and len(hr_name) > 4:
            short = re.match(r"^[\u4e00-\u9fff]{2,3}", hr_name)
            if short:
                opened = self.open_conversation_by_name(short.group(0))
        if not opened:
            log.warning(f"[监控] 发送前无法定位会话 {hr_name}，放弃本轮发送")
            self._bump_failure(fail_key)
            return

        log.info(f"[监控] AI回复: {reply[:60]}...")
        if self.send_message(reply):
            add_message(conv_id, "me", reply, ai_generated=True)
            update_conversation_last_message(conv_id, reply, "me", 0)
            increment_daily_stat("auto_replies_sent")
            result["replies_sent"] += 1
            if hasattr(self, "_reply_failures"):
                self._reply_failures.pop(fail_key, None)
            if task.get("interest"):
                update_conversation_interest(conv_id, task["interest"])
                log.info(f"[监控] HR兴趣度: {task['interest']}")
            log.info("[监控] 回复已发送")
            # 风险会话检测：Agent 内部通过 mark_dangerous 工具处理
            if matched_conv.get("is_dangerous"):
                log.warning(f"[监控] ⚠️ 会话已标记为风险: {matched_conv.get('hr_name')}")
        else:
            # 发送失败同样计入退避,防止反复失败无限重试
            prev = self._bump_failure(fail_key)
            log.warning(f"[监控] 回复发送失败（第{prev['count']}次失败）!")
        self._clear_input_box()
        pause(5, 15)

