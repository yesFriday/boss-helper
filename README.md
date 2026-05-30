<div align="center">

# bosshelper

**AI 驱动的 BOSS 直聘智能求职助手 · Web 控制台 + CLI**

> 搜索 60+ 城市 · 福利筛选 · 一键批量投递 · AI 接管聊天 · 自动交换微信简历 · CLI 供 Agent 调用

[![Python](https://img.shields.io/badge/Python-≥3.10-3776AB?logo=python&logoColor=white&style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![CLI](https://img.shields.io/badge/CLI-14_Commands-blue.svg?style=flat-square)](#-cli-命令)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](https://github.com/yesFriday/bosshelper/pulls)

[快速开始](#-快速开始) · [CLI 命令](#-cli-命令) · [核心能力](#-核心能力) · [AI 配置](#-ai-模型配置) · [API 端点](#-api-端点参考) · [诊断](#-诊断与排障) · [架构](#-技术架构)

</div>

> BOSS Zhipin job hunting assistant with web dashboard + CLI. Auto search, batch apply, AI chat replies, welfare filter, multi-model support. AI Agent friendly JSON output.

---

## ⚠️ 合规边界

- ✅ 仅用于**个人账号**求职辅助
- ✅ 每日投递有**上限**（默认 15 条，可调）
- ❌ 不得批量注册、商业采集、规避风控
- ❌ 触发风控时立即停止自动化，回平台手动操作

---

## 💡 为什么用 bosshelper

| 传统流程 | bosshelper |
|----------|---------------------|
| 打开网页逐个搜索 | `bosshelper search` 一行搜全国 |
| 手动翻页看薪资 | 福利筛选一键过滤双休五险一金 |
| 逐一点"立即沟通" | 一键批量投递 + 进度条 |
| 时刻盯手机回复HR | AI 自动接管聊天 |
| 忘了跟谁聊过什么 | Web 控制台全记录 + 投递漏斗 |

**Web 控制台** 适合日常操作，**CLI** 适合 AI Agent 调用。两套界面共用同一套后端。

---

## 📦 安装

```bash
git clone https://github.com/yesFriday/bosshelper.git
cd bosshelper
pip install -e .              # 含 CLI 入口 bosshelper
playwright install firefox    # 浏览器自动化
```

---

## 🚀 快速开始

```bash
# 1. 启动后台服务
python boss_app.py --port 8010
# 或 CLI 启动
bosshelper server --start --port 8010

# 2. 浏览器打开 http://127.0.0.1:8010
#    设置页 → 启动浏览器 → 扫码登录 BOSS 直聘

# 3. 配置 AI
#    设置页 → AI模型配置 → 选平台 → 填 Key → 保存

# 4. 搜索 → 一键投递
#    搜索页 → 选城市 → 输关键词 → 搜索 → 一键投递
```

<details>
<summary>5 分钟视频教程（待补充）</summary>
暂无，欢迎贡献 demo 录制。
</details>

---

## 💻 CLI 命令

安装后即获 `bosshelper` 命令，stdout 仅输出 JSON，AI Agent 友好。

### 14 条命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `bosshelper search` | 搜索岗位 | `bosshelper search "AI Agent" --city 广州 --welfare "双休,五险一金"` |
| `bosshelper status` | 浏览器状态 + 今日统计 | `bosshelper status` |
| `bosshelper stats` | 投递转化漏斗 | `bosshelper stats` |
| `bosshelper jobs` | 岗位列表 | `bosshelper jobs --status pending` |
| `bosshelper apply` | 投递单个 | `bosshelper apply <job_url>` |
| `bosshelper apply-batch` | 批量投递待投递 | `bosshelper apply-batch` |
| `bosshelper conversations` | HR 会话列表 | `bosshelper conversations` |
| `bosshelper chat` | 查看聊天记录 | `bosshelper chat 1` |
| `bosshelper send` | 手动发消息 | `bosshelper send 1 --msg "你好"` |
| `bosshelper analyze` | AI 分析岗位匹配度 | `bosshelper analyze <job_url> --title "AI开发"` |
| `bosshelper shortlist` | 候选池增删查 | `bosshelper shortlist list` |
| `bosshelper schema` | 输出工具描述 JSON | `bosshelper schema` |
| `bosshelper doctor` | 环境诊断 | `bosshelper doctor` |
| `bosshelper server` | 管理后台服务 | `bosshelper server --start` |

### 输出格式

```json
{
  "ok": true,
  "command": "search",
  "data": [{ "title": "AI开发", "company": "XX科技", ... }],
  "pagination": { "page": 1, "has_more": true, "total": 15 },
  "error": null
}
```

- `stdout` — 仅 JSON
- `stderr` — 日志/进度
- exit `0` 成功，exit `1` 失败

### AI Agent 集成

```bash
# 1. 获取工具清单
$ bosshelper schema

# 2. 检查登录
$ bosshelper status
# → {"ok": true, "data": {"browser_running": true}}

# 3. 搜索岗位
$ bosshelper search "Golang" --city 北京
# → {"ok": true, "data": [...], "total": 23}

# 4. 批量投递
$ bosshelper apply-batch
```

> 详细集成指南见 [SKILL.md](SKILL.md)

---

## 🌟 核心能力

| 功能 | Web 控制台 | CLI |
|------|:--:|:--:|
| 🔍 60+ 城市搜索 | ✅ | ✅ |
| 🎯 福利筛选（双休/五险一金） | ✅ | ✅ |
| 🚀 一键批量投递 + 进度条 | ✅ | ✅ |
| 🤖 AI 自动回复 | ✅ | — |
| 📱 自动交换微信/简历/电话 | ✅ | — |
| 📊 投递转化漏斗 | ✅ | ✅ |
| 🧠 AI JD 分析 | ✅ | ✅ |
| 📌 本地候选池 | ✅ | ✅ |
| 🩺 环境诊断 | — | ✅ |
| 🧩 AI Agent 集成 | — | ✅ |

---

## 🤖 AI 模型配置

设置页选平台 → 自动填 Base URL 和模型列表 → 填 Key 即可。

| 平台 | 自动填充 |
|------|:--:|
| DeepSeek | ✅ |
| OpenRouter | ✅ |
| 小米MiMo | ✅ |
| 自定义（任意 OpenAI 兼容 API） | — |

---

## 📁 项目结构

```
├── backend/                 # 后端代码
│   ├── app.py               # FastAPI Web 后端
│   ├── automation.py        # 自动化投递 + 聊天
│   ├── firefox.py           # BOSS 搜索 + 福利筛选
│   ├── replier.py           # AI 回复生成
│   └── state.py             # SQLite 数据持久化
├── bosshelper_cli/          # CLI (14 命令)
│   ├── cli.py / client.py / output.py / schema.json
├── frontend/                # React 前端
├── static/                  # 静态文件
├── interview/               # 面试问答子模块
├── pyproject.toml           # 打包 + CLI 入口
├── SKILL.md                 # Agent 集成指南
└── CHANGELOG.md
```

---

## 🔌 API 端点参考

<details>
<summary>点击展开完整 API 列表</summary>

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/api/status` | 浏览器状态 |
| `GET` | `/api/stats` | 投递漏斗 |
| `GET` | `/api/doctor` | 环境诊断 |
| `POST` | `/api/jobs/search` | 搜索岗位 |
| `GET` | `/api/jobs` | 岗位列表 |
| `POST` | `/api/jobs/apply` | 投递单个 |
| `POST` | `/api/jobs/apply-batch` | 批量投递 |
| `POST` | `/api/jobs/analyze` | AI JD 分析 |
| `GET` | `/api/shortlists` | 候选池 |
| `POST` | `/api/shortlists` | 添加收藏 |
| `DELETE` | `/api/shortlists/{id}` | 取消收藏 |
| `GET` | `/api/conversations` | 会话列表 |
| `GET` | `/api/settings` | 读取设置 |
| `PUT` | `/api/settings` | 更新设置 |
| `POST` | `/api/system/start` | 启动浏览器 |
| `POST` | `/api/system/relogin` | 重新扫码 |
| `WS` | `/ws` | 实时推送 |

</details>

---

## 🏗️ 技术架构

```
Web 浏览器                  FastAPI                     BOSS 直聘
┌──────────┐  WebSocket   ┌──────────────┐  Playwright  ┌──────────────┐
│dashboard │◄────────────►│  boss_app.py  │◄────────────►│  zhipin.com   │
│  .html   │  HTTP/REST   │               │  Firefox     │               │
└──────────┘              │  automation   │              └──────────────┘
                          │  replier ─────────────────►│  AI API       │
                          │  state ─────► SQLite       └──────────────┘
                          └──────────────┘
              bosshelper CLI ──► HTTP 客户端 ──► FastAPI
```

| 层级 | 选型 |
|------|------|
| 后端 | Python >= 3.10 + FastAPI |
| 浏览器 | Playwright + Firefox 持久化 Profile |
| 数据库 | SQLite (WAL) |
| 前端 | 单文件 HTML + Vanilla JS + WebSocket |
| CLI | Click + httpx + JSON 信封 |
| AI | OpenAI Chat Completions 兼容 API |

---

## 🔧 诊断与排障

```bash
bosshelper doctor             # 一键诊断
bosshelper status             # 浏览器状态
```

<details>
<summary>常见问题</summary>

| 问题 | 解决 |
|------|------|
| 端口被占用 | `bosshelper server --port 8015` |
| 浏览器启动失败 | `playwright install firefox --force` |
| 登录过期 | 设置页点击「重新扫码登录」|
| 搜索返回 500 | 浏览器未启动，先去设置页启动 |
| AI 不回复 | 检查设置页 AI 配置是否保存 |

</details>

---

## ⚙️ 配置

### config.yaml

```yaml
browser:
  headless: false
  profile_dir: ./.boss_profile/firefox_user_data
```

### Web 设置项

| 设置 | 说明 |
|------|------|
| 招呼语模板 | 投递时自动发送 |
| AI 回复风格 | professional / casual / enthusiastic |
| 每日投递上限 | 1-30，默认 15 |
| 回复间隔 | 30-120 秒随机延迟 |
| 搜索关键词 | 一行一个 |
| 简历摘要 | AI 生成回复素材 |
| AI 配置 | 平台 / Key / Base URL / 模型 |

---

## ⚠️ 免责声明

本项目仅供学习交流和个人求职辅助。使用请遵守 BOSS 直聘用户协议。因不当使用产生的后果由使用者自行承担。

---

## 📑 许可证

[MIT](LICENSE)

## 🙏 致谢

- [can4hou6joeng4/boss-agent-cli](https://github.com/can4hou6joeng4/boss-agent-cli) — 设计灵感来源
- [Playwright](https://playwright.dev/) · [FastAPI](https://fastapi.tiangolo.com/)
