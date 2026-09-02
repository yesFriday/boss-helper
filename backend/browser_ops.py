"""浏览器占用挡板:前端操作(搜索/投递/手动发消息/同步)与聊天监控的互斥。

问题:
- monitor_paused 只在监控周期"之间"检查,拦不住进行中的周期;
- 搜索/投递等操作与进行中的周期共用同一个 page,互相抢导航,
  造成标签页来回切换,手动消息甚至可能发进错误会话。

方案:
- browser_busy_lock:所有独占浏览器的操作必须持有,彼此串行;
- 拿锁后置 busy_flag,监控循环见到即让路(不再发起周期,keep_alive 不抢导航);
- 进入临界区前先等正在进行的监控周期结束(复用 monitor._cycle_lock),
  不把进行中的周期拦腰截断;周期拿到锁后若发现 busy_flag 也会主动跳过。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from backend.logger import get_logger

log = get_logger("browser_ops")

# 事件循环内使用的互斥锁;Python 3.10+ 创建时不绑定事件循环,可惰性初始化
browser_busy_lock: Optional[asyncio.Lock] = None
busy_flag: bool = False


def _get_lock() -> asyncio.Lock:
    global browser_busy_lock
    if browser_busy_lock is None:
        browser_busy_lock = asyncio.Lock()
    return browser_busy_lock


def is_busy() -> bool:
    """浏览器是否被前端独占操作占用(监控循环/keep_alive 据此让路)。"""
    return busy_flag


async def wait_cycle_done(monitor) -> None:
    """等待进行中的监控周期结束(只等待,不置 busy,不阻止后续周期)。"""
    if monitor is None:
        return
    cycle_lock = getattr(monitor, "_cycle_lock", None)
    if cycle_lock is not None and cycle_lock.locked():
        async with cycle_lock:
            pass


class browser_op:
    """浏览器独占操作上下文。

    用法:
        async with browser_op(automation, reason="搜索岗位"):
            jobs = await _run_pw(automation.search, keyword, city)

    进入: 拿互斥锁 → 置 busy(监控让路) → 等进行中的监控周期结束
    退出: 清 busy → 释放周期锁 → 释放互斥锁
    """

    def __init__(self, monitor=None, *, reason: str = "browser_op"):
        self._monitor = monitor
        self._reason = reason
        self._hold_cycle_lock = False

    async def __aenter__(self) -> "browser_op":
        global busy_flag
        lock = _get_lock()
        if lock.locked():
            log.info(f"[挡板] {self._reason}: 等待其它浏览器操作完成")
        await lock.acquire()
        try:
            busy_flag = True
            # 复用监控实例的周期锁:等当前周期跑完,并让新周期排队在本操作之后
            cycle_lock = getattr(self._monitor, "_cycle_lock", None)
            if cycle_lock is None and self._monitor is not None:
                cycle_lock = asyncio.Lock()
                self._monitor._cycle_lock = cycle_lock
            if cycle_lock is not None:
                if cycle_lock.locked():
                    log.info(f"[挡板] {self._reason}: 等待进行中的监控周期结束")
                await cycle_lock.acquire()
                self._hold_cycle_lock = True
        except BaseException:
            busy_flag = False
            lock.release()
            raise
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        global busy_flag
        busy_flag = False
        if self._hold_cycle_lock:
            self._monitor._cycle_lock.release()
            self._hold_cycle_lock = False
        _get_lock().release()
        return False
