# M1-5 计划生成、调整和确认交接

状态：**待主控验收**

## 交付范围

M1-5 已在既有规划领域服务、JobQueue、Worker、AgentRun/SSE、Demo Session、
CSRF 和统一前端 Client 上形成离线可验收闭环。没有新增第二套规划器、规则引擎、
Approval 服务、任务状态机、Provider、AgentRunner、ToolRegistry、API Client 或
前端全局状态。

正式 `/plans` 支持时间和活动范围、预算、节奏、交通、包含/避开条件及仅收藏模式；
生成前先展示条件确认卡。提交后返回统一 202 Job 契约，通过原 SSE Client 展示进度，
断线、刷新和重新进入均回读后端权威状态。计划结果展示主方案、备选方案、时间光轨、
费用、路线、收藏/外部来源和风险。

收藏不足且存在明确的包含目标时，既有 `ExternalPlaceSupplementService` 可产生一次性
外部地点授权。批准、拒绝、过期和重复决定由正式 Approval 记录约束；外部地点始终
标记为“高德补充 · 未收藏”，确认计划不会创建收藏。

## API 与状态

- `POST /api/v1/plans`：创建首版计划并返回 202。
- `GET /api/v1/plans`：每条计划链只返回最新版本。
- `GET /api/v1/plans/{plan_id}`：读取指定不可变版本、完整版本索引及相关授权。
- `POST /api/v1/plans/{plan_id}/adjustments`：解析明确的自然语言修改，保留未修改
  条件并创建子版本，返回 202。
- `POST /api/v1/plans/{plan_id}/confirm`：只确认用户明确指定且仍为当前的 draft。
- `POST /api/v1/approvals/{approval_id}/decision`：批准或拒绝一次外部地点补充。

版本状态为 `generating / waiting_approval / draft / confirmed / superseded / failed /
cancelled`。每个版本都有独立 trace 和幂等键。旧任务只能完成其绑定版本，状态条件
更新阻止重复或迟到任务重写已完成版本；列表和确认只认版本链的最新项。未来执行
入口必须通过 `require_confirmed_for_execution`，本阶段没有实现导航、日历或其他
M1-6 动作。

## 数据库

新增单一迁移 `20260728_0012`，直接继承 `20260727_0011`：

- `plans`：正式保存 owner、root/parent、version、operation、status、trace、
  idempotency、确认时间和错误状态；约束与草案快照使用 JSON。
- `plan_items`：保存方案位置、时间、来源类型和展示快照。
- `approvals`：保存 owner、动作、目标版本、外部需求身份、状态、过期和决定时间。

版本链、唯一版本、每条链最多一个 confirmed、确认幂等、跨用户外键和 Approval
形状均有数据库约束。迁移 upgrade、current、check 及 downgrade/upgrade 往返通过，
Alembic 唯一 head 为 `20260728_0012`。

## Worker 与规划复用

生成 Handler 注册在原 `JobWorker`，任务类型为 `plan.generate`，并继续使用原
Job lease、恢复和 AgentRun 事件。计划任务 `max_attempts=1`，不会隐式自动重试。
`ExistingPlanServicesExecutor` 依次组合：

1. `StructuredCollectionRetrievalService`
2. `ExternalPlaceSupplementService`
3. `PlanDraftService`

`MapPlanFactResolver` 只获取并标准化天气、路线、可用性和停留输入；确定性筛选、
排序、预算、时间窗、路线校验和主备方案仍由原领域服务完成。真实地图适配器只有在
运行时显式配置后才注册；本阶段开发和验证没有读取本机 `.env`，也没有调用真实
模型、地图、网页或付费 API。

## 前端与可访问性

页面以移动端为主，复用原 App Shell、视觉 token、API Client 和 SSE Client。
operation generation、AbortController 和 SSE cancel 共同拒绝旧响应覆盖新版本。
表单从首次实现即包含未保存离页提示、显式 autocomplete、44px 触控目标、键盘焦点
和 reduced-motion 支持；授权与确认是两个明确分离的操作。加载、空、错误、停止
等待、重试入口及权威恢复均有可见状态。

前端设计遵循现有“纸面网格、湾绿色、荧光节点和宋体标题”的视觉语言；时间光轨
采用小型纵向轨道而非复制 UX 原型结构。

## 验证结果

- 后端：pip check、Ruff、mypy 通过。
- 后端完整离线回归：`1585 passed, 11 skipped, 2 deselected`。
- M1-5/规划聚焦封网复测：`177 passed`；临时 pytest 插件位于仓库外并封锁 DNS、
  `connect`、`connect_ex` 和 `create_connection`，完成后已删除。
- 迁移专测：`23 passed`；唯一 head、current、check 和往返均通过。
- 前端：lint、typecheck、build 通过；Vitest `58 passed`。
- Playwright：`25 passed`，覆盖 320px 移动端条件确认、刷新后的权威计划、费用、
  路线、来源、触控目标与键盘确认。
- 生产依赖 audit：0 个漏洞；`npm ci` 报告的 9 个 high 均来自开发依赖树。

## 复杂度与已知风险

- 规划业务仍只有 `PlanDraftService` 一套实现；新增应用服务负责持久化、排队和版本
  生命周期，不复制候选筛选或预算规则。
- Approval、Job、Run/SSE、Session/CSRF 和前端 Client 均为原实现扩展。
- 未增加测试专用生产分支、样本白名单、重复 DTO 或前端后端规则镜像。
- 当前事实解析器只把拥有正式 exact PlaceTarget 的 active Place 作为地图动态事实
  输入；Event 和任意分店继续由原检索服务保守排除或要求验证，不猜测正式地点。
- 没有真实地图配置时 Worker 不注册地图计划 Handler；离线验收通过注入既有
  `MapProvider` 边界的 Stub/Fixture 执行。真实 Amap 联调留待用户单独授权。
- 当前无已知未关闭 P0/P1；阶段状态保持“待主控验收”。

## 范围声明

未实现 M1-6 的 iCalendar、导航执行、完成反馈，也未实现 M1-7“我的”、记忆和数据
控制；没有分享、提醒、微信、云部署、自动收藏外部地点、自动确认或多城市计划。
