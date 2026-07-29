# M1-Gate 核心闭环验收报告

## 1. 结论

M1-Gate 的离线、封网、PostgreSQL 16、Compose、前端、闭环场景和离线性能观测已
完成，当前没有未关闭 P0/P1。M1-Gate **仍在进行中，等待主控最终验收和真实性能
授权**；本报告不宣布 M1 关闭，不允许开始 M2。

本次真实模型、地图、网页、截图识别、对象存储或其他外部/付费 API 调用均为 0。
离线 Fake/Stub 的 P95 只说明本机编排开销，不能替代真实 Provider P95。用户尚未
授权真实取样，因此真实文本、网页和图片性能保持“等待授权”。

## 2. 基线与开始门禁

- 指定基线、`main`、`origin/main` 和分支起点均为
  `350beedec38013588a9aeba1812bf110f8ba6d8a`。
- 工作分支：`codex/m1-gate`；开始时工作区干净。
- Alembic 唯一 head：`20260729_0017`。
- M1-8 已完成，M2 未开始。
- `docs/technical/M1_2_HANDOFF.md` 历史上未单独创建。按用户更正，该差异不构成
  阻塞；M1-2 权威证据来自 `DEV_STATUS` 完整记录、阶段定义、README、确认版
  UI/UX 原型、实际前端、测试和线性 Git 历史。本次没有补建重复交接文档。
- 未读取仓库或本机 `.env`。

## 3. 范围、架构与安全复核

闭环覆盖输入、收藏、编辑/地点消歧、收藏检索、计划生成、自然语言调整、确认、
路线/日历、手动反馈、记忆/数据控制以及脱敏只读分享。

静态实现和自动化证据确认：

- `AgentRunner`、`ToolRegistry`、`ModelProvider` 抽象与正式
  `OpenAICompatibleProvider` 各只有一套；
- Collection 查询/写入、计划草案/体验/反馈、Memory、分享以及对应正式 Repository
  均保持唯一实现；
- 文字、URL、图片继续复用统一 Message、Source、运行跟踪和收藏写入边界；
- Demo 与真实用户使用独立数据库、存储根和 Web Session；
- PostgreSQL Job 领取/租约恢复、SSE sequence/replay、并发幂等、取消与所有权约束
  通过；重放未产生重复收藏、计划版本、文件、反馈、记忆或分享；
- 未发现测试白名单、地名样本特例、第二套 Runner/Registry/Repository、生产测试
  分支或重复业务规则；
- 未实现微信、提醒发送、云部署、账号绑定或其他 M2 功能；
- 日志、异常、公开 DTO、Git 与前端产物未发现密钥、Cookie、CSRF、Bearer、私人
  原文、完整外部响应或本机路径泄漏。

## 4. Gate 中关闭的测试缺陷

本次没有修改生产代码，只关闭两个时间/调度相关测试缺陷：

1. 图片外层截止测试原先假定图片线程准备必定在 0.6 秒内完成；全集负载下可能在
   Provider 请求开始前合法超时，导致取消 handler 断言偶发失败。测试现以确定性
   图片准备隔离取消传播边界，产品 60 秒共享截止和 Provider 75 秒异常上限不变。
   修复后聚焦连续 20 次通过，M0-4D 文件 `30 passed`，非真实全集稳定通过。
2. PostgreSQL 反馈测试以墙上时钟创建固定 2026-07-29 行程，执行时间越过行程末尾后
   会违反审批 `created_at < expires_at` 约束。种子现使用固定
   `PlanConstraints.created_at`，不改变生产审批规则或数据库约束。聚焦
   `3 passed`，全部 PostgreSQL marker `16 passed`。

## 5. 后端与迁移证据

全新 Python 3.14 虚拟环境、仓库外临时 SQLite：

- `pip check`：通过；
- Ruff：通过；
- strict mypy：139 个源文件通过；
- 非真实全集：`1654 passed, 16 skipped, 2 deselected`；
- Core：`120 passed`；
- Integration：`161 passed, 18 skipped`；
- 仓库外插件同时封锁 `socket.getaddrinfo`、`socket.connect`、
  `socket.connect_ex`、`socket.create_connection` 后，非真实全集仍为
  `1654 passed, 16 skipped, 2 deselected`；
- 封网核心闭环聚焦：`233 passed`。

SQLite 迁移完成：

`heads → upgrade head → current → check → downgrade base → upgrade head → current`

最终仍为唯一 `20260729_0017 (head)`，`alembic check` 无待生成操作。

一次性 PostgreSQL 16 全部 marker：`16 passed, 1656 deselected`。覆盖：

- 两 Worker 领取、幂等、三次有界尝试、租约/心跳和服务恢复；
- RunEvent sequence、并发发布与 SSE replay；
- Web Session 并发创建/撤销、Demo 恢复和双库隔离；
- 反馈并发幂等、更正、所有权复合外键；
- Memory 更新/删除/重放和所有权；
- 分享同计划串行、不同计划并发、哈希 token 和唯一终态；
- PostgreSQL 迁移往返。

## 6. 前端与 Compose

Node 25.8.0、npm 11.11.0：

- `npm ci`：通过；
- lint：通过；
- typecheck：通过；
- Vitest：`81 passed`；
- 生产 build：通过，7 个正式路由生成；
- Playwright：`29 passed`，包含真实离线 FastAPI 输入/收藏闭环、计划生成/调整/
  确认/重启恢复、Memory 控制和匿名分享。

仓库外无密钥 `compose.env` 与独立 project name 完成：

- Compose 配置校验和镜像构建；
- API、Worker、真实 PostgreSQL、Demo PostgreSQL 全部 healthy；
- `/healthz` 返回 `ok`；
- Demo Session API 返回 201；
- 两个数据库分别迁移且 Demo User 只写入 Demo 数据库；
- API/Worker 日志未发现 traceback、error 或 credential 泄漏；
- 验证后容器、网络和一次性数据卷均已删除。

首次 BuildKit 拉取 Python 基础镜像元数据发生一次环境网络 deadline；显式拉取基础
镜像后单次重试成功，未修改代码或 Compose。

## 7. 闭环场景和硬约束

精选完整闭环自动化得到 `21 passed`，成功率 `100%`，覆盖：

- 文字、URL、清晰图片和低信息图片；
- 地点候选消歧、跨城市与城市待确认收藏；
- 收藏编辑、删除、恢复和并发版本冲突；
- 收藏充足、结构化缺口、拒绝外部补充；
- 计划生成、自然语言调整、并发重放和明确确认；
- 路线、iCalendar、三态反馈及反馈更正；
- Memory 确认、拒绝、禁用、删除和私有导出；
- 分享预览、创建、重建、撤销、取消、过期和匿名无内容；
- 超时、取消、重复请求、并发和 Worker 租约恢复。

另有 20 组具名确定性计划 fixture：`20 passed`，生成后硬约束违反总数为 0。

## 8. 离线性能观测

所有 P95 均使用 nearest-rank，且每组至少 20 个观测。这里的 SSE 指首个持久化、
可重放 RunEvent 出现时间；不是浏览器网络传输的真实公网首字节。

### PostgreSQL 收藏查询

一次性 PostgreSQL 16、单用户 5,000 条收藏、10 次预热、100 次正式观测：

| 指标 | P50 | P95 | 最大值 | 超时率 |
|---|---:|---:|---:|---:|
| 收藏文本查询完整 Application 调用 | 16.353 ms | 18.652 ms | 20.394 ms | 0% |

低于 500 ms 目标。

### Fake/Stub 异步输入链

每类 20 次，SQLite、Fake Model、Stub Web、本地私有存储、真实 Job/Worker 和持久化
RunEvent：

| 输入 | 阶段 | P50 | P95 | 最大值 | 超时率 |
|---|---|---:|---:|---:|---:|
| 文字 | 202 提交 | 6.754 ms | 14.741 ms | 69.661 ms | 0% |
| 文字 | 首个持久化 SSE 事件 | 16.288 ms | 30.998 ms | 83.401 ms | 0% |
| 文字 | 最终权威结果 | 32.940 ms | 55.265 ms | 102.302 ms | 0% |
| URL | 202 提交 | 6.565 ms | 7.150 ms | 7.672 ms | 0% |
| URL | 首个持久化 SSE 事件 | 16.240 ms | 20.333 ms | 20.434 ms | 0% |
| URL | 最终权威结果 | 34.817 ms | 37.845 ms | 38.878 ms | 0% |
| 图片 | 202 提交 | 8.687 ms | 9.229 ms | 9.420 ms | 0% |
| 图片 | 首个持久化 SSE 事件 | 19.605 ms | 22.030 ms | 22.282 ms | 0% |
| 图片 | 最终权威结果 | 38.713 ms | 41.726 ms | 45.792 ms | 0% |

这些结果证明离线编排没有性能阻断，但不能验证真实文本 12 秒或真实网页/图片 20 秒
目标。普通 Agent 60 秒硬截止和 Provider 75 秒异常安全上限均未调整。

## 9. 剩余 P2 与授权状态

- 真实文本、地图、网页和图片性能：等待当前任务明确授权；请求数和费用上限尚未
  批准，真实调用次数为 0。
- 既有 M1-5 高基数候选截断为非阻断 P2。
- npm 完整开发依赖 audit 仍有 9 个 high，位于既有 ESLint/minimatch 开发依赖链；
  生产构建通过，既有阶段证据中的生产依赖 audit 为 0。
- 浏览器自动化仍以本机 Chromium 为主，未覆盖 Safari/Firefox/Windows。
- M1-2 没有独立 HANDOFF 文件是历史文档组织差异，不是缺陷。

主控复验和真实性能授权完成前，M1-Gate 不得标记“已完成”，不得合并、推送或开始
M2。
