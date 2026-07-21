# 拾光 Shiguang

拾光是一款“把收藏变成行动”的个人生活 Agent：用户保存想去、想做或想吃的地点与活动，之后由 Agent 结合时间、范围、天气、路线和费用生成可执行的深圳同城计划。

## 当前阶段

项目处于 **M0 技术验证**。当前开发子阶段是 **M0-1B 真实百炼接入**，状态为**待验收（真实验证未执行）**：应用层已实现 OpenAI-compatible Chat Completions Provider，并复用唯一的 Nanobot Core Provider、Runner 与 Tool Registry 契约。

普通测试全部离线，不读取真实模型密钥或访问网络。真实 Tool Calling 入口必须同时具备完整模型配置并显式设置 `RUN_REAL_MODEL_TESTS=1`；未经用户授权不得运行。当前不包含 Provider 自动重试、AgentRun/ToolRun、trace_id、收藏/地点/计划/记忆等业务功能，也没有前端；M0-1B 真实验证通过前不会进入 M0-1C。

Dockerfile 推迟到 M0-Gate；本阶段不创建 Docker Compose。

## 仓库目录

```text
Shiguang_Nanobot/
├── backend/
│   ├── app/                    # FastAPI、配置、日志和数据库基础设施
│   ├── nanobot_core/           # 与 Web、数据库和业务解耦的最小 Agent 核心
│   ├── migrations/             # Alembic 空基线迁移
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
```

测试进程显式使用 `APP_ENV=test` 并禁止读取开发者真实 `.env`；测试只使用临时 SQLite 数据库，不调用网络或付费 API。

### 数据库迁移

默认数据库是 `backend/data/shiguang.db`，目录和数据库文件均被 Git 忽略。从 `backend` 目录运行：

```bash
python -m alembic upgrade head
python -m alembic downgrade base
python -m alembic upgrade head
```

当前 revision 是无业务表的 M0-0B 基线。应用不会在导入或启动时自动执行迁移，也不使用 `create_all()` 代替 Alembic。

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
| `RUN_REAL_MODEL_TESTS` | `0` | 只有精确设为 `1` 才授权真实 Provider 测试 |

`.env` 会被 Git 忽略，不要把真实密钥、Token、Cookie 或账号写入代码、示例、测试输出或提交。

真实 Provider 测试只包含一个无文件、消息或外部 API 副作用的确定性加法工具。获得用户明确授权并完成上述四项模型配置后，从 `backend` 目录运行：

```bash
RUN_REAL_MODEL_TESTS=1 python -m pytest -q -m real_provider -rs
```

该用例最多发出两次非流式 Chat Completions 请求（工具调用与最终回答各一次），SDK 自动重试已关闭。不要使用普通 `pytest` 命令隐式触发真实调用。

## 开发规则与 UX 原型

后续任务开始前依次阅读 `AGENTS.md`、`docs/DEVELOPMENT_STAGES.md`、`docs/DEV_STATUS.md` 和当前阶段相关正式文档。每个任务只处理状态文档允许的一个阶段。

UX 原型是评审用静态页面，不是正式前端。可直接打开 `prototypes/ux/index.html`，或从 `prototypes/ux` 运行 `python3 -m http.server 4173 --bind 127.0.0.1` 后访问 <http://127.0.0.1:4173/>。
