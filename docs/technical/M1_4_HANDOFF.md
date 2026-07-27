# M1-4 收藏库与地点消歧交接

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
  `CollectionWriteService` 和既有 `expected_version`/恢复边界。
- `GET /api/v1/collections/{item_id}/poi-candidates`：返回持久化快照的公开候选
  字段、当前版本和快照指纹；不返回坐标、评分证据或供应商原文。
- `POST /api/v1/collections/{item_id}/poi-selection`：输入
  `expected_version`、`snapshot_fingerprint`、`idempotency_key` 和
  `choice=candidate | none_of_above`，复用 `PlaceTargetSelectionService`。

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

## 前端状态与可访问性

正式 `/collections` 使用 M1-2 唯一 API Client、Token 和 App Shell。搜索、城市、
类型、状态、页码及打开的详情写入 URL，刷新、前进和后退可恢复。列表与详情分别
使用 generation/AbortSignal，迟到响应不能覆盖新查询或新详情版本。页面覆盖首次
加载、空、失败重试、分页、编辑、候选选择、删除和恢复；React 默认转义不可信
文本。详情打开后焦点进入关闭按钮，支持 Escape，交互目标保持 44px，并遵守
`prefers-reduced-motion`。

## 数据库与迁移

未新增迁移。现有 `collection_items` 已包含版本、逻辑删除/恢复状态、
`place_candidate_snapshot`、扁平化正式 `poi_city_code` 和 PlaceTarget；
`collection_sources` 已表达来源关系，因此 M1-4 没有新的持久化事实。Alembic
继续保持单一 `20260727_0011` head，并由迁移往返测试验证。

## 验证

- M1-4 后端契约：5 项。
- 前端 Vitest：47 项，其中 M1-4 组件 9 项。
- Playwright：22 项，其中 M1-4 8 项，覆盖 320/390/768/1024/1440px、URL
  历史、恶意文本、候选恢复路径、删除恢复、键盘焦点和 reduced motion。
- 后端完整离线回归：`1576 passed, 11 skipped, 2 deselected`；M1-3 回归 7 项，
  迁移往返 23 项。
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
- 未实现 M1-5、真实登录、分享、提醒、微信、日历或“我的”业务。
