# AI 对话质量与上下文加载修复计划

> 范围:`replier.py` / `agent_loop.py` / `boss_chat_monitor.py` / `tool_executor.py` / `state.py`
> 原则:API 与调用链签名尽量不动,monitor 的 DOM 流程不动,只修数据流和上下文质量。

---

## 问题 → 解决方案总表

### P0-1 系统通知污染上下文
**问题**:「该Boss已查看了你的简历」「BOSS安全提示」等系统消息以 `HR:` 身份存库并进入 LLM 上下文;`_is_system_notification` 只用于判断是否回复,存库不过滤。
**方案**:
- 把闭包函数 `_is_system_notification` 提升为 `boss_chat_monitor.py` 模块级 `is_system_notification()`
- `run_chat_monitor_cycle` 构建 `clean_msgs` 时直接过滤系统通知(存库前),回复判断复用同一函数
**验收**:存库消息无系统通知;单测验证过滤函数。

### P0-2 历史对齐失败导致消息重复
**问题**:`replace_conversation_messages` 滑动窗口要求逐字全等,一次读取偏差 → `overlap_len=0` → 整段网页历史重复追加,污染后续所有轮次。
**方案**:无重叠且 DB 非空时,先做**尾部连续去重**:逐条比较「网页头部 vs DB 尾部」的 (sender, content),相同的头部前缀跳过不插入。处理整段重复追加的主场景;HR 真正重发的独立消息不受影响(仅头部连续重复才跳过)。
**验收**:单测——先写入 3 条,再用「3 条旧 + 2 条新」无重叠输入同步,断言 DB 共 5 条而非 8 条。

### P0-3 会话状态未注入上下文
**问题**:interest_level / hr_wechat / resume_sent / phone_shared / is_dangerous 存在 DB 但 Agent 看不到,导致重复发名片、重复评估兴趣。
**方案**:`build_agent_context` 新增注入「会话状态」段:已评估兴趣度、已交换微信/电话、已发简历、风险标记。`run_agent` 传完整 ctx 进去。
**验收**:单测断言上下文含状态字段。

### P0-4 岗位信息大面积缺失
**问题**:JD 只在 `application_id` 关联投递记录时才有;聊天页新发现的会话公司/岗位靠正则猜,Agent 经常不知道对方招什么。
**方案**:
- 新增 `state.get_application_by_hr_name()`:按 HR 名匹配 applications 表(HR 名在投递记录里有),回填 title/company/description
- 上下文中岗位信息仍缺失时**显式标注**「岗位信息暂缺」,prompt 指引 Agent 主动询问岗位方向而不是尬聊
**验收**:单测——applications 表有该 HR 记录时 job_info 被回填;仍缺时上下文含「暂缺」标注。

### P0-5 HR 最新消息在上下文重复两次
**问题**:`hr_message` 已在历史里,又拼一段「HR刚刚说」,Agent 看到同一句两遍。
**方案**:历史展示时剔除尾部与 `hr_message` 完全相同的消息,保留「HR刚刚说」指令段。
**验收**:单测断言历史段不含该消息、指令段含。

### P1-6 style 设置是死代码
**问题**:`style_hint` 塞进 agent_ctx 但无人读取,前端风格切换静默失效。
**方案**:`build_agent_context` 读取 `ctx["style_hint"]` 写入上下文;AGENT_SYSTEM_PROMPT 增加「回复风格」指令位。
**验收**:单测断言上下文含风格描述。

### P1-7 只回最后一条未回复消息
**问题**:HR 连发多条,只有最后一条作为 `hr_message`,前面的被弱化。
**方案**:提取**连续未回复块**——从尾部向前找到最后一条我方消息,其后所有 HR 消息按序合并(`\n` 连接)作为待回复内容。抽为纯函数 `extract_unreplied_block(msgs)` 便于单测。
**验收**:单测——3 条 HR 消息无我方回复 → 块含 3 条;中间夹我方回复 → 只取其后。

### P1-8 工具副作用不持久
**问题**:发简历失败/成功、面试创建结果只有当轮 LLM 可见,下一轮全部失忆。
**方案**:新表 `tool_events`(id, conversation_id, tool_name, result_summary, created_at);`tool_executor` 对 5 个有副作用的工具(send_resume/share_wechat/share_phone/propose_interview/mark_dangerous)在执行后记录(成功与失败都记,check_schedule 纯查询不记);`build_agent_context` 注入最近 5 条事件。
**验收**:单测——record 后 get_recent 返回;上下文含事件段。

### P1-9 长对话硬截断无摘要
**问题**:`msgs[-10:]` 直接丢更早历史,谈妥的薪资/时间全忘。
**方案**:conversations 表加列 `summary` + `summary_upto_id`(ALTER 兼容);`agent_loop` 在消息总数 > 30 且未摘要覆盖 > 20 时,后台一次性生成滚动摘要(旧摘要 + 新消息 → ≤200 字),失败静默跳过不阻塞主流程;上下文 = 摘要 + 最近 12 条。
**验收**:单测——触发条件判断、摘要写回、上下文含摘要段(LLM 调用 mock)。

### P2-10 简单问候千篇一律
**问题**:说「你好」的 HR 全部收到同一条硬编码开场白,是机器人指纹。
**方案**:保留不走 LLM 的快速路径(用户偏好:口语化、不暴露 AI 身份),但改为**8 个变体模板池随机** + 岗位/公司变量差异化 + 自然语气词。
**验收**:单测断言返回值在模板池内且池大小 ≥ 8;两次调用可不同(概率性,放宽断言)。

### P2-11 interest 标记解析脆弱
**问题**:正则只匹配 `[INTEREST: xxx]` 英文冒号+空格,LLM 稍变格式就丢。
**方案**:正则放宽为 `\[INTEREST?\s*[:：]\s*(high|medium|low)\]`(支持中文冒号、无空格)。
**验收**:单测覆盖 3 种格式变体。

### P2-12 失败无退避
**问题**:某条消息生成失败 → 每轮重试同一条直到日上限。
**方案**:`BossChatMonitor` 实例内存字典 `{conv_id: (消息hash, 连续失败数, 上次失败时间)}`,同一条消息连续失败 ≥ 3 次 → 冷却 30 分钟内跳过(重启清零,可接受)。
**验收**:单测纯逻辑(抽 `_should_skip_for_backoff` 可测函数)。

### P2-13 无回复去重
**问题**:不检查与上一条已发消息是否雷同,可能连发两条一样的。
**方案**:发送前与该会话我方最后一条消息比对,完全相同 → 重新生成一次;第二次仍相同 → 本轮跳过并告警。
**验收**:单测 mock 场景断言重试与跳过路径。

---

## 实施顺序

| 步骤 | 内容 | 涉及文件 |
|------|------|----------|
| F1 | state.py:tool_events 表、conversations ALTER(summary/summary_upto_id)、`get_application_by_hr_name`、`record_tool_event`/`get_recent_tool_events`、`update_conversation_summary`、replace 防重 | state.py |
| F2 | monitor:模块级 `is_system_notification`、存库前过滤、`extract_unreplied_block` 纯函数、失败退避、回复去重、job_info 回填 | boss_chat_monitor.py |
| F3 | agent_loop:上下文重构(状态/工具事件/摘要/风格/去重/岗位缺失标注)、prompt 更新、interest 正则放宽、滚动摘要 | agent_loop.py |
| F4 | tool_executor:副作用工具记录事件 | tool_executor.py |
| F5 | replier:问候模板池 | replier.py |
| F6 | 新增 `tests/test_chat_context.py` + 全量回归 | tests/ |

## 不变量
- `generate_reply()` / `run_agent()` / `execute_tool()` 对外签名不变
- DOM 操作、选择器、页面流程零改动
- WebSocket 消息类型不变,前端零改动

## 风险
- replace 防重逻辑误删 HR 真重发的消息 → 只处理「网页头部与 DB 尾部连续相同」的整段重复场景,独立重复不受影响
- 摘要生成引入额外 LLM 调用 → 仅长会话触发,失败静默降级,不阻塞回复主链路
