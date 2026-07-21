# 拾光 Shiguang

拾光是一款“把收藏变成行动”的个人生活 Agent：用户可以保存不同城市中想去、想做或想吃的地点与活动；当前 MVP 由 Agent 结合时间、深圳活动范围、天气、路线和费用生成可执行的单城市计划。

## 当前阶段

项目处于 **M0 技术验证**。M0-2A 领域模型与 M0-2B 结构化抽取已经主控验收；当前允许开始的子阶段是 **M0-2C 自动保存与可逆操作**，状态为**未开始**。

普通测试全部离线，不读取真实模型密钥或访问网络。当前没有任何真实调用授权；不得设置 `RUN_REAL_MODEL_TESTS=1`。M0-2C 将在现有唯一 Collection Repository 与抽取契约上实现自动保存、幂等和 Undo，不包含 M0-2D API、Demo 初始化、高德、URL/截图流水线、计划、SSE 或前端。

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
python -m pytest -q -m "not real_provider"
python -m pytest -q tests/core
python -m pytest -q tests/test_migrations.py
```

测试进程显式使用 `APP_ENV=test` 并禁止读取开发者真实 `.env`；测试只使用临时 SQLite 数据库，不调用网络或付费 API。

### 数据库迁移

默认数据库是 `backend/data/shiguang.db`，目录和数据库文件均被 Git 忽略。从 `backend` 目录运行：

```bash
python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
```

当前 HEAD revision 是 `20260721_0004`：在 `0003` 的六张收藏领域表之上，将用户字段明确为 `default_plan_city`，并把收藏城市调整为可空 `city_hint`。只有空表或全部 `city_hint='shenzhen'` 时才能安全降级到 `0003`；存在空值或其他城市时会在 DDL 前明确拒绝，避免数据丢失。应用不会在导入或启动时自动执行迁移，也不使用 `create_all()` 代替 Alembic。

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

`.env` 会被 Git 忽略，不要把真实密钥、Token、Cookie 或账号写入代码、示例、测试输出或提交。

模型价格不会硬编码。只有模型名、输入/输出 Token 和两项配置单价都完整时才使用 Decimal 估算并以 8 位小数保存；未知 Token、模型名变化或价格缺失都会保留未知费用和明确原因，不会伪造零费用。合法的零 Token 与零单价仍得到真实的零费用。

### M0-1C 运行记录

每次应用层执行先创建不可推测的 `trace_id`，持久化 `queued → running`，再进入唯一 Runner。最终状态为 `succeeded`、`partially_succeeded`、`failed` 或 `cancelled`；`waiting_user` 已纳入契约但本阶段不实现审批流程。

Runner 在同一执行循环中保证：最多执行 8 次绝对 Tool Call；第 9 次记录为 blocked 且不执行；使用工具名与规范化 JSON 参数的 SHA-256 指纹阻止异常重复；通过可取消等待和单调时钟把总时限限制在 60 秒。Provider 或 Tool 正在等待时也会被总时限取消，外部 `CancelledError` 落库后继续向调用方传播。

`AgentRunService.get_by_trace_id()` 返回模型调用元数据、Token/费用汇总、有序 ToolRun、安全错误码和结束原因。数据库只保存结构化输入/输出摘要与指纹，不保存消息、完整模型响应、Prompt、思维链、完整工具参数、异常对象、Authorization、Cookie 或密钥。本阶段故意不提供 `GET /agent-runs` 路由。

### M0-2A/B 文字收藏领域与结构化抽取

`app.domain.collections` 是 User、Session、Message、Source、CollectionItem、CollectionSource、Place/Event 类型和收藏状态的唯一应用层契约。实体 ID 使用命名空间加 128 位随机值，服务端时间统一为 UTC；稳定的所有权、状态、版本、Source 抓取时间和 Event 时间使用独立数据库列。Source 元数据使用字段白名单，不接受 Header、Cookie、原始正文或凭证。

`SqlAlchemyCollectionRepository` 的所有公开读写方法都显式要求 `user_id`。Message 通过用户拥有的 Session 查询；CollectionSource 在 Repository 与复合外键两层保证 Source 和 CollectionItem 属于同一用户；跨用户资源与不存在资源采用同一安全结果。默认收藏查询排除 `recognizing`、`failed`、`archived` 和 `deleted`，只有 `active` 具备后续进入计划的状态资格。

`User.default_plan_city` 当前保持深圳计划语义；`CollectionItem.city_hint` 只保存可空的来源城市线索，允许广州、上海等其他城市收藏，不代表正式城市或计划资格。唯一 `TextExtractionService` 使用现有 `ModelProvider` 抽取严格的 Place/Event 候选，普通结果调用一次，结构错误最多修复一次，并明确保留缺失与不确定字段。

M0-2C 开始前尚未提供自动保存、幂等、修改、逻辑删除、Undo 或 API 路由。CollectionItem 的正整数 `version` 继续作为并发边界；正式城市确认和 POI 匹配属于 M0-3。

真实 Provider 测试只包含一个无文件、消息或外部 API 副作用的确定性加法工具。获得用户明确授权并完成上述四项模型配置后，从 `backend` 目录运行：

```bash
RUN_REAL_MODEL_TESTS=1 python -m pytest -q -m real_provider -rs
```

该用例最多发出两次非流式 Chat Completions 请求（工具调用与最终回答各一次），SDK 自动重试已关闭。不要使用普通 `pytest` 命令隐式触发真实调用。

## 开发规则与 UX 原型

后续任务开始前依次阅读 `AGENTS.md`、`docs/DEVELOPMENT_STAGES.md`、`docs/DEV_STATUS.md` 和当前阶段相关正式文档。每个任务只处理状态文档允许的一个阶段。

UX 原型是评审用静态页面，不是正式前端。可直接打开 `prototypes/ux/index.html`，或从 `prototypes/ux` 运行 `python3 -m http.server 4173 --bind 127.0.0.1` 后访问 <http://127.0.0.1:4173/>。
