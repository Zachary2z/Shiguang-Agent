# M1-7 我的、记忆和数据控制交接

状态：**待主控验收**

## 基线与提交

- 指定基线：`c4d23b716af1426054705912ed0d7067e95e11e4`。
- 开发分支：`codex/m1-7-memory-data-control`。
- 实现提交：`78543b611d564a83dab0e4d601619706e366369e`。
- 隔离补测提交：`1cf4a1b06b9a746a7baff6b77a460bacb430ee4d`。
- 文档提交将在本文件和 `docs/DEV_STATUS.md` 完成后创建，完整分支 HEAD 由最终交付
  返回。
- 开始时 `main`、`origin/main` 和工作区 HEAD 均精确等于指定基线，工作区干净，
  Alembic 唯一 head 为 `20260728_0015`，M1-7 是唯一允许阶段。

## 产品行为与领域边界

- 新增唯一结构化 `Memory` 聚合，记录内容、类型、结构化值、来源、确认状态、
  置信度、有效期、创建/更新时间、停用/删除时间、最后使用时间和乐观版本。
- 正式 Memory 表只允许 `confirmed`。M1-6 的推断建议继续保留在原反馈审计中，
  确认后才创建 Memory；拒绝只保存决定，不创建 Memory，同一反馈证据不再出现。
- 显式“记住/以后”写入要求明确授权。常用区域还必须声明为粗粒度；精确或未授权
  位置请求在公开写边界拒绝。Memory 类型不包含天气、票价、闭馆或排队等动态事实。
- 临时条件仍只存在于既有 `PlanConstraints`，不复制进 Memory。检索时只读取已确认、
  未过期、未停用、未删除的 Memory；删除或停用提交后，下次读取立即排除。
- 正向/负向偏好进入既有 `StructuredCollectionRetrievalService` 的软排序分值，
  不伪装成硬约束；节奏偏好在既有计划执行组合边界生成请求级有效条件，不持久化为
  本次临时约束。既有 `PlanDraftService` 继续承担唯一稳定排序。
- 只有主方案实际选择的候选和实际采用的节奏才写 `memory_plan_usages`。详情可查看
  使用依据、计划 ID 和时间；未实际影响方案的 Memory 不制造使用记录。

## 数据库与迁移

线性迁移 `20260728_0016_memory_data_control.py` 直接继承 `20260728_0015`，唯一
 Alembic head 为 `20260728_0016`。新增：

- `memories`：唯一长期记忆；
- `memory_suggestion_decisions`：建议确认/拒绝和推断 Memory 的授权依据；
- `memory_operations`：显式创建、修改、停用、删除的用户作用域幂等结果；
- `memory_plan_usages`：Memory 对计划的实际影响。

所有关系通过 `user_id` 复合外键绑定反馈、计划和 Memory 所有权。写入使用用户作用域
幂等键、请求指纹、数据库唯一约束、行锁、expected version 和单事务提交；失败会显式
回滚。迁移有数据时拒绝破坏性降级。PostgreSQL QA 删除了复合主键上重复的唯一约束，
模型、迁移和数据库反射保持一致。

## 正式 Application/API 入口

应用层只有一个 `MemoryService` 负责用户控制写入，一个
`MemoryPlanningService` 负责有效读取和实际使用记录；仓储只有
`SqlAlchemyMemoryRepository`。没有第二套 Memory Store、偏好服务或计划检索。

新增 API：

- `GET /api/v1/memories`
- `POST /api/v1/memories`
- `GET /api/v1/memories/{memory_id}`
- `PATCH /api/v1/memories/{memory_id}`
- `DELETE /api/v1/memories/{memory_id}`
- `GET /api/v1/memory-suggestions`
- `POST /api/v1/memory-suggestions/{suggestion_id}/decision`
- `GET /api/v1/data-export.json`

全部使用当前浏览器 Session 的 `user_id`，客户端不能提交所有者。导出是 allowlist JSON，
只包含当前用户收藏、最新计划和已确认 Memory；不输出 Cookie、Token、幂等键、密钥、
原始内部审计或服务端配置，并返回 `private, no-store`、`no-cache`、`nosniff` 和附件
响应头。

## Web/H5 M07

`/me` 复用 App Shell、`apiClient`、现有设计 token 和组件内局部状态，实现：

- 待确认建议及其证据，确认或拒绝；
- 记忆列表、详情、来源、有效期、最后使用和影响计划；
- 修改、停用/启用、两步删除；
- 当前用户私有 JSON 下载；
- “主动提醒：尚未实现 · 已关闭”的禁用状态，不制造已开启假象。

列表、详情和写操作分别拥有 generation 所有权。切换记忆、刷新或卸载后，迟到详情、
写响应及其 `finally` 不能覆盖更新的选择、Memory 版本或 busy 状态。原生按钮、表单
和链接支持键盘；390px M07 E2E 和既有 320–1440px 基础测试均无横向溢出，交互目标
保持至少 44px。

## 测试结果

后端：

- `pip check`、Ruff、strict mypy（135 个源文件）：通过。
- M1-7 契约：`6 passed`；覆盖显式 Memory、建议确认/拒绝、串行/并发幂等、同键
  不同载荷、版本冲突、事务回滚、跨用户/建议/计划组合、过期/停用/删除、来源与
  使用记录、敏感区域和私有导出。
- 计划检索/排序聚焦与 M1-7 合计回归通过；有效确认 Memory 进入唯一检索分值，
  停用 Memory 不参与，Memory 分值在稳定排序边界生效。
- 非真实全集：`1625 passed, 15 skipped, 2 deselected`。
- SQLite 迁移：`24 passed`；`alembic heads` 为 `20260728_0016 (head)`。
- 一次性本地 PostgreSQL 16：Memory 并发/所有权及迁移往返 `2 passed`；容器已
  移除。
- 仓库外 pytest 插件封锁 DNS、解析、`create_connection`、`connect`、
  `connect_ex`、`sendto` 后，聚焦 `103 passed`，非真实全集再次
  `1625 passed, 15 skipped, 2 deselected`。

前端：

- lint、typecheck、build：通过。
- Vitest：`69 passed`，其中 M07 `4 passed`，覆盖加载、建议决定、修改/停用/
  删除、提醒关闭和迟到详情隔离。
- Playwright：`27 passed`，包含 M07 移动端、刷新恢复、键盘焦点、导出和无横向
  溢出；既有真实离线计划闭环继续穿过 Next.js、FastAPI、临时数据库和 Worker。

## 安全、唯一性与风险

- 未读取 `.env`，未调用真实模型、地图、网页或付费 API，未读取或提交真实用户
  数据、数据库、导出文件或缓存。
- 没有 Markdown/文件式 Memory、关键词意图猜测、自动确认、动态事实记忆、临时
  条件复制、第二套 Repository/Provider/Planner/API Client/前端状态框架。
- 未实现 M1-8 分享、微信、主动提醒、云部署、账号注销或后续阶段。
- 当前无已知未关闭 P0/P1。保留既有 M1-5 高基数候选截断 P2：事实读取仍先按稳定
  仓储顺序截取有限候选，较晚但软偏好更高的收藏可能无法进入排序；后续只能在唯一
  检索边界内收敛。
- M07 Playwright 使用状态化 API route 验证 UI 竞态与移动交互；API/数据库行为由
  FastAPI ASGI 契约、完整离线回归和 PostgreSQL 专测独立证明。没有为测试增加生产
  白名单、样本特例或重复业务校验。

## 主控验收建议

1. 复核 `20260728_0016` 在 SQLite/PostgreSQL 的线性迁移、复合所有权和降级保护。
2. 并发重放同 key 同载荷应一真一假，同 key 不同载荷应冲突，事务失败后不留部分
   Memory 或 operation。
3. 确认拒绝建议不建 Memory；停用、删除、过期后下一次有效读取立即排除。
4. 从 M07 查看来源和影响计划，验证刷新和切换后的迟到响应不覆盖新状态。
5. 检查导出 allowlist、当前用户作用域和 `no-store` 响应头。

阶段保持“待主控验收”；不合并 main、不推送、不开始 M1-8。
