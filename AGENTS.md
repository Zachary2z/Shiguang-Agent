# Shiguang_Nanobot 开发说明

在修改本仓库前，必须依次阅读：

1. docs/DEVELOPMENT_STAGES.md
2. docs/DEV_STATUS.md
3. 已迁入 docs/product/ 和 docs/technical/ 的相关需求文档

如果产品文档尚未迁入本仓库，可从以下只读参考目录读取：

- /Users/zhangzihao/Documents/Nanobot 学习/产品文档
- /Users/zhangzihao/Documents/Nanobot 学习/shiguang-ux-prototype
- /Users/zhangzihao/Documents/Nanobot 学习/nanobot

## 开发规则

- 当前仓库是拾光正式产品代码的唯一写入位置，不得修改上面的学习参考目录。
- 开始任务前检查当前阶段、Git 状态、已有实现和测试基线。
- 每个开发任务只处理 docs/DEV_STATUS.md 中指定的一个阶段或子阶段。
- 复用仓库中的 Nanobot 核心，不得另建第二套 AgentRunner、ToolRegistry 或 Provider。
- 业务规则放在拾光应用层和领域层，不写入通用 Agent Runner。
- 默认先使用 Fake、Stub 和固定 Fixture 测试，真实付费 API 测试必须显式开启。
- 密钥只写入未提交的本机 .env，不得写入代码、文档、测试输出或 Git。
- 完成任务前必须运行与改动相称的测试，并更新 docs/DEV_STATUS.md。
- 不得因为测试失败而删除测试、放宽核心断言或静默跳过功能。
- 未经用户明确授权，不执行付费调用、外部发布、云部署或消息发送。

## Git 规则

- 开发分支使用 codex/ 前缀。
- 阶段分支名称和验收标准以 docs/DEVELOPMENT_STAGES.md 为准。
- 不直接覆盖不属于当前任务的用户改动。
- 每个提交只表达一个清晰目的，并保留可回滚边界。

## 冲突处理

文档冲突时按以下优先级处理：

1. 用户在当前任务中的明确要求
2. 最新确认版 PRD
3. 核心用户流程
4. MVP 技术方案
5. docs/DEVELOPMENT_STAGES.md
6. UX HTML 原型

若冲突会改变产品行为、数据含义或权限边界，停止实现并向用户说明。
