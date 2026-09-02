#!/usr/bin/env python3
"""
定时调度器 —— 独立模块,负责「搜索 → 分块投递 → 聊天兜底」的时间段自动化。

设计要点:
- 状态持久化:enabled 与执行日志写入 settings 表,服务重启后自动恢复
- 聊天监控单一所有者:常规轮询归 app.py 的 chat_monitor_loop;
  本调度器仅在 monitor_task 已死时作为兜底跑一轮聊天周期
- 分块投递:批量投递拆为 APPLY_CHUNK 条/块,块间内联跑一轮聊天监控,
  避免长投递会话期间 HR 消息无人回复
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from backend.logger import get_logger

log = get_logger("scheduler")

CONFIG_KEY = "scheduler_config"
ENABLED_KEY = "scheduler_enabled"
LOG_KEY = "scheduler_log"

TICK_SECONDS = 30
APPLY_CHUNK = 5
LOG_MAX = 50
NO_PROGRESS_LIMIT = 3  # 连续 N 轮投递无进展(计数不涨)则熔断,防止无限重投

DEFAULT_CONFIG = {
    "days": [],
    "time_ranges": [],
    "auto_apply": {
        "keyword": "AI Agent",
        "city": "广州",
        "daily_limit": 30,
        "hr_active_filter": "在线,刚刚活跃,今日活跃,3日内活跃,本周活跃,本月活跃",
    },
    "auto_reply": {"style": "professional"},
}


@dataclass
class SchedulerDeps:
    """app.py 注入的运行时依赖,全部可 mock 以便单测。"""

    get_setting: Callable[[str, str], str]
    set_setting: Callable[[str, str], None]
    run_pw: Callable[..., Awaitable[Any]]
    get_automation: Callable[[], Any]
    broadcast: Callable[[dict], Awaitable[None]]
    city_code: Callable[[str], str]
    save_jobs: Callable[[list], tuple[int, int]]
    pending_jobs: Callable[[int, str], list]
    today_count: Callable[[], int]
    set_monitor_paused: Callable[[bool], None]
    get_monitor_paused: Callable[[], bool]
    monitor_alive: Callable[[], bool]
    run_chat_cycle: Callable[[], Awaitable[dict]]
    wait_monitor_idle: Callable[[], Awaitable[None]]


def match_time_range(config: dict, now: Optional[datetime] = None) -> Optional[str]:
    """返回 now 命中的时间段 key(如 "09:00~12:00"),未命中返回 None。"""
    now = now or datetime.now()
    if now.isoweekday() not in config.get("days", []):
        return None
    current_time = now.strftime("%H:%M")
    for tr in config.get("time_ranges", []):
        start = tr.get("start", "")
        end = tr.get("end", "")
        if start <= current_time <= end:
            return f"{start}~{end}"
    return None


class Scheduler:
    def __init__(self, deps: SchedulerDeps):
        self.d = deps
        self.enabled = deps.get_setting(ENABLED_KEY, "false") == "true"
        self.phase = "idle"
        self.log_entries: list[dict] = self._load_log()
        if self.enabled:
            log.info("[调度器] 从持久化状态恢复:已启用")

    # ── 持久化 ──

    def _load_log(self) -> list[dict]:
        raw = self.d.get_setting(LOG_KEY, "[]")
        try:
            entries = json.loads(raw)
            return entries if isinstance(entries, list) else []
        except Exception:
            return []

    def _persist_log(self):
        try:
            self.d.set_setting(LOG_KEY, json.dumps(self.log_entries[-LOG_MAX:], ensure_ascii=False))
        except Exception as e:
            log.warning(f"[调度器] 日志持久化失败: {e}")

    def _add_log(self, tasks: list) -> dict:
        entry = {"time": datetime.now().strftime("%H:%M"), "tasks": tasks}
        self.log_entries.append(entry)
        if len(self.log_entries) > LOG_MAX:
            self.log_entries.pop(0)
        self._persist_log()
        log.info(f"[调度器] {' | '.join(tasks)}")
        return entry

    async def _report(self, tasks: list):
        entry = self._add_log(tasks)
        await self.d.broadcast({"type": "scheduler_tick", "log": entry})

    # ── 配置 ──

    def get_config(self) -> dict:
        raw = self.d.get_setting(CONFIG_KEY, "{}")
        try:
            config = json.loads(raw)
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        merged = {**DEFAULT_CONFIG, **config}
        merged["enabled"] = self.enabled
        return merged

    async def update_config(self, req: dict) -> dict:
        enabled = bool(req.get("enabled", False))
        await self.set_enabled(enabled, persist_config=True, config=req)
        return self.get_config()

    async def set_enabled(self, enabled: bool, persist_config: bool = False, config: Optional[dict] = None):
        self.enabled = enabled
        self.d.set_setting(ENABLED_KEY, "true" if enabled else "false")
        if persist_config and config is not None:
            db_config = {k: v for k, v in config.items() if k != "enabled"}
            self.d.set_setting(CONFIG_KEY, json.dumps(db_config, ensure_ascii=False))
        if not enabled:
            self.phase = "idle"
        await self.d.broadcast({"type": "scheduler_config_updated", "config": self.get_config()})

    def get_status(self) -> dict:
        config = self.get_config()
        return {
            "active": self.enabled,
            "phase": self.phase,
            "today_count": self.d.today_count(),
            "daily_limit": config.get("auto_apply", {}).get("daily_limit", 30),
            "execution_log": self.log_entries[-20:],
        }

    def stop(self):
        """外部安全停止(页面异常等)。"""
        self.enabled = False
        self.d.set_setting(ENABLED_KEY, "false")
        self.phase = "idle"

    # ── 主循环 ──

    async def run(self):
        await asyncio.sleep(5)
        log.info("[调度器] 调度器已启动" + (",当前状态:启用" if self.enabled else ",等待用户开启"))
        while True:
            try:
                await asyncio.sleep(TICK_SECONDS)
                await self._tick()
            except asyncio.CancelledError:
                log.info("[调度器] 调度器已停止")
                self.phase = "idle"
                break
            except Exception as e:
                log.error(f"[调度器] 异常: {e}", exc_info=True)
                self.phase = "idle"
                await asyncio.sleep(TICK_SECONDS)

    async def _tick(self):
        if not self.enabled:
            self.phase = "idle"
            return

        config = self.get_config()

        # ── 聊天兜底:仅当 monitor_task 已死时,由调度器代跑一轮 ──
        automation = self.d.get_automation()
        if automation is not None and automation.page is not None and not self.d.monitor_alive():
            try:
                result = await self.d.run_chat_cycle()
                await self._emit_chat_result(result)
            except Exception as e:
                log.error(f"[调度器] 聊天兜底异常: {e}", exc_info=True)

        if match_time_range(config) is None:
            self.phase = "paused"
            return

        if automation is None or automation.page is None:
            return

        await self._apply_session(config)

    async def _emit_chat_result(self, result: dict):
        if result.get("replies_sent", 0) > 0:
            entry = self._add_log([f"AI回复{result['replies_sent']}条"])
            await self.d.broadcast({"type": "scheduler_tick", "log": entry})
            await self.d.broadcast({"type": "auto_reply_sent", "summary": result})
        if result.get("new_messages", 0) > 0:
            await self.d.broadcast({"type": "new_messages", "summary": result})

    async def _safety_ok(self, automation) -> bool:
        if await self.d.run_pw(automation.check_page_safety):
            return True
        self.stop()
        entry = self._add_log(["页面异常(验证码/登录失效)，已停止定时任务"])
        await self.d.broadcast({"type": "scheduler_tick", "log": entry})
        await self.d.broadcast({"type": "safety_warning", "message": "检测到页面异常，定时任务已自动停止"})
        return False

    async def _ensure_pending(self, config: dict) -> list:
        """取待投岗位;不足时补充搜索一次。"""
        auto_cfg = config.get("auto_apply", {})
        hr_filter = auto_cfg.get("hr_active_filter", "all")
        remaining = auto_cfg.get("daily_limit", 30) - self.d.today_count()
        pending = self.d.pending_jobs(max(remaining, 1), hr_filter)
        if pending:
            return pending
        keyword = auto_cfg.get("keyword", "AI Agent")
        city = auto_cfg.get("city", "广州")
        self.phase = "searching"
        log.info("[调度器] 待投岗位不足，补充搜索")
        try:
            total, saved = await self.d.save_jobs(keyword, self.d.city_code(city))
            await self._report([f"搜索「{keyword}」{total}条，保存{saved}条"])
        except Exception as e:
            log.error(f"[调度器] 补充搜索失败: {e}", exc_info=True)
            await self._report([f"搜索失败: {e}"])
            return []
        return self.d.pending_jobs(max(remaining, 1), hr_filter)

    async def _apply_session(self, config: dict):
        """一个时间窗内的投递会话:分块投递,块间跑一轮聊天监控。"""
        auto_cfg = config.get("auto_apply", {})
        daily_limit = auto_cfg.get("daily_limit", 30)
        automation = self.d.get_automation()

        was_paused = self.d.get_monitor_paused()
        self.d.set_monitor_paused(True)
        # 挡板:等进行中的监控周期跑完再开投递,避免与监控抢同一页面
        await self.d.wait_monitor_idle()
        no_progress = 0
        try:
            while self.enabled:
                applied = self.d.today_count()
                if applied >= daily_limit:
                    await self._report([f"今日已投递{applied}条，达到上限"])
                    break

                if not await self._safety_ok(automation):
                    break

                pending = await self._ensure_pending(config)
                if not pending:
                    await self._report(["无更多待投岗位"])
                    break

                remaining = daily_limit - applied
                urls = [p["job_url"] for p in pending if p.get("job_url")][:remaining]
                self.phase = "applying"
                try:
                    results = await self.d.run_pw(automation.apply_batch, urls[:APPLY_CHUNK], None, daily_limit)
                    ok = sum(1 for r in results if r.get("success"))
                    await self._report([f"投递{len(results)}条，成功{ok}条"])
                except Exception as e:
                    log.error(f"[调度器] 投递异常: {e}", exc_info=True)
                    await self._report([f"投递异常: {e}"])
                    break

                # 熔断:连续多轮计数不涨说明投递未生效(如账号被限流),停止本轮会话
                if self.d.today_count() == applied:
                    no_progress += 1
                    if no_progress >= NO_PROGRESS_LIMIT:
                        await self._report([f"连续{no_progress}轮投递无进展，熔断本轮会话"])
                        break
                else:
                    no_progress = 0

                # ── 块间喂一轮聊天,投递期间 HR 消息不再饿死 ──
                if self.enabled and self.d.today_count() < daily_limit:
                    self.phase = "chatting"
                    try:
                        result = await self.d.run_chat_cycle()
                        await self._emit_chat_result(result)
                    except Exception as e:
                        log.error(f"[调度器] 块间聊天异常: {e}", exc_info=True)
            self.phase = "idle"
        finally:
            self.d.set_monitor_paused(was_paused)
