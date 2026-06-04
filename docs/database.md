# 数据库文档

数据库文件位置：`.boss_profile/boss_state.db`

类型：SQLite，可用 Navicat 直接打开。

---

## 表结构总览

| 表名 | 用途 | 主键 |
|------|------|------|
| applications | 岗位/投递记录 | id (自增) |
| conversations | HR会话（一个HR一条） | id (自增) |
| messages | 聊天消息（一条会话多条消息） | id (自增) |
| settings | 系统配置（键值对） | key (文本) |
| daily_stats | 每日统计 | date (日期文本) |
| shortlists | 候选池（收藏的岗位） | id (自增) |

---

## applications — 岗位/投递记录表

每搜索到一个岗位或投递一个岗位，生成一条记录。

| 字段 | 类型 | 说明 | 取值示例 |
|------|------|------|----------|
| id | INTEGER | 主键，自增 | 1, 2, 3 |
| job_title | TEXT | 岗位名称 | "AI Agent开发", "大模型算法工程师" |
| company | TEXT | 公司名称 | "字节跳动", "腾讯" |
| salary | TEXT | 薪资范围 | "15-25K", "面议" |
| job_url | TEXT | 岗位详情页URL，唯一约束 | https://www.zhipin.com/job_detail/... |
| city | TEXT | 城市 | "淄博", "北京", "上海" |
| experience | TEXT | 经验要求 | "3-5年", "不限" |
| education | TEXT | 学历要求 | "本科", "硕士" |
| hr_name | TEXT | HR姓名 | "张女士" |
| hr_title | TEXT | HR职位 | "招聘经理", "HRBP" |
| description | TEXT | 岗位描述/JD全文 | 完整的职位描述文本 |
| status | TEXT | 投递状态 | pending=待投递, applied=已投递, skipped=已跳过 |
| greeting_text | TEXT | 发送的招呼语内容 | "您好！看到贵司在招..." |
| greeting_sent_at | TIMESTAMP | 招呼语发送时间 | "2026-06-01 10:30:00" |
| created_at | TIMESTAMP | 记录创建时间 | 自动填充 |
| updated_at | TIMESTAMP | 最后更新时间 | 每次操作自动更新 |

---

## conversations — 会话表

每个HR的对话记录，一个HR对应一条会话。

| 字段 | 类型 | 说明 | 取值示例 |
|------|------|------|----------|
| id | INTEGER | 主键，自增 | 1, 2, 3 |
| application_id | INTEGER | 关联的岗位ID（外键→applications.id） | 1 |
| hr_name | TEXT | HR姓名 | "张女士" |
| hr_company | TEXT | HR所在公司 | "字节跳动" |
| job_title | TEXT | 应聘岗位名称 | "AI Agent开发" |
| last_message_text | TEXT | 最后一条消息内容 | "方便面试吗？" |
| last_message_from | TEXT | 最后消息发送者 | hr=HR发送, me=我方发送 |
| last_message_at | TIMESTAMP | 最后消息时间 | "2026-06-01 14:20:00" |
| unread_count | INTEGER | 未读消息数 | 0, 1, 3 |
| status | TEXT | 会话状态 | active=活跃, closed=已结束 |
| auto_reply_enabled | INTEGER | 是否开启自动回复 | 1=开启, 0=关闭 |
| interest_level | TEXT | HR兴趣度（AI评估） | high=高, medium=中, low=低 |
| hr_wechat | TEXT | HR的微信号（从聊天中提取） | "hr_zhangsan" |
| wechat_shared_at | TIMESTAMP | 微信交换时间 | "2026-06-01 15:00:00" |
| resume_sent | INTEGER | 是否已发送简历 | 1=已发送, 0=未发送 |
| phone_shared | INTEGER | 是否已交换电话 | 1=已交换, 0=未交换 |
| created_at | TIMESTAMP | 记录创建时间 | 自动填充 |
| updated_at | TIMESTAMP | 最后更新时间 | 每次操作自动更新 |

---

## messages — 消息表

每条聊天消息，一个会话下有多条消息。

| 字段 | 类型 | 说明 | 取值示例 |
|------|------|------|----------|
| id | INTEGER | 主键，自增 | 1, 2, 3 |
| conversation_id | INTEGER | 所属会话ID（外键→conversations.id） | 1 |
| sender | TEXT | 发送者 | hr=HR发送, me=我方发送 |
| content | TEXT | 消息内容 | "你好，请问还在看机会吗？" |
| delivery_status | TEXT | 送达状态 | 已读/未读/送达/发送失败 |
| ai_generated | INTEGER | 是否AI生成 | 1=AI自动生成, 0=人工发送 |
| created_at | TIMESTAMP | 消息时间 | "2026-06-01 14:20:00" |

---

## settings — 配置表

系统配置项，以键值对形式存储。value 字段为 JSON 字符串。

| 字段 | 类型 | 说明 | 取值示例 |
|------|------|------|----------|
| key | TEXT | 配置项名称（主键） | "daily_apply_limit" |
| value | TEXT | 配置项值（JSON字符串） | "15", "true", "[\"AI Agent\"]" |
| updated_at | TIMESTAMP | 最后更新时间 | 自动填充 |

### 常用配置项

| key | 说明 | 默认值 |
|-----|------|--------|
| greeting_template | 招呼语模板，支持 {job_title} {company} 占位符 | "您好！看到贵司在招{job_title}..." |
| greeting_enabled | 是否发送招呼语 | "true" |
| ai_reply_style | AI回复风格 | "professional" |
| daily_apply_limit | 每日投递上限 | "15" |
| auto_reply_enabled | 是否开启AI自动回复 | "true" |
| min_reply_delay_sec | 回复最小延迟（秒） | "15" |
| max_reply_delay_sec | 回复最大延迟（秒） | "20" |
| batch_delay_min_sec | 批次间最小延迟（秒） | "30" |
| batch_delay_max_sec | 批次间最大延迟（秒） | "90" |
| resume_summary | 简历摘要（供AI回复参考） | "" |
| wechat_id | 求职者微信号 | "" |
| search_keywords | 搜索关键词，逗号分隔 | "AI Agent,大模型开发,..." |
| search_city | 搜索城市编码 | "100010000" |
| scheduler_config | 调度器完整配置（JSON） | 见下方 |

### scheduler_config 结构

```json
{
  "enabled": true,
  "time_range": {"start": "09:00", "end": "22:00"},
  "search_keywords": ["AI Agent", "大模型开发"],
  "search_city": "100010000",
  "auto_apply": {"daily_limit": 15},
  "auto_reply": {
    "style": "professional",
    "min_delay_sec": 15,
    "max_delay_sec": 20
  }
}
```

---

## daily_stats — 每日统计表

每天的投递和聊天统计汇总。

| 字段 | 类型 | 说明 | 取值示例 |
|------|------|------|----------|
| date | TEXT | 日期（主键） | "2026-06-01" |
| applications_sent | INTEGER | 当日投递数 | 10 |
| messages_sent | INTEGER | 当日发送消息数 | 25 |
| messages_received | INTEGER | 当日接收消息数 | 20 |
| auto_replies_sent | INTEGER | 当日AI自动回复数 | 15 |

---

## shortlists — 候选池表

收藏/暂存的岗位，后续决定是否投递。

| 字段 | 类型 | 说明 | 取值示例 |
|------|------|------|----------|
| id | INTEGER | 主键，自增 | 1, 2, 3 |
| job_url | TEXT | 岗位URL，唯一约束 | https://www.zhipin.com/job_detail/... |
| job_title | TEXT | 岗位名称 | "AI Agent开发" |
| company | TEXT | 公司名称 | "字节跳动" |
| salary | TEXT | 薪资范围 | "15-25K" |
| city | TEXT | 城市 | "北京" |
| note | TEXT | 备注 | "技术栈对口，优先投递" |
| created_at | TIMESTAMP | 记录创建时间 | 自动填充 |

---

## 表关系

```
applications (1) ──→ (0..1) conversations
                通过 application_id 关联

conversations (1) ──→ (0..n) messages
                通过 conversation_id 关联
```

- 一个岗位投递后可能产生一个会话（HR回复了）
- 一个会话下有多条聊天消息
- settings 和 daily_stats 是独立表，无外键关联
