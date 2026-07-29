# 拾光 Shiguang

拾光是一款“把收藏变成行动”的个人生活 Agent：用户可以保存不同城市中想去、想做或想吃的地点与活动；当前 MVP 由 Agent 结合时间、深圳活动范围、天气、路线和费用生成可执行的单城市计划。

## 当前阶段

**M0 技术验证已正式完成。** M0-0A 至 M0-5D 和 M0-Gate 均已通过主控验收；
**M1-0 PostgreSQL 与任务基础、M1-1 Web 会话与 Demo 身份、M1-2 正式前端基础、
M1-3 Agent 与内容导入页面、M1-4 收藏库与地点消歧、M1-5 计划生成/调整/确认、
M1-6 执行入口与手动反馈、M1-7 我的/记忆/数据控制、M1-8 只读分享能力均已通过
主控验收。** 当前允许开始 M1-Gate 核心闭环验收；后续阶段不得提前开发。

普通测试全部离线，不读取真实模型或地图密钥，也不访问网络。M0 历史真实验收的
逐次授权不延续到 M1；真实模型、高德、网页、对象存储及其他外部/付费调用仍默认
未授权，必须在当前任务中重新取得明确授权并限制请求范围。

正式运行使用 PostgreSQL；Demo 与真实数据使用两个独立数据库，SQLite 继续支持
适合的单元测试。根目录 Dockerfile 和 `compose.yaml` 提供两套 PostgreSQL、唯一
API 入口与唯一 Worker 入口。M1-0 已先修复
`IdempotencyLockRegistry` 无界增长 P2，再加入持久化 Job、只负责创建 Job 的
APScheduler 适配、租约恢复、SSE 持久化与 `Last-Event-ID` 重放。

M0 关闭后的 Event 日期粒度与富输入截止校准也已完成。固定截图样本 03 在 60 秒
应用层共享截止、75 秒 Provider 异常安全上限下约 47.1 秒成功，展期日期被保留且
准确时刻保持为空；实际 1 次请求、0 repair、0 重试。47.1 秒超过 20 秒性能观察目标，
仍作为小样本风险监测；若同步请求达到 60 秒，后续转为 M1 后台 Job，不再提高时限。

## 仓库目录

```text
Shiguang_Nanobot/
├── backend/
│   ├── app/                    # FastAPI、配置、日志和数据库基础设施
│   ├── nanobot_core/           # 与 Web、数据库和业务解耦的最小 Agent 核心
│   ├── migrations/             # Alembic 基线、运行记录与收藏领域迁移
│   ├── tests/                  # 后端与 Nanobot Core 离线自动化测试
│   ├── alembic.ini
│   └── pyproject.toml
├── frontend/                   # Next.js + TypeScript 正式 Web/H5 前端
├── docs/                       # 正式产品、技术、阶段与状态文档
├── prototypes/ux/              # 静态 UX/UI 评审原型
├── compose.yaml                # PostgreSQL、API、Worker 本地开发栈
├── .env.example                # 无敏感信息的配置示例
└── README.md
```

## 正式前端本地开发

需要 Node.js 20.9 或更高版本。前端只使用 npm，并提交唯一
`frontend/package-lock.json`：

```bash
cd frontend
npm ci
npm run dev
```

打开 <http://127.0.0.1:3000/>。质量检查与离线测试：

```bash
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

API 默认同源；仅在本地前后端使用不同 origin 时设置公开的
`NEXT_PUBLIC_API_BASE_URL`，不得在该变量或任何前端配置中放入密钥或凭据。更完整
说明见 `frontend/README.md`。

## 后端本地开发

需要 Python 3.11 或更高版本。以下创建环境和安装命令从仓库根目录运行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install --upgrade pip
python -m pip install -e "./backend[dev]"
cd backend
```

Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`，之后同样进入 `backend` 目录运行后续命令。

### 代码质量与测试

以下命令均从 `backend` 目录运行：

```bash
python -m ruff check .
python -m mypy app migrations nanobot_core
python -m pytest -q -m "not real_provider and not real_map_provider"
python -m pytest -q tests/core
python -m pytest -q tests/integration/test_migrations.py
python -m pytest -q tests/contract/test_m0_2d_api.py
python -m pytest -q tests/unit/test_place_contracts.py tests/contract/test_map_provider_contract.py tests/integration/test_map_provider_stub.py
python -m pytest -q tests/unit/test_amap_provider.py tests/test_config.py
python -m pytest -q tests/contract/test_storage_provider_contract.py tests/integration/test_local_private_storage.py
python -m pytest -q tests/contract/test_web_content_provider_contract.py tests/unit/test_web_url_security.py tests/unit/test_httpx_web_content_provider.py
python -m pytest -q tests/unit/test_image_recognition_service.py tests/unit/test_openai_compatible_provider.py tests/unit/test_text_extraction_service.py
python -m pytest -q tests/contract/test_m0_4d_unified_input.py
python -m pytest -q tests/unit/test_plan_constraints.py
python -m pytest -q tests/application/test_structured_collection_retrieval.py
python -m pytest -q tests/application/test_plan_drafts.py
```

测试进程显式使用 `APP_ENV=test` 并禁止读取开发者真实 `.env`；普通测试使用临时
SQLite。显式设置 `TEST_POSTGRESQL_URL` 后可运行标记为 `postgresql` 的一次性数据库
测试；这些测试只连接授权的本地 PostgreSQL，不调用网络 Provider 或付费 API。

```bash
TEST_POSTGRESQL_URL='postgresql+asyncpg://USER:PASSWORD@127.0.0.1:5432/ADMIN_DB' \
python -m pytest -q -m postgresql
```

### M1-0 PostgreSQL、Job 与运行事件

`JobQueue` 是唯一任务契约，`PostgresJobQueue` 是唯一正式实现。任务状态为
`queued/running/succeeded/failed/cancelled`，使用 PostgreSQL 行锁和
`SKIP LOCKED` 领取；同用户幂等键有唯一约束。Worker 只通过该契约领取、完成、失败、
取消和恢复任务。失败最多执行三次，重试间隔固定为 5 秒和 30 秒；运行中任务使用
60 秒租约，服务重启后由 Worker 恢复。APScheduler 只负责按时间调用
`JobQueue.create()`，不直接执行业务。

`run_events` 是现有 `AgentRun` 的子记录，不是第二套运行主表。每个 trace 的 sequence
单调递增，公开类型包括 `run.started`、`stage.changed`、`tool.completed`、
`approval.required`、`result.updated`、`run.completed` 和 `run.failed`。订阅入口为
`GET /api/v1/agent-runs/{trace_id}/events`；`Last-Event-ID` 表示客户端已经确认的
sequence，服务只返回更大的持久化事件。Job payload 是内部有界 JSON，不会自动进入
公开结果或 SSE；Job 结果和七类 RunEvent 摘要由显式允许字段的冻结模型生成。常见
敏感别名、Prompt、完整模型响应、Header、私有文件 key/路径没有公开字段，合法
`content_sha256` 只在明确允许的位置序列化。

### M1-1 Web Session 与 Demo 身份

`BrowserSession`、`WebSessionService` 和 `SqlAlchemyWebSessionRepository` 分别是
唯一浏览器会话领域、应用和持久化边界；既有 `Session` 继续只表示 Agent/消息
会话。服务端生成 256-bit 随机 Session Token；CSRF 由该 Token 通过带版本化领域
上下文的 HMAC-SHA-256 确定性派生，数据库仍只保存两者的 SHA-256。
Cookie 固定为 `HttpOnly`、`SameSite=Lax`、`Path=/` 且不设置 `Domain`；
production 强制 `Secure`。所有认证写请求统一使用 `X-CSRF-Token`，过期采用绝对
时间且不滑动续期，恢复 Cookie 的 `Max-Age`/`Expires` 对应数据库剩余寿命，当前
设备可显式撤销。

`POST /api/v1/demo/sessions` 不接受客户端 `user_id` 或 Token。首次访问在独立 Demo
数据库中创建该浏览器专属的 Demo User、Web Session 和消息 Session；有效 Cookie
以只读方式恢复同一沙盒和稳定凭据，跨进程并发恢复不会互相失效。无效、伪造、
过期或撤销 Cookie 会创建全新的随机 Demo 沙盒。Demo 默认 2 小时、配置上限 24
小时；真实 Web Session 保留 30 天能力，但本阶段没有真实登录入口。
`ChannelIdentity` 只保留供应商无关最小协议，持久化和微信绑定延后到 M2-2。

### M1-8 行程只读分享

已确认行程可以生成 256-bit 随机只读链接；数据库只保存 SHA-256 摘要，同一行程
同时最多一个未撤销分享。创建、重建和撤销复用现有浏览器 Session、所有权与 CSRF
边界；重建会立即撤销旧链接。匿名入口
`GET /api/v1/public/plan-share` 使用 `Authorization: Share …`，不创建 Cookie 或
Session，只返回该行程最新
确认版本的脱敏快照；未确认草稿不会进入公开结果。精确起点降级为结构化行政区，
收藏正文、来源 URL、备注、记忆、对话、授权与内部 ID 均不在公开 DTO 中。

分享在行程结束七天后过期。撤销、过期和不存在统一返回无内容状态，行程取消返回
独立取消状态。API 与 `/share#token` 页面均使用 `Cache-Control: no-store` 和
`Referrer-Policy: no-referrer`；分享链接将 bearer 放在不会发送到服务器的 URL
fragment 中，访问路径、Referer 与请求日志均不包含 token。
公开接口仅提供 GET，页面不加载账号导航或编辑入口。

### 价格与人民币契约

拾光当前只支持中国本地场景，用户无需填写或选择币种。文字、URL 正文和图片共用 `parse_extraction_response()` 抽取信任边界：模型已经明确识别出的本地金额若未写币种，会在进入严格候选契约前统一补为内部单位 `CNY`；系统不会扫描原文数字或自行猜测价格。明确免费保存为 `Decimal("0") + CNY`，无法确认价格时金额和币种都保持 `None` 并标记价格缺失、不确定或计划风险。

所有正式领域对象只接受 `None + None` 或 `Decimal + CNY`，半完整价格与外币均被拒绝。收藏修改只提交金额时自动配对 CNY，清空金额时同时清空币种。数据库 `price_currency` 列暂时保留，仅表示内部金额单位，不代表币种选择、多币种计划、外汇换算、汇率 Provider 或相关功能已经实现。

### M0-5A PlanConstraints

`app.domain.plans.PlanConstraints` 是唯一完整计划约束契约。调用方必须显式传入 `PlanCity.SHENZHEN`；通过 `city_scope` 可转换为既有 `CityScope`，不依赖全局当前城市。契约复用既有 `Coordinate` 和 `TransportMode`（公共交通值保持 `transit`），要求一个 aware 且不超过 24 小时的连续时间段，以及粗粒度 `ActivityArea` 或敏感 `origin` 二者之一。

预算使用严格 `Decimal | None`，`None` 不会被改写成默认金额；pace、交通方式、include/exclude 和 `collection_only` 均为可选且不阻塞。`resolve_plan_constraints()` 只会按稳定顺序返回一个缺失项：先 `time_window`，再 `activity_range`。临时约束在 `[created_at, expires_at)` 内有效，到达过期时刻后整组约束不可继续解析；该纯函数不访问数据库、文件、网络或 Provider，也不写入长期记忆。

`PlanConstraints` 和 `PlanConstraintInput` 保持原生 Pydantic 契约；其原始 `ValidationError` 只属于内部实现，不得由 Application、API 或日志直接记录、返回。不可信 Python/JSON 输入必须使用 `app.domain.plans` 导出的 `parse_plan_constraint_input*` 或 `parse_plan_constraints*`，这些入口共用唯一内部捕获映射，只返回合法领域对象，失败时只抛出固定 `PlanConstraintParseError(code="INVALID_PLAN_CONSTRAINTS")`，不携带原始 input、JSON、Pydantic 消息/context/URL 或异常链。未来模型结构输出和 API 输入必须复用该边界，不得直接公开底层 Pydantic 错误。成功对象的精确 `origin` 仍不进入 repr、日志、`model_dump()` 或 `model_dump_json()`。聚焦回归入口为 `APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0 python -m pytest -q tests/unit/test_plan_constraints.py`。

### M0-5B 结构化收藏检索和规则

`StructuredCollectionRetrievalService` 是唯一正式检索入口：它用显式 `user_id` 从既有 `CollectionRepository` 只读加载收藏，并复用 M0-5A `PlanConstraints`、既有 `PlaceTarget`、`PlaceMatchingService` 和 `MapProvider`。正式城市只来自已确认 POI 或请求级的已核验 Event 位置事实；`city_hint` 不参与计划城市判断。非 active、已删除、待选择、待补充、位置/城市未确认、已结束 Event 及违反行政区、活动范围、时间、预算、include/exclude、路线、天气或营业硬条件的条目会得到稳定原因码，不会仅降低分数。

调用 `retrieve()` 必须显式传入确定性的 aware `now`。入口先复用 `PlanConstraints.is_active()` 校验 `[created_at, expires_at)`，过期或非法时间分别通过同一个安全错误类型返回 `PLAN_CONSTRAINTS_EXPIRED` 或 `INVALID_RETRIEVAL_TIME`，并在 Repository、地点匹配和 MapProvider 之前停止。路线期限规则只有一份：普通 Place 必须在计划结束前到达，Event 还必须严格早于其结束时间到达；到达时刻等于期限也会排除。

路线、天气、营业和 Event 正式位置通过冻结的 `PlanningFactSnapshot` 注入；未知、离线失败和明确冲突分别保留不同结论，不把未知路线、天气或营业状态伪造成通过。结果只有 `included`、`excluded` 和 `verification_required` 三种稳定结论，并携带固定安全摘要。预算为 `None` 时不按价格过滤，正式的完全未知价格 `None + None` 可以进入草案并由 M0-5C 标记 `PRICE_UNKNOWN`；用户提供预算时，完全未知价格仍进入 `verification_required`，已知 CNY 超预算候选继续排除。

`any_branch` 在本次请求中只用已确认 `BrandIdentity` 作为匹配身份，计划城市、单一行政区和精确 origin 仅来自本次 `PlanConstraints`。原收藏残留的旧分店 district、address、business_district、landmark、metro_station 和描述不会复制到动态分店匹配候选；原收藏本身不被清空、改绑或写回。无候选、证据不足、Provider 失败和没有满足硬约束的分店均有独立原因码。品牌收藏与精确收藏解析到同一 `provider + poi_id` 时合并为一个候选，同时保留全部 `collection_item_ids` 和任意分店来源 ID，供后续 M0-5C 解释；本阶段没有 Plan、PlanItem 或草案代码。

聚焦回归入口为 `APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0 python -m pytest -q tests/application/test_structured_collection_retrieval.py`。

### M0-5C 确定性计划草案

`PlanDraftService` 是唯一草案生成与复核入口。它只读取 M0-5B `StructuredCollectionResult.included`，并接收冻结的 `PlanDraftFactSnapshot`：每个候选的访问时长、Event 固定时间、任意分店查询时间，以及从出发点或上一地点到下一地点的供应商无关路线事实都必须显式注入。缺少访问时长或首段路线时不猜测；缺少地点间路线时只生成合法单地点方案；没有任何可执行组合时返回稳定的不可生成原因。

默认按 pace 确定性使用 10/15/20 分钟地点切换缓冲和 15/20/30 分钟结束留白。每个方案最多一个核心地点和一个辅助地点；输出为一个主方案和最多两个备选。排序依次使用已知首段路线时长、规范化标题、POI 身份和收藏 ID，因此相同输入与相同事实重复调用得到完全相同的业务结果。费用未知保持 `None` 并显示 `PRICE_UNKNOWN` 风险，不伪造为 0；已知预算下无法证明费用合规的组合不会生成。

每个 PlanItem 草案快照包含时间、访问时长、入站路线、费用、收藏来源 ID、具体 POI、风险和稳定选择理由。任意分店必须同时保存本次解析出的具体 POI、查询时间、品牌级来源 ID，并固定标记为 `collection_derived`；M0-5B 已合并的 exact/any_branch 同 POI 来源只产生一个 PlanItem。生成后 `PlanDraftService.validate()` 使用同一事实契约重新检查时间/Event 边界、路线和交通方式、缓冲、结束留白、预算、费用、来源、任意分店快照及重复 POI；被篡改结果返回稳定违反码。

M0-5C 使用 20 组固定 Fixture 验证生成后的硬约束违反数为 0。聚焦回归入口为 `APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0 python -m pytest -q tests/application/test_plan_drafts.py`。

### M0-5D 收藏不足与高德补充

`ExternalPlaceSupplementService` 是唯一外部 Place 补充编排入口。调用方必须提供结构化的单个 `RequiredPlanGap`，服务不会扫描自由文本、把软偏好变成缺口，或因为计划仍有空闲时间而外搜。它直接消费唯一 `StructuredCollectionRetrievalService` 的结果，复用既有 `PlaceMatchingService`、`MapProvider` 与 `PlanDraftService.generate()/validate()`；每次最多执行一次 `search_poi`，最多保留 3 个候选，且最多向主方案加入一个外部 Place。

收藏已满足且没有显式必要缺口时地图调用为 0；`collection_only` 和 Event 缺口始终禁止外搜。没有可执行收藏核心时，决定必须携带与当前缺口绑定的确定性 Approval ID；未决定或决定不匹配时返回 `waiting_user`，拒绝后只返回收藏内草案或继续添加收藏的恢复路径。外部地点固定标记为“高德补充 · 未收藏”，保存供应商无关 POI、查询时间、补充原因、已知路线以及价格/营业时间风险，不携带 CollectionItem ID，也不会写入收藏或数据库。本阶段只验证不可变草案与授权边界，不提供正式确认或“加入收藏”动作。

本阶段只有不可变技术验证契约，不创建 Plan/PlanItem Repository 或数据库表，不调用模型、地图、路线、天气、网页及其他外部 API。M0-5D 聚焦回归入口为 `APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0 python -m pytest -q tests/application/test_external_place_supplement.py`。

### 数据库迁移

默认数据库是 `backend/data/shiguang.db`，目录和数据库文件均被 Git 忽略。从 `backend` 目录运行：

```bash
python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
```

当前唯一 HEAD revision 是 `20260727_0010`。`0008` 增加持久化
`scheduled_jobs`，`0009` 增加现有 AgentRun 的 `run_events` 子记录，`0010` 增加
只保存凭据哈希的 `web_sessions`。正式运行使用 `postgresql+asyncpg`；SQLite 继续
用于适合的测试。应用导入和普通启动不使用 `create_all()`；Compose 的 API 启动
命令会分别将真实与 Demo 数据库升级到 head。

### 启动 API

从 `backend` 目录运行：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

在另一个终端验证健康检查与 Request ID：

```bash
curl -i http://127.0.0.1:8000/healthz
curl -i -H 'X-Request-ID: local-check-001' http://127.0.0.1:8000/healthz
```

响应 JSON 固定为 `{"status":"ok"}`，响应头包含 `X-Request-ID`。请求日志只记录 request ID、方法、路径、状态码和耗时，不记录正文、查询字符串、Authorization 或 Cookie。

### 最小容器运行

以下命令从仓库根目录执行。Compose 不复制 `.env`，镜像内不保存模型、高德或其他密钥：

```bash
docker compose up --build -d
docker compose ps
curl -i http://127.0.0.1:8000/healthz
```

API 等两套 PostgreSQL 健康后分别执行迁移并启动既有 `app.main:app`；Worker 再等
API 健康后从正式 PostgreSQL 队列领取任务。API 和 Worker 都继承 Dockerfile 的
非 root 用户。
如需验证两个 Worker 竞争，可临时扩容：

```bash
docker compose up -d --scale worker=2
```

停止并清除本地 Compose 数据：

```bash
docker compose down --volumes
```

Compose 中的数据库口令是仅供本机开发的默认值，可通过 shell 环境变量
`POSTGRES_PASSWORD` 覆盖；不要把生产口令写入 Compose、`.env.example` 或 Git。

## 配置

服务端默认读取仓库根目录 `.env`；可复制 `.env.example` 后按需覆盖。当前实现的变量为：

| 变量 | 默认/示例 | 说明 |
|---|---|---|
| `APP_NAME` | `Shiguang API` | OpenAPI 应用标题 |
| `APP_VERSION` | `0.1.0` | API 版本 |
| `APP_ENV` | `development` | `development`、`test` 或 `production` |
| `APP_TIMEZONE` | `Asia/Shanghai` | 有效 IANA 时区 |
| `DATABASE_URL` | `postgresql+asyncpg://...` | 正式运行 PostgreSQL URL；测试可使用异步 SQLite |
| `DEMO_DATABASE_URL` | `postgresql+asyncpg://...` | 独立 Demo PostgreSQL URL；production 启用 Demo 时必须显式提供且不得等于正式库 |
| `DEMO_ENABLED` | `1` | 是否启用 Demo；production 启用时强制独立数据库 |
| `WEB_SESSION_COOKIE_SECURE` | 环境决定 | production 必须为 Secure；开发 HTTP 可显式关闭 |
| `REAL_WEB_SESSION_TTL_SECONDS` | `2592000` | 真实 Web Session 绝对有效期，上限 30 天；本阶段无公开登录入口 |
| `DEMO_WEB_SESSION_TTL_SECONDS` | `7200` | Demo Web Session 绝对有效期，上限 24 小时 |
| `LOG_LEVEL` | `INFO` | 标准 Python 日志级别 |
| `MODEL_API_BASE` | 无 | OpenAI-compatible API Base，仅启用真实 Provider 时必填 |
| `MODEL_API_KEY` | 无 | 服务端密钥，以 `SecretStr` 脱敏，仅启用真实 Provider 时必填 |
| `MODEL_NAME` | 无 | 供应商侧模型名称，仅启用真实 Provider 时必填 |
| `MODEL_TIMEOUT_SECONDS` | `75` | Provider/传输层异常安全上限，只允许有限值 `(0, 75]`；正常 URL/图片流程先由应用层 60 秒截止取消请求；无模型配置时应用仍可启动 |
| `MODEL_INPUT_PRICE_PER_MILLION_TOKENS` | 无 | `MODEL_NAME` 的每百万输入 Token Decimal 单价；非负有限值 |
| `MODEL_OUTPUT_PRICE_PER_MILLION_TOKENS` | 无 | `MODEL_NAME` 的每百万输出 Token Decimal 单价；非负有限值 |
| `MODEL_COST_CURRENCY` | `CNY` | 三位大写币种代码 |
| `MODEL_PRICING_SOURCE` | `configured_model_rates` | 可审计的价格配置来源标签 |
| `AGENT_MAX_TOOL_CALLS` | `8` | 单次 Run 绝对工具调用上限，只允许 `1..8` |
| `AGENT_TIMEOUT_SECONDS` | `60` | 单次 Run 总时限，只允许有限值 `(0, 60]` |
| `WORKER_POLL_SECONDS` | `1` | Worker 空队列轮询间隔，只允许有限值 `(0, 60]` |
| `RUN_REAL_MODEL_TESTS` | `0` | 只有精确设为 `1` 才授权真实 Provider 测试 |
| `AMAP_API_KEY` | 无 | 高德 Web 服务 Key，以 `SecretStr` 脱敏；只在显式构造真实地图 Provider 时必填 |
| `AMAP_BASE_URL` | `https://restapi.amap.com` | 固定高德 Web 服务官方 origin；只允许可规范化的末尾 `/`，拒绝其他域名、端口、路径、凭证、查询和 fragment |
| `AMAP_TIMEOUT_SECONDS` | `5` | 单次 HTTP 尝试超时，只允许有限值 `(0, 30]` |
| `AMAP_MAX_RETRIES` | `1` | 每个逻辑请求额外尝试次数，只允许 `0..1` |
| `AMAP_RETRY_AFTER_MAX_SECONDS` | `1` | `Retry-After` 等待上限，只允许有限值 `[0, 5]` |
| `PLACE_MATCH_UNIQUE_SCORE` | `75` | 唯一自动匹配的最低可解释证据分数，只允许有限正数 `(0, 100]` |
| `PLACE_MATCH_MINIMUM_SCORE_GAP` | `12` | 第一名相对第二名的最小自动匹配分差，只允许有限正数 `(0, 100]` |
| `PLACE_MATCH_CANDIDATE_SCORE` | `35` | 合理候选的最低分数，只允许有限正数 `(0, 100]` 且不得高于唯一匹配阈值 |
| `RUN_REAL_MAP_TESTS` | `0` | 只有精确设为 `1` 且另获授权才允许真实高德测试 |
| `STORAGE_PRIVATE_ROOT` | `./data/private` | 本地私有根目录；不得位于公开 `public/static` 目录，完整路径不会进入公开对象或错误 |
| `DEMO_STORAGE_PRIVATE_ROOT` | `./data/demo-private` | 与真实用户文件物理分离的 Demo 私有根目录 |
| `STORAGE_MAX_FILE_SIZE_BYTES` | `10000000` | 流式写入上限，只允许 `1..20000000` 字节 |
| `STORAGE_ALLOWED_CONTENT_TYPES` | `image/jpeg,image/png,image/webp` | 允许类型的逗号分隔子集；声明类型还必须通过集中式文件签名校验 |

`.env` 会被 Git 忽略，不要把真实密钥、Token、Cookie 或账号写入代码、示例、测试输出或提交。

模型价格不会硬编码。只有模型名、输入/输出 Token 和两项配置单价都完整时才使用 Decimal 估算并以 8 位小数保存；未知 Token、模型名变化或价格缺失都会保留未知费用和明确原因，不会伪造零费用。合法的零 Token 与零单价仍得到真实的零费用。

### M0-1C 运行记录

每次应用层执行先创建不可推测的 `trace_id`，持久化 `queued → running`，再进入唯一 Runner。最终状态为 `succeeded`、`partially_succeeded`、`failed` 或 `cancelled`；`waiting_user` 已纳入契约但本阶段不实现审批流程。

Runner 在同一执行循环中保证：最多执行 8 次绝对 Tool Call；第 9 次记录为 blocked 且不执行；使用工具名与规范化 JSON 参数的 SHA-256 指纹阻止异常重复；通过可取消等待和单调时钟把总时限限制在 60 秒。Provider 或 Tool 正在等待时也会被总时限取消，外部 `CancelledError` 落库后继续向调用方传播。

`AgentRunService.get_by_trace_id()` 返回模型调用元数据、Token/费用汇总、有序 ToolRun、安全错误码和结束原因。数据库只保存结构化输入/输出摘要与指纹，不保存消息、完整模型响应、Prompt、思维链、完整工具参数、异常对象、Authorization、Cookie 或密钥。本阶段故意不提供 `GET /agent-runs` 路由。

### M0-2A/B/C 文字收藏、结构化抽取与可逆写入

`app.domain.collections` 是 User、Session、Message、Source、CollectionItem、CollectionSource、Place/Event 类型和收藏状态的唯一应用层契约。实体 ID 使用命名空间加 128 位随机值，服务端时间统一为 UTC；稳定的所有权、状态、版本、Source 抓取时间和 Event 时间使用独立数据库列。Event 的 `event_start_date/event_end_date` 是不带时区、结束日包含当天的有效自然日期；`event_start_at/event_end_at` 只保存来源明确到钟点的 aware 场次时间。date-only 事实不会转换成午夜、推断时区或每日开闭馆时间。Source 元数据使用字段白名单，不接受 Header、Cookie、原始正文或凭证。

`SqlAlchemyCollectionRepository` 的所有公开读写方法都显式要求 `user_id`。Message 通过用户拥有的 Session 查询；CollectionSource 在 Repository 与复合外键两层保证 Source 和 CollectionItem 属于同一用户；跨用户资源与不存在资源采用同一安全结果。默认收藏查询排除 `recognizing`、`failed`、`archived` 和 `deleted`，只有 `active` 具备后续进入计划的状态资格。

`User.default_plan_city` 当前保持深圳计划语义；`CollectionItem.city_hint` 只保存可空的来源城市线索，允许广州、上海等其他城市收藏，不代表正式城市或计划资格。唯一 `TextExtractionService` 使用现有 `ModelProvider` 抽取严格的 Place/Event 候选，普通结果调用一次，结构错误最多修复一次，并明确保留缺失与不确定字段。

唯一 `CollectionWriteService` 将候选、共享 Source、CollectionSource、幂等记录和 Undo 关联放在同一事务中。`user_id + idempotency_key` 与 `user_id + source_id` 的数据库唯一约束覆盖重复消息、并发提交和同来源重试；请求只持久化规范化 SHA-256 指纹。首次成功返回 10 分钟 Undo Token，数据库只保存 Token 哈希，重试不再次返回明文。Undo 只把本次操作创建的条目逻辑删除，不删除 Source 或其他收藏。

`CollectionItemPatch` 只开放标题、城市线索、位置/时间线索、Event 日期与准确时间、价格、标签、缺失字段和不确定项。成功变更使用 `expected_version` 并递增版本；无实际变化不生成新版本，旧版本不会覆盖新数据。默认查询立即隐藏 `deleted`，内部 `include_inactive` 仍可复核。M0-3 前 Place 自动保存为 `pending_details`，不会伪造 POI 候选、正式城市或计划资格；只有日期范围的 Event 也保持 `pending_details` 且不进入正式计划，精确起止时间完整的 Event 才映射为 `active`。

### M0-2D 最小 HTTP API

接口前缀统一为 `/api/v1`，OpenAPI 由 FastAPI 在 `/openapi.json` 提供：

- `POST /demo/sessions`：确保服务端固定 Demo User，并创建新的 Demo Session；请求体为空且不接受客户端 `user_id`。
- `POST /sessions/{session_id}/messages`：同步提交兼容旧格式的纯文字 JSON、新的 `text`/`url` 判别 JSON，或带 `Idempotency-Key` 的有界 JPEG/PNG/WebP 原始请求体；返回统一终态、来源摘要、恢复动作、`trace_id`、结构化收藏和首次创建时的一次性 Undo Token。响应不公开 URL、`file_key`、路径或图片字节。
- `GET /agent-runs/{trace_id}`：按服务端身份读取安全运行摘要，不返回用户 ID、Prompt、消息正文、完整模型响应、原始工具参数或参数指纹。
- `GET /collections` 与 `GET /collections/{item_id}`：支持城市线索/城市待确认、区域、类型、状态、标签、显式 inactive、稳定排序与分页；详情只返回必要来源摘要。
- `PATCH /collections/{item_id}`：请求体为 `{"expected_version": 1, "changes": {...}}`，`changes` 直接复用唯一 `CollectionItemPatch`。
- `DELETE /collections/{item_id}`：可选 `expected_version` 查询参数，只执行既有逻辑删除。
- `POST /collections/{item_id}/undo`：请求体携带 `undo_token`；服务在原子认领前先确认 Token 操作组包含路径条目。

M0 使用服务端固定 Demo User；所有 Repository 调用仍显式携带该 `user_id`。消息 ID、Source ID 和 trace ID 由 `user_id + session_id + idempotency_key` 确定性派生；同 Session 同 key 的顺序/并发重放复用结果，不同正文、类型或图片摘要稳定冲突，不同 Session 使用同 key 则保持隔离。请求校验错误为 422，不存在与跨用户资源统一为 404，真实版本冲突为 409；验证错误响应只返回字段路径和错误类型，不回显正文、图片或 Undo Token。

M0-2D 没有新增迁移或配置变量。应用、`/healthz`、OpenAPI 和 Demo Session 在没有模型配置时仍可启动；测试通过 `create_app(..., text_provider=FakeProvider(...))` 显式注入离线 Provider。

### M0-3A MapProvider Stub

`app.domain.places` 是坐标、POI、路线、天气和导航 DTO 的唯一归属。所有模型均为 strict、extra-forbid、不可变契约；坐标显式携带坐标系，城市使用稳定 `city_code`，POI 使用唯一受限 `PoiProvider` 身份，距离和耗时分别使用非负米与秒，天气使用 `date` 和有界摄氏温度。DTO 不包含 `adcode`、`pname`、`cityname`、API Key、Header 或供应商原始响应。

`app.providers.MapProvider` 是唯一地图能力边界。`search_poi`、`get_poi`、`route`、`weather` 和 `build_navigation_uri` 分别接收严格请求对象，每个请求都显式包含 `CityScope`；没有进程级当前城市、默认深圳状态或城市缓存。相比技术方案中的早期简写签名，M0-3A 按最新阶段要求让五类方法全部显式携带城市范围。

`StubMapProvider` 通过构造参数注入不可变 Fixture 映射，不访问网络或环境变量，不使用供应商 SDK，也不按调用顺序消费共享队列。相同输入返回内容相等但对象独立的快照；深圳、广州连续、交错和并发调用互不污染。未配置的搜索返回显式空结果，详情不存在使用固定安全错误，超时由请求 Fixture 确定；取消会原样传播，不自动重试、退避、熔断或缓存。

共享测试数据位于 `tests.fixtures.maps`，包含深圳和广州唯一结果、深圳连锁品牌多结果、无结果、超时、详情、路线、天气与导航 URI。Stub Fixture 明确模拟 Amap 来源，因此稳定携带 `provider=amap`；`provider + poi_id` 可作为后续正式地点引用的供应商身份。Fixture 只配置正式 Stub，不复制搜索、验证或匹配算法。本阶段没有数据库模型或迁移。

### M0-3B 高德 Web 服务适配

`AmapMapProvider` 是复用现有 `MapProvider` 和地点 DTO 的唯一正式高德适配器。其输出 POI 固定携带受限身份 `provider=amap`，并保留供应商 `poi_id`、正式 `city_code` 和 GCJ-02；深圳和广州共享同一实现与同一内部城市目录：`shenzhen → adcode 440300 / citycode 0755`，`guangzhou → adcode 440100 / citycode 020`。每次调用从请求内 `CityScope` 取值；没有 `AMAP_CITY`、`CURRENT_CITY` 或默认深圳状态。供应商 `adcode`、`pname`、`cityname`、`typecode` 和 `infocode` 只在适配层校验/映射，不进入领域 DTO。

高德 HTTP origin 固定为 `https://restapi.amap.com`；安全的末尾 `/` 会规范化，其他 hostname、相似后缀域名、userinfo、HTTP、显式端口、路径、查询、fragment、控制字符和损坏 URL 都在 Provider 构造前拒绝。所有供应商/解析异常先在内部收敛，退出 `except` 后再创建并抛出固定 `MapProviderError`；公开错误的 `context` 与 `cause` 均为空，也不保留 request、response、URL、Key、正文或原始字段。

高德 `10012/10013` 映射鉴权权限失败且不重试；`10014/10015/10019` 映射限流，`10016/10017` 映射临时不可用；后两类与 `3xxxx` 服务错误一样最多额外尝试一次。未知 infocode 保持 `INVALID_RESPONSE`，供应商 `info` 文本不会成为公开错误。

POI 搜索使用显式城市与 `citylimit=true`，无结果保留空列表；详情同时核验 POI ID 与城市归属。步行、骑行、公交和驾车使用高德 v5 路线接口，只返回 GCJ-02 端点、总米数和总秒数。天气使用城市正式 adcode 和预报日期。导航链接在本地生成 `https://uri.amap.com/marker`，不发 HTTP，也不包含 Key。

`create_amap_http_client()` 是唯一 HTTP Client 构造入口；生产连接池由 Provider 关闭，测试通过该入口注入 `MockTransport`。单个逻辑请求最多 2 次 HTTP 尝试：只重试超时、连接错误、HTTP 429、500/502/503/504，以及明确可恢复的高德限流/引擎错误。鉴权、参数、响应损坏、无结果和其他 4xx 不重试；`Retry-After` 只接受有限非负秒数并受配置上限约束。取消原样传播。错误只公开固定摘要，不记录 Key、完整查询 URL 或响应正文。

默认测试完全离线；真实入口只执行只读搜索、详情、路线和天气，并本地构造导航 URI：

```bash
python -m pytest -q tests/unit/test_amap_provider.py tests/test_config.py
RUN_REAL_MAP_TESTS=1 python -m pytest -q -m real_map_provider -rs
```

真实入口包含 5 个逻辑 HTTP 请求（深圳搜索、广州搜索、一个详情、一条路线、一个城市天气），在 `AMAP_MAX_RETRIES=1` 时最多 10 次 HTTP 尝试；导航 URI 不增加请求。只有用户配置 Key 并对本次真实调用单独授权后才能运行。普通 `pytest` 会默认 skip；本阶段未执行该入口。

### M0-3C 地点匹配评分与候选

`app.domain.places.matching` 是唯一地点评分契约与纯规则归属，按固定顺序评估名称、分店、行政区、商圈、地址、地标、地铁、电话、POI 类型和安全处理后的来源上下文。每个候选保留 `provider + poi_id`、正式 `city_code`、GCJ-02 坐标、供应商原始排名、确定性结果排名、`0..100` 有限分数、置信度和结构化证据；来源全文、电话和供应商响应不进入结果。供应商排名只在分数相同时作为稳定决胜项。

`PlaceMatchingService` 是唯一应用层编排入口。每次调用显式接收 `CityScope`，只把标题与可选行政区交给现有 `MapProvider` 搜索；Event 会在 Provider 调用前拒绝。搜索范围的城市证据固定为零分，只用于拒绝混城结果，因此默认搜索深圳不会成为已确认城市事实。空结果为 `not_found`，弱证据或硬冲突为 `needs_context`，多个合理候选为 `ambiguous`；只有分数、第一二名差距和无硬冲突三项同时通过才为 `matched`，输出最多 3 项。

唯一服务端阈值入口是 `Settings.place_matching_policy()`，由 `PLACE_MATCH_UNIQUE_SCORE`、`PLACE_MATCH_MINIMUM_SCORE_GAP` 和 `PLACE_MATCH_CANDIDATE_SCORE` 构造；三者只接受有限正数 `(0, 100]`，候选阈值不得高于唯一阈值。同分结果不会自动匹配。用户可见候选必须达到候选阈值且无硬冲突；Provider 有返回但没有可靠候选时返回可为空候选的 `needs_context`。用户选择契约仅表达当前候选中的具体 POI、显式“任意分店”或“以上都不是”；M0-3C 不写数据库，不持久化 `exact / any_branch`，也不修改 CollectionItem。

### M0-3D 连锁品牌与统一地点目标

`app.domain.places.targets` 定义唯一 `PlaceTarget`：`exact` 保存一个已确认 POI 的 `provider + poi_id`、正式 `city_code`、GCJ-02 坐标、确认来源/时间、匹配状态与必要证据；`any_branch` 只接受显式用户选择和已确认的稳定品牌命名空间/身份，不根据相似名称推断或合并。候选快照继续复用 M0-3C 契约，最多 3 项并保存 `queried_at`，不是独立收藏。`resolve_place_target()` 只提供 exact、any_branch、unconfirmed 三态规划边界，不包含路线或动态选店实现。

`PlaceTargetSelectionService` 在现有 CollectionItem、Repository、Source 和事务上完成选择：未选保持 `pending_selection`；具体 POI 转为 `active + exact`；显式任意分店转为 `active + any_branch`；“以上都不是”回到 `pending_details`。多选具体分店在一个事务内拆成独立收藏并共享原 Source，新增分店会加入原写入操作的 Undo 组。每用户的 exact POI、any-branch 品牌和选择幂等键均有数据库约束；唯一冲突会回读并收敛，跨用户复合外键继续阻止 Source、收藏与操作串用。Alembic `20260722_0006` 是从 `20260721_0005` 向前的唯一新迁移。

### M0-4A 私有文件存储

`app.providers.StorageProvider` 是唯一供应商无关边界，提供流式 `put_private`、受控 `get_private_access` 和幂等 `delete`。返回 DTO 只包含随机、不透明 `file_key`、创建时间、字节数、内容类型、保留策略、可选过期时间和 SHA-256，不包含原始文件名、文件内容、绝对路径或本地 URL。当前没有下载路由，因此本地访问明确标记为 `application_download_route_required`，不会伪造 `file://`、HTTP 或公开签名 URL。

唯一 `LocalPrivateStorageProvider` 位于 `app.infrastructure.storage`。它使用密码学安全随机 key、受限目录/文件权限、受控临时目录、排他预留和原子硬链接发布；碰撞不覆盖已有对象，超限、签名不符、异常与取消都会清除临时/最终残留。对象名不使用扩展名或原始文件名，所有查找均拒绝路径语法和 Unicode 混淆，并用 no-follow 目录操作阻止符号链接逃逸。类型、签名和最大硬上限集中在 `app.storage_policy`，没有复制到 API、Source Repository 或 Fixture。

原始截图使用 `original_screenshot_30_days`，Demo 文件可用 `demo_session_max_24_hours`，其他内部文件可显式使用 `user_controlled`；Provider 保存生命周期元数据并在访问描述中标记已过期对象。本阶段没有后台清理 Worker，也没有图片上传/下载 API、OCR、网页抓取、COS/S3 适配或数据库表。

### M0-4B 安全网页解析

`app.providers.WebContentProvider` 是唯一供应商无关的网页获取边界，返回 `app.domain.web` 中唯一的成功/可恢复失败契约。成功结果只包含规范化原始 URL、最终 URL、标题、清理正文、固定白名单元数据、Content-Type、UTC 获取时间和有界诊断；失败结果使用固定代码与摘要，并明确允许后续请求用户补充文字或截图。两类结果都不包含原始 HTML、HTTP 响应、Cookie、Authorization、代理凭证、内部地址、异常文本或堆栈。

唯一 `HttpxWebContentProvider` 显式注入 `AsyncClient` 和 DNS Resolver。集中式 URL/SSRF 策略只允许标准端口的 HTTP(S)，拒绝用户信息、混淆 IP、本机/内网/链路本地/元数据/非全局地址及混合 DNS 答案；每一跳都重新解析并校验，再把实际连接固定到已验证 IP，同时保留安全的 Host 与 TLS SNI。应用显式处理最多 5 次重定向并检测循环；客户端禁用环境代理、认证、Cookie、自动重定向、自动重试和持久连接，`CancelledError` 原样传播。

响应只接受 `text/html`、`application/xhtml+xml` 和 `text/plain`；传输体与解压后正文均有 2 MB 硬上限，清理后文本最多 50,000 字符。唯一 BeautifulSoup 抽取器移除脚本、样式、导航与不可见内容，只允许 description、canonical 和三项 Open Graph 元数据。BeautifulSoup 是本阶段唯一新增的解析依赖；未增加配置变量、路由、持久化、迁移、截图/OCR 或统一 Source 工作流。

### M0-4C 截图识别

`ImageRecognitionService` 在应用层接收受限异步图片流，复用 M0-4A 的唯一 `StorageProvider` 与 `ORIGINAL_SCREENSHOT` 30 天生命周期。服务在消费异步流前检查 MIME，再按现有签名和配置大小边界缓冲，并用唯一 Pillow 解码器校验 JPEG/PNG/WebP 的格式、完整性、静态帧、宽高和 4000 万像素安全上限；任何空文件、伪装、截断、损坏、超限或像素异常输入都在保存和模型调用前失败。标准库没有 JPEG/PNG/WebP 完整解码器，无法可靠执行这些安全检查，因此 Pillow 是本阶段唯一新增的图片依赖，不接 OCR SDK 或外部 OCR 服务。

验证通过后原图才进入私有存储，返回值只组合既有 `PrivateFileMetadata` 和 `ExtractionResult`，不提供本地路径、公开 URL、图片专用候选或 OCR DTO。模型侧每边必须至少 11 像素且比例不超过 200:1；普通小图直接使用已验证原字节，较大图片只在内存中确定性转换为最长边 4096、最多 400 万像素的 JPEG 推理副本，并在编码前后保证完整 data URL 严格小于 10,000,000 字符。推理副本不进入存储，原图仍按 30 天策略保存，也不读取 EXIF。多模态消息继续通过唯一 `ModelProvider` 与 `OpenAICompatibleProvider`，SDK 仍为非流式、`max_retries=0`；文字和图片共用一处 JSON Schema 校验与最多一次结构修复。Provider 异常与取消只清理本次对象；清理期间新取消继续传播，其他意外清理错误固定脱敏。

本阶段没有上传 HTTP 路由、Source/Collection/AgentRun 编排、配置变量、数据库迁移、真实视觉测试入口或 M0-4D 统一输入。离线聚焦命令：

```bash
python -m pytest -q tests/unit/test_image_recognition_service.py tests/unit/test_openai_compatible_provider.py tests/unit/test_text_extraction_service.py
```

当前修复前交接基线的上述精确命令为 `120 passed`；验收阻断修复后的数量以 `docs/DEV_STATUS.md` 最新交接记录为准。

### M0-4D 统一输入流水线

`TextCollectionWorkflow` 已原位演进为唯一输入编排，不新增平行业务入口。严格冻结的 `TextInput`、`UrlInput`、`ImageInput` 进入同一 Message、Source、AgentRun 与 `CollectionWriteService`；文字旧 JSON 请求继续兼容。URL 只调用一次现有 `WebContentProvider`，成功正文有界截断后交给唯一 `TextExtractionService`，失败不调用模型并返回补充文字/截图动作。图片 API 使用原始有界请求体而非 Base64，按内容 SHA-256 幂等，只调用一次现有 `ImageRecognitionService`，Source 只保存私有 `file_key`、MIME、大小和摘要。

URL 与图片整链路使用一个不超过 60 秒的共享总墙钟硬兜底。该预算只由既有 `AgentRunService` 在统一工作流外层建立一次，覆盖上传、校验、存储、initial、唯一 repair、解析、数据库写入和清理；initial 与 repair 不会分别重置预算，repair 只能使用 initial 之后的剩余时间。`MODEL_TIMEOUT_SECONDS=75` 只作为 Provider/传输层异常安全上限，正常统一输入流程必须先由应用层 60 秒截止取消进行中的 SDK 请求，因此 60 秒是正常路径唯一可触达的硬截止。20 秒只保留为图片与网页解析的非阻断性能观察目标，超过 20 秒但未达到 60 秒时可以正常完成。真实网页和图片步骤通过既有 AgentRun 收集器写入实际 ToolRun，模型调用继续只保存安全摘要。相同用户、Session 与 key 的重放不会重复消息、来源、Run、网页获取、模型、收藏或文件；不同 Session 隔离。图片识别后若数据库/收藏写入失败、超时或取消，只删除本次新文件。达到硬截止时，进行中的操作会被取消并等待既有清理完成；Provider 传播外部 `CancelledError` 原对象。SDK `max_retries=0`，应用层不自动重试，一次 chat 只产生一次非流式 HTTP 请求。URL 查询、网页正文、图片/Base64、Prompt、模型响应、Cookie、Authorization、私有路径和异常原文不进入公开响应、运行记录或普通日志。若真实请求仍超过 60 秒，不再提高同步上限，后续改由 M1 后台 Job 承载。

本阶段不新增迁移、依赖或配置。现有 Source JSON 元数据已能表达最终 URL、失败码、HTTP 状态、重定向次数、MIME、大小和 SHA-256；当前 Alembic 唯一 head 为 `20260724_0007`。聚焦离线验证：

```bash
python -m pytest -q tests/contract/test_m0_4d_unified_input.py
```

真实 Provider 测试只包含一个无文件、消息或外部 API 副作用的确定性加法工具。获得用户明确授权并完成上述四项模型配置后，从 `backend` 目录运行：

```bash
RUN_REAL_MODEL_TESTS=1 python -m pytest -q -m real_provider -rs
```

该用例最多发出两次非流式 Chat Completions 请求（工具调用与最终回答各一次），SDK 自动重试已关闭。不要使用普通 `pytest` 命令隐式触发真实调用。

## 开发规则与 UX 原型

后续任务开始前依次阅读 `AGENTS.md`、`docs/DEVELOPMENT_STAGES.md`、`docs/DEV_STATUS.md` 和当前阶段相关正式文档。每个任务只处理状态文档允许的一个阶段。

UX 原型是评审用静态页面，不是正式前端。可直接打开 `prototypes/ux/index.html`，或从 `prototypes/ux` 运行 `python3 -m http.server 4173 --bind 127.0.0.1` 后访问 <http://127.0.0.1:4173/>。
