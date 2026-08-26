"""运行时执行器:Playwright 专属线程 + LLM 专属线程。

背景(设计缺陷 D3 修复):
原来 `run_chat_monitor_cycle` 整体提交到单线程 Playwright 执行器,内嵌 LLM 调用
(每会话 5-30 秒)与随机 sleep,导致执行器大半时间被监控占用,前端手动操作全部排队。

拆分后:
- pw_executor(1 线程): 所有 Playwright page 操作必须在此线程(sync API 线程绑定)
- llm_executor(2 线程): LLM 生成阶段,期间 pw 线程空闲,前端操作可插队;
  Agent 工具需要浏览器时经 run_in_pw() 同步 hop 回 pw 线程
- 死锁分析: llm 线程可能阻塞等 pw 线程(工具 hop);pw 线程不依赖 llm 线程
  (apply_batch 等无 LLM 调用) → 无循环等待
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

pw_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pw")
llm_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="llm")


def _strip_asyncio():
    # Python 3.14 + uvicorn 可能继承事件循环策略,清掉避免线程内事件循环误用
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    asyncio.set_event_loop(None)


async def aio_run_pw(fn: Callable, *args) -> Any:
    """异步执行:在 Playwright 线程中跑同步函数。"""
    loop = asyncio.get_running_loop()

    def _wrapper():
        _strip_asyncio()
        return fn(*args)

    return await loop.run_in_executor(pw_executor, _wrapper)


async def aio_run_llm(fn: Callable, *args) -> Any:
    """异步执行:在 LLM 线程中跑同步函数。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(llm_executor, lambda: fn(*args))


def run_in_pw(fn: Callable, *args) -> Any:
    """同步 hop:从其它线程(如 llm 线程)把浏览器操作转回 Playwright 线程执行。"""
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # 不在事件循环线程 → 可安全阻塞
    else:
        # 在事件循环线程内同步等待 pw 线程会死锁(pw 可能正被本协程排队占用)
        raise RuntimeError("run_in_pw 不能在事件循环线程内同步调用")

    fut = pw_executor.submit(fn, *args)
    try:
        return fut.result(timeout=120)
    except concurrent.futures.TimeoutError:
        fut.cancel()
        raise TimeoutError("run_in_pw 等待 Playwright 线程超时(120s)")
