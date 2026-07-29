# M1-8 行程只读分享交接

## 结论

M1-8 已在 `codex/m1-8-readonly-sharing` 完成开发，状态为“待主控验收”。实现只覆盖
行程级、匿名、只读分享；没有进入微信 SDK、短链接、协作编辑、通知、部署或 M2。

基线为 `e8d8f918469428e97be528a1770377d889fcbcc6`。最终开发提交的完整 SHA 由交付
消息返回。

## 数据与迁移

新增 Alembic revision `20260729_0017`，唯一 head 为该 revision。

`plan_share_links` 保存：

- 随机分享记录 ID、根 `plan_id` 和 `user_id`；
- 64 位 SHA-256 `token_hash`，不保存 bearer 明文或完整 URL；
- `created_at`、`expires_at`、`revoked_at`；
- 行程/所有者复合外键、token 哈希唯一约束；
- `revoked_at IS NULL` 的行程级部分唯一索引，保证一个行程最多一个未撤销分享；
- 创建/过期和创建/撤销时间检查。

创建与重建对根 Plan 行使用 `SELECT ... FOR UPDATE`。重建先撤销旧记录再创建新摘要，
旧 bearer 在事务提交后立即失效。SQLite 继续用于单元与契约测试；PostgreSQL 是
最终并发边界。

迁移已在临时 SQLite 上显式完成 `upgrade head`、`alembic check`、
`downgrade 20260728_0016`、再次 `upgrade head`；完整迁移集成测试也覆盖往返、
字段、复合外键、token 唯一和未撤销部分唯一索引。

## 正式业务边界

`PlanShareService` 是唯一分享应用服务，`SharedPlanSnapshot` 是唯一脱敏快照入口。
服务复用既有 `SqlAlchemyPlanRepository.latest_confirmed()`、Plan 版本、会话、
CSRF 和 MapProvider；确认新版本后只同步分享审计过期时间，公开读取始终动态选择最新
确认版本。

所有者接口：

- `GET /api/v1/plans/{plan_id}/share`
- `POST /api/v1/plans/{plan_id}/share`
- `POST /api/v1/plans/{plan_id}/share/regenerate`
- `DELETE /api/v1/plans/{plan_id}/share`

写接口要求当前行程所有者的浏览器 Session 和 CSRF。重复创建返回现有状态，但不会
再次返回明文。明文仅在创建/重建成功响应中出现一次。

公共接口只有：

- `GET /api/v1/public/plan-share`，bearer 通过 `Authorization: Share …` 传递

该入口不依赖登录，不创建 Cookie/Session，也没有公共写路由。撤销、过期和不存在
统一返回 `unavailable + null`；行程取消返回 `cancelled + null`。

## 脱敏规则

公开 DTO 允许日期、时间线、公开 POI 地址、交通、距离、缓冲、费用、风险、查询时间、
公开地点/路线入口、确认版本和更新时间。

以下内容没有公开 DTO 字段：用户身份、微信/账号、收藏来源 URL、收藏正文、私人备注、
Memory、Agent 对话、授权、未确认草稿、未选候选、数据库 ID、session、trace、
幂等键和安全字段。自由文本活动范围可能包含家庭、学校或工作地址，因此起点只使用
结构化行政区；缺失行政区时固定降级为“深圳市内出发”。地点地址只来自已确认公开
POI。

## Web/H5

确认版计划页新增所有者分享管理区：

- 创建链接；
- 只对本次新建明文执行复制和预览；
- 哈希存储状态明确提示不能再次读取明文；
- 重建前确认旧链接立即失效；
- 立即撤销；
- 展示当前状态和七天过期时间。

`/share#token` 使用独立匿名壳层，不显示主产品导航、账号或编辑控件。页面覆盖加载、
正常、取消和统一无内容状态，并展示 M08 时间轨、风险、成本、缓冲、公开地址/路线、
确认版本和更新时间。320px 与 1280px 全页截图已目视检查，无横向溢出；链接具有
可访问名称、键盘焦点语义和 `rel=noreferrer`。

## 安全复核

- bearer 为 `secrets.token_urlsafe(32)`，提供 256-bit 熵；
- 查找前统一 SHA-256，命中和未命中都执行 `hmac.compare_digest`；
- 真实库和 Demo 库均完成读取后再选结果，不因早返回放大存在性时序差异；
- API 与 Next 页面设置 `Cache-Control: no-store`、`Referrer-Policy: no-referrer`、
  `X-Content-Type-Options: nosniff` 和禁止索引/归档；
- 公共前端请求使用 `credentials: omit`、`cache: no-store` 和
  `referrerPolicy: no-referrer`；
- 对外分享 URL 使用 `/share#token`，fragment 不会进入 Next/代理请求、Referer 或
  访问日志；固定公共 API path 也不含 token，Authorization header 不被请求日志记录；
- bearer 作为 Session Cookie 会得到 401，公开访问不返回 `Set-Cookie`；
- 没有读取 `.env`，没有真实模型、地图、网页、消息或其他外部调用。

## 测试

已完成：

- `pip check`；
- Ruff；
- strict mypy：139 个源文件；
- 后端普通离线全集：`1649 passed, 18 skipped`；
- M1-8 与 SQLite 迁移聚焦：`33 passed`；
- 仓库外临时 pytest 网络封锁插件复跑 M1-6/M1-7/M1-8 与迁移：`55 passed`；
- Alembic upgrade/check/downgrade-upgrade/唯一 head；
- 前端 lint、typecheck、生产 build；
- Vitest：`80 passed`；
- Playwright：`29 passed`。

覆盖创建、重复创建、重建、撤销、哈希落库、旧 token 失效、最新确认/草稿隔离、
确认更新、取消/过期/不存在、七天边界、所有权、CSRF、Session 不可兑换、起点降级、
DTO/日志不泄漏、同计划/不同计划并发、迁移约束、匿名公开页、复制/重建/撤销、
正常/取消/无内容/加载状态、无编辑入口、320px 响应式和键盘/可访问名称。

全量复跑跨过既有 M1-6 固定行程的结束时刻后，暴露 `_seed_plan` 使用墙上时钟导致
审批 Fixture 过期。测试种子已固定在其 2026-07-28 有效窗口内；生产时间规则和全部
原断言未修改，M1-6/M1-7/M1-8 聚焦及全量回归均恢复通过。

## PostgreSQL 待主控复跑

仓库新增 `tests/integration/test_postgresql_plan_sharing.py`，在一次性 PostgreSQL
数据库中用八个独立客户端并发创建同一行程分享，验证仅一次返回新明文、终态只有一条
未撤销记录；随后并发重建第一行程与创建第二行程，验证两个行程互不干扰且部分唯一
约束保持。

当前机器没有 Docker，也没有 `postgres`、`initdb`、`pg_ctl`、`psql` 或已配置的
`TEST_POSTGRESQL_URL`，因此该测试按仓库既有 fixture 规则跳过。主控验收必须提供
隔离 PostgreSQL 并运行：

```bash
cd backend
TEST_POSTGRESQL_URL='postgresql+asyncpg://USER:PASSWORD@127.0.0.1:5432/ADMIN_DB' \
../.venv/bin/python -m pytest -q \
  tests/integration/test_postgresql_plan_sharing.py \
  tests/integration/test_postgresql_migrations.py
```

## 冗余与范围检查

代码搜索和人工复核确认仍只有一套 Plan/Version、Session、权限依赖、AgentRunner、
ToolRegistry 和正式分享服务。分享规则只在应用服务与领域契约中定义，Controller
不复制脱敏逻辑；前后端共用稳定 DTO 形状。没有样本白名单、关键词地址判断、进程锁、
测试专用生产分支、第二 Repository、第二前端状态框架或静默跳过核心断言。
