# M1-7 我的、记忆和数据控制交接

状态：**已通过主控验收**

## 基线与提交

- 指定开发基线：`c4d23b716af1426054705912ed0d7067e95e11e4`。
- 开发分支：`codex/m1-7-memory-data-control`。
- 初始实现：`78543b611d564a83dab0e4d601619706e366369e`。
- 隔离补测：`1cf4a1b06b9a746a7baff6b77a460bacb430ee4d`。
- 初始交接：`2342cfef31cb0962cb4f212f6bfea68a01d4883e`。
- 主控验收缺陷修复：`aa21144f83d536426578ba333ab449121a881289`。
- 第一轮修复交接：`f3cf6b165f00afb752fedf08660c440d5d2699e6`。
- 第二轮主控验收缺陷修复：`1baa982dbec8d8dc2a8d7c68dbd34b4506de32a8`。
- 第三轮主控验收缺陷修复：`90b1ec1600b76c154679ee1c070eff7847303c8e`。

开始和修复门禁均满足：main 与 origin/main 保持
`c4d23b716af1426054705912ed0d7067e95e11e4`，修复从指定 HEAD 追加；没有 amend、
rebase、合并或推送。

## 最终产品行为

- 唯一结构化 `Memory` 聚合记录内容、类型、结构化值、来源、确认状态、置信度、
  有效期、创建/更新时间、停用/删除时间、最后使用时间和乐观版本。
- 正式 Memory 只允许 `confirmed`。计划的完成、部分完成、未完成和自由文本原因只
  是反馈事实，不自动生成 relaxed 或其他长期偏好。现有反馈入口增加可选的结构化
  `preference_candidate`：类型、内容、值和证据必须完整，并原样进入反馈审计；
  没有候选时继续保存 `None`。
- 新结构化候选与 0015 历史候选都只是 pending。M07 必须再次明确提交 Memory
  字段并确认后才创建 Memory；拒绝只保存决定。相同结构化证据之后即使通过反馈更正
  再提交也会被抑制，不重新出现在待确认列表。
- 结构化候选的稳定证据身份由当前用户、来源计划和 NFKC/空白/casefold 规范化后的
  `evidence_summary` 构成，不再使用完整候选 JSON。确认和拒绝都是该证据的终态；
  同一计划更正候选类型、内容或值不会重复询问或创建 Memory，不同计划的独立证据
  不会互相抑制。
- 0015 历史 JSON 中只有 `content/confirmation_status` 的建议继续可读，但统一作为
  中性证据候选。用户确认时必须明确提交 Memory 类型、内容和值；拒绝只保存决定，
  不创建 Memory，同一证据不再出现。
- 显式长期写入要求明确授权。动态天气、价格、闭馆和排队事实不能成为 Memory；
  临时条件仍只存在于唯一 `PlanConstraints`，到期或任务结束后退出规划。
- 常用区域创建和修改复用计划侧唯一 `ActivityArea` 粗区域契约，要求恰好一个明确
  分类的 district 或 area label；服务端生成展示内容和规范 JSON 值。该契约不绑定
  深圳，已覆盖南山区、大学城附近和大鹏新区；origin、经纬度、地址和 POI 字段因
  严格结构直接拒绝。反馈建议不能确认成位置 Memory。
- 有效读取只返回已确认、未过期、未停用、未删除的 Memory；停用或删除提交后，
  下一次计划立即排除。

## 当前请求和计划检索

- 唯一 `PlanConstraints` 使用 `pace_source` 明确区分 `user_request`、
  `system_default` 和 `memory_default`。公开请求明确提交任意 pace（包括 balanced）
  时当前请求优先；只有省略 pace 的系统默认场景，唯一
  `MemoryPlanningService` 才可选择确定性的有效 pace Memory 作为默认。
- 每次生成、调整、重试或审批恢复时，非 `user_request` 节奏先重置为
  `balanced/system_default`，再从本次读取的有效 Memory 确定性选择最新值。没有
  有效 Memory 或有效值就是 balanced 时保持系统默认且不记录 usage；删除、停用、
  过期或被新值替换的旧默认不会从持久化约束继续泄漏。
- 应用 Memory 后得到的仍是同一个 `PlanConstraints` 实例类型；事实解析、收藏检索、
  草案、持久化和公开响应全部使用这份最终有效约束。只有 Memory 实际改变计划输入
  时才附带使用依据；停用、删除或过期记录不会进入候选。
- 正向、负向和常用区域 Memory 只进入既有
  `StructuredCollectionRetrievalService`。任意数量的匹配被归一为负向、无影响、
  正向三档（`-1/0/1`）；正负冲突时负向稳定优先，同档重复 Memory 只保留一个
  确定性依据。
- 既有 `PlanDraftService` 仍是唯一排序器。所有候选同档时不记录虚假依据；只有
  真正参与差异化排序且进入主方案的 Memory 才写 `memory_plan_usages`、计划 ID、
  使用说明和最后使用时间。
- 1000 条匹配 Memory 的回归保持固定有界分值，无 ValidationError、超时、第二检索
  或第二排序器。

## 写入、幂等与事务

- 应用层只有一个 `MemoryService` 负责控制写入，一个 `MemoryPlanningService` 负责
  有效读取和使用记录；仓储只有 `SqlAlchemyMemoryRepository`。
- 显式创建、修改、停用、删除继续使用用户作用域幂等键、请求指纹、
  `memory_operations` 唯一约束、Memory 行锁、expected version 和单事务提交。
- update/delete 在取得包含逻辑删除行的 Memory 行锁后、比较 version 或返回
  NotFound 前再次检查同键重放。删除后的并发请求仍可从 operation 返回原结果。
- 事务失败显式回滚，不留下部分 Memory 或 operation；没有进程锁、重试循环、
  sleep 或第二套幂等服务。

一次性 PostgreSQL 16 测试先持有 Memory 行锁，再启动两个请求，并证明二者都完成
初次重放检查后等待。update/delete 均覆盖：

- 同键同载荷两个成功，`replayed` 一真一假；
- 同键不同载荷冲突；
- 不同键同版本只有一个成功；
- 删除提交后的同键仍可重放；
- operation 和业务版本各写一次。

## 迁移与 API

线性迁移 `20260728_0016_memory_data_control.py` 直接继承已集成的 0015，唯一 head 为
`20260728_0016`。本次没有新增 0017，也没有修改 0015 及更早迁移。0016 表主体保持：

- `memories`：唯一长期记忆；
- `memory_suggestion_decisions`：建议决定和授权依据；
- `memory_operations`：唯一写入幂等审计；
- `memory_plan_usages`：Memory 对计划的实际影响。

全部反馈、计划和 Memory 关系使用 `user_id` 复合所有权。新增迁移回归在 0015 写入
真实旧式建议 JSON，升级 0016 后确认原值无损；公开契约再证明该旧建议可作为中性
候选读取，不伪造缺失类型、值或依据。

正式 API 保持：

- `GET/POST /api/v1/memories`
- `GET/PATCH/DELETE /api/v1/memories/{memory_id}`
- `GET /api/v1/memory-suggestions`
- `POST /api/v1/memory-suggestions/{suggestion_id}/decision`
- `GET /api/v1/data-export.json`

全部使用当前 Session 的 `user_id`。导出是当前用户 allowlist JSON，只包含收藏、
计划和已确认 Memory；不输出 Cookie、Token、幂等键、密钥、内部审计或服务端配置，
并返回 `private, no-store`、`no-cache`、`nosniff` 和附件响应头。

领域导入边界也已收敛：`Memory` 只在验证 `usual_area` 值时延迟引用唯一
`ActivityArea`，模块顶层不再初始化整个 `plans` 包。全新 Python 解释器无需
pytest `conftest` 或预先导入 `app.main` 即可独立执行
`import app.domain.memories`。

## Web/H5 M07

`/me` 继续复用 App Shell、API Client、既有设计 token 和组件局部状态：

- 新反馈建议预填其结构化类型、内容和值并展示证据；历史建议仍显示为中性候选，
  明确补齐类型、内容和值后才能确认；
- M06 和 M07 的 pace 候选值都使用 `relaxed / balanced / packed` 三项选择控件；
  正向、负向偏好仍使用文本值。领域 `PreferenceSuggestion` 与公开反馈请求同时
  执行同一 `PlanPace` 枚举校验，非法 pace 在反馈写入前返回安全 422；
- Memory 列表、详情、来源、有效期、最后使用和影响计划；
- 普通 Memory 修改、全部 Memory 停用/启用和两步删除；
- usual_area 通过“行政区 / 商圈或粗区域”结构化表单修改，和创建共用后端边界；
- 当前用户私有 JSON 下载；
- “主动提醒：尚未实现 · 已关闭”，不制造已开启状态。

同一写入载荷由 ref 保留原幂等键；不确定网络结果继续复用，成功或载荷改变后才换键。
409 同时刷新列表与当前详情。列表、详情和写操作继续使用既有 generation；选择变化、
刷新或卸载后的迟到详情、迟到写响应和 `finally` 都不能恢复旧版本、旧详情或 busy。
原生表单、按钮和链接支持键盘；390px M07 及 320–1440px 基础 E2E 无横向溢出。

本次界面调整遵循现有 token、排版和移动交互，没有引入新视觉系统或状态框架。

## 最终验证

后端：

- `pip check`、Ruff、strict mypy（135 个源文件）：通过。
- 指定 M1-6/M1-7/检索/草案/迁移聚焦：`150 passed`。
- 普通非真实全集：`1641 passed, 15 skipped, 2 deselected`。
- 首次完整运行曾有一个既有图片外层超时取消测试偶发失败；该测试单独立即通过，
  随后普通全集和封网全集均完整通过。
- SQLite 迁移：`25 passed`；Alembic 唯一 head：`20260728_0016 (head)`。
- 一次性 PostgreSQL 16 强制行锁并发及迁移往返：`2 passed`，容器已移除。
- 仓库外插件封锁 DNS、`create_connection`、`connect`、`connect_ex`、`sendto` 后，
  聚焦 `150 passed`；非真实全集再次
  `1641 passed, 15 skipped, 2 deselected`。

前端：

- lint、typecheck、build：通过。
- Vitest：`73 passed`，其中 M07 `8 passed`。
- Playwright：`27 passed`，包含 M07 移动端、刷新、键盘、导出和无横向溢出。

## 安全、复杂度与风险

- 未读取 `.env`，未调用真实模型、地图、网页或付费 API；未读取或提交真实用户数据、
  数据库、导出文件或缓存。
- 没有 Markdown/文件式 Memory、关键词意图猜测、自动确认、动态事实记忆、临时
  条件复制、第二套 Memory Store、Repository、偏好服务、排序器、Provider、API
  Client、进程锁、重试循环或前端状态框架。
- 删除了无产品依据的反馈推断服务；规则分别收敛在既有 Memory 写边界、唯一结构化
  检索和 M07 局部状态，没有生产白名单、样本特例或重复校验。
- 没有实现 M1-8 分享、微信、提醒任务、云部署、账号注销或后续阶段。
- 第三轮四项缺陷已由主控独立复现并确认关闭；当前无未关闭 P0/P1。保留既有 M1-5
  高基数候选截断 P2：事实读取仍先按稳定仓储顺序截取有限候选，较晚收藏可能不进入
  排序；后续只能在唯一检索边界内收敛。

`codex/m1-7-memory-data-control` 已以 `--ff-only` 集成到 `main`，无冲突、merge
commit 或额外生产代码变化。M1-7 正式完成，当前允许开始 M1-8。
