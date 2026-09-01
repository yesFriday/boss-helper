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

MAX_APPLY_PER_DAY = 30


class BossApplier(AutomationBase):
    """投递简历业务类"""

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
        if today_count >= min(daily_limit, MAX_APPLY_PER_DAY):
            return {"success": False, "message": f"已达今日上限({today_count}条)"}

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

            # 检查是否已投递
            if self._has_text("已沟通", "继续沟通"):
                existing = get_application_by_url(job_url)
                if existing and existing["status"] == "pending":
                    update_application_status(existing["id"], "applied")
                return {"success": True, "message": "已投递过", "already_applied": True}

            # 从详情页提取 HR 真实姓名和岗位信息
            app_record = get_application_by_url(job_url) or {}
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
                return {"success": False, "message": "未找到投递按钮"}

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

            # 1. 尝试在详情页弹出的聊天输入框中发送
            chat_input = self._find_element(SELECTORS["chat_input"], timeout_ms=3000)
            if chat_input and greeting_text:
                greeting_sent = self.send_message(greeting_text)
                if greeting_sent:
                    log.info("在详情页弹窗中成功发送自定义招呼语: %s", greeting_text[:40])

            # 2. 如果详情页未弹出输入框，直接前往聊天页面补发自定义招呼语
            if not greeting_sent and greeting_text:
                log.info("详情页未内嵌输入框，正在前往聊天页面发送自定义招呼语...")
                try:
                    self.page.goto("https://www.zhipin.com/web/geek/chat", wait_until="domcontentloaded", timeout=25000)
                    pause(1.5, 2.5)
                    # 点击列表第一项（刚刚发起沟通的 HR）
                    top_conv = self.page.locator('li[role="listitem"], .friend-content, [class*="chat-item"]').first
                    if top_conv and top_conv.is_visible():
                        top_conv.click()
                        pause(1, 1.5)
                    chat_input = self._find_element(SELECTORS["chat_input"], timeout_ms=5000)
                    if chat_input:
                        greeting_sent = self.send_message(greeting_text)
                        if greeting_sent:
                            log.info("在聊天页成功发送自定义招呼语: %s", greeting_text[:40])
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
