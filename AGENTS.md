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

## 简洁实现与测试原则

- 测试用于证明产品行为和架构边界正确，不得为了让单个测试通过而在生产代码中堆叠特例、白名单、代理或重复校验。
- 先区分来自 PRD 的业务硬规则与框架实现细节；安全、错误映射和输入校验应放在真实公开边界，不追逐第三方库的每个内部调用入口。
- 同一缺陷在一次修复后又出现新的旁路时，停止继续打补丁，重新检查抽象、归属和边界；修复应删除已被替代的旧路径，而不是长期保留多套保护层。
- 优先保持一个公共契约、一个正式入口和一份业务规则。新增代码前说明为何不能通过删除、收敛或复用现有实现解决。
- 全部测试通过不等于可以验收；主控与 QA 还必须检查净复杂度、重复规则、无产品含义的防御代码和对框架内部属性的脆弱依赖。

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
