"""bosshelper CLI — BOSS直聘岗位雷达命令行工具."""

import json
import sys
import click

from . import client, output


@click.group()
def main():
    """bosshelper — BOSS直聘岗位雷达 v0.1.0

    命令返回结构化 JSON 到 stdout，Agent 友好。
    """


# ── 版本 ──
@main.command("version")
def version_cmd():
    output.emit(output.ok("version", data={"version": "0.1.0"}))


# ── Schema：AI Agent 工具描述 ──
@main.command("schema")
def schema_cmd():
    path = __file__.replace("cli.py", "schema.json")
    with open(path, encoding="utf-8") as f:
        schema = json.load(f)
    output.emit(output.ok("schema", data=schema))


# ── 搜索 ──
@main.command("search")
@click.argument("keyword")
@click.option("--city", default="全国", help="城市名")
@click.option("--welfare", default=None, help="福利筛选 如 双休,五险一金")
@click.option("--count", type=int, default=60, help="返回条数上限")
def search_cmd(keyword, city, welfare, count):
    """搜索BOSS直聘岗位。"""
    payload = {"keyword": keyword, "city": city, "limit": count}
    if welfare:
        payload["welfare"] = welfare
    resp = client.search(keyword, city, count)
    result = output.ok_or_fail(resp, "search")
    output.emit(result)


# ── 状态 ──
@main.command("status")
def status_cmd():
    resp = client.status()
    result = output.ok_or_fail(resp, "status")
    output.emit(result)


# ── 投递漏斗 ──
@main.command("stats")
def stats_cmd():
    resp = client.stats()
    result = output.ok_or_fail(resp, "stats")
    output.emit(result)


# ── 岗位列表 ──
@main.command("jobs")
@click.option("--status", "filter_status", default=None, help="pending / applied / replied")
@click.option("--limit", type=int, default=50)
def jobs_cmd(filter_status, limit):
    resp = client.jobs(filter_status, limit)
    result = output.ok_or_fail(resp, "jobs")
    output.emit(result)


# ── 投递单个 ──
@main.command("apply")
@click.argument("job_url")
def apply_cmd(job_url):
    resp = client.apply_one(job_url)
    result = output.ok_or_fail(resp, "apply")
    output.emit(result)


# ── 批量投递 ──
@main.command("apply-batch")
@click.option("--status", "filter_status", default="pending", help="pending 等状态")
def apply_batch_cmd(filter_status):
    r = client.jobs(filter_status, limit=200)
    if r.is_error:
        output.emit(output.fail("apply-batch", f"fetch jobs failed: {r.status_code}"))
        return
    jobs_list = r.json().get("jobs", [])
    urls = [j["job_url"] for j in jobs_list if j.get("job_url")]
    if not urls:
        output.emit(output.fail("apply-batch", "no job_urls found"))
        return
    resp = client.apply_batch(urls)
    result = output.ok_or_fail(resp, "apply-batch")
    output.emit(result)


# ── 会话列表 ──
@main.command("conversations")
def conversations_cmd():
    resp = client.conversations()
    result = output.ok_or_fail(resp, "conversations")
    output.emit(result)


# ── 聊天记录 ──
@main.command("chat")
@click.argument("conv_id", type=int)
def chat_cmd(conv_id):
    resp = client.chat_messages(conv_id)
    result = output.ok_or_fail(resp, "chat")
    output.emit(result)


# ── 手动发消息 ──
@main.command("send")
@click.argument("conv_id", type=int)
@click.option("--msg", required=True, help="消息内容")
def send_cmd(conv_id, msg):
    resp = client.send_message(conv_id, msg)
    result = output.ok_or_fail(resp, "send")
    output.emit(result)


# ── 诊断 ──
@main.command("doctor")
def doctor_cmd():
    resp = client.doctor()
    result = output.ok_or_fail(resp, "doctor")
    output.emit(result)


# ── 扫码登录 ──
@main.command("login")
def login_cmd():
    resp = client.relogin()
    result = output.ok_or_fail(resp, "login")
    output.emit(result)


# ── AI JD分析 ──
@main.command("analyze")
@click.argument("job_url")
@click.option("--title", default="", help="岗位名称")
@click.option("--company", default="", help="公司名")
@click.option("--desc", default="", help="JD描述")
def analyze_cmd(job_url, title, company, desc):
    resp = client.analyze(job_url, title, company, desc)
    output.emit(output.ok_or_fail(resp, "analyze"))


# ── 候选池 ──
@main.command("shortlist")
@click.argument("action", type=click.Choice(["list", "add", "remove"]))
@click.option("--job-url", help="岗位URL")
@click.option("--title", default="", help="岗位名称")
@click.option("--company", default="", help="公司名")
@click.option("--id", "sid", type=int, help="shortlist ID")
def shortlist_cmd(action, job_url, title, company, sid):
    if action == "list":
        resp = client.get_shortlists()
        output.emit(output.ok_or_fail(resp, "shortlist"))
    elif action == "add":
        if not job_url:
            output.emit(output.fail("shortlist", "--job-url required"))
            return
        resp = client.add_shortlist(job_url, title, company)
        output.emit(output.ok_or_fail(resp, "shortlist"))
    elif action == "remove":
        if not sid:
            output.emit(output.fail("shortlist", "--id required"))
            return
        resp = client.remove_shortlist(sid)
        output.emit(output.ok_or_fail(resp, "shortlist"))


# ── 服务管理 ──
@main.command("server")
@click.option("--start", is_flag=True, help="启动后台服务")
@click.option("--stop", is_flag=True, help="停止后台服务")
@click.option("--port", type=int, default=8010, help="服务端口")
def server_cmd(start, stop, port):
    import subprocess
    import os

    if start:
        project_dir = os.path.dirname(os.path.dirname(__file__))
        cmd = ["python", f"{project_dir}/boss_app.py", "--port", str(port)]
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0)
        output.emit(output.ok("server", data={"status": "started", "url": f"http://127.0.0.1:{port}"}))
    elif stop:
        import platform

        if platform.system() == "Windows":
            os.system(f"taskkill /F /IM python.exe 2>nul")
        else:
            os.system("pkill -f boss_app.py")
        output.emit(output.ok("server", data={"status": "stopped"}))
    else:
        resp = client.status()
        if resp.is_error:
            output.emit(output.ok("server", data={"status": "not running"}))
        else:
            output.emit(output.ok("server", data={"status": "running"}))


if __name__ == "__main__":
    main()
