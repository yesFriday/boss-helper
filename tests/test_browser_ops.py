"""browser_ops 并发挡板单元测试:全部 mock,不依赖 FastAPI / Playwright / SQLite。

运行: pytest tests/test_browser_ops.py -v
"""

import asyncio
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend import browser_ops


@pytest.fixture(autouse=True)
def _clean_state():
    browser_ops.busy_flag = False
    browser_ops.browser_busy_lock = None
    yield
    browser_ops.busy_flag = False
    browser_ops.browser_busy_lock = None


def test_browser_op_sets_busy_and_releases():
    """进入时置 busy,退出后清零并释放锁。"""
    seen = []

    class FakeMonitor:
        pass

    async def main():
        async with browser_ops.browser_op(FakeMonitor(), reason="测试"):
            seen.append(browser_ops.is_busy())
            assert browser_ops._get_lock().locked()

    asyncio.run(main())
    seen.append(browser_ops.is_busy())
    assert seen == [True, False]
    assert not browser_ops._get_lock().locked()


def test_browser_op_waits_running_cycle():
    """进入时若监控周期进行中,应等周期结束才继续;退出后周期锁归还。"""

    class FakeMonitor:
        def __init__(self):
            self._cycle_lock = asyncio.Lock()

    monitor = FakeMonitor()

    async def main():
        cycle_in_cycle_lock = asyncio.Event()
        cycle_done = asyncio.Event()

        async def fake_cycle():
            async with monitor._cycle_lock:
                cycle_in_cycle_lock.set()
                await asyncio.sleep(0.05)
            cycle_done.set()

        cycle_task = asyncio.create_task(fake_cycle())
        await asyncio.wait_for(cycle_in_cycle_lock.wait(), timeout=2)

        op_entered = asyncio.Event()

        async def op():
            async with browser_ops.browser_op(monitor, reason="测试"):
                op_entered.set()
                # 进入临界区时进行中的周期必须已经跑完
                assert cycle_done.is_set()

        op_task = asyncio.create_task(op())
        # 周期(0.05s)没结束时操作不得进入
        await asyncio.sleep(0.02)
        assert not op_entered.is_set()
        await asyncio.wait_for(op_entered.wait(), timeout=2)
        await asyncio.wait_for(op_task, timeout=2)
        await asyncio.wait_for(cycle_task, timeout=2)

    asyncio.run(main())
    assert browser_ops.is_busy() is False


def test_browser_op_serializes_concurrent_ops():
    """两个并发 browser_op 串行执行,不重叠。"""
    events = []

    async def main():
        async def op(name):
            async with browser_ops.browser_op(None, reason=name):
                events.append(("enter", name))
                await asyncio.sleep(0.01)
                events.append(("exit", name))

        await asyncio.gather(op("A"), op("B"))

    asyncio.run(main())

    # 第一个必须完全退出后第二个才能进入
    assert events[0][0] == "enter" and events[1][0] == "exit"
    assert events[2][0] == "enter" and events[3][0] == "exit"
    assert events[0][1] == events[1][1]


def test_browser_op_releases_on_exception():
    """临界区内抛异常:busy 清零、锁释放、异常正常向上传播。"""

    class FakeMonitor:
        def __init__(self):
            self._cycle_lock = asyncio.Lock()

    monitor = FakeMonitor()

    async def main():
        with pytest.raises(RuntimeError):
            async with browser_ops.browser_op(monitor, reason="测试"):
                raise RuntimeError("boom")

    asyncio.run(main())
    assert browser_ops.is_busy() is False
    assert not browser_ops._get_lock().locked()
    assert not monitor._cycle_lock.locked()


def test_wait_cycle_done_returns_when_idle():
    """无周期进行中时立即返回。"""
    assert asyncio.run(browser_ops.wait_cycle_done(None)) is None
    assert asyncio.run(browser_ops.wait_cycle_done(object())) is None
