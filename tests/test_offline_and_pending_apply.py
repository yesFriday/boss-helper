"""
测试已下架岗位自动识别、防重复投递机制与严格仅投递待投递 (pending) 岗位规范。

运行命令:
    .venv\\Scripts\\python.exe -m pytest tests/test_offline_and_pending_apply.py -v
"""

import os
import sys
import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def isolated_test_db():
    """每个测试使用 E:\\ 盘临时目录下的独立 SQLite 数据库，确保与真实生产库完全隔离"""
    test_id = uuid.uuid4().hex[:8]
    test_dir = project_root / "build_temp" / f"test_data_{test_id}"
    test_dir.mkdir(parents=True, exist_ok=True)
    os.environ["BOSS_DATA_DIR"] = str(test_dir)

    # 重新初始化 DB
    import backend.state as state
    state.DB_PATH = test_dir / "boss_state.db"
    if hasattr(state._local, "conn") and state._local.conn is not None:
        try:
            state._local.conn.close()
        except Exception:
            pass
        state._local.conn = None

    state.init_db()

    yield test_dir

    # 清理数据库连接与临时目录
    if hasattr(state._local, "conn") and state._local.conn is not None:
        try:
            state._local.conn.close()
        except Exception:
            pass
        state._local.conn = None

    try:
        shutil.rmtree(test_dir, ignore_errors=True)
    except Exception:
        pass


def make_fake_applier():
    """构造轻量 Mock 的 BossApplier 实例，避免启动真实浏览器"""
    from backend.boss_applier import BossApplier

    applier = BossApplier.__new__(BossApplier)
    applier.page = MagicMock()
    applier.check_page_safety = MagicMock(return_value=True)
    applier._safe_click = MagicMock()
    applier.send_message = MagicMock(return_value=True)
    return applier


# ══════════════════════════════════════════════════════════════
#  1. 下架识别与标记测试
# ══════════════════════════════════════════════════════════════

def test_apply_marks_offline_when_closed_keyword_present():
    """详情页检测到职位已关闭/下线关键词时，应自动标记为 offline 并阻止投递"""
    from backend.state import add_application, get_application_by_url

    url = "https://www.zhipin.com/job_detail/test_offline_keyword.html"
    add_application({"title": "Python开发", "company": "测试科技", "url": url})

    applier = make_fake_applier()
    # 模拟页面命中了“职位已关闭”关键词
    applier._has_text = MagicMock(side_effect=lambda *texts: any("关闭" in t or "停止" in t for t in texts))

    with patch("backend.boss_applier.pause"):
        res = applier.apply_to_job(url)

    assert res["success"] is False
    assert res["status"] == "offline"
    assert res["is_offline"] is True
    assert "下架" in res["message"] or "关闭" in res["message"]

    # 验证 SQLite 数据库状态确实被更新为 offline
    saved = get_application_by_url(url)
    assert saved is not None
    assert saved["status"] == "offline"


def test_apply_marks_offline_when_apply_button_missing():
    """详情页无下架文案，但未找到立即沟通按钮时，应自动标记为 offline"""
    from backend.state import add_application, get_application_by_url

    url = "https://www.zhipin.com/job_detail/test_no_apply_button.html"
    add_application({"title": "后端架构师", "company": "测试科技", "url": url})

    applier = make_fake_applier()
    # 页面没有下架文案，也没有“已沟通”
    applier._has_text = MagicMock(return_value=False)
    # 模拟找不到投递按钮
    applier._find_element = MagicMock(return_value=None)
    loc_mock = MagicMock()
    loc_mock.is_visible.return_value = False
    applier.page.locator = MagicMock(return_value=MagicMock(first=loc_mock))
    applier.page.evaluate = MagicMock(return_value={})

    with patch("backend.boss_applier.pause"):
        res = applier.apply_to_job(url)

    assert res["success"] is False
    assert res["status"] == "offline"
    assert res["is_offline"] is True
    assert "未找到投递按钮" in res["message"]

    # 验证 SQLite 数据库状态确实被更新为 offline
    saved = get_application_by_url(url)
    assert saved is not None
    assert saved["status"] == "offline"


# ══════════════════════════════════════════════════════════════
#  2. 防重复投递测试 (Fast Exit Check)
# ══════════════════════════════════════════════════════════════

def test_apply_skips_already_offline_job_without_page_load():
    """已在库中标记为 offline 的岗位，再次投递时必须秒级跳过，禁止调用 page.goto"""
    from backend.state import add_application, update_application_status

    url = "https://www.zhipin.com/job_detail/test_fast_exit.html"
    app_id = add_application({"title": "测试岗位", "company": "某公司", "url": url})
    update_application_status(app_id, "offline")

    applier = make_fake_applier()

    res = applier.apply_to_job(url)

    # 校验结果
    assert res["success"] is False
    assert res["status"] == "offline"
    assert res["is_offline"] is True
    # 关键点：page.goto 绝对不能被调用，避免浪费页面加载
    applier.page.goto.assert_not_called()


# ══════════════════════════════════════════════════════════════
#  3. 严格仅投递「待投递 (pending)」岗位测试
# ══════════════════════════════════════════════════════════════

def test_apply_rejects_non_pending_jobs():
    """非 pending 状态的岗位（如 skipped, failed）在投递时必须被拒绝并跳过"""
    from backend.state import add_application, update_application_status

    # 1. 测试已跳过状态
    url_skipped = "https://www.zhipin.com/job_detail/test_skipped.html"
    app_id1 = add_application({"title": "已跳过岗位", "company": "某公司", "url": url_skipped})
    update_application_status(app_id1, "skipped")

    applier = make_fake_applier()
    res1 = applier.apply_to_job(url_skipped)
    assert res1["success"] is False
    assert "非待投递状态" in res1["message"]
    applier.page.goto.assert_not_called()

    # 2. 测试已失败状态
    url_failed = "https://www.zhipin.com/job_detail/test_failed.html"
    app_id2 = add_application({"title": "失败岗位", "company": "某公司", "url": url_failed})
    update_application_status(app_id2, "failed")

    res2 = applier.apply_to_job(url_failed)
    assert res2["success"] is False
    assert "非待投递状态" in res2["message"]
    applier.page.goto.assert_not_called()


def test_apply_batch_skips_offline_and_non_pending():
    """批量投递列表中包含 offline、applied、skipped 和 pending 时，只有 pending 会真正执行投递"""
    from backend.state import add_application, update_application_status

    url_offline = "https://www.zhipin.com/job_detail/batch_offline.html"
    id1 = add_application({"title": "下架岗", "company": "A", "url": url_offline})
    update_application_status(id1, "offline")

    url_skipped = "https://www.zhipin.com/job_detail/batch_skipped.html"
    id2 = add_application({"title": "跳过岗", "company": "B", "url": url_skipped})
    update_application_status(id2, "skipped")

    url_applied = "https://www.zhipin.com/job_detail/batch_applied.html"
    id3 = add_application({"title": "已投岗", "company": "C", "url": url_applied})
    update_application_status(id3, "applied")

    url_pending = "https://www.zhipin.com/job_detail/batch_pending.html"
    add_application({"title": "待投岗", "company": "D", "url": url_pending})

    applier = make_fake_applier()
    applier._has_text = MagicMock(return_value=False)
    applier._find_element = MagicMock(return_value=MagicMock())
    applier.page.evaluate = MagicMock(return_value={"hrName": "王经理", "title": "待投岗", "company": "D"})

    with patch("backend.boss_applier.pause"), patch("time.sleep"):
        results = applier.apply_batch([url_offline, url_skipped, url_applied, url_pending])

    assert len(results) == 4
    # offline 立即拦截
    assert results[0]["status"] == "offline"
    # skipped 立即拦截
    assert "非待投递状态" in results[1]["message"]
    # applied 返回已投递过
    assert results[2]["already_applied"] is True
    # pending 正常成功投递
    assert results[3]["success"] is True

    # 检查 page.goto 只对 pending 岗位调用了 1 次
    assert applier.page.goto.call_count == 1
    assert applier.page.goto.call_args[0][0] == url_pending


# ══════════════════════════════════════════════════════════════
#  4. 数据库查询与分类过滤测试
# ══════════════════════════════════════════════════════════════

def test_db_filtering_offline_and_pending_applications():
    """验证 list_applications 和 get_pending_applications_by_activity 的分类隔离"""
    from backend.state import (
        add_application,
        update_application_status,
        list_applications,
        get_pending_applications_by_activity,
    )

    # 创建 1 条 pending, 1 条 offline, 1 条 applied
    id_p = add_application({"title": "待投岗位", "company": "P公司", "url": "https://zhipin.com/p"})
    id_o = add_application({"title": "下架岗位", "company": "O公司", "url": "https://zhipin.com/o"})
    update_application_status(id_o, "offline")
    id_a = add_application({"title": "已投岗位", "company": "A公司", "url": "https://zhipin.com/a"})
    update_application_status(id_a, "applied")

    # 1. 过滤 offline 分类
    offline_list = list_applications(status="offline")
    assert len(offline_list) == 1
    assert offline_list[0]["id"] == id_o
    assert offline_list[0]["status"] == "offline"

    # 2. 过滤 pending 分类
    pending_list = list_applications(status="pending")
    assert len(pending_list) == 1
    assert pending_list[0]["id"] == id_p

    # 3. 调度器/批量投递的待投岗位获取函数，严格杜绝 offline 和 applied
    auto_pending = get_pending_applications_by_activity(limit=10)
    assert len(auto_pending) == 1
    assert auto_pending[0]["id"] == id_p
    assert all(item["status"] == "pending" for item in auto_pending)


# ══════════════════════════════════════════════════════════════
#  5. FastAPI 接口层拦截守卫测试
# ══════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_api_apply_precheck_offline_and_non_pending():
    """FastAPI 接口层对 offline 与 non-pending 的前置校验拦截"""
    from backend.state import add_application, update_application_status
    import backend.app as app_module
    from backend.app import ApplyRequest, apply_to_job

    url_off = "https://zhipin.com/api_offline"
    app_id = add_application({"title": "接口测试下架", "company": "X", "url": url_off})
    update_application_status(app_id, "offline")

    # 模拟 automation 存在
    app_module.automation = MagicMock()

    # 投递 offline 岗位，接口层应在调用自动化前就返回 offline 响应
    res = await apply_to_job(ApplyRequest(job_url=url_off))
    assert res["success"] is False
    assert res["status"] == "offline"
    assert res["is_offline"] is True

    # 投递 skipped 岗位
    url_skip = "https://zhipin.com/api_skip"
    app_id2 = add_application({"title": "接口测试跳过", "company": "Y", "url": url_skip})
    update_application_status(app_id2, "skipped")

    res2 = await apply_to_job(ApplyRequest(job_url=url_skip))
    assert res2["success"] is False
    assert "非待投递状态" in res2["message"]


# ══════════════════════════════════════════════════════════════
#  6. 消息监控防误判与自愈拉起测试
# ══════════════════════════════════════════════════════════════

def test_check_page_safety_no_false_positive_on_normal_texts():
    """页面包含实名验证、学历验证等正常词汇时，不应误判为验证码"""
    from backend.automation_base import AutomationBase

    auto = AutomationBase.__new__(AutomationBase)
    auto._login_prompt_visible = MagicMock(return_value=False)
    auto.page = MagicMock()
    # 模拟普通页面文字包含“实名验证通过”、“微信号验证”
    auto.page.inner_text.return_value = "欢迎使用BOSS直聘，实名验证已通过，微信号已验证完毕。企业信用等级A。"
    # 弹窗不存在
    loc_mock = MagicMock()
    loc_mock.is_visible.return_value = False
    auto.page.locator.return_value = MagicMock(first=loc_mock)

    assert auto.check_page_safety() is True

    # 当真正出现滑块/安全验证文案时，精准拦截
    auto.page.inner_text.return_value = "安全检查：请拖动滑块完成拼图"
    assert auto.check_page_safety() is False


@pytest.mark.anyio
async def test_resume_monitor_resurrects_dead_task():
    """当后台监控 task 挂掉时，调用 resume_monitor 会自愈重新创建协程任务"""
    import backend.app as app_module
    from backend.app import resume_monitor

    app_module.automation = MagicMock()
    app_module.automation.page = MagicMock()
    app_module.monitor_task = None

    with patch("backend.app.chat_monitor_loop") as mock_loop:
        # mock chat_monitor_loop 为一个可 await 的协程
        async def fake_loop():
            pass
        mock_loop.side_effect = fake_loop

        res = await resume_monitor()
        assert res["status"] == "resumed"
        assert app_module.monitor_paused is False
        assert app_module.monitor_task is not None

