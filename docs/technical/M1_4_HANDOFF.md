# M1-4 收藏库与地点消歧交接

状态：**收藏详情保存 P1 修复完成，待主控复验**

## 范围与结论

M1-4 在既有收藏、地点目标、候选快照、Session 和写入边界上完成，没有新增第二套
Repository、写服务、候选评分/选择、Undo/Restore、API Client 或前端全局状态。
其他城市收藏可以查看和编辑；只有状态为 `active`、正式城市为 `shenzhen` 且拥有
可规划 PlaceTarget 的 Place 才标记为可进入当前深圳计划。城市待确认、
`pending_selection`、`pending_details` 和非深圳收藏均明确返回排除原因。

## API 契约

- `GET /api/v1/collections`
  - 参数：`search`、`city_code`、`city_group`、`kind`、`status`、`tag`、
    `sort`、`page`、`page_size`
  - `city_group`：`shenzhen | other | pending`
  - 默认不返回逻辑删除项；显式 `status=deleted` 才读取回收状态
  - 搜索覆盖名称、城市线索、行政区、地址、商圈、地标、地铁站和标签
  - 返回既有 `items/page/page_size/total` 分页结构
- `GET /api/v1/collections/{item_id}`：返回允许公开的收藏详情和来源摘要。
- `PATCH /api/v1/collections/{item_id}`、`DELETE`、`POST .../restore`：继续复用
  `CollectionWriteService` 和既有 `expected_version`/恢复边界。PATCH 的唯一公开
  请求模型会把 JSON array 递归规范化为领域不可变 tuple，再交给唯一
  `CollectionItemPatch`；该步骤不转换标量，也不复制字段或标签校验。
- `GET /api/v1/collections/{item_id}/poi-candidates`：返回持久化快照的公开候选
  字段、当前版本和快照指纹；不返回坐标、评分证据或供应商原文。
- `POST /api/v1/collections/{item_id}/poi-selection`：输入
  `expected_version`、`snapshot_fingerprint`、`idempotency_key` 和
  `choice=candidate | none_of_above`，复用 `PlaceTargetSelectionService`。
  HTTP 层不再挑选某一条来源；服务在用户隔离范围内确定关联来源，并在同一事务
  中处理选择、收藏合并和全部来源迁移。

所有读取和写入都以当前浏览器 Session 的 `user_id` 为首要约束；跨用户的收藏、
来源和候选统一表现为不可见。

## 查询、排序与分页

筛选、搜索、排序、计数和分页集中在
`SqlAlchemyCollectionRepository.query_collection_items`。查询先应用用户隔离和
全部筛选，再执行同一条件的 `count` 与页面查询。排序始终追加不可变 `id`
作为决胜键，因此同值记录不会在页间重复、遗漏或漂移。前端只编码 URL 参数，不
复制城市分类、规划资格或筛选业务判断；搜索采用显式提交。

## 候选选择语义

- 单候选和既有已选择状态继续遵守原 PlaceTarget 服务契约。
- 多候选必须由用户明确选择具体 `provider + poi_id`；候选卡展示名称、分店、
  行政区、商圈、地址和 POI 类型。
- “以上都不是”不会猜测或采用第一项；原收藏保留并转为 `pending_details`，可继续
  编辑补充。
- 同一幂等键和同一载荷稳定重放；同键不同载荷冲突。过期版本试图改变已确认选择
  返回版本冲突。
- 选择具体候选或任意分店时，如果命中既有正式收藏，原待选收藏的全部
  `CollectionSource` 关联都会在原选择事务内幂等补到目标收藏；既有目标来源不变，
  跨用户来源不可读取或迁移。

## 前端状态与可访问性

正式 `/collections` 使用 M1-2 唯一 API Client、Token 和 App Shell。搜索、城市、
类型、状态、页码及打开的详情写入 URL，刷新、前进和后退可恢复。列表与详情分别
使用 generation/AbortSignal，迟到响应不能覆盖新查询或新详情版本。页面覆盖首次
加载、空、失败重试、分页、编辑、候选选择、删除和恢复；React 默认转义不可信
文本。详情打开后焦点进入关闭按钮，支持 Escape，交互目标保持 44px，并遵守
`prefers-reduced-motion`。

P1 修复后，PATCH、DELETE、restore 和候选选择统一使用绑定
`detail generation + collection id` 的详情操作归属检查。关闭详情、切换详情以及
URL 前进/后退都会使旧操作失效；迟到成功、失败和清理均不能修改新详情、
feedback、saving 或候选状态。若候选选择合并到不同收藏，仍属于当前操作时只替换
URL 的 `item`，保留搜索、筛选和页码，并加载服务端返回的正式收藏；同 ID 的
“以上都不是”不触发额外导航。

收藏详情保存 P1 的根因是 FastAPI 已将 JSON array 解码为 Python `list`，而嵌套的
`CollectionItemPatch` 使用 strict 模式并以 tuple 表达不可变集合；原前端组件测试
直接 mock 了成功响应，因此没有经过真实请求 DTO。修复只位于
`CollectionPatchRequest.changes` 这一公开 JSON 边界：统一转换 JSON 容器后继续由
原领域契约验证未知字段、成员类型、标签规则和字段组合。前端仍发送正常 JSON
array，没有省略或伪装 `tags`。

## 数据库与迁移

未新增迁移。现有 `collection_items` 已包含版本、逻辑删除/恢复状态、
`place_candidate_snapshot`、扁平化正式 `poi_city_code` 和 PlaceTarget；
`collection_sources` 已表达来源关系，因此 M1-4 没有新的持久化事实。Alembic
继续保持单一 `20260727_0011` head，并由迁移往返测试验证。

## 验证

- M1-4 真实 ASGI 契约：6 项；地点选择与迁移组合：66 项。
- 前端 Vitest：54 项，其中 M1-4 组件 16 项；新增覆盖真实 PATCH body、保留已有
  标签修改标题、标签修改/清空和 422 不伪装成功；原保存迟到成功/失败，
  删除、恢复和候选选择迟到，合并后 URL/详情/刷新一致，以及同 ID 不导航。
- Playwright：23 项；新增真实 FastAPI + FakeProvider 收藏详情保存链路，覆盖已有
  标签、保存成功及关闭重开后的持久化一致性。原 M1-4 8 项继续覆盖
  320/390/768/1024/1440px、URL
  历史、恶意文本、候选恢复路径、删除恢复、键盘焦点和 reduced motion。
- 后端完整离线回归：`1578 passed, 11 skipped, 2 deselected`；仓库外插件封锁
  DNS、`connect`、`connect_ex` 和 `create_connection` 后相关回归 `72 passed`。
- pip check、Ruff、mypy、前端 lint/typecheck/build、生产依赖 audit 均通过。
  全部使用 Fake/Fixture 和本地临时数据库，不调用真实模型、地图、网页或付费 API。

## 风险与冗余检查

- Event 当前没有正式 POI 城市事实，因此保守归入“城市待确认”，可管理但不进入
  深圳计划；后续若产品确认 Event 正式城市来源，应扩展统一领域事实而非根据
  `city_hint` 猜测。
- SQLite 标签查询使用 `json_each`，PostgreSQL 使用 JSON 文本匹配；其公开语义
  相同，后续规模化可在不改变 Repository 契约的前提下增加 PostgreSQL JSON 索引。
- 本阶段没有新增迁移、全局状态框架、前端业务筛选、候选评分、Undo/Restore 或
  Session/CSRF 实现；没有样本白名单、供应商原文或敏感字段输出。
- P1 修复只增加一套详情操作归属机制，并扩展既有
  `PlaceTargetSelectionService`；没有新增 Mutation Manager、合并服务、来源迁移
  路径、Repository、幂等记录或来源模型。
- 收藏保存修复没有新增 `CollectionItemPatch`、编辑服务、标签校验器或字段级转换
  分支；仍只有一个 PATCH 路由和一个 `CollectionWriteService`。严格成员类型、
  未知字段、版本冲突、用户隔离及原三个 P1 修复均保持。
- 未实现 M1-5、真实登录、分享、提醒、微信、日历或“我的”业务。
