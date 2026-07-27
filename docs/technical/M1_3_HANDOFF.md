# M1-3 Agent 与内容导入页面交接

## 范围与结论

M1-3 在基线 `d1832e9ae8355fe1e58faae0e101b9f8e0a4d2c8` 上完成。实现复用
M1-0 的唯一 JobQueue/Worker/RunEvent、M0 的唯一 TextCollectionWorkflow 和
CollectionWriteService，以及 M1-2 的唯一 API/SSE Client、Token 与 App Shell。
没有实现 M1-4 收藏库、候选选择或完整详情，也没有实现计划、真实登录或外部发布。

## 接口变化

- `POST /api/v1/sessions/{session_id}/messages`：改为 `202 Accepted`，返回
  `message_id`、`trace_id`、`run_status`、`events_url`、`result_url` 和
  `replayed`。文字/URL 使用 JSON，截图使用原始 JPEG/PNG/WebP 与
  `Idempotency-Key`。
- `GET /api/v1/agent-runs/{trace_id}/events`：沿用既有单调 sequence、SSE replay
  与 `Last-Event-ID`。
- `GET /api/v1/agent-runs/{trace_id}/result`：读取持久化权威终态、收藏、来源、
  恢复动作及安全工具步骤；不从 SSE 摘要推断结果。
- `GET /api/v1/sessions/{session_id}/messages`：恢复当前对话和未完成运行。
- `POST /api/v1/collections/{item_id}/restore`：在既有写服务内幂等恢复删除前状态。

正式内容导入 Job 类型为 `content.import`。Job payload 只含 session/message/source
标识与输入类型；用户正文、URL、文件 key、图片字节和 Base64 均留在既有持久化或
私有存储边界。Worker 只恢复输入并调用 TextCollectionWorkflow。

## 前端状态机

```text
idle
  -> submitting
  -> queued / processing
  -> saved | pending_selection | pending_details | failed
  -> undone
```

提交后立即进入 queued/processing。SSE 阶段仅映射为“内容接收、地点识别、结果
整理”，不显示百分比；有限重连后仍读取权威结果。收藏卡展示确认字段、缺失项和
不确定项。修改、撤销、恢复和继续添加均调用正式接口。工具过程默认折叠，只显示
工具名、阶段、状态、来源、耗时与安全错误码。

## 数据迁移

新增 `20260727_0011_collection_restore_status.py`，为 `collection_items` 增加
`deleted_from_status`。现有 `status=deleted` 无法表达删除前是 active、
pending_selection 还是 pending_details，因此无法保证真实无损恢复；这就是新增
字段的必要性。迁移可升降级，Alembic 只有 `20260727_0011` 一个 head。

## 测试结果

- 后端：`pip check`、Ruff、严格 mypy 通过；core `120 passed`；迁移
  `23 passed`；完整离线回归 `1563 passed, 10 skipped, 2 deselected`。
- 前端：生产依赖 audit 为 0；lint、typecheck、build 通过；Vitest
  `29 passed`。
- 浏览器：Playwright `14 passed`，覆盖 320/390/768/1024/1440px、44px 目标、
  键盘焦点、reduced motion，以及真实 FastAPI + 离线 Fake Provider 的
  “首次进入 → 提交 → 识别 → 权威结果 → 修改 → 撤销/恢复 → 继续添加”。
- M1-3 聚焦后端契约 `4 passed`，覆盖 202/SSE/权威结果、幂等复用、图片安全引用、
  删除恢复及 Session/CSRF 边界。

所有测试默认离线，未读取 `.env`，未调用真实模型、地图、网页或付费 API。

## 安全、清理与冗余

- CSRF 仅保存在 React 运行内存；Cookie 由浏览器管理。
- 图片先完整校验并进入既有私有存储；上传中断不会创建 Job/Source/文件，存储写入
  失败会清空临时文件和预留记录并终结 queued run。
- 已登记原图沿用既有 30 天保留策略；识别失败不立即删除该原图，这是可恢复性与
  生命周期策略的当前取舍。
- 工具 DTO 不含 Prompt、思维链、模型原文、敏感参数或供应商响应。
- 页面不使用 `dangerouslySetInnerHTML`；用户输入、文件名与后端内容按文本渲染。
- 没有新增第二套 API Client、SSE Client、JobQueue、Worker、AgentRunner、
  ToolRegistry、Parser、收藏工作流或 Undo/Restore 系统。

## 已知风险与主控复测

- 当前浏览器联调使用 SQLite 与离线 Fake Provider；请主控补测 PostgreSQL 的
  API/Worker 分进程并发与 SSE replay。
- 请重点复测刷新恢复、断线重放、同键并发、上传中断、终态前不显示成功、恶意
  HTML 文本化、跨 Cookie 所有权、删除前各状态的精确恢复。
- 尚未覆盖 Node 20/22、Windows/Linux、Safari/Firefox；不阻塞当前 macOS/
  Chromium 阶段验收。

## 主控 QA 缺陷修复

本节记录候选提交 `d1daa7354d3ae63dd71972cf6a6631c968637c1b` 之后的 M1-3
修复。公开 HTTP 路由和 DTO 没有增加；内部唯一 `JobQueue` 契约新增通用
`renew_lease(job_id, worker_id, now)`。

### Worker 与租约生命周期

- Worker 启动只在模型三项配置完整时构造既有
  `OpenAICompatibleProvider`；三项全空时 Provider 为 `None`，部分配置仍按原
  Settings 边界拒绝启动。没有把 Fake Provider 放入生产代码。
- 无模型的 `content.import` 仍进入唯一 TextCollectionWorkflow，由工作流记录
  `MODEL_PROVIDER_NOT_CONFIGURED` 终态；Handler 将该业务终态作为已处理 Job
  完成，避免进程退出、无限 queued 或无意义重试。
- `PostgresJobQueue.renew_lease` 只允许当前 Worker 在原租约尚有效且 Job 仍为
  running 时续租。`JobWorker` 同时管理 Handler 和唯一心跳任务：Handler
  完成/异常、任务取消、Worker 退出或租约丢失都会取消另一侧；真正失联后没有心跳，
  原 `recover_stale` 仍可领取。
- Compose 的 API 与 Worker 共享既有本地私有存储 volume，避免图片 Source 由 API
  登记后在分进程 Worker 中不可见。

### 提交原子性与幂等

输入准备继续由唯一 TextCollectionWorkflow 完成。Queue 创建异常时先按 trace 查询
现有 Job：若只是响应丢失则直接复用；确认不存在 Job 才通过既有
`SqlAlchemyCollectionRepository`、`AgentRunRepository` 与 Storage Provider 删除
本次 Message、queued Run/RunEvent、未关联 Source 和私有文件。没有跨库事务，也
没有新增 Repository、队列或锁。数据库唯一约束仍是并发与最终一致性的最后边界。
既有图片校验与推理图准备使用线程卸载避免阻塞事件循环，因此外层工作流截止仍能
及时取消正在等待的 Provider，并复用原图片清理路径；校验规则、文件边界和 Provider
契约没有变化。

前端在同一输入的提交身份内保存一个随机 idempotency key；timeout、
`network_error`、取消等“服务端是否接收不确定”的重试继续使用该 key。正文变化、
选择新文件或“继续添加”才清空它。key 不由正文、URL、文件或密钥派生，也不写入
日志。

### 前端状态所有权与多结果

Session 创建、对话恢复、新提交、SSE 回调和权威结果读取统一受 operation generation
管理。恢复完成前输入处于 recovering 门禁；开始新 Run 会先取消唯一 SseClient
连接，组件卸载或 generation 变化后迟到响应无权更新状态。

结果状态由全部 `collections` 汇总，页面逐项显示状态、确认字段、缺失项与不确定
项；修改、撤销和恢复都携带用户所选 item 的 id/version，不再隐含操作首项。没有
加入 M1-4 的收藏库、分页、搜索、完整详情或候选选择。主输入和快速编辑字段拥有
稳定 name/autocomplete，继续添加与补充文字会把焦点返回主 textarea，失败消息
只由失败卡的 live region 朗读。

### 修复后验证

- 后端：`pip check`、Ruff、严格 mypy 通过；完整默认离线回归
  `1571 passed, 11 skipped, 2 deselected`；core `120 passed`；迁移
  `23 passed`；配置真实临时 PostgreSQL 后 `-m postgresql` 为
  `11 passed, 1573 deselected`。
- 前端：`npm audit --omit=dev` 为 0；lint、typecheck、build 通过；Vitest
  `34 passed`。
- 浏览器：Playwright `14 passed`，其中真实 FastAPI + 离线 Fake Provider 完成
  首次进入、提交、识别、权威结果、修改、撤销、恢复与继续添加。
- Compose：干净快照、不使用 `--env-file`；PostgreSQL、Demo PostgreSQL、API、
  Worker 全部 healthy，API/Worker restart count 为 0。无模型导入从 queued
  收敛到 `failed / MODEL_PROVIDER_NOT_CONFIGURED`；API 与独立 Worker 进程使用
  离线 Provider 完成一条 `content.import`；SSE 从 `Last-Event-ID: 1` 重放的
  sequence 全部大于 1；短租约双 Worker 执行计数为 1，第二 Worker 未领取。

本次没有新增迁移，Alembic 仍只有 `20260727_0011` 一个 head。删除/收敛的旧路径
包括 Worker 启动时无条件要求模型、每次前端提交无条件生成新 key、Session 恢复与
新提交相互独立写状态，以及所有收藏操作默认指向首项。仍只有一套 Provider 接入、
JobQueue、Worker、AgentRunner、ToolRegistry、TextCollectionWorkflow、API Client、
SSE Client、幂等边界和 Undo/Restore 写服务。

### 未关闭风险与主控复测

- 请独立复测 Worker 在 SIGTERM、数据库瞬时异常和超过 60 秒的真实 Handler 下停止
  心跳/恢复行为，以及多 Worker 长时间运行时的数据库负载。
- 请复测浏览器真实 PostgreSQL 环境中的刷新恢复、网络响应丢失后同 key 重试、
  多收藏混合状态与逐项版本冲突。
- 当前浏览器矩阵仍限 macOS/Chromium；Node 20/22、Windows/Linux、
  Safari/Firefox 未覆盖。M1-3 继续标记“待主控验收”。

## 多收藏并发状态覆盖 P1 修复

修复基线为 `da60a6db0cdf450f1dc4630166e44f426d24eed1`。本次没有修改 HTTP
契约、后端、数据库或迁移。

旧 `replaceCollection` 从事件处理器闭包读取整份 `result`，再用该旧快照调用
`setResult(next)`；因此不同收藏的并发响应反序完成时，后响应会把先完成项恢复为
旧值。该路径已删除。唯一替换入口现在使用函数式
`setResult(current => ...)`，在 React 提供的最新 current 上只映射目标 item。

每个收藏请求发起时记录既有 operation generation、当前结果 trace id 和 collection
id。响应必须仍属于该 generation，服务端返回 item id 必须等于请求 item id，
函数式 updater 中的 current trace 必须一致且仍包含该收藏，才允许替换。继续添加
和新 Run 已经递增同一个 generation，因此旧成功不会恢复旧结果，旧失败也不会写入
新 Run 的 feedback。不同收藏的 updater 可以按任意顺序组合；同一收藏仍完全依赖
请求中的 `expected_version` 和现有服务端冲突边界。

结果状态标签由最新 `result` 纯计算用于显示；没有在 React state updater 内调用
其他 setState，也没有增加第二份结果状态、API Client、Mutation Manager、收藏写
服务、版本校验、全局禁用或人工顺序延迟。

修复后前端 lint、typecheck、build 和 `npm audit --omit=dev` 均通过；Vitest
`38 passed`，新增 4 项覆盖两种 A 修改/B 撤销反序、继续添加后的迟到成功及新 Run
后的迟到失败。既有多收藏逐项修改/撤销/恢复、输入变化与不确定网络失败的
idempotency key 回归继续通过。未修改后端，按要求只运行 M1-3 聚焦契约，
`7 passed`。M1-3 继续为“待主控验收”。

## 最终主控验收

主控确认最终修复提交 `f761c9dcdca11ec9b296c7f1638ad9bfe04a8275` 线性继承
阶段基线，并将阶段分支纯快进集成到 `main`。独立快照中前端 lint、typecheck、
build、生产依赖 audit、Vitest `38 passed` 和 Playwright `14 passed`；M1-3 后端
契约 `7 passed`，Alembic 唯一 head 为 `20260727_0011`。合并后 M1-3 契约与迁移
`30 passed`，前端 Vitest `38 passed`，lint 通过。

主控实际浏览器使用真实 FastAPI 与离线 Fake Provider 复核提交、权威结果、撤销和
恢复，控制台无 warning/error。上一轮多收藏反序和跨 Run 迟到响应 P1 已关闭；
当前无未关闭 P0/P1。验收过程未读取 `.env`，未调用真实模型、地图、网页或付费
API，也未实现 M1-4。M1-3 正式完成，当前允许开始 M1-4 收藏库与地点消歧。
