# bosshelper

> AI Agent 专用的 BOSS 直聘自动化工具。CLI 提供 14 条命令，stdout JSON 信封，Agent 友好。

## Install

```bash
git clone https://github.com/yesFriday/bosshelper.git
cd bosshelper
pip install -e .
playwright install firefox
```

## First Minute

按顺序跑，不需要先读完 README：

```bash
bosshelper server --start --port 8010    # 启动后台服务
bosshelper doctor                         # 环境诊断
bosshelper schema                         # 获取工具清单
bosshelper status                         # 检查登录态
```

完成标准：
- `bosshelper doctor` 返回 `ok=true`
- `bosshelper schema` 返回 12 个可用命令
- `bosshelper status` 返回 `browser_running: true`

**如 `browser_running: false`**：提示用户在浏览器打开 `http://127.0.0.1:8010`，设置页启动浏览器并扫码登录。

---

## Core Loop（核心求职闭环）

```bash
# 1. 搜索岗位
bosshelper search "AI Agent" --city 广州 --welfare "双休,五险一金"

# 2. 查看岗位列表
bosshelper jobs --status pending --limit 20

# 3. AI 分析某个岗位匹配度
bosshelper analyze <job_url> --title "AI开发工程师"

# 4. 收藏感兴趣的岗位
bosshelper shortlist add --job-url <job_url> --title "AI开发"

# 5. 批量投递
bosshelper apply-batch

# 6. 查看投递漏斗
bosshelper stats
```

---

## Commands Reference

| 命令 | 必填参数 | 可选参数 | 说明 |
|------|---------|---------|------|
| `search` | `KEYWORD` | `--city` `--welfare` `--count` | 搜索岗位 |
| `status` | — | — | 浏览器状态 + 今日统计 |
| `stats` | — | — | 投递漏斗 |
| `jobs` | — | `--status` `--limit` | 岗位列表 |
| `apply` | `JOB_URL` | — | 投递单个 |
| `apply-batch` | — | `--status` | 批量投递 |
| `conversations` | — | — | HR 会话列表 |
| `chat` | `CONV_ID` | — | 查看聊天记录 |
| `send` | `CONV_ID` | `--msg` | 手动发消息 |
| `analyze` | `JOB_URL` | `--title` `--company` `--desc` | AI JD 分析 |
| `shortlist` | `ACTION` | `--job-url` `--title` `--id` | 候选池管理 |
| `schema` | — | — | 输出工具描述 |
| `doctor` | — | — | 环境诊断 |
| `server` | — | `--start` `--stop` `--port` | 管理后台服务 |

---

## Output Contract

所有命令 stdout 统一 JSON 信封：

```json
{
  "ok": true,
  "command": "search",
  "data": [
    {
      "title": "AI开发工程师",
      "company": "XX科技",
      "salary": "15-25K",
      "city": "广州",
      "experience": "3-5年",
      "job_url": "https://www.zhipin.com/job_detail/xxx.html",
      "status": "pending"
    }
  ],
  "pagination": { "page": 1, "has_more": true, "total": 15 },
  "error": null
}
```

**约定：**
- `stdout` → 仅 JSON 数据
- `stderr` → 日志和进度
- exit `0` → `ok=true`
- exit `1` → `ok=false`，读取 `error` 字段

---

## Error Handling

| `ok` | 状态 | Agent 动作 |
|------|------|-----------|
| `true` | 成功 | 读取 `data`，按 `pagination` 翻页 |
| `false` + HTTP 503 | 服务未启动 | 提示用户 `bosshelper server --start` |
| `false` + 500 | 浏览器未登录 | 提示用户登录 `http://127.0.0.1:8010` |
| `false` + 429 | 今日上限 | 告知用户，等待次日 |
| `false` + 404 | 资源不存在 | 确认参数正确 |

---

## Agent Integration Examples

### subprocess 调用（Python）

```python
import subprocess, json

def bosshelper_cmd(*args):
    result = subprocess.run(["bosshelper"] + list(args), capture_output=True, text=True)
    return json.loads(result.stdout)

# 搜索
r = bosshelper_cmd("search", "AI Agent", "--city", "北京")
if r["ok"]:
    jobs = r["data"]
    print(f"找到 {r['total']} 个岗位")

# 诊断
r = bosshelper_cmd("doctor")
print("环境OK" if r["ok"] else f"问题: {r['checks']}")
```

### Node.js / TypeScript

```typescript
import { execSync } from 'child_process';

function bosshelper(...args: string[]) {
  const stdout = execSync(`bosshelper ${args.join(' ')}`).toString();
  return JSON.parse(stdout);
}

const result = bosshelper('search', 'Golang', '--city', '广州');
console.log(`找到 ${result.total} 个岗位`);
```

### Shell

```bash
result=$(bosshelper search "Golang" --city 北京)
if echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d['ok'] else 1)"; then
  echo "搜索成功"
fi
```

---

## Safety & Compliance

> ⚠️ 本工具直接操作 BOSS 直聘账号，Agent 调用时请注意：

- 每日投递上限默认 15 条，超限返回 429
- 投递频率内置随机延迟，不要禁用
- **不要用 `while true` 循环投递**
- 账号触发风控时：立即停止，提示用户回平台手动操作
- AI 回复内容由设置中的简历摘要和风格决定，Agent 无法修改

---

## Agent Rule Template

在你的 AI Agent 规则文件（如 opencode 的 AGENTS.md）中添加：

```markdown
当用户要求搜索职位、投递岗位、查看聊天等 BOSS 直聘操作时：
1. 先运行 `bosshelper doctor` 检查环境
2. 若 `browser_running: false`，提示用户在浏览器登录
3. 运行 `bosshelper schema` 获取最新工具列表（不要硬编码命令）
4. 根据用户意图调用对应命令
5. 解析 stdout JSON，检查 `ok` 字段
6. `ok=false` 时读取错误信息，给出可操作建议
```

---

## License

MIT
