# 会话定位与回复链路设计缺陷修复计划

> 修复上一轮审查确认的 3 个设计级缺陷:
> D1 会话身份靠"名字子串匹配"→ 可能回错人(最严重)
> D2 检测靠未读红点,回复失败即成"孤儿消息"永不重试
> D3 LLM 调用嵌在浏览器单线程临界区内 → 前端操作排队卡顿

---

## D1: securityId 作为会话身份主键

**现状**:`open_conversation_by_name` 用 `li:has-text("名字")` 点击列表项(列表项含公司/岗位/消息预览,子串撞上即点错);DB 会话匹配也仅靠 HR 名(同名 HR 合并成一锅)。`_get_chat_security_id()` 已存在(BOSS 每个会话有唯一 securityId)但只用于发微信。

**方案**:
1. conversations 表加 `security_id` 列(ALTER,非唯一索引——存量行为空)
2. `poll_conversation_list` 每 cycle 调一次 friends API(`geekFilterByLabel`,带 encryptSystemId)拿 name→securityId 映射,附加到每个会话条目;API 失败退化为现行为(纯名字匹配),不影响可用性
3. 匹配优先级: security_id 精确 → 名字精确 → 名字子串;新建会话写入 security_id
4. **身份校验(安全网)**: 打开会话后提取当前页面 securityId 与期望比对,不一致 → 告警跳过不回复;期望为空(存量会话)→ 学习写入
5. 同名不同 securityId → 自然拆成两个会话(正确性优先)

**验收**: 单测覆盖 security_id 命中返回同会话、不同 sid 同名新建、match_conversation_item 纯函数优先级、identity 校验逻辑。

## D2: DB 驱动的孤儿消息兜底扫描

**现状**: 检测靠"未读 Tab + 红点",会话被打开即已读、从未读列表消失;回复生成失败/为空/退避跳过后,该消息"已读未回",下一轮列表里没有它 → 永不重试。

**方案**:
1. state 加 `get_stale_hr_conversations(minutes, limit)`: active + auto_reply_enabled=1 + 非 dangerous + `last_message_from='hr'` + `last_message_at < datetime('now','-N分钟')`(last_message_at 用 CURRENT_TIMESTAMP 存储,UTC,一致)
2. 新设置项 `sweep_after_minutes`(默认 10),每轮扫描后把未在本轮处理过的 stale 会话并入处理列表(走同一条"打开→读取→生成→发送"管线,自动复用退避/去重闸门)
3. 发送失败也计入失败退避计数(原来只算生成失败),防 send 反复失败无限重试
4. 每轮 sweep 上限 2 个,避免积压时爆发

**验收**: 单测覆盖 stale 查询(时间窗、状态门卫、limit)、本轮已处理会话不重复进 sweep。

## D3: 三阶段拆分,LLM 移出浏览器临界区

**现状**: `run_chat_monitor_cycle` 整体提交单线程 pw 执行器,内嵌 LLM 调用(每会话 5-30s)与随机 sleep;轮询间隔 15-25s → 执行器大半时间被占,前端手动操作全部排队。

**方案**:
1. 新建 `backend/runtime.py`: `pw_executor`(1 线程,从 app.py 迁移)+ `llm_executor`(2 线程)+ `aio_run_pw/aio_run_llm` 异步 hop + `run_in_pw` 同步 hop
2. `run_chat_monitor_cycle` 改为 **async 编排**,每会话流水线:
   - `[pw] _open_and_read(item)` — 打开+身份校验+读DOM+存库+提块+岗位回填(纯 DOM/DB,无 LLM)
   - `[llm] _generate_one(task)` — 问候快速路径/Agent/降级 + 退避/去重闸门(无浏览器;Agent 工具经 ctx["run_pw"] hop 回 pw 执行器)
   - `[pw] _send_one(task)` — 重新定位会话 + send_message + 落库 + 统计(发送失败计退避)
   执行器只在 DOM 块期间被占,LLM 期间前端操作可插队
3. `tool_executor` 浏览器操作改为 `ctx.get("run_pw")` hop(未提供则直调,兼容 CLI/测试)
4. **死锁分析**: llm 线程可能阻塞等 pw 执行器(工具 hop);pw 执行器不依赖 llm 执行器(apply_batch 无 LLM 调用)→ 无循环等待
5. 调用点适配: app.py 两处 `await _run_pw(automation.run_chat_monitor_cycle)` → `await automation.run_chat_monitor_cycle()`;scheduler deps 的 `run_chat_cycle` lambda 同步改(仍返回 awaitable,scheduler.py 零改动)

**验收**: 冒烟测试验证 scan 阶段不调 LLM、generate 阶段不直接碰 page、三阶段顺序执行;全量 pytest + import 冒烟。

---

## 实施步骤

| 步骤 | 内容 | 文件 |
|------|------|------|
| W1 | security_id 列/索引 + get_or_create 按 sid 归并 + get_conversation_by_security_id + update_conversation_security_id + get_stale_hr_conversations | state.py |
| W2 | runtime.py 执行器;poll 挂 sid;match_conversation_item 纯函数;monitor 拆 _scan_list/_open_and_read/_generate_one/_send_one + async 编排 + 身份校验 + 孤儿 sweep + 发送失败退避 | runtime.py, boss_chat_monitor.py |
| W3 | tool_executor run_pw hop;app.py 调用点适配;grep 兜底所有 run_chat_monitor_cycle 引用 | tool_executor.py, app.py |
| W4 | tests/test_conversation_identity.py + 全量回归 + 冒烟 | tests/ |

## 不变量
- `run_chat_monitor_cycle` 返回结构 `{checked, new_messages, replies_sent}` 不变(WebSocket 广播兼容)
- WebSocket 消息类型不变,前端零改动
- `_get_chat_security_id`/`send_wechat`/`send_phone`/`send_resume` 等现有方法签名不变
- DOM 选择器与页面交互流程不变

## 风险与回滚
- friends API 每轮多一次调用(原来 send_wechat 时每会话最多 3 次重试,频率反而降低);失败自动退化,不阻塞
- Playwright sync API 线程绑定: 所有 page 操作仍收敛在 pw 执行器,llm 线程仅经 hop 间接访问
- async 化调用点遗漏 → W3 全局 grep 兜底;调度器对 run_chat_cycle 的 await 语义不变
- 回滚: 改动集中在 4 个文件 + 新增 runtime.py,git revert 干净
