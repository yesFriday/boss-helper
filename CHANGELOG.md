# CHANGELOG

## [0.1.0] - 2026-05-27

### Added
- 自动投递：搜索后一键批量投递，带进度条和取消按钮
- AI 自动回复：DeepSeek/OpenRouter/小米MiMo多平台模型驱动
- 智能交换：HR要简历/微信/手机号时自动通过BOSS发送
- Web 控制台：FastAPI后端 + 黑暗风UI + WebSocket实时推送
- CLI 工具：12条命令，Agent友好JSON输出，`bosshelper` 入口
- 福利筛选：搜索时按"双休/五险一金"等关键词过滤
- 投递漏斗：搜索→待投递→已投递→HR回复→面试可视化
- AI JD分析：岗位匹配度评分、关键技能、差距建议
- 本地候选池：收藏岗位，支持备注
- 60+城市支持，按省份分组
- 诊断命令 `bosshelper doctor`

### Changed
- 潍坊城市代码从101120700修正为101120600
- README.md 对标 boss-agent-cli 重写

### Fixed
- 投递后招呼语发送
- AI回复时序（先发送再回复）
- 防重复发送简历/微信/电话
- 一键投递从数据库加载待投递岗位
