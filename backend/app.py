#!/usr/bin/env python3
"""
BOSS直聘自动化控制台 —— FastAPI 后端
提供 REST API + WebSocket + 后台监控循环。
用法: python backend/app.py --port 8000
"""

import argparse
import asyncio
import json
import random
import re
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional, List
from urllib.parse import urljoin

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.logger import get_logger
from backend.autochat import BossAutomation

log = get_logger("app")
from backend.state import (
    add_application,
    get_application,
    get_application_by_url,
    update_application_from_job,
    list_applications,
    update_application_status,
    delete_application,
    delete_applications,
    get_today_application_count,
    get_or_create_conversation,
    get_conversation,
    list_active_conversations,
    add_message,
    get_messages,
    replace_conversation_messages,
    update_conversation_last_message,
    update_conversation_status,
    set_auto_reply,
    get_setting,
    set_setting,
    get_all_settings,
    get_daily_stats,
    get_wechat_exchanges,
    get_today_pending_count,
    get_pending_applications,
    get_pending_applications_by_activity,
    count_hours_replied_in_range,
    count_interest_level,
    add_to_shortlist,
    remove_from_shortlist,
    list_shortlists,
    is_in_shortlist,
)
from backend.replier import generate_greeting
from backend.scheduler import Scheduler, SchedulerDeps

# ── FastAPI 应用 ──
app = FastAPI(title="BOSS直聘自动化控制台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

project_root = Path(__file__).parent.parent
static_dir = project_root / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ── 全局状态 ──
automation: Optional[BossAutomation] = None
monitor_task: Optional[asyncio.Task] = None
scheduler_task: Optional[asyncio.Task] = None
scheduler: Optional["Scheduler"] = None
ws_clients: List[WebSocket] = []
monitor_paused: bool = False
browser_sync_lock: Optional[asyncio.Lock] = None
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "bosshelper_backend", "version": "1.0.0"}


@app.post("/api/system/shutdown")
async def shutdown_system():
    log.info("收到关机请求，正在退出服务...")
    asyncio.create_task(_graceful_shutdown())
    return {"status": "shutting_down"}


async def _graceful_shutdown():
    await asyncio.sleep(0.5)
    global automation
    if scheduler_task and not scheduler_task.done():
        scheduler_task.cancel()
    if automation:
        try:
            automation.stop()
        except Exception:
            pass
    sys.exit(0)


def _build_scheduler_deps() -> SchedulerDeps:
    async def _save_jobs(keyword: str, city_code: str) -> tuple:
        if automation is None:
            return 0, 0
        jobs = await _run_pw(automation.search, keyword, city_code)
        saved = 0
        for j in jobs:
            j["url"] = _normalize_job_url(j.get("url", ""))
            if j.get("url"):
                existing = get_application_by_url(j["url"])
                if existing:
                    update_application_from_job(existing["id"], j)
                else:
                    aid = add_application(j)
                    if aid:
                        saved += 1
        return len(jobs), saved

    def _set_monitor_paused(v: bool):
        global monitor_paused
        monitor_paused = v

    return SchedulerDeps(
        get_setting=get_setting,
        set_setting=set_setting,
        run_pw=_run_pw,
        get_automation=lambda: automation,
        broadcast=broadcast_ws,
        city_code=lambda city: CITY_MAP.get(city, "101280100"),
        save_jobs=_save_jobs,
        pending_jobs=get_pending_applications_by_activity,
        today_count=get_today_application_count,
        set_monitor_paused=_set_monitor_paused,
        get_monitor_paused=lambda: monitor_paused,
        monitor_alive=lambda: monitor_task is not None and not monitor_task.done(),
        run_chat_cycle=lambda: automation.run_chat_monitor_cycle(),
    )


@app.on_event("startup")
async def on_startup():
    global automation, monitor_task, scheduler_task, browser_sync_lock, scheduler
    browser_sync_lock = asyncio.Lock()
    # 清理旧垃圾会话 + 合并同名重复会话
    try:
        from backend.state import get_db

        db = get_db()
        junk_names = [
            "HR",
            "你好",
            "消息",
            "未知HR",
            "AI简历",
            "简历更新",
            "附件简历制作",
            "附件上传",
        ]
        for name in junk_names:
            db.execute("DELETE FROM conversations WHERE hr_name = ?", (name,))
        db.execute("DELETE FROM conversations WHERE hr_name IS NULL OR length(hr_name) < 2")
        # 合并同名重复：保留最早的，把重复的改成 closed
        db.execute("""
            UPDATE conversations SET status = 'closed'
            WHERE id NOT IN (
                SELECT MIN(id) FROM conversations WHERE status != 'closed' GROUP BY hr_name
            ) AND status != 'closed'
        """)
        db.commit()
    except Exception:
        pass
    # 清理历史存库的 BOSS 系统通知（一次性迁移，幂等）
    try:
        from backend.state import purge_system_notifications

        purge_system_notifications()
    except Exception:
        pass
    if automation is not None and automation.page is not None:
        monitor_task = asyncio.create_task(chat_monitor_loop())
    # 启动定时调度器(状态从 settings 表恢复)
    scheduler = Scheduler(_build_scheduler_deps())
    scheduler_task = asyncio.create_task(scheduler.run())

# Playwright 同步 API 要求所有操作在同一线程 —— 单线程池收敛在 runtime 模块,
# 监控的 LLM 生成阶段走 runtime.llm_executor,浏览器线程期间空闲供前端手动操作使用
from backend.runtime import pw_executor as _playwright_executor  # noqa: E402


async def _run_pw(fn, *args):
    """在 Playwright 专属线程中执行同步操作，彻底清除该线程的 asyncio 状态。"""

    def _wrapper():
        import asyncio
        # Python 3.14 + uvicorn 可能继承事件循环策略，重置掉
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
        asyncio.set_event_loop(None)
        return fn(*args)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_playwright_executor, _wrapper)


# BOSS直聘城市代码（按省份分组）
CITY_MAP = {
    # 山东省
    "济南": "101120100",
    "青岛": "101120200",
    "淄博": "101120300",
    "德州": "101120400",
    "烟台": "101120500",
    "潍坊": "101120600",
    "济宁": "101120700",
    "泰安": "101120800",
    "临沂": "101120900",
    "菏泽": "101121000",
    "滨州": "101121100",
    "东营": "101121200",
    "威海": "101121300",
    "枣庄": "101121400",
    "日照": "101121500",
    "聊城": "101121700",
    # 一线城市
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    # 新一线城市
    "成都": "101270100",
    "杭州": "101210100",
    "武汉": "101200100",
    "南京": "101190100",
    "重庆": "101040100",
    "西安": "101110100",
    "长沙": "101250100",
    "天津": "101030100",
    "苏州": "101190400",
    "郑州": "101180100",
    "东莞": "101281600",
    "沈阳": "101070100",
    "宁波": "101210400",
    "昆明": "101290100",
    # 其他省会城市
    "合肥": "101220100",
    "福州": "101230100",
    "厦门": "101230200",
    "南昌": "101240100",
    "贵阳": "101260100",
    "南宁": "101300100",
    "太原": "101100100",
    "石家庄": "101090100",
    "哈尔滨": "101050100",
    "长春": "101060100",
    "兰州": "101160100",
    "乌鲁木齐": "101130100",
    "呼和浩特": "101080100",
    "拉萨": "101140100",
    "西宁": "101150100",
    "银川": "101170100",
    "海口": "101310100",
    "三亚": "101310200",
    # 特殊选项
    "全国": "100010000",
}


def _normalize_job_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    return urljoin("https://www.zhipin.com", url)


def _search_job_payload(job: dict, application: Optional[dict] = None) -> dict:
    """统一搜索结果和数据库记录的字段名，方便前端直接渲染。"""
    application = application or {}
    return {
        "id": application.get("id"),
        "job_title": application.get("job_title") or job.get("title", ""),
        "company": application.get("company") or job.get("company", ""),
        "salary": application.get("salary") or job.get("salary", ""),
        "job_url": application.get("job_url") or _normalize_job_url(job.get("url", "")),
        "city": application.get("city") or job.get("city", ""),
        "experience": application.get("experience") or job.get("experience", ""),
        "education": application.get("education") or job.get("education", ""),
        "hr_name": application.get("hr_name") or job.get("hr_name", ""),
        "hr_title": application.get("hr_title") or job.get("hr_title", ""),
        "description": application.get("description") or job.get("description", ""),
        "status": application.get("status") or ("pending" if job.get("url") else "missing_url"),
    }


def _clean_messages_for_web(messages: List[dict]) -> List[dict]:
    """清理 BOSS DOM 里混入的已读/送达状态，保持 Web 端只展示聊天正文。"""
    cleaned = []
    status_words = ("已读", "未读", "送达", "发送失败", "已发送")
    for msg in messages:
        item = dict(msg)
        content = (item.get("content") or "").strip()
        for word in status_words:
            if content.startswith(word):
                content = content[len(word) :].strip()
            if content.endswith(word):
                content = content[: -len(word)].strip()
        item["content"] = content
        if content:
            cleaned.append(item)
    return cleaned


# ══════════════════════════════════════
#  Pydantic Models
# ══════════════════════════════════════


class SearchRequest(BaseModel):
    keyword: str = "AI Agent"
    city: str = "广州"
    welfare: Optional[str] = None  # 福利筛选 如 "双休,五险一金"
    salary_expect: Optional[int] = None  # 期望薪资(K)，闭区间判断
    experience_expect: Optional[int] = None  # 工作年限(年)，闭区间判断
    exclude_hr_active: Optional[str] = None  # 排除HR活跃状态，如 "半年前活跃,一年前活跃"
    limit: int = 60


class ApplyRequest(BaseModel):
    job_url: str
    greeting: Optional[str] = None


class ApplyBatchRequest(BaseModel):
    job_urls: List[str]
    greeting: Optional[str] = None


class AnalyzeRequest(BaseModel):
    job_url: str
    job_title: Optional[str] = ""
    company: Optional[str] = ""
    description: Optional[str] = ""


class DeleteJobsBatchRequest(BaseModel):
    job_ids: List[int]


class SendMessageRequest(BaseModel):
    content: str


class SettingsUpdate(BaseModel):
    greeting_template: Optional[str] = None
    greeting_enabled: Optional[str] = None
    ai_reply_style: Optional[str] = None
    daily_apply_limit: Optional[str] = None
    auto_reply_enabled: Optional[str] = None
    min_reply_delay_sec: Optional[str] = None
    max_reply_delay_sec: Optional[str] = None
    batch_delay_min_sec: Optional[str] = None
    batch_delay_max_sec: Optional[str] = None
    resume_summary: Optional[str] = None
    wechat_id: Optional[str] = None
    search_keywords: Optional[str] = None  # 逗号分隔的搜索关键词
    selector_overrides: Optional[str] = None  # JSON 格式的选择器覆盖
    ai_api_key: Optional[str] = None  # AI API Key
    ai_base_url: Optional[str] = None  # AI Base URL
    ai_model: Optional[str] = None  # AI 模型名称
    ai_is_full_url: Optional[str] = None  # 是否为完整 URL 模式
    interview_format: Optional[str] = None  # 面试形式限制 (online/offline/both)
    interview_time_slots: Optional[str] = None  # 面试时间段配置 (JSON格式)
    interview_daily_limit: Optional[str] = None  # 每日面试上限数


# ══════════════════════════════════════
#  WebSocket 广播
# ══════════════════════════════════════


async def broadcast_ws(message: dict):
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in ws_clients:
            ws_clients.remove(ws)


# ══════════════════════════════════════
#  页面
# ══════════════════════════════════════


@app.get("/", response_class=HTMLResponse)
def index():
    # 优先使用 React 构建产物
    react_index = static_dir / "dist" / "index.html"
    if react_index.exists():
        return HTMLResponse(content=react_index.read_text(encoding="utf-8"))
    # 回退到旧版 dashboard.html
    html_path = static_dir / "dashboard.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>BOSS直聘自动化控制台</h1><p>dashboard.html 未找到</p>")


# ══════════════════════════════════════
#  系统状态
# ══════════════════════════════════════


@app.get("/api/status")
def get_status():
    browser_ok = automation is not None and automation.page is not None
    return {
        "browser_running": browser_ok,
        "auto_reply_enabled": get_setting("auto_reply_enabled", "true") == "true",
        "monitor_running": monitor_task is not None and not monitor_task.done(),
        "monitor_paused": monitor_paused,
        "today_applications": get_today_application_count(),
        "active_conversations": len(list_active_conversations()),
        "daily_stats": get_daily_stats(),
    }


@app.get("/api/stats")
def get_stats():
    """投递转化漏斗统计。"""
    today = get_daily_stats()
    return {
        "today_applications": get_today_application_count(),
        "pending": get_today_pending_count(),
        "replied": count_hours_replied_in_range(24),
        "interview": count_interest_level("high"),
        "active_conversations": len(list_active_conversations()),
        "daily_stats": today,
    }


@app.get("/api/doctor")
def doctor():
    """诊断环境：Python版本、浏览器状态、登录态、AI配置等。"""
    import os
    import sys as _sys

    try:
        _sys.path.insert(0, str(project_root / "interview"))
        from llm_client import _load_ai_config

        cfg = _load_ai_config()
        ai_key_ok = bool(cfg.get("api_key") and len(cfg["api_key"]) > 10)
    except Exception:
        ai_key_ok = False

    browser_ok = automation is not None and automation.page is not None
    checks = {
        "python": {"ok": True, "detail": _sys.version.split()[0]},
        "browser": {"ok": browser_ok, "detail": "运行中" if browser_ok else "未启动"},
        "boss_login": {"ok": browser_ok, "detail": "已登录" if browser_ok else "未登录"},
        "ai_key": {"ok": ai_key_ok, "detail": "已配置" if ai_key_ok else "未配置"},
        "today_applications": get_today_application_count(),
        "pending_jobs": get_today_pending_count(),
    }
    all_ok = all(v.get("ok", True) for v in checks.values())
    return {"ok": all_ok, "checks": checks}


@app.post("/api/system/start")
async def start_automation():
    global automation, monitor_task
    if automation is not None and automation.page is not None:
        return {"status": "already_started"}

    # 在后台线程启动浏览器，避免阻塞事件循环
    def _do_start():
        a = BossAutomation(headless=False)
        a.start()
        return a

    try:
        automation = await _run_pw(_do_start)
    except Exception as e:
        automation = None
        return {"status": "error", "message": f"浏览器启动失败: {e}"}

    if automation is None or automation.page is None:
        # 半启动状态必须彻底关闭,否则 Playwright 循环残留导致后续启动报 Sync API 错误
        if automation is not None:
            try:
                await _run_pw(automation.close)
            except Exception:
                pass
        automation = None
        return {"status": "error", "message": "浏览器启动后页面为空，请重试"}

    if monitor_task is None or monitor_task.done():
        monitor_task = asyncio.create_task(chat_monitor_loop())
    await broadcast_ws({"type": "system", "event": "started"})
    return {"status": "started"}


@app.post("/api/system/stop")
async def stop_automation():
    global automation, monitor_task
    if monitor_task and not monitor_task.done():
        monitor_task.cancel()
        monitor_task = None
    if automation:
        try:
            await _run_pw(automation._save_state)  # 正常关闭时保存登录态
        except Exception:
            pass
        try:
            await _run_pw(automation.close)
        except Exception:
            pass
        automation = None
    await broadcast_ws({"type": "system", "event": "stopped"})
    return {"status": "stopped"}


@app.post("/api/system/relogin")
async def relogin():
    """重新登录 BOSS直聘。会打开浏览器让用户扫码。"""
    global automation, monitor_task
    if monitor_task and not monitor_task.done():
        monitor_task.cancel()
        monitor_task = None
    if automation:
        try:
            await _run_pw(automation.close)
        except Exception:
            pass
        automation = None

    def _do_relogin():
        a = BossAutomation(headless=False)
        a.start()
        a.login()
        # login() 会轮询等用户扫码，完成后保存状态
        return a

    try:
        automation = await _run_pw(_do_relogin)
    except Exception as e:
        automation = None
        return {"status": "error", "message": f"登录失败: {e}"}

    if automation is None or automation.page is None:
        automation = None
        return {"status": "error", "message": "登录后页面异常，请重试"}

    if monitor_task is None or monitor_task.done():
        monitor_task = asyncio.create_task(chat_monitor_loop())
    await broadcast_ws({"type": "system", "event": "relogin_ok"})
    return {"status": "ok", "message": "扫码登录成功"}


@app.post("/api/system/heartbeat")
async def manual_heartbeat():
    """手动心跳保活。"""
    if not automation or automation.page is None:
        raise HTTPException(status_code=503, detail="浏览器未启动")
    alive = await _run_pw(automation.heartbeat)
    if not alive:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return {"status": "ok", "alive": True}


@app.post("/api/monitor/pause")
async def pause_monitor():
    global monitor_paused
    monitor_paused = True
    await broadcast_ws({"type": "monitor_paused"})
    return {"status": "paused"}


@app.post("/api/monitor/resume")
async def resume_monitor():
    global monitor_paused
    monitor_paused = False
    await broadcast_ws({"type": "monitor_resumed"})
    return {"status": "resumed"}


@app.post("/api/system/navigate-chat")
async def navigate_to_chat_page():
    """在浏览器中打开 BOSS 直聘聊天页。"""
    if not automation or automation.page is None:
        raise HTTPException(status_code=503, detail="浏览器未启动")
    success = await _run_pw(automation.navigate_to_chat)
    return {
        "status": "ok" if success else "error",
        "message": "已跳转到聊天页" if success else "跳转失败，请检查登录状态",
    }


class OpenUrlRequest(BaseModel):
    url: str


@app.post("/api/system/open-url")
def open_system_url(req: OpenUrlRequest):
    """使用系统默认浏览器打开指定 URL。"""
    if not req.url:
        raise HTTPException(status_code=400, detail="url 不能为空")
    try:
        webbrowser.open(req.url)
        return {"status": "ok", "url": req.url}
    except Exception as e:
        log.error(f"打开链接失败 {req.url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
def health():
    return {"status": "ok", "browser": automation is not None}


# ══════════════════════════════════════
#  调试 / 页面分析（BOSS改版时诊断选择器）
# ══════════════════════════════════════


class SelectorTest(BaseModel):
    selector: str


@app.post("/api/debug/selector-test")
async def test_selector(req: SelectorTest):
    """测试任意 CSS 选择器，返回匹配元素数和文本。"""
    if not automation or automation.page is None:
        raise HTTPException(status_code=503, detail="浏览器未启动")
    result = await _run_pw(
        lambda: automation.page.evaluate(
            """(sel) => {
            try {
                const els = document.querySelectorAll(sel);
                const items = [];
                for (let i = 0; i < Math.min(els.length, 10); i++) {
                    items.push((els[i].innerText || '').trim().substring(0, 200));
                }
                return {count: els.length, samples: items};
            } catch(e) {
                return {error: e.message};
            }
        }""",
            req.selector,
        )
    )
    return result


@app.get("/api/debug/page-stats")
async def page_stats():
    """返回当前页面 DOM 统计，帮助诊断选择器失效。"""
    if not automation or automation.page is None:
        raise HTTPException(status_code=503, detail="浏览器未启动")
    result = await _run_pw(
        lambda: automation.page.evaluate("""() => {
        const stats = {};
        stats.url = window.location.href;
        stats.title = document.title;
        stats.bodyLength = (document.body?.innerText || '').length;
        // 关键元素计数
        stats.liCount = document.querySelectorAll('li').length;
        stats.inputCount = document.querySelectorAll('input, textarea, [contenteditable]').length;
        stats.buttonCount = document.querySelectorAll('button').length;
        stats.messageItems = document.querySelectorAll('li.message-item, [class*="message-item"]').length;
        stats.listItems = document.querySelectorAll('li[role="listitem"]').length;
        stats.chatInput = document.querySelector('#chat-input') ? 1 : 0;
        stats.sendButton = document.querySelector('button[type="send"]') ? 1 : 0;
        // body 前 500 字符
        stats.bodyPreview = (document.body?.innerText || '').substring(0, 500);
        return stats;
    }""")
    )
    return result


@app.get("/api/debug/selectors-status")
async def selectors_status():
    """检查所有关键选择器的有效性。"""
    if not automation or automation.page is None:
        raise HTTPException(status_code=503, detail="浏览器未启动")
    from backend.autochat import SELECTORS

    result = await _run_pw(
        lambda: automation.page.evaluate(
            """(groups) => {
            const res = {};
            for (const [key, sels] of Object.entries(groups)) {
                for (const sel of sels) {
                    try {
                        const count = document.querySelectorAll(sel).length;
                        if (count > 0) {
                            res[key] = {selector: sel, count: count, ok: true};
                            break;
                        }
                    } catch(e) {}
                }
                if (!res[key]) res[key] = {selector: sels[sels.length-1], count: 0, ok: false};
            }
            return res;
        }""",
            SELECTORS,
        )
    )
    return result


# ══════════════════════════════════════
#  岗位搜索 & 管理
# ══════════════════════════════════════


@app.get("/api/jobs")
def list_jobs(status: Optional[str] = None, limit: int = 100):
    jobs = list_applications(status, limit)
    return {"jobs": jobs, "total": len(jobs)}


@app.post("/api/jobs/search/cancel")
async def cancel_search():
    global search_cancelled
    search_cancelled = True
    if automation:
        automation.search_cancelled = True
    log.info("[搜索] 用户取消搜索")
    return {"status": "cancelled"}


@app.post("/api/jobs/search")
async def search_jobs(req: SearchRequest):
    global monitor_paused, search_cancelled
    search_cancelled = False  # 重置取消标志
    if not automation or automation.page is None:
        raise HTTPException(status_code=503, detail="浏览器未启动，请先到设置Tab点击「启动浏览器」")
    automation.search_cancelled = False  # 重置自动化对象的取消标志
    was_paused = monitor_paused
    monitor_paused = True
    try:
        city_code = CITY_MAP.get(req.city, "101280100")
        try:
            jobs = await _run_pw(automation.search, req.keyword, city_code)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"搜索失败: {e}")

        # 福利筛选
        if req.welfare:
            welfare_kw = [w.strip() for w in req.welfare.split(",") if w.strip()]
            jobs = automation._filter_by_welfare(jobs, welfare_kw)

        # 薪资和经验筛选
        if req.salary_expect is not None or req.experience_expect is not None:
            jobs = automation._filter_by_expect(jobs, req.salary_expect, req.experience_expect)

        # HR 活跃度筛选
        if req.exclude_hr_active:
            exclude_list = [s.strip() for s in req.exclude_hr_active.split(",") if s.strip()]
            jobs = automation._filter_by_hr_active(jobs, exclude_list)

        saved_ids = []
        result_jobs = []
        for j in jobs:
            j["url"] = _normalize_job_url(j.get("url", ""))
            if j.get("url"):
                existing = get_application_by_url(j["url"])
                if existing:
                    updated = update_application_from_job(existing["id"], j) or existing
                    saved_ids.append(updated["id"])
                    result_jobs.append(_search_job_payload(j, updated))
                else:
                    aid = add_application(j)
                    if aid:
                        saved_ids.append(aid)
                        result_jobs.append(_search_job_payload(j, get_application(aid)))
                    else:
                        result_jobs.append(_search_job_payload(j))
            else:
                result_jobs.append(_search_job_payload(j))

        await broadcast_ws(
            {
                "type": "search_complete",
                "keyword": req.keyword,
                "city": req.city,
                "found": len(jobs),
            }
        )
        return {"jobs_found": len(jobs), "saved": len(saved_ids), "jobs": result_jobs}
    finally:
        monitor_paused = was_paused


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    job = get_application(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return {"job": job}


@app.post("/api/jobs/{job_id}/skip")
async def skip_job(job_id: int):
    update_application_status(job_id, "skipped")
    await broadcast_ws({"type": "job_updated", "job_id": job_id, "status": "skipped"})
    return {"status": "ok"}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int):
    success = delete_application(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="岗位记录不存在或已删除")
    await broadcast_ws({"type": "job_deleted", "job_id": job_id})
    return {"status": "ok", "deleted_id": job_id}


@app.post("/api/jobs/delete-batch")
async def delete_jobs_batch(req: DeleteJobsBatchRequest):
    count = delete_applications(req.job_ids)
    await broadcast_ws({"type": "jobs_batch_deleted", "job_ids": req.job_ids, "count": count})
    return {"status": "ok", "deleted_count": count}


# ══════════════════════════════════════
#  投递
# ══════════════════════════════════════


@app.post("/api/jobs/apply")
async def apply_to_job(req: ApplyRequest):
    if not automation:
        raise HTTPException(status_code=503, detail="浏览器未启动")

    daily_limit = int(get_setting("daily_apply_limit", "15"))
    if get_today_application_count() >= daily_limit:
        raise HTTPException(status_code=429, detail="已达到今日投递上限")

    greeting = req.greeting
    if not greeting:
        job = get_application_by_url(req.job_url)
        title = job["job_title"] if job else "相关岗位"
        company = job["company"] if job else "贵公司"
        style = get_setting("ai_reply_style", "professional")
        greeting = generate_greeting(title, company, style=style)

    # 在后台线程运行（Playwright 是同步的）
    result = await _run_pw(automation.apply_to_job, req.job_url, greeting)
    if result.get("success"):
        await broadcast_ws(
            {
                "type": "apply_complete",
                "job_url": req.job_url,
                "job_id": result.get("application_id"),
            }
        )
    return result


@app.post("/api/jobs/apply-batch")
async def apply_batch(req: ApplyBatchRequest):
    if not automation:
        raise HTTPException(status_code=503, detail="浏览器未启动")

    daily_limit = int(get_setting("daily_apply_limit", "15"))
    remaining = daily_limit - get_today_application_count()
    urls = req.job_urls[: max(1, remaining)]

    results = await _run_pw(automation.apply_batch, urls, req.greeting)
    await broadcast_ws(
        {
            "type": "batch_complete",
            "total": len(results),
            "success": sum(1 for r in results if r.get("success")),
        }
    )
    return {"results": results}


@app.post("/api/jobs/analyze")
async def analyze_jd(req: AnalyzeRequest):
    """AI分析岗位JD，返回匹配度、关键技能、差距、建议。"""
    resume = get_setting("resume_summary", "")
    desc = req.description or ""
    title = req.job_title or ""
    company = req.company or ""

    if resume and len(resume.strip()) > 5:
        prompt = f"""你是求职辅导专家。分析以下岗位JD，对比求职者简历，输出JSON。

## 求职者简历
{resume}

## 岗位信息
- 公司: {company}
- 职位: {title}
- JD: {desc[:2000]}

## 输出格式（严格JSON）
{{
  "match_score": 85,
  "key_skills": ["Python", "LangChain", "RAG"],
  "gap": "缺少K8s部署经验",
  "advice": "建议强调Agent开发经验，问对方技术栈",
  "summary": "整体匹配度较高，注意补充部署相关经验"
}}"""
    else:
        prompt = f"""你是求职辅导专家。分析以下岗位JD，提取关键信息，输出JSON。

## 岗位信息
- 公司: {company}
- 职位: {title}
- JD: {desc[:2000]}

## 输出格式（严格JSON）
{{
  "match_score": 70,
  "key_skills": ["Python", "LangChain", "RAG"],
  "gap": "",
  "advice": "",
  "summary": "该岗位的核心要求是..."
}}

注意：match_score 基于 JD 难度和市场需求预估即可，不必对比简历。summary 用一两句总结这个岗位的核心要求。"""

    try:
        sys.path.insert(0, str(project_root / "interview"))
        from llm_client import get_llm
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = get_llm(temperature=0.3)
        raw = llm.invoke([
            SystemMessage(content="你是求职辅导专家，输出严格JSON。"),
            HumanMessage(content=prompt)
        ]).content
        import json

        return json.loads(raw.strip().strip("`").strip("json").strip())
    except Exception as e:
        return {"error": f"AI分析失败: {e}", "match_score": 0, "summary": "请检查AI配置"}


# ══════════════════════════════════════
#  候选池
# ══════════════════════════════════════


@app.get("/api/shortlists")
def get_shortlists():
    return {"shortlists": list_shortlists()}


@app.post("/api/shortlists")
def add_shortlist(req: dict = {}):
    url = req.get("job_url", "")
    if not url:
        raise HTTPException(status_code=400, detail="缺少 job_url")
    if is_in_shortlist(url):
        return {"status": "already_exists"}
    sid = add_to_shortlist(
        url,
        req.get("title", ""),
        req.get("company", ""),
        req.get("salary", ""),
        req.get("city", ""),
        req.get("note", ""),
    )
    if sid:
        return {"status": "ok", "id": sid}
    return {"status": "duplicate"}


@app.delete("/api/shortlists/{sid}")
def remove_shortlist(sid: int):
    remove_from_shortlist(sid)
    return {"status": "ok"}


@app.get("/api/interviews")
def get_interviews():
    from backend.state import get_all_interviews
    return {"interviews": get_all_interviews()}


@app.delete("/api/interviews/{iid}")
def remove_interview(iid: int):
    from backend.state import delete_interview
    success = delete_interview(iid)
    if success:
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="面试记录不存在")


# ══════════════════════════════════════
#  会话 & 聊天
# ══════════════════════════════════════


@app.get("/api/wechat-exchanges")
def list_wechat_exchanges():
    """返回所有已获取到 HR 微信号的会话。"""
    records = get_wechat_exchanges()
    return {"exchanges": records}


@app.get("/api/conversations")
def list_conversations(filter: str = ""):
    dangerous_only = filter == "dangerous"
    convs = list_active_conversations(dangerous_only=dangerous_only)
    return {"conversations": convs}


@app.get("/api/conversations/{conv_id}")
def get_conversation_detail(conv_id: int):
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    messages = _clean_messages_for_web(get_messages(conv_id, 100))
    return {"conversation": conv, "messages": messages}


@app.get("/api/conversations/{conv_id}/messages")
def get_conversation_messages(conv_id: int, limit: int = 50):
    # 这个接口被前端频繁轮询，必须只读本地缓存，不能每次都控制浏览器。
    return {"messages": _clean_messages_for_web(get_messages(conv_id, limit))}


@app.post("/api/conversations/{conv_id}/sync")
async def sync_conversation_messages(conv_id: int):
    """按需从当前 BOSS 浏览器会话同步一次消息。"""
    global browser_sync_lock
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not automation or automation.page is None:
        return {
            "success": False,
            "message": "浏览器未启动",
            "messages": _clean_messages_for_web(get_messages(conv_id, 100)),
        }

    hr_name = conv.get("hr_name", "")
    if not hr_name:
        raise HTTPException(status_code=400, detail="会话缺少HR姓名")

    if browser_sync_lock is None:
        browser_sync_lock = asyncio.Lock()
    if browser_sync_lock.locked():
        return {
            "success": False,
            "message": "浏览器正忙，先显示缓存",
            "messages": _clean_messages_for_web(get_messages(conv_id, 100)),
        }

    try:
        async with browser_sync_lock:
            opened = await asyncio.wait_for(_run_pw(automation.open_conversation_by_name, hr_name), timeout=8)
            if not opened:
                return {
                    "success": False,
                    "message": f"无法打开 {hr_name} 的会话",
                    "messages": _clean_messages_for_web(get_messages(conv_id, 100)),
                }

            live_messages = await asyncio.wait_for(_run_pw(automation.read_visible_messages), timeout=5)
            if live_messages:
                replace_conversation_messages(conv_id, live_messages)
                last = live_messages[-1]
                update_conversation_last_message(conv_id, last.get("content", ""), last.get("sender", "hr"))
    except asyncio.TimeoutError:
        return {
            "success": False,
            "message": "同步超时，先显示缓存",
            "messages": _clean_messages_for_web(get_messages(conv_id, 100)),
        }

    return {
        "success": True,
        "messages": _clean_messages_for_web(get_messages(conv_id, 100)),
    }


@app.post("/api/conversations/{conv_id}/send")
async def send_manual_message(conv_id: int, req: SendMessageRequest):
    if not automation:
        raise HTTPException(status_code=503, detail="浏览器未启动")
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    hr_name = conv.get("hr_name", "")
    if not hr_name:
        raise HTTPException(status_code=400, detail="会话缺少HR姓名")

    # 先打开对应会话
    opened = await _run_pw(automation.open_conversation_by_name, hr_name)
    if not opened:
        raise HTTPException(status_code=500, detail=f"无法在浏览器中打开 {hr_name} 的会话")

    browser_ok = await _run_pw(automation.send_message, req.content, False)
    if not browser_ok:
        raise HTTPException(status_code=500, detail="浏览器发送失败，本地不会写入这条消息")

    add_message(conv_id, "me", req.content, ai_generated=False)
    update_conversation_last_message(conv_id, req.content, "me")
    await broadcast_ws(
        {
            "type": "manual_message_sent",
            "conversation_id": conv_id,
        }
    )
    return {"success": True, "browser_sent": browser_ok}


@app.post("/api/conversations/{conv_id}/open")
async def open_conversation_in_browser(conv_id: int):
    """在浏览器中打开对应会话。"""
    if not automation:
        raise HTTPException(status_code=503, detail="浏览器未启动")
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    hr_name = conv.get("hr_name", "")
    if not hr_name:
        raise HTTPException(status_code=400, detail="会话缺少HR姓名")
    success = await _run_pw(automation.open_conversation_by_name, hr_name)
    return {
        "success": success,
        "message": f"已在浏览器中打开 {hr_name} 的会话" if success else "打开失败",
    }


@app.post("/api/conversations/{conv_id}/pause")
async def pause_auto_reply(conv_id: int):
    set_auto_reply(conv_id, False)
    await broadcast_ws(
        {
            "type": "auto_reply_toggled",
            "conversation_id": conv_id,
            "enabled": False,
        }
    )
    return {"status": "ok"}


@app.post("/api/conversations/{conv_id}/resume")
async def resume_auto_reply(conv_id: int):
    set_auto_reply(conv_id, True)
    update_conversation_status(conv_id, "active")
    await broadcast_ws(
        {
            "type": "auto_reply_toggled",
            "conversation_id": conv_id,
            "enabled": True,
        }
    )
    return {"status": "ok"}


# ══════════════════════════════════════
#  设置
# ══════════════════════════════════════


@app.get("/api/settings")
def read_settings():
    settings = get_all_settings()
    # 检查AI Key是否已配置
    ai_key = settings.get("ai_api_key", "")
    settings["ai_key_configured"] = "true" if ai_key and len(ai_key) > 10 else "false"
    return {"settings": settings}


@app.put("/api/settings")
async def update_settings(req: SettingsUpdate):
    updates = {}
    for k, v in req.model_dump().items():
        if k == "ai_api_key" and v:
            set_setting("ai_api_key", str(v))
            updates["ai_key_configured"] = "true"
            continue
        if v is not None and v != "":
            set_setting(k, str(v))
            updates[k] = str(v)
    await broadcast_ws({"type": "settings_updated", "updates": updates})
    return {"status": "ok", "updated": updates}


class AITestRequest(BaseModel):
    ai_api_key: Optional[str] = None
    ai_base_url: Optional[str] = None
    ai_model: Optional[str] = None
    ai_is_full_url: Optional[str] = None


@app.post("/api/settings/test-ai")
def test_ai_settings(req: AITestRequest):
    api_key = req.ai_api_key
    base_url = req.ai_base_url
    model = req.ai_model
    is_full_url = req.ai_is_full_url

    if not api_key:
        api_key = get_setting("ai_api_key", "")
    if not base_url:
        base_url = get_setting("ai_base_url", "https://api.deepseek.com")
    if not model:
        model = get_setting("ai_model", "deepseek-chat")
    if is_full_url is None:
        is_full_url = get_setting("ai_is_full_url", "false")

    if not api_key:
        return {"status": "error", "message": "API Key 不能为空"}

    # 处理 base_url：
    # 如果用户开启了"完整 URL 模式"，填入的是如 https://api.xxx.com/v1/chat/completions，
    # 由于 ChatOpenAI 会在发起请求时自动拼接 /chat/completions，因此传给 ChatOpenAI 的 base_url 需裁掉末尾 /chat/completions 以精确还原用户的完整请求地址。
    if base_url:
        base_url = base_url.strip().rstrip("/")
        if is_full_url == "true" or is_full_url is True:
            if base_url.endswith("/chat/completions"):
                base_url = base_url[:-len("/chat/completions")].rstrip("/")
        else:
            if base_url.endswith("/chat/completions"):
                base_url = base_url[:-len("/chat/completions")].rstrip("/")

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage
        
        llm = ChatOpenAI(
            model=model,
            openai_api_key=api_key,
            openai_api_base=base_url,
            temperature=0.3,
            max_retries=1,
            timeout=15,
        )
        resp = llm.invoke([HumanMessage(content="Hello! Please reply with 'ok'.")])
        return {"status": "ok", "message": f"连接成功！AI 回复: {resp.content}"}
    except Exception as e:
        return {"status": "error", "message": f"测试失败: {str(e)}"}


# ══════════════════════════════════════
#  定时调度器(API 委托 backend.scheduler)
# ══════════════════════════════════════


@app.get("/api/scheduler")
def get_scheduler_config():
    if scheduler is None:
        raise HTTPException(status_code=503, detail="调度器未初始化")
    return {"config": scheduler.get_config()}


@app.put("/api/scheduler")
async def update_scheduler_config(req: dict):
    if scheduler is None:
        raise HTTPException(status_code=503, detail="调度器未初始化")
    config = await scheduler.update_config(req)
    return {"status": "ok", "config": config}


@app.get("/api/scheduler/status")
def get_scheduler_status():
    if scheduler is None:
        raise HTTPException(status_code=503, detail="调度器未初始化")
    return scheduler.get_status()


# ══════════════════════════════════════
#  WebSocket
# ══════════════════════════════════════


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    try:
        await websocket.send_json(
            {
                "type": "connected",
                "status": {
                    "browser_running": automation is not None,
                    "monitor_running": monitor_task is not None and not monitor_task.done(),
                    "monitor_paused": monitor_paused,
                },
            }
        )
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in ws_clients:
            ws_clients.remove(websocket)


# ══════════════════════════════════════
#  后台监控循环
# ══════════════════════════════════════


async def chat_monitor_loop():
    """后台轮询聊天消息 + 自动回复。带 session 心跳保活。"""
    global automation
    await asyncio.sleep(3)  # 启动后简短等待

    if automation:
        log.info("[监控] 后台监控任务已启动")
        await _run_pw(automation.keep_alive)

    # 验证 AI 回复系统
    try:
        sys.path.insert(0, str(project_root / "interview"))
        from llm_client import _load_ai_config

        cfg = _load_ai_config()
        if cfg["api_key"] and len(cfg["api_key"]) > 10:
            log.info(f"[监控] AI API 已配置（{cfg['model']}），自动回复就绪")
        else:
            log.warning("[监控] AI API Key 未配置，请在前端设置页配置")
    except Exception as e:
        log.warning(f"[监控] AI 回复系统加载失败: {e}")

    # 首次立即跑一轮监控，不等延迟（暂停时不执行）
    if automation and not monitor_paused:
        log.info("[监控] 执行首次会话扫描...")
        try:
            result = await automation.run_chat_monitor_cycle()
            if result.get("new_messages", 0) > 0:
                await broadcast_ws({"type": "new_messages", "summary": result})
            if result.get("replies_sent", 0) > 0:
                await broadcast_ws({"type": "auto_reply_sent", "summary": result})
            if result.get("new_conversations"):
                await broadcast_ws({"type": "new_messages"})
        except Exception as e:
            log.error(f"[监控] 首次扫描异常: {e}", exc_info=True)

    _heartbeat_count = 0
    _heartbeat_misses = 0
    while True:
        try:
            min_delay = int(get_setting("min_reply_delay_sec", "15"))
            max_delay = int(get_setting("max_reply_delay_sec", "20"))
            delay = random.randint(min(min_delay, max_delay), max(min_delay, max_delay) + 5)
            await asyncio.sleep(delay)

            if monitor_paused:
                continue

            if not automation:
                continue

            # 每轮轻量检查登录态（不导航，不触发BOSS反爬）
            _heartbeat_count += 1
            alive = await _run_pw(automation.heartbeat)
            if not alive:
                await asyncio.sleep(5)
                alive = await _run_pw(automation.heartbeat)

            if not alive:
                _heartbeat_misses += 1
            else:
                _heartbeat_misses = 0

            if _heartbeat_misses >= 2:
                await broadcast_ws(
                    {
                        "type": "session_expired",
                        "message": "BOSS直聘登录已过期，请点击设置Tab的「重新扫码登录」",
                    }
                )
                break

            # 每轮都轻量保活，避免 BOSS session 超时
            if _heartbeat_count >= 1:
                await _run_pw(automation.keep_alive)

            if get_setting("auto_reply_enabled", "true") != "true":
                continue

            result = await automation.run_chat_monitor_cycle()

            if result.get("new_messages", 0) > 0:
                await broadcast_ws(
                    {
                        "type": "new_messages",
                        "summary": result,
                    }
                )
            if result.get("replies_sent", 0) > 0:
                await broadcast_ws(
                    {
                        "type": "auto_reply_sent",
                        "summary": result,
                    }
                )
            if result.get("new_conversations"):
                await broadcast_ws({"type": "new_messages"})
            if result.get("wechat_exchanged"):
                await broadcast_ws({"type": "wechat_exchanged"})

            safety_ok = await _run_pw(automation.check_page_safety)
            if not safety_ok:
                await broadcast_ws(
                    {
                        "type": "safety_warning",
                        "message": "检测到页面异常(验证码/登录失效/账号限制)，已暂停自动操作。请手动检查浏览器。",
                    }
                )
                break

        except asyncio.CancelledError:
            break
        except Exception as e:
            await broadcast_ws(
                {
                    "type": "error",
                    "message": f"监控循环异常: {e}",
                }
            )
            await asyncio.sleep(60)


# ══════════════════════════════════════
#  MCP Server (Streamable HTTP)
# ══════════════════════════════════════

try:
    from backend.mcp_server import mcp as mcp_server
    app.mount("/mcp", mcp_server.streamable_http_app())
    log.info("[OK] MCP Server mounted at /mcp")
except ImportError:
    log.info("[SKIP] mcp not installed. Install with: pip install mcp")
except Exception as e:
    log.warning(f"[WARN] MCP Server mount failed: {e}")


# ══════════════════════════════════════
#  启动
# ══════════════════════════════════════


def main():
    import os
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--auto-start", action="store_true", help="启动时自动打开浏览器")
    parser.add_argument("--user-data-dir", type=str, default=None, help="自定义数据与配置文件存储目录")
    args = parser.parse_args()

    if args.user_data_dir:
        os.environ["BOSS_DATA_DIR"] = args.user_data_dir
        log.info(f"使用数据路径: {args.user_data_dir}")

    if args.auto_start:
        global automation, monitor_task
        try:

            def _do_start():
                a = BossAutomation(headless=False)
                a.start()
                return a

            automation = _playwright_executor.submit(_do_start).result()
            log.info("[OK] 浏览器已启动")
        except Exception as e:
            log.warning(f"自动启动失败: {e}")

    log.info(f"BOSS直聘自动化控制台: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
