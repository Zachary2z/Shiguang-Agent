# M1-5 计划生成、调整和确认交接

状态：**待主控验收**

## 本次主控缺陷修复

本轮最后修复线性继承候选 `2646f1d70248bff3b59cd9585b78c5f7ce165fa6`，不改写
历史、不合并或推送，也不开始 M1-6。

- `SqlAlchemyPlanRepository` 的 DML 行数统一通过仓库既有
  `execute_dml_rowcount` 获取，失败候选的 3 个 strict mypy 错误已消除。
- 创建和调整仍只使用现有 AgentRun、JobQueue 与 Worker。Job 创建异常或取消且按
  trace 确认没有 Job 时，补偿删除仍为 generating 的 Plan 和 queued AgentRun；
  补偿自身一次瞬时失败会重试。原幂等键随后可安全重用、同请求可重放，不留无 Job
  的 generating Plan 或 AgentRun。
- 生产自然语言短语正则已删除。唯一 `PlanAdjustmentParser` 通过既有
  `ModelProvider` 和严格 JSON Schema 生成最小 `PlanConstraints` patch；未提及
  字段保持不变，完整约束最终只验证一次。
- `MapPlanFactResolver` 先复用正式收藏资格规则完成确定性筛选，再读取有限候选的
  天气和路线。支持 active exact Place、准确时间且带 exact 正式地点的 Event，以及
  在本次计划城市/范围内由既有 `PlaceMatchingService` 解析并固定具体 POI 的
  any_branch。
- 单次计划最多选择 6 个事实候选，路线 Provider 调用硬上限为 48。其他城市、
  archived、pending、时间冲突、范围/包含/排除不符的收藏不会触发路线调用。
- 未配置 MapProvider 时，创建在持久化前返回安全 503，不产生 Plan、Run 或 Job；
  调整同时要求既有 ModelProvider。
- `/plans` 对已有 draft/confirmed 计划提供“新建计划”，创建新的 root；最新调整
  failed/cancelled 时仍展示版本索引，可读取上一份草案。显式确认、未确认不执行、
  确认外部地点不自动收藏的边界不变。
- any_branch 在单次计划中只由 `MapPlanFactResolver` 调用一次既有
  `PlaceMatchingService`；解析出的 POI 按 `collection_item_id` 冻结在
  `CollectionPlanningFacts.resolved_poi`。`StructuredCollectionRetrievalService`
  不再持有 matcher，也不会二次搜索，草案来源使用同一 POI 和同一查询时间。失败
  原因也冻结在同一事实中：Provider 超时/不可用、正常无结果和有结果但证据不足
  分别保持 `BRANCH_PROVIDER_FAILED`、`BRANCH_NOT_FOUND` 和
  `BRANCH_EVIDENCE_INSUFFICIENT`。
- `PlanAdjustmentParser` 使用 `Settings.extraction_structured_output_mode()` 和公共
  `structured_response_format`。百炼默认明确请求已验证的 `json_object`，schema
  写入 Prompt，返回后仍由严格 Pydantic 契约校验；没有探测、fallback 或重试。
  `PlanAdjustmentPatch` 不接受 `location_intent`、`Coordinate` 或 `ActivityArea`，
  发送给模型的当前约束也排除 origin。唯一 Parser 在新版本持久化前运行；精确地点
  或活动范围调整返回 `PLAN_ADJUSTMENT_UNSUPPORTED` 并提示新建计划，不留下已知
  必失败的 Plan、AgentRun、幂等键或 Job。Worker 只消费已验证的约束，不重复解析。
- Event 仍是单一 Event 收藏。文本/截图保存后，经同一 `PlaceMatchingService`、
  `PlaceCandidateSnapshot` 和 `PlaceTargetSelectionService` 产生地点候选；只有
  用户明确选择一个 exact POI 后才可进入计划，未选择、日期不完整或仅日期 Event
  继续被保守排除，Event 仍禁止 any_branch。只有既有城市提示解析边界确认深圳时
  才发起深圳候选搜索；广州或城市待确认 Event 的地图搜索调用为 0。“以上都不是”
  会清除候选快照并回到 `pending_details`，保留 Event、准确时间和来源，支持幂等
  重放与并发版本冲突。
- 事实候选不再按随机 UUID 排序。当前在确定性资格过滤后，仍按收藏仓储
  `created_at, id` 稳定顺序取得最多 6 条，路线调用硬上限为 48；这不等同于最终
  规划排序，最终候选仍由既有 `PlanDraftService` 排序。历史版本标签已修正为
  “历史版本”，不会再显示“当前版本”。

## 唯一实现与数据模型

规划仍只由现有 `StructuredCollectionRetrievalService`、
`ExternalPlaceSupplementService` 和 `PlanDraftService` 负责；分店解析继续使用
`PlaceMatchingService` 和唯一 MapProvider。确定性排序、预算、时间窗和硬约束没有
移入模型或前端。

计划 API 仍为：

- `POST /api/v1/plans`
- `GET /api/v1/plans`
- `GET /api/v1/plans/{plan_id}`
- `POST /api/v1/plans/{plan_id}/adjustments`
- `POST /api/v1/plans/{plan_id}/confirm`
- `POST /api/v1/approvals/{approval_id}/decision`

版本继续使用 `generating / waiting_approval / draft / confirmed / superseded / failed /
cancelled`。每个版本有独立 trace 和幂等键，旧任务只能条件更新其绑定版本；列表、
刷新、SSE 恢复和确认都读取权威数据库状态。未来执行入口必须通过
`require_confirmed_for_execution`，本阶段没有实现任何执行动作。

数据库现有 `20260728_0012` 保存 plans、plan_items、approvals。本修复新增单一向前
迁移 `20260728_0013` 允许 Event 保存 exact 正式 PlaceTarget，并将 exact POI 收藏
去重索引限定为 Place。本轮新增单一向前迁移 `20260728_0014`，直接继承 `0013`，
允许 Event 保存用户选择所需的候选快照；Event 仍不能保存 any_branch。Alembic
唯一 head 为 `20260728_0014`。

## 产品示例

离线 Fake Provider 对以下输入：

> 不要咖啡店，换成适合散步的地方，其他不变。

输出严格 patch：移除被替换的咖啡店包含目标，加入散步地点目标，并明确排除咖啡店；
时间、预算、活动范围、节奏、交通、`collection_only` 及其他未提及字段保持不变。
生产代码没有中文短语表或正则兜底。

## 前端与真实离线验收

移动端 `/plans` 继续复用统一 App Shell、API Client、SSE Client 和现有组件语言。
操作 generation、AbortController 和 SSE cancel 拒绝迟到响应；条件表单保留未保存
提示、autocomplete、键盘焦点和触控目标。

新增 Playwright 流程不 mock `/api/v1/plans`、Job、SSE 或结果接口，真实穿过
Next.js、FastAPI、JobQueue、Worker、临时 SQLite 与 StubMapProvider，覆盖：

1. 创建 root 计划并由 Worker 完成；
2. SSE 进度与权威结果恢复；
3. 自然语言调整并创建 V2；
4. V1/V2 切换与明确确认；
5. 新建第二份独立 root 计划；
6. 第二条链请求修改精确地点时收到可恢复提示，继续停留在 V1 且不产生 V2。

## 验证结果

- `pip check`、Ruff：通过。
- strict mypy：`126 source files`，0 错误。
- 后端完整离线：`1603 passed, 13 skipped`。
- 迁移专测：`23 passed`；upgrade/current/check、downgrade/upgrade 和唯一 head
  均通过。
- 仓库外 DNS/socket 封锁插件：非真实全集
  `1603 passed, 11 skipped, 2 deselected`。
- 前端 lint、typecheck、build：通过；Vitest `60 passed`。
- Playwright：`26 passed`，其中 1 条为上述真实计划栈闭环。

仓库默认开发数据库仍停在旧 revision，直接对其运行 `alembic check` 会正确提示未
升级；没有修改该用户数据库。仓库外临时数据库已完成 `upgrade head → current →
check`，结果为 `20260728_0014 (head)` 且无待生成操作。

## 复杂度、安全与范围

原生产短语解析路径和 Worker 内重复调整解析路径已删除。没有新增第二套规划器、
规则引擎、Plan DTO、Approval 服务、Job/Worker/SSE 状态机、Provider、Matcher、
Parser、排序器、AgentRunner、ToolRegistry、API Client 或前端全局状态；地图事实层
只负责有限、可测试的 Provider 事实读取。

离线 QA 显式使用 `_env_file=None`，未读取本机 `.env` 内容；真实模型、地图、网页
及其他外部/付费 API 调用为 0。计划表单 input/select/checkbox 已具有稳定 `name`。
未实现 iCalendar、导航执行、完成反馈、“我的”、记忆、分享、提醒、微信、云部署、
多城市或自动收藏外部地点。当前无已知未关闭 P0/P1；剩余 P2 是高基数收藏在事实
读取阶段仍按稳定仓储顺序截取前 6 个合格候选，可能使更晚出现但软偏好更高的候选
未进入最终排序。本轮按要求不新增第二套预排序；后续应扩展唯一规划排序边界解决。
阶段保持“待主控验收”。
