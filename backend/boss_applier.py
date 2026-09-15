#!/usr/bin/env python3
"""
BossApplier — 专门负责岗位投递逻辑。
"""

import random
import time
from typing import Optional, List

from backend.automation_base import AutomationBase
from backend.firefox import pause
from backend.logger import get_logger
from backend.boss_selectors import SELECTORS
from backend.state import (
    get_setting,
    get_today_application_count,
    get_application_by_url,
    update_application_status,
    add_application,
    get_or_create_conversation,
    add_message,
    update_conversation_last_message,
    increment_daily_stat,
)

log = get_logger("boss_applier")


class BossApplier(AutomationBase):
    """投递简历业务类"""

    # 聊天页头部身份结构(与 boss_chat_monitor.EXTRACT_CHAT_CONTEXT_JS 同源):
    # .base-info: [.name-content .name-text]=HR名, 无class的span=公司名
    # .chat-position-content .position-content: .position-name=会话对应的岗位名
    _CHAT_IDENTITY_JS = """() => {
        const trim = s => (s || '').trim();
        const base = document.querySelector('.chat-conversation .base-info, .top-info-content .base-info');
        let hr_name = '', company = '';
        if (base) {
            hr_name = trim((base.querySelector('.name-content .name-text') || {}).textContent);
            const compSpan = [...base.querySelectorAll(':scope > span')].find(
                s => !s.className && trim(s.textContent)
            );
            company = compSpan ? trim(compSpan.textContent) : '';
        }
        const bar = document.querySelector('.chat-position-content .position-content, [ka="geek_chat_job_detail"]');
        const job_title = bar ? trim((bar.querySelector('.position-name') || {}).textContent) : '';
        return {hr_name, company, job_title};
    }"""

    def _verify_chat_window_identity(self, job_title: str = "", company: str = "", strict: bool = False) -> bool:
        """校验当前打开的聊天窗口是否目标岗位的会话,防止发错人。

        strict=True(兜底路径): 头部信息读不到也判不通过——宁可漏发不可错发;
        strict=False(继续沟通路径): 产品流程保证窗口正确,仅在能读出且明显不符时拦截。
        匹配规则: 岗位名或公司名任一方向包含即通过。
        """
        try:
            info = self.page.evaluate(self._CHAT_IDENTITY_JS) or {}
        except Exception as e:
            log.warning("[招呼语] 读取会话窗口身份失败: %s", e)
            return not strict
        hdr_job = (info.get("job_title") or "").strip()
        hdr_company = (info.get("company") or "").strip()
        exp_job = (job_title or "").strip()
        exp_company = (company or "").strip()
        log.info("[招呼语] 窗口身份: HR=%s 岗位=%s 公司=%s", info.get("hr_name") or "?", hdr_job or "?", hdr_company or "?")

        if not hdr_job and not hdr_company:
            return not strict

        def _match(a: str, b: str) -> bool:
            return bool(a) and bool(b) and (a in b or b in a)

        if _match(exp_job, hdr_job) or _match(exp_company, hdr_company):
            return True
        log.warning(
            "[招呼语] 身份不匹配: 期望岗位[%s]/公司[%s] vs 窗口岗位[%s]/公司[%s]",
            exp_job, exp_company, hdr_job, hdr_company,
        )
        return False

    def _force_click_safe(self, locator, timeout_ms: int = 5000) -> bool:
        """强制点击:普通 click 会等"元素稳定+可接收事件",弹窗按钮带动画/遮挡时会
        卡满 30s 超时导致整个投递失败。这里跳过可点性检查+短超时,失败再用 JS 派发
        点击兜底,保证不阻塞投递流程。"""
        try:
            locator.click(force=True, timeout=timeout_ms)
            return True
        except Exception as e:
            log.warning("[招呼语] force click 失败(%s)，尝试 JS 派发点击", str(e)[:100])
        try:
            locator.dispatch_event("click")
            return True
        except Exception as e:
            log.warning("[招呼语] JS 派发点击也失败: %s", str(e)[:100])
            return False

    def apply_to_job(self, job_url: str, greeting: Optional[str] = None, max_apply_limit: int = 0) -> dict:
        """
        对单个岗位执行投递流程:
        1. 打开详情页
        2. 点击"立即沟通"
        3. 发送招呼语
        max_apply_limit: 外部传入的每日上限，0 表示用全局设置
        返回 {success, message, application_id}
        """
        if not job_url:
            return {"success": False, "message": "缺少岗位链接"}

        # 日限检查：外部传入的上限优先，否则用全局设置
        today_count = get_today_application_count()
        if max_apply_limit > 0:
            daily_limit = max_apply_limit
        else:
            daily_limit = int(get_setting("daily_apply_limit", "15"))
        if today_count >= daily_limit:
            return {"success": False, "message": f"已达今日上限({daily_limit}条)"}

        existing = get_application_by_url(job_url)
        if existing and existing.get("status") == "offline":
            log.info(f"岗位已在库中标记为已下架，跳过投递: {job_url[:60]}")
            return {"success": False, "message": "岗位已下架", "status": "offline", "is_offline": True}
        if existing and existing.get("status") in ("applied", "replied"):
            return {"success": True, "message": "已投递过", "already_applied": True}
        if existing and existing.get("status") not in ("pending", "", None):
            log.info(f"岗位非待投递状态({existing.get('status')})，跳过投递: {job_url[:60]}")
            return {"success": False, "message": f"岗位非待投递状态({existing.get('status')})", "status": existing.get("status")}

        log.info(f"投递: {job_url[:60]}...")

        try:
            try:
                self.page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                if "NS_ERROR_ABORT" in str(e) or "net::ERR_ABORTED" in str(e):
                    try:
                        self.page.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                else:
                    raise
            pause(1, 2)

            if not self.check_page_safety():
                return {"success": False, "message": "安全检查未通过"}

            # 优先检查页面是否包含下架/关闭提示
            is_offline = self._has_text(
                "该职位已关闭", "职位已关闭", "已停止招聘", "停止招聘",
                "该职位已下线", "职位已下架", "已暂停招聘", "职位已暂停", "该职位不存在"
            )
            if is_offline:
                if existing:
                    update_application_status(existing["id"], "offline")
                    app_id = existing["id"]
                else:
                    app_id = add_application({"title": "已下架岗位", "company": "", "url": job_url})
                    if app_id:
                        update_application_status(app_id, "offline")
                log.info(f"检测到页面提示职位已关闭/下线，已标记为已下架(offline): {job_url[:60]}")
                return {"success": False, "message": "岗位已下架", "status": "offline", "is_offline": True, "application_id": app_id}

            # 检查是否已投递
            if self._has_text("已沟通", "继续沟通"):
                if existing and existing["status"] == "pending":
                    update_application_status(existing["id"], "applied")
                return {"success": True, "message": "已投递过", "already_applied": True}

            # 从详情页提取 HR 真实姓名和岗位信息
            app_record = existing or {}
            hr_name = app_record.get("hr_name", "")
            hr_company = app_record.get("company", "")
            job_title = app_record.get("job_title", "")
            try:
                page_info = self.page.evaluate("""() => {
                    const body = (document.body || {}).innerText || '';
                    const lines = body.split('\\n').map(l => l.trim()).filter(Boolean);
                    let hrName = '', hrTitle = '', title = '', company = '';
                    const titleEl = document.querySelector('.job-title, .job-name, .name, [class*="job-name"]');
                    if (titleEl) title = (titleEl.innerText || '').trim();
                    const compEl = document.querySelector('.company-name, .company-info a, [class*="company-name"]');
                    if (compEl) company = (compEl.innerText || '').trim();
                    for (let i = 0; i < lines.length; i++) {
                        const l = lines[i];
                        if (l.includes('HR') || l.includes('招聘者') || l.includes('招聘经理') ||
                            l.includes('人事') || l.includes('HRBP') || l.includes('猎头')) {
                            if (i > 0 && lines[i-1].length <= 6 && !/\\d|省|市|区|路|号|招聘|公司|BOSS/.test(lines[i-1])) {
                                hrName = lines[i-1];
                            }
                            hrTitle = l;
                            break;
                        }
                    }
                    return {hrName, hrTitle, title, company};
                }""")
                if page_info.get("hrName") and not hr_name:
                    hr_name = (page_info.get("hrName") or "").strip()
                if page_info.get("title") and not job_title:
                    job_title = (page_info.get("title") or "").strip()
                if page_info.get("company") and not hr_company:
                    hr_company = (page_info.get("company") or "").strip()
            except Exception:
                pass

            # 查找"立即沟通"按钮
            apply_btn = self._find_element(SELECTORS["apply_button"])
            if not apply_btn:
                try:
                    apply_btn = self.page.locator("text=立即沟通").first
                    if not apply_btn.is_visible():
                        apply_btn = None
                except Exception:
                    apply_btn = None

            if not apply_btn:
                if existing:
                    update_application_status(existing["id"], "offline")
                    app_id = existing["id"]
                else:
                    app_id = add_application({"title": job_title or "已下架岗位", "company": hr_company or "", "url": job_url})
                    if app_id:
                        update_application_status(app_id, "offline")
                log.info(f"未找到投递按钮，已标记为已下架(offline): {job_url[:60]}")
                return {"success": False, "message": "未找到投递按钮(岗位已下架)", "status": "offline", "is_offline": True, "application_id": app_id}

            # 点击"立即沟通"（触发平台默认第1条打招呼）
            self._safe_click(apply_btn)
            pause(2, 3)

            # 检查限制消息
            if self._has_text("已达上限", "沟通人数已用完", "今日次数已用完", "今日沟通次数已用完"):
                return {"success": False, "message": "BOSS直聘今日沟通次数已用完"}

            # 生成自定义打招呼语（第2条真人个性化消息）
            from backend.replier import generate_greeting
            greeting_text = greeting or generate_greeting(job_title or "相关岗位", hr_company or "贵公司")
            greeting_sent = False

            # ── 优先级1: 点"立即沟通"弹出的会话窗口里直接发（窗口必然属于本岗位,无需校验）──
            chat_input = self._find_element(SELECTORS["chat_input"], timeout_ms=5000)
            if chat_input and greeting_text:
                greeting_sent = self.send_message(greeting_text)
                if greeting_sent:
                    log.info("在详情页弹窗中成功发送自定义招呼语: %s", greeting_text[:40])

            # ── 优先级2: "已向BOSS发送消息"确认框 → 跳到聊天页,目标会话自动打开 ──
            if not greeting_sent and greeting_text:
                # 首选: 点完立即沟通后,页面主按钮 a.btn-startchat 自带 redirect-url
                # (含会话id+jobId+securityId),直接 goto 它 100% 打开正确会话,无需点击
                redirect_url = None
                try:
                    redirect_url = self.page.locator('a[redirect-url]').first.get_attribute(
                        "redirect-url", timeout=3000
                    )
                except Exception:
                    pass
                if not redirect_url:
                    # 备选: 点弹窗的确认按钮(注意是 span.btn-sure,ka=dialog_confirm,不是 button/a)
                    dialog_btn = self._find_element(
                        [
                            '[ka="dialog_confirm"]',
                            'span.btn-sure:has-text("继续沟通")',
                            '.dialog-footer :text("继续沟通")',
                        ],
                        timeout_ms=3000,
                    )
                    if dialog_btn and self._force_click_safe(dialog_btn):
                        nav_deadline = time.time() + 12
                        while time.time() < nav_deadline and "/web/geek/chat" not in (self.page.url or ""):
                            time.sleep(0.5)
                if redirect_url or "/web/geek/chat" in (self.page.url or ""):
                    if redirect_url:
                        target = redirect_url if redirect_url.startswith("http") else "https://www.zhipin.com" + redirect_url
                        log.info("[招呼语] 检测到弹窗，按页面自带 redirect-url 直达目标会话...")
                        try:
                            self.page.goto(target, wait_until="domcontentloaded", timeout=25000)
                        except Exception as e:
                            log.warning("[招呼语] 打开会话链接异常: %s", str(e)[:100])
                        pause(1.5, 2.5)
                    chat_input = self._find_element(SELECTORS["chat_input"], timeout_ms=10000)
                    if chat_input:
                        # 产品流程保证窗口正确,仅在读得出且明显不符时拦截
                        if self._verify_chat_window_identity(job_title, hr_company, strict=False):
                            greeting_sent = self.send_message(greeting_text)
                            if greeting_sent:
                                log.info("继续沟通跳转后成功发送自定义招呼语: %s", greeting_text[:40])
                        else:
                            log.warning("[招呼语] 继续沟通打开的窗口身份可疑，保守跳过发送")
                    else:
                        log.warning("[招呼语] 继续沟通已跳转但未找到输入框，转兜底路径")

            # ── 兜底: 自行跳聊天页点列表第一项(按最新消息排序,可能被其他HR新消息顶掉) → 必须严格校验身份 ──
            if not greeting_sent and greeting_text:
                try:
                    log.info("弹窗/继续沟通均未发送，走兜底: 跳聊天页点第一项+身份校验...")
                    self.page.goto("https://www.zhipin.com/web/geek/chat", wait_until="domcontentloaded", timeout=25000)
                    pause(1.5, 2.5)
                    top_conv = self._find_element(
                        [
                            '.user-list li[role="listitem"]',
                            'li[role="listitem"]',
                            ".friend-content",
                            '[class*="chat-item"]',
                        ],
                        timeout_ms=8000,
                    )
                    if top_conv is None:
                        log.warning("[招呼语] 兜底: 聊天页未找到会话列表项(url=%s)", self.page.url[:80])
                    elif self._force_click_safe(top_conv):
                        pause(1, 1.5)
                    chat_input = self._find_element(SELECTORS["chat_input"], timeout_ms=8000)
                    if chat_input is None:
                        try:
                            snippet = (self.page.inner_text("body") or "")[:150].replace("\n", " ")
                        except Exception:
                            snippet = ""
                        log.warning("[招呼语] 兜底: 未找到输入框(url=%s, 页面片段=%s)", self.page.url[:80], snippet)
                    elif self._verify_chat_window_identity(job_title, hr_company, strict=True):
                        greeting_sent = self.send_message(greeting_text)
                        if greeting_sent:
                            log.info("兜底成功发送自定义招呼语: %s", greeting_text[:40])
                    else:
                        log.warning("[招呼语] 兜底: 会话身份校验未通过，放弃发送(防错发)")
                except Exception as e:
                    log.warning("在聊天页补发自定义招呼语异常: %s", e)

            # 记录到 SQLite
            existing = get_application_by_url(job_url)
            if existing:
                if greeting_sent:
                    update_application_status(existing["id"], "applied", greeting_text)
                else:
                    update_application_status(existing["id"], "applied")
                app_id = existing["id"]
            else:
                app_id = add_application({"title": job_title, "company": hr_company, "url": job_url})
                if greeting_sent:
                    update_application_status(app_id, "applied", greeting_text)
                else:
                    update_application_status(app_id, "applied")

            # 记录会话与消息
            if hr_name and len(hr_name) >= 2:
                conv_id = get_or_create_conversation(app_id, hr_name, hr_company, job_title)
                if conv_id and greeting_sent:
                    add_message(conv_id, "me", greeting_text, ai_generated=False)
                    update_conversation_last_message(conv_id, greeting_text, "me", 0)

            increment_daily_stat("applications_sent")
            log.info("投递成功 (HR: %s, 招呼语已发送: %s)", hr_name or "未知", greeting_sent)
            return {"success": True, "message": "投递成功", "application_id": app_id}

        except Exception as e:
            log.error(f"投递失败: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def apply_batch(self, job_urls: List[str], greeting_template: Optional[str] = None, max_apply_limit: int = 0) -> List[dict]:
        """批量投递，带间隔延迟。可通过设置 batch_delay_sec 控制间隔。"""
        results = []
        min_delay = int(get_setting("batch_delay_min_sec", "3"))
        max_delay = int(get_setting("batch_delay_max_sec", "8"))
        for i, url in enumerate(job_urls):
            if i > 0:
                delay = random.uniform(min_delay, max_delay)
                log.info(f"[WAIT] 等待 {delay:.0f}s 后投递下一条...")
                time.sleep(delay)

            result = self.apply_to_job(url, greeting_template, max_apply_limit=max_apply_limit)
            results.append(result)

            if not result["success"] and "上限" in result.get("message", ""):
                break
        return results
