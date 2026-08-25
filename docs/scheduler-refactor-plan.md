# 定时调度器重构执行计划

> 目标:把 `backend/app.py` 中内嵌的 240 行调度器逻辑抽成独立模块 `backend/scheduler.py`,
> 修复状态不持久、聊天监控双通道、投递期间聊天饿死三个结构性问题。
> API 契约(`/api/scheduler`、`/api/scheduler/status`)保持不变,前端零改动。

---

## 一、现状问题(重构动机)

| # | 问题 | 位置 | 后果 |
|---|------|------|------|
| 1 | `scheduler_enabled` / `_scheduler_phase` / `_scheduler_log` 全是内存变量 | app.py:83-86, 1156-1157 | 服务重启后定时任务静默关闭,执行日志清零;与"持续监控回复 HR"的目标冲突 |
| 2 | 调度状态机 ~240 行混在 app.py | app.py:1151-1392 | 无法单测,和 API 端点/启动逻辑耦合 |
| 3 | 聊天监控双通道:`chat_monitor_loop` 与 `scheduler_loop` 每 tick 都各跑一轮 `run_chat_monitor_cycle` | app.py:1271-1281 vs 1514 | 重复轮询,靠 `monitor_paused` 标志脆弱协调 |
| 4 | 投递期间 `monitor_paused = True` 贯穿整个批量投递循环 | app.py:1300-1384 | 一轮投递数分钟,期间 HR 消息完全无人回复 |
| 5 | `enabled` 只存内存,config 存 SQLite,同一份配置两个来源 | app.py:1222-1224 | 语义不一致 |

## 二、目标架构

```
app.py (瘦身后)                    backend/scheduler.py (新)
┌──────────────────┐              ┌──────────────────────────┐
│ /api/scheduler   │──委托──────► │ Scheduler 类             │
│ /api/scheduler/  │              │  ├─ run()          主循环│
│   status         │              │  ├─ set_enabled()  开关  │
│ startup:         │              │  ├─ _tick()        一轮  │
│   Scheduler(deps)│─注入依赖───► │  ├─ _apply_session()分块投递│
└──────────────────┘              │  └─ 状态持久化到 settings │
                                  └──────────────────────────┘
依赖注入(Deps dataclass): get_setting / set_setting / run_pw /
get_automation / broadcast / city_code / save_jobs /
pending_jobs / today_count / set_monitor_paused /
run_chat_cycle —— 全部可 mock,可单测
```

### 关键设计决策

1. **状态持久化**
   - `scheduler_enabled` → settings 表 key `scheduler_enabled`,启动时读取恢复
   - 执行日志 → settings 表 key `scheduler_log`(JSON,上限 50 条),重启后保留
   - phase 为纯运行时态(重启后自然回 idle),不持久化

2. **聊天监控单一所有者 + 看门狗**
   - 常规聊天监控唯一归 `chat_monitor_loop`(monitor_task)
   - 调度器不再每 tick 重复跑聊天周期;仅当 monitor_task 已死(会话过期/安全检查 break)
     时,调度器作为兜底跑一轮 —— 保留原安全网,消除双通道轮询

3. **分块投递,块间喂聊天(修问题 4)**
   - 投递会话拆为 ≤5 条/块
   - 每块:安全检查 → apply_batch(≤5) → **跑一轮聊天监控周期**(内联,期间 monitor 仍暂停)
   - 效果:投递数分钟期间 HR 消息最多延迟一块(约 1-2 分钟)即被回复,
     且浏览器任一时刻只有一个操作者,无页面争抢

4. **时间窗判断保持字符串比较**(周一~周日 + HH:MM 区间),
   重叠区间命中任意一个即视为在窗内,行为与旧版一致

## 三、实施步骤

| 步骤 | 内容 | 产出 | 验收 |
|------|------|------|------|
| S1 | 新建 `backend/scheduler.py`:`SchedulerDeps` 注入 + `Scheduler` 类(主循环/tick/分块投递会话/日志持久化/看门狗聊天兜底) | scheduler.py (~260 行) | 纯逻辑不依赖 FastAPI,可直接 import |
| S2 | 改造 `app.py`:删除内嵌调度器代码段,组装 deps,启动时实例化并 `create_task(scheduler.run())`;3 个 API 端点委托给 scheduler 实例 | app.py 净减 ~150 行 | API 响应字段与旧版逐字段一致 |
| S3 | 新建 `tests/test_scheduler.py`:时间窗匹配 / enabled 持久化恢复 / 日志封顶 / 分块投递与聊天交错 / 达到日上限停止 / monitor 存活时不重复跑聊天 | test_scheduler.py | `pytest tests/test_scheduler.py` 全绿 |
| S4 | 回归:跑全量测试 + 语法检查 + 启动冒烟(import app 不报错) | — | 现有 test_server.py 不受影响 |

## 四、不变量(API 契约冻结)

- `GET /api/scheduler` → `{config: {enabled, days, time_ranges, auto_apply, auto_reply}}`
- `PUT /api/scheduler` → 接收同样结构,`enabled` 落库
- `GET /api/scheduler/status` → `{active, phase, today_count, daily_limit, execution_log}`
- WebSocket 消息类型不变:`scheduler_tick` / `scheduler_config_updated` / `safety_warning` /
  `auto_reply_sent` / `new_messages` / `search_complete`
- 前端 `frontend/src/api/scheduler.ts` 零改动

## 五、风险与回滚

- 风险:调度器与手动搜索/投递端点仍共享 `monitor_paused` 全局标志 → 保持原标志机制不动,
  调度器只是通过注入的 `set_monitor_paused` 操作它,行为等价
- 回滚:scheduler.py 为新增文件,app.py 改动集中在调度器段与端点段,git revert 即可
