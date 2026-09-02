#!/usr/bin/env python3
"""
AutomationBase — 基础自动化类，包含底层 UI 交互和页面安全检查方法。
"""

import json
import random
import time
from typing import Optional, List

from playwright.sync_api import Locator

from backend.firefox import BossScraper, pause
from backend.logger import get_logger
from backend.state import init_db, get_setting
from backend import browser_ops

log = get_logger("automation_base")


class AutomationBase(BossScraper):
    """基础交互类，提供定位、模拟打字、安全校验和保活能力"""

    def __init__(self, headless=False):
        super().__init__(headless)
        init_db()

    # ══════════════════════════════════════
    #  底层交互 helpers
    # ══════════════════════════════════════

    def _find_element(self, selector_list: List[str], timeout_ms: int = 5000) -> Optional[Locator]:
        """逐个尝试选择器，返回第一个可见匹配。"""
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            for sel in selector_list:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible():
                        return loc
                except Exception:
                    continue
            time.sleep(0.3)
        return None

    def _find_all_elements(self, selector_list: List[str]) -> List[Locator]:
        """返回所有匹配的可见元素。"""
        for sel in selector_list:
            try:
                locs = self.page.locator(sel)
                count = locs.count()
                if count > 0:
                    return [locs.nth(i) for i in range(count)]
            except Exception:
                continue
        return []

    def _human_type(self, locator: Locator, text: str):
        """逐字输入，模拟真人打字。"""
        try:
            locator.click()
            time.sleep(random.uniform(0.1, 0.3))
        except Exception:
            pass
        for ch in text:
            self.page.keyboard.type(ch, delay=random.randint(50, 150))
        time.sleep(random.uniform(0.3, 0.8))

    def _safe_click(self, locator: Locator):
        """带随机延迟的点击。"""
        time.sleep(random.uniform(0.2, 0.6))
        try:
            locator.hover()
            time.sleep(random.uniform(0.1, 0.3))
        except Exception:
            pass
        locator.click()

    def _has_text(self, *texts: str) -> bool:
        """检查页面是否包含任意关键词。"""
        try:
            body = self.page.inner_text("body").lower()
            return any(t.lower() in body for t in texts)
        except Exception:
            return False

    # ══════════════════════════════════════
    #  安全检查
    # ══════════════════════════════════════

    def check_page_safety(self) -> bool:
        """所有自动化操作前检查页面安全状态。"""
        try:
            body = self.page.inner_text("body")
            body_lower = body.lower()

            if self._login_prompt_visible():
                log.warning("安全检查: 需要重新登录")
                return False
            if any(kw in body_lower[:500] for kw in ["验证", "滑块", "拼图", "captcha", "verify"]):
                log.warning("安全检查: 检测到验证码")
                return False
            if any(kw in body_lower[:500] for kw in ["账号异常", "违规", "限制使用", "冻结"]):
                log.warning("安全检查: 账号异常")
                return False
            if any(kw in body_lower[:500] for kw in ["操作太频繁", "稍后再试", "休息一下"]):
                log.warning("安全检查: 操作频率限制")
                return False
            return True
        except Exception:
            return True

    # ══════════════════════════════════════
    #  Session 保活 & 心跳
    # ══════════════════════════════════════

    def check_logged_in(self) -> bool:
        """快速检查当前是否已登录；未知空白页不直接当作过期。"""
        try:
            return self.is_logged_in_page()
        except Exception:
            return False

    def heartbeat(self) -> bool:
        """心跳: 只检查当前页面登录状态，不主动跳转。"""
        try:
            return self.check_logged_in()
        except Exception:
            return False

    def keep_alive(self):
        """主动保活: 在聊天页保持 BOSS session 活跃。已登录时用轻量操作代替完整刷新。"""
        try:
            current_url = self.page.url
            need_navigate = "/web/geek/chat" not in current_url
            # 前端独占操作(搜索/投递/手动发消息)进行中时不抢导航,只检查登录态
            if need_navigate and browser_ops.is_busy():
                return self.check_logged_in()
            try:
                if need_navigate:
                    self.page.goto("https://www.zhipin.com/web/geek/chat", wait_until="load", timeout=30000)
                    pause(2, 4)
                else:
                    # 已在聊天页，轻量滚动模拟用户活动，避免频繁 reload 被检测
                    try:
                        self.page.mouse.move(random.randint(200, 600), random.randint(300, 500))
                        pause(0.5, 1.0)
                        self.page.evaluate("window.scrollBy(0, %d)" % random.randint(-100, 100))
                    except Exception:
                        pass
            except Exception:
                pass
            return self.check_logged_in()
        except Exception:
            return False

    def _save_state(self):
        """保存当前浏览器状态到文件。"""
        try:
            from backend.firefox import STATE_FILE

            state = self._ctx.storage_state()
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
        except Exception:
            pass
