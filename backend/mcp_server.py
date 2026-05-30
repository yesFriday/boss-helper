"""MCP Streamable HTTP Server for bosshelper.

将 CLI 命令封装为 MCP Tools，供 AI Agent 通过标准 MCP 协议调用。
"""

import json
import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("BOSSHELPER_API", "http://127.0.0.1:8010")

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("bosshelper")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(path: str, timeout: int = 30) -> dict:
    try:
        resp = httpx.get(f"{BASE_URL}{path}", timeout=timeout)
        if resp.is_error:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        return {"ok": True, "data": resp.json()}
    except httpx.ConnectError:
        return {"ok": False, "error": "无法连接后端服务，请先运行 `bosshelper server --start`"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _post(path: str, json_body: dict = None, timeout: int = 120) -> dict:
    try:
        resp = httpx.post(f"{BASE_URL}{path}", json=json_body, timeout=timeout)
        if resp.is_error:
            detail = ""
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                pass
            return {"ok": False, "error": detail or f"HTTP {resp.status_code}: {resp.text[:200]}"}
        return {"ok": True, "data": resp.json()}
    except httpx.ConnectError:
        return {"ok": False, "error": "无法连接后端服务，请先运行 `bosshelper server --start`"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _delete(path: str, timeout: int = 30) -> dict:
    try:
        resp = httpx.delete(f"{BASE_URL}{path}", timeout=timeout)
        if resp.is_error:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        return {"ok": True, "data": resp.json()}
    except httpx.ConnectError:
        return {"ok": False, "error": "无法连接后端服务，请先运行 `bosshelper server --start`"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def search_jobs(keyword: str, city: str = "全国", welfare: str = "", limit: int = 60) -> str:
    """搜索BOSS直聘岗位。

    Args:
        keyword: 搜索关键词，如 "Python开发"、"AI Agent"
        city: 城市名，如 "北京"、"广州"、"全国"
        welfare: 福利筛选，逗号分隔，如 "双休,五险一金"
        limit: 返回数量上限，默认60

    Returns:
        岗位列表JSON，包含薪资、公司、城市、经验要求等
    """
    body = {"keyword": keyword, "city": city, "limit": limit}
    if welfare:
        body["welfare"] = welfare
    result = _post("/api/jobs/search", body)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_status() -> str:
    """查看系统运行状态，包括浏览器状态、今日投递数、AI配置等。"""
    result = _get("/api/status")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_stats() -> str:
    """查看投递转化漏斗统计：搜索→待投递→已投递→HR回复→面试。"""
    result = _get("/api/stats")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_jobs(status: str = "", limit: int = 50) -> str:
    """列出本地数据库中的岗位。

    Args:
        status: 岗位状态筛选，可选值: pending(待投递)、applied(已投递)、replied(已回复)
        limit: 返回数量上限，默认50

    Returns:
        岗位列表
    """
    path = f"/api/jobs?limit={limit}"
    if status:
        path += f"&status={status}"
    result = _get(path)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def apply_job(job_url: str) -> str:
    """投递单个岗位。

    Args:
        job_url: 岗位URL，如 https://www.zhipin.com/job_detail/xxx.html

    Returns:
        投递结果
    """
    result = _post("/api/jobs/apply", {"job_url": job_url})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def apply_batch(status: str = "pending") -> str:
    """批量投递待投递岗位。

    Args:
        status: 筛选状态，默认 pending(待投递)

    Returns:
        批量投递结果
    """
    # 先获取岗位列表
    jobs_result = _get(f"/api/jobs?status={status}&limit=100")
    if not jobs_result.get("ok"):
        return json.dumps(jobs_result, ensure_ascii=False, indent=2)

    jobs = jobs_result.get("data", [])
    if not jobs:
        return json.dumps({"ok": True, "data": {"message": "没有待投递的岗位"}}, ensure_ascii=False, indent=2)

    job_urls = [j.get("job_url") for j in jobs if j.get("job_url")]
    result = _post("/api/jobs/apply-batch", {"job_urls": job_urls})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_conversations() -> str:
    """列出所有HR会话，包括会话ID、HR姓名、公司、最后消息等。"""
    result = _get("/api/conversations")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_chat(conv_id: int) -> str:
    """查看与某HR的聊天记录。

    Args:
        conv_id: 会话ID，可通过 list_conversations 获取

    Returns:
        聊天消息列表
    """
    result = _get(f"/api/conversations/{conv_id}/messages")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def send_message(conv_id: int, content: str) -> str:
    """向HR手动发送消息。

    Args:
        conv_id: 会话ID
        content: 消息内容

    Returns:
        发送结果
    """
    result = _post(f"/api/conversations/{conv_id}/send", {"content": content})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def analyze_job(job_url: str, title: str = "", company: str = "", description: str = "") -> str:
    """AI分析岗位JD，评估匹配度。

    Args:
        job_url: 岗位URL
        title: 岗位名称（可选）
        company: 公司名（可选）
        description: JD描述（可选）

    Returns:
        AI分析结果，包含匹配度评分和建议
    """
    body = {"job_url": job_url, "job_title": title, "company": company, "description": description}
    result = _post("/api/jobs/analyze", body)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def manage_shortlist(action: str, job_url: str = "", title: str = "", company: str = "", shortlist_id: int = 0) -> str:
    """候选池管理。

    Args:
        action: 操作类型，可选值: list(列出)、add(添加)、remove(删除)
        job_url: 岗位URL（add时必填）
        title: 岗位名称（add时可选）
        company: 公司名（add时可选）
        shortlist_id: 候选池记录ID（remove时必填）

    Returns:
        操作结果
    """
    if action == "list":
        result = _get("/api/shortlists")
    elif action == "add":
        if not job_url:
            return json.dumps({"ok": False, "error": "添加候选池需要提供 job_url"}, ensure_ascii=False, indent=2)
        body = {"job_url": job_url, "title": title, "company": company}
        result = _post("/api/shortlists", body)
    elif action == "remove":
        if not shortlist_id:
            return json.dumps({"ok": False, "error": "删除候选池需要提供 shortlist_id"}, ensure_ascii=False, indent=2)
        result = _delete(f"/api/shortlists/{shortlist_id}")
    else:
        return json.dumps({"ok": False, "error": f"未知操作: {action}，可选: list/add/remove"}, ensure_ascii=False, indent=2)

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def run_doctor() -> str:
    """环境诊断：检查Python版本、浏览器状态、登录态、AI配置等。"""
    result = _get("/api/doctor")
    return json.dumps(result, ensure_ascii=False, indent=2)
