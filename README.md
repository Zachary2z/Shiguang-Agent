# 拾光 Shiguang

拾光是一款“把收藏变成行动”的个人生活 Agent：用户可以保存不同城市中想去、想做或想吃的地点与活动；当前 MVP 由 Agent 结合时间、深圳活动范围、天气、路线和费用生成可执行的单城市计划。

## 当前阶段

项目处于 **M0 技术验证**。M0-2A 至 M0-2D、M0-3A 至 M0-3D、M0-4A 至 M0-4C 均已通过主控验收。当前分支只实施 M0-4D：文字、URL 与图片进入同一个消息、Source、AgentRun/ToolRun、结构抽取和收藏写入流水线；阶段状态为待验收，M0-5 尚未开始。

普通测试全部离线，不读取真实模型或地图密钥，也不访问网络。M0-3B 的单次真实高德授权不延续到本阶段。M0-4D 只使用 Fake Provider、Stub WebContentProvider、固定图片与临时私有目录；真实模型、高德、网页、对象存储及其他外部/付费调用均未授权。计划、SSE、Worker、前端和 M0-5 不在本阶段范围内。

Dockerfile 推迟到 M0-Gate；本阶段不创建 Docker Compose。

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
├── docs/                       # 正式产品、技术、阶段与状态文档
├── prototypes/ux/              # 静态 UX/UI 评审原型
├── .env.example                # 无敏感信息的配置示例
└── README.md
```

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
```

测试进程显式使用 `APP_ENV=test` 并禁止读取开发者真实 `.env`；测试只使用临时 SQLite 数据库，不调用网络或付费 API。

### 数据库迁移

默认数据库是 `backend/data/shiguang.db`，目录和数据库文件均被 Git 忽略。从 `backend` 目录运行：

```bash
python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
```

当前 HEAD revision 是 `20260722_0006`。M0-4D 没有新增迁移：现有 `sources` 已有原始 URL、私有 `file_key`、解析状态、抓取时间和受限 JSON 元数据，足以保存最终 URL、网页失败码、MIME、大小及 SHA-256；现有 Message、AgentRun/ToolRun 与收藏幂等表也可直接复用。应用不会在导入或启动时自动执行迁移，也不使用 `create_all()` 代替 Alembic。

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

## 配置

服务端默认读取仓库根目录 `.env`；可复制 `.env.example` 后按需覆盖。当前实现的变量为：

| 变量 | 默认/示例 | 说明 |
|---|---|---|
| `APP_NAME` | `Shiguang API` | OpenAPI 应用标题 |
| `APP_VERSION` | `0.1.0` | API 版本 |
| `APP_ENV` | `development` | `development`、`test` 或 `production` |
| `APP_TIMEZONE` | `Asia/Shanghai` | 有效 IANA 时区 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/shiguang.db` | M0 异步 SQLite URL |
| `LOG_LEVEL` | `INFO` | 标准 Python 日志级别 |
| `MODEL_API_BASE` | 无 | OpenAI-compatible API Base，仅启用真实 Provider 时必填 |
| `MODEL_API_KEY` | 无 | 服务端密钥，以 `SecretStr` 脱敏，仅启用真实 Provider 时必填 |
| `MODEL_NAME` | 无 | 供应商侧模型名称，仅启用真实 Provider 时必填 |
| `MODEL_TIMEOUT_SECONDS` | `30`（示例） | 有限正数的单次模型请求超时，仅启用真实 Provider 时必填 |
| `MODEL_INPUT_PRICE_PER_MILLION_TOKENS` | 无 | `MODEL_NAME` 的每百万输入 Token Decimal 单价；非负有限值 |
| `MODEL_OUTPUT_PRICE_PER_MILLION_TOKENS` | 无 | `MODEL_NAME` 的每百万输出 Token Decimal 单价；非负有限值 |
| `MODEL_COST_CURRENCY` | `CNY` | 三位大写币种代码 |
| `MODEL_PRICING_SOURCE` | `configured_model_rates` | 可审计的价格配置来源标签 |
| `AGENT_MAX_TOOL_CALLS` | `8` | 单次 Run 绝对工具调用上限，只允许 `1..8` |
| `AGENT_TIMEOUT_SECONDS` | `60` | 单次 Run 总时限，只允许有限值 `(0, 60]` |
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
| `STORAGE_MAX_FILE_SIZE_BYTES` | `10000000` | 流式写入上限，只允许 `1..20000000` 字节 |
| `STORAGE_ALLOWED_CONTENT_TYPES` | `image/jpeg,image/png,image/webp` | 允许类型的逗号分隔子集；声明类型还必须通过集中式文件签名校验 |

`.env` 会被 Git 忽略，不要把真实密钥、Token、Cookie 或账号写入代码、示例、测试输出或提交。

模型价格不会硬编码。只有模型名、输入/输出 Token 和两项配置单价都完整时才使用 Decimal 估算并以 8 位小数保存；未知 Token、模型名变化或价格缺失都会保留未知费用和明确原因，不会伪造零费用。合法的零 Token 与零单价仍得到真实的零费用。

### M0-1C 运行记录

每次应用层执行先创建不可推测的 `trace_id`，持久化 `queued → running`，再进入唯一 Runner。最终状态为 `succeeded`、`partially_succeeded`、`failed` 或 `cancelled`；`waiting_user` 已纳入契约但本阶段不实现审批流程。

Runner 在同一执行循环中保证：最多执行 8 次绝对 Tool Call；第 9 次记录为 blocked 且不执行；使用工具名与规范化 JSON 参数的 SHA-256 指纹阻止异常重复；通过可取消等待和单调时钟把总时限限制在 60 秒。Provider 或 Tool 正在等待时也会被总时限取消，外部 `CancelledError` 落库后继续向调用方传播。

`AgentRunService.get_by_trace_id()` 返回模型调用元数据、Token/费用汇总、有序 ToolRun、安全错误码和结束原因。数据库只保存结构化输入/输出摘要与指纹，不保存消息、完整模型响应、Prompt、思维链、完整工具参数、异常对象、Authorization、Cookie 或密钥。本阶段故意不提供 `GET /agent-runs` 路由。

### M0-2A/B/C 文字收藏、结构化抽取与可逆写入

`app.domain.collections` 是 User、Session、Message、Source、CollectionItem、CollectionSource、Place/Event 类型和收藏状态的唯一应用层契约。实体 ID 使用命名空间加 128 位随机值，服务端时间统一为 UTC；稳定的所有权、状态、版本、Source 抓取时间和 Event 时间使用独立数据库列。Source 元数据使用字段白名单，不接受 Header、Cookie、原始正文或凭证。

`SqlAlchemyCollectionRepository` 的所有公开读写方法都显式要求 `user_id`。Message 通过用户拥有的 Session 查询；CollectionSource 在 Repository 与复合外键两层保证 Source 和 CollectionItem 属于同一用户；跨用户资源与不存在资源采用同一安全结果。默认收藏查询排除 `recognizing`、`failed`、`archived` 和 `deleted`，只有 `active` 具备后续进入计划的状态资格。

`User.default_plan_city` 当前保持深圳计划语义；`CollectionItem.city_hint` 只保存可空的来源城市线索，允许广州、上海等其他城市收藏，不代表正式城市或计划资格。唯一 `TextExtractionService` 使用现有 `ModelProvider` 抽取严格的 Place/Event 候选，普通结果调用一次，结构错误最多修复一次，并明确保留缺失与不确定字段。

唯一 `CollectionWriteService` 将候选、共享 Source、CollectionSource、幂等记录和 Undo 关联放在同一事务中。`user_id + idempotency_key` 与 `user_id + source_id` 的数据库唯一约束覆盖重复消息、并发提交和同来源重试；请求只持久化规范化 SHA-256 指纹。首次成功返回 10 分钟 Undo Token，数据库只保存 Token 哈希，重试不再次返回明文。Undo 只把本次操作创建的条目逻辑删除，不删除 Source 或其他收藏。

`CollectionItemPatch` 只开放标题、城市线索、位置/时间线索、Event 时间、价格、标签、缺失字段和不确定项。成功变更使用 `expected_version` 并递增版本；无实际变化不生成新版本，旧版本不会覆盖新数据。默认查询立即隐藏 `deleted`，内部 `include_inactive` 仍可复核。M0-3 前 Place 自动保存为 `pending_details`，不会伪造 POI 候选、正式城市或计划资格；精确起止时间完整的 Event 才映射为 `active`。

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

URL 与图片整链路使用不超过 20 秒的逻辑预算。真实网页和图片步骤通过既有 AgentRun 收集器写入实际 ToolRun，模型调用继续只保存安全摘要。相同用户、Session 与 key 的重放不会重复消息、来源、Run、网页获取、模型、收藏或文件；不同 Session 隔离。图片识别后若数据库/收藏写入失败、超时或取消，只删除本次新文件。URL 查询、网页正文、图片/Base64、Prompt、模型响应、Cookie、Authorization、私有路径和异常原文不进入公开响应、运行记录或普通日志。

本阶段不新增迁移、依赖或配置。现有 Source JSON 元数据已能表达最终 URL、失败码、HTTP 状态、重定向次数、MIME、大小和 SHA-256；Alembic head 仍为 `20260722_0006`。聚焦离线验证：

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
