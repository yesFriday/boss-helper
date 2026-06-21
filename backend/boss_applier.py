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
            self.page.goto(job_url, wait_until="load", timeout=45000)
            pause(1, 2)

            if not self.check_page_safety():
                return {"success": False, "message": "安全检查未通过"}

            # 检查是否已投递
            if self._has_text("已沟通", "继续沟通"):
                existing = get_application_by_url(job_url)
                if existing and existing["status"] == "pending":
                    update_application_status(existing["id"], "applied")
                return {"success": True, "message": "已投递过", "already_applied": True}

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

            self._safe_click(apply_btn)
            pause(2, 3)

            # 检查限制消息
            if self._has_text("已达上限", "沟通人数已用完", "今日次数已用完", "今日沟通次数已用完"):
                return {"success": False, "message": "BOSS直聘今日沟通次数已用完"}

            # 等待聊天窗口加载
            log.info("等待聊天窗口加载...")
            chat_input = self._find_element(SELECTORS["chat_input"], timeout_ms=10000)
            if not chat_input:
                log.warning("未找到聊天输入框（等待10秒后），跳过发送招呼语")
                log.debug(f"当前页面URL: {self.page.url}")
                log.debug(f"当前页面标题: {self.page.title()}")

            # 发送招呼语
            greeting_text = greeting or get_setting(
                "greeting_template",
                "您好，我对贵公司的{job_title}岗位很感兴趣，请问可以详细了解一下吗？",
            )
            greeting_sent = False
            if chat_input and greeting_text:
                # 注意：send_message 属于聊天模块的方法。因为 BossChatMonitor 继承自 BossApplier，
                # 所以实例化后的 self.send_message 会指向聊天模块的实现。这里通过调用 self.send_message
                # 依然是完全没问题的。
                greeting_sent = self.send_message(greeting_text)
                if greeting_sent:
                    log.info("招呼语已发送")
                else:
                    log.warning("招呼语发送失败")

            # 记录到 SQLite
            existing = get_application_by_url(job_url)
            if existing:
                if greeting_sent:
                    update_application_status(existing["id"], "applied", greeting_text)
                else:
                    update_application_status(existing["id"], "applied")
                app_id = existing["id"]
            else:
                app_id = add_application({"title": "", "company": "", "url": job_url})
                if greeting_sent:
                    update_application_status(app_id, "applied", greeting_text)
                else:
                    update_application_status(app_id, "applied")

            # 从详情页提取 HR 真实姓名和岗位信息
            hr_name = ""
            hr_company = ""
            job_title = ""
            try:
                hr_info = self.page.evaluate("""() => {
                    const body = (document.body || {}).innerText || '';
                    const lines = body.split('\\n').map(l => l.trim()).filter(Boolean);
                    let hrName = '', hrTitle = '';
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
                    return {hrName, hrTitle};
                }""")
                hr_name = (hr_info.get("hrName") or "").strip()
                if not hr_name:
                    hr_name = ""
            except Exception:
                pass

            app_record = get_application_by_url(job_url) or {}
            hr_name = hr_name or app_record.get("hr_name", "")
            hr_company = app_record.get("company", "")
            job_title = app_record.get("job_title", "")

            # 只创建有 HR 名字的会话，避免"未知HR"垃圾数据
            if hr_name and len(hr_name) >= 2:
                get_or_create_conversation(app_id, hr_name, hr_company, job_title)

            increment_daily_stat("applications_sent")
            log.info("投递成功")
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
