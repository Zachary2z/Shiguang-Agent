# 拾光开发状态

| 项目 | 当前值 |
|---|---|
| 当前总阶段 | M0 技术验证 |
| 当前子阶段 | M0-2A 领域模型 |
| 状态 | 未开始 |
| 当前分支 | main |
| 最近更新 | 2026-07-21 |
| 阻塞项 | 无；M0-2A 前置条件已满足 |

## 当前任务

M0-1C 已通过主控独立 QA 并纯快进集成到 `main`：唯一 Runner 在核心内部强制 8 次绝对工具调用和 60 秒总时限硬上限，AgentRun/ToolRun 契约、两张 SQLite 表、Repository/服务、trace 查询、Token/Decimal 费用估算及安全运行摘要均已验收。M0-2A 领域模型前置条件已满足，但尚未开始开发。

## M0 状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| M0-0A 项目基线与资料迁移 | 已完成 | 主控验收通过，阶段提交 `79848c7` 已集成到 `main` |
| M0-0B 后端工程骨架 | 已完成 | 主控验收通过，阶段提交 `6cd5646` 已集成到 `main` |
| M0-0C Nanobot 核心迁移 | 已完成 | 主控验收通过，阶段提交 `5c4a8fb` 已集成到 `main` |
| M0-1 模型与运行记录 | 已完成 | M0-1A、M0-1B、M0-1C 均已通过主控验收 |
| M0-2 文字收藏 | 未开始 | M0-2A 领域模型前置条件已满足，允许开始 |
| M0-3 地点匹配 | 未开始 | 依赖 M0-2 |
| M0-4 URL 与截图 | 未开始 | 依赖 M0-3 |
| M0-5 计划技术验证 | 未开始 | 依赖 M0-2、M0-3 |
| M0-Gate 阶段验收 | 未开始 | 依赖全部 M0 阶段 |

状态只允许使用：未开始、进行中、待验收、已完成、阻塞。

## 已完成

- 产品 PRD、核心用户流程、竞品分析和 MVP 技术方案已在学习目录完成。
- HTML UX/UI 评审原型已完成，可作为正式前端的设计基线。
- 已创建独立 Git 仓库 Shiguang_Nanobot。
- 已建立完整开发阶段文档和仓库级开发规则。
- M0-0A 已完成：正式产品文档、技术方案与 UX 原型已迁入本仓库，README、Git 忽略规则和 Nanobot 许可证归属说明已建立。
- M0-0B 已完成：FastAPI 后端骨架、测试隔离配置、异步 SQLite、Alembic 空基线迁移、安全请求日志和自动化测试基线已通过主控验收。
- M0-0C 已完成：唯一且业务无关的 Nanobot Core、结构化 ToolResult、Provider 抽象、离线 Fake 测试和 Nanobot MIT 许可证归属已通过主控验收。
- M0-1A 已完成：供应商无关的模型响应元数据、Token/完成原因契约、五类 Provider 错误和完全离线 Fake 覆盖已通过主控验收。
- M0-1B 已完成：唯一应用层 OpenAI-compatible 百炼 Provider、固定非思考模式、离线错误与安全覆盖及一次真实 Tool Calling 链路已通过主控验收。
- M0-1C 已完成：唯一 Runner 的运行硬上限、AgentRun/ToolRun 持久化、trace 查询、运行终结、Token/费用汇总、安全摘要和迁移往返已通过主控验收。

## 下一步

从本状态文档提交后的最新 `main` 创建 `codex/m0-2-text-collection`，只实施 M0-2A：User、Session、Message、Source、CollectionItem、CollectionSource、收藏状态机、Repository 接口和用户隔离。不得提前实现结构化抽取、自动保存/Undo、收藏 API、高德、URL/截图或其他 M0-2B 及后续能力；未经新授权不得调用真实或付费 API。

## 阶段交接记录

每个窗口结束时在下面追加，不覆盖历史记录。

### 交接模板

#### YYYY-MM-DD｜阶段编号｜状态

- 分支：
- 提交：
- 完成内容：
- 主要文件：
- 验证命令：
- 验证结果：
- 未完成：
- 已知风险：
- 下一步：

#### 2026-07-21｜M0-0A｜待验收

- 分支：`codex/m0-0a-project-baseline`
- 提交：阶段提交将在本文件更新后的最终暂存检查通过后创建，实际哈希见最终交接报告
- 完成内容：创建项目 README、Git 忽略规则与 Nanobot 来源/许可证说明；迁入 3 份产品文档、1 份技术方案和 4 个静态 UX 原型文件；修复技术方案到正式原型的仓库内相对链接
- 主要文件：`README.md`、`.gitignore`、`NOTICE.md`、`docs/product/*`、`docs/technical/*`、`prototypes/ux/*`
- 验证命令：`shasum -a 256`、`cmp`、`diff -u`、Markdown/HTML/CSS 本地引用检查脚本、`node --check prototypes/ux/app.js`、`python3 -m http.server`、`curl`、浏览器视觉与页面切换检查、`git check-ignore`、`rg` 敏感信息扫描、文件与阶段范围检查、`git diff --cached --check`、`git diff --cached --name-status`
- 验证结果：11 个只读参考文件迁移前后 SHA-256 一致；7 个原样迁移文件逐字节一致，技术方案只有设计基线路径发生预期变化；本地 Markdown/HTML/CSS 引用无缺失；入口、CSS 和 JS 返回 200，8 个原型页面可渲染并切换，浏览器控制台无警告或错误；未发现高置信密钥、非空凭证赋值、PRD Word 文件或越界工程目录；`.DS_Store` 和敏感本机文件会被忽略，测试 Fixture 仍可跟踪；12 个 staged 文件均在 M0-0A 范围内，除保留的上游 Markdown 硬换行格式外无空白问题或冲突标记
- 未完成：等待主控任务验收；未调用真实模型、高德或其他 API，未做 Windows 跨平台验证
- 已知风险：外部竞品链接未在本阶段联网重验；浏览器会惯例请求原型未声明的 `favicon.ico` 并收到 404，但显式引用的 CSS 和 JS 均正常；两个上游 Markdown 文件保留了用于硬换行的行尾双空格及一个末尾空行，因此完整 `git diff --cached --check` 会报告 7 条已审阅的格式提示；只读 Nanobot 学习仓库在本任务开始前已有大量未提交改动，本阶段通过所需源文件 SHA-256 前后对比确认未再改动
- 下一步：主控任务复核阶段提交与验收结果；验收通过后另开 M0-0B 任务，本窗口不继续开发

#### 2026-07-21｜M0-0A｜已完成（主控验收）

- 分支：`main`（由 `codex/m0-0a-project-baseline` 快进集成）
- 提交：`79848c7`（M0-0A 阶段提交）
- 完成内容：主控任务复核 M0-0A 文件范围、迁移一致性、仓库内链接、静态原型加载、忽略规则、敏感信息和越界目录后验收通过，并将阶段提交快进集成到 `main`
- 主要文件：`README.md`、`.gitignore`、`NOTICE.md`、`docs/product/*`、`docs/technical/*`、`prototypes/ux/*`
- 验证命令：`git diff --stat main..codex/m0-0a-project-baseline`、`cmp`、`diff -u`、`node --check prototypes/ux/app.js`、本地 `python3 -m http.server` 与 `curl`、`git check-ignore`、敏感信息和越界目录扫描、`git status`
- 验证结果：3 份产品文档和 4 个 UX 文件与只读来源一致；技术方案仅包含预期的仓库内原型链接修复；原型入口、CSS 和 JS 均返回 200；JavaScript 语法检查通过；`.DS_Store` 被忽略；未发现 PRD Word 文件、真实凭证、后端/前端工程或其他越界实现；集成前工作区干净
- 未完成：未进行 Windows 跨平台验证，未联网复验竞品外链；这些不阻塞资料迁移阶段完成
- 已知风险：上游 Markdown 为语义换行保留的行尾双空格会触发 7 条 `git show --check` 格式提示；该格式来自正式文档且不影响渲染或后续开发
- 下一步：从最新 `main` 创建 `codex/m0-0b-backend-scaffold`，只实施 M0-0B 后端工程骨架

#### 2026-07-21｜M0-0B｜待验收

- 分支：`codex/m0-0b-backend-scaffold`
- 基线：`bde8203c27ecf5f4a1ca1e01ace89f377160e915`（包含已验收 M0-0A）
- 提交：阶段提交将在最终暂存检查通过后创建，实际哈希见最终交接报告
- 完成内容：建立 Python 3.11+ PEP 621 可编辑安装包、Pydantic Settings、FastAPI app factory 与 Uvicorn 入口、`GET /healthz`、安全 Request ID 与基础请求日志、异步 SQLite/SQLAlchemy Engine 与 Session 生命周期、Alembic 空基线 revision，以及配置/API/数据库/迁移自动化测试
- 主要文件：`backend/pyproject.toml`、`backend/app/config.py`、`backend/app/main.py`、`backend/app/observability.py`、`backend/app/infrastructure/db/*`、`backend/migrations/*`、`backend/tests/*`、`.env.example`、`README.md`
- 新增配置：`APP_NAME`、`APP_VERSION`、`APP_ENV`、`APP_TIMEZONE`、`DATABASE_URL`、`LOG_LEVEL`；测试通过 `_env_file=None` 和 `APP_ENV=test` 显式禁止读取真实 `.env`
- 验证环境：全新 `/tmp/shiguang-m0-0b-venv-20260721-1`，Python 3.13.5，`python -m pip install -e './backend[dev]'`，依赖完整性检查无错误
- 验证命令：`python -m ruff check .`、`python -m mypy app migrations`、`python -m pytest -q`；临时 SQLite 上依次执行 `python -m alembic upgrade head`、`downgrade base`、`upgrade head`；使用临时 SQLite 启动 `python -m uvicorn app.main:app --host 127.0.0.1 --port 18080` 并用 `curl` 验证自动和显式 `X-Request-ID`；另执行 `git diff --check`、忽略规则、范围、数据库残留、冲突标记和高置信密钥扫描
- 验证结果：Ruff 通过；mypy 对 10 个源文件无问题；pytest 收集 13 项，13 通过、0 失败、0 跳过；Alembic 升级、回滚、再次升级均通过且只有 `alembic_version` 表；Uvicorn 启停正常，两次 `/healthz` 均返回 HTTP 200 和 `{"status":"ok"}`，响应头分别生成和回显 Request ID，关闭后端口无残留监听；无真实或付费 API 调用
- 数据迁移：新增 `20260721_0001` 空基线 revision，不创建任何业务表；应用不在导入或启动时自动迁移，也不调用 `create_all()`
- Dockerfile：按阶段默认建议推迟到 M0-Gate；未创建 Dockerfile 或 Docker Compose
- 未完成：等待主控任务验收；未在 Python 3.11/3.12 和 Windows 上重复验证；未进行任何模型、高德、微信、PostgreSQL 或云环境验证
- 已知风险：当前仅验证 SQLite/aiosqlite；默认本地数据库是开发用途，M1 才切换 PostgreSQL；日志仅提供 M0-0B 请求级追踪，不包含后续 AgentRun/ToolRun 可观测能力
- 下一步：主控任务在全新 Python 3.11+ 环境复现验收并检查 staged diff；通过后集成本阶段，再另开 M0-0C，本分支不继续开发

#### 2026-07-21｜M0-0B｜已完成（主控验收）

- 分支：`main`（由 `codex/m0-0b-backend-scaffold` 快进集成）
- 提交：`6cd5646`（完整提交 `6cd56463fda6fd55b12570fceed0e7aef84e8f86`）
- 完成内容：主控任务确认待验收分支与指定提交一致，复核后端工程骨架、依赖和阶段边界；未发现 M0-0C 提前开发、业务实体、真实 Provider、前端、付费调用或第二套 AgentRunner/ToolRegistry/Provider；阶段提交已快进集成到 `main`
- 主要文件：`backend/pyproject.toml`、`backend/app/config.py`、`backend/app/main.py`、`backend/app/observability.py`、`backend/app/infrastructure/db/*`、`backend/migrations/*`、`backend/tests/*`、`.env.example`、`README.md`
- 验证命令：在指定提交的独立 `git archive` 快照和全新 Python 3.13.5 虚拟环境中执行 `python -m pip install -e './backend[dev]'`、`python -m pip check`、`python -m ruff check .`、`python -m mypy app migrations`、`python -m pytest -q`；在临时 SQLite 上执行 Alembic `upgrade head`、`downgrade base`、再次 `upgrade head`；启动 Uvicorn 后用 `curl` 验证健康检查、404、自动/显式/边界 Request ID 和敏感日志；另执行提交一致性、范围、生成产物、忽略规则、绝对路径和敏感信息扫描；合并后重复 Ruff、mypy 和 pytest
- 验证结果：全新环境安装和依赖完整性检查通过；Ruff 通过；mypy 对 10 个源文件无问题；pytest 13 项全部通过、0 失败、0 跳过；Alembic 升降级往返通过且仅创建 `alembic_version` 表；Uvicorn 启停和 `/healthz` 通过；128 字符 Request ID 被保留，129 字符和非法值被安全替换；查询参数、Authorization 和 Cookie 标记未进入日志；启动连接失败会关闭数据库资源，Session 异常会回滚；合并未产生冲突或额外代码变化，合并后复检再次全部通过；没有未关闭的 P0/P1，未调用真实或付费 API
- 异常、边界与幂等：覆盖无真实 `.env`、无效时区、非异步 SQLite URL、数据库启动失败、Session 异常、404、非法及长度边界 Request ID；健康检查为只读操作，迁移升级/降级/再次升级可重复执行；本阶段没有业务写接口、任务或外部副作用，因此业务幂等不适用
- 未完成：未在 Python 3.11/3.12 和 Windows 上重复验证；未验证真实模型、高德、微信、PostgreSQL 或云环境，这些均不属于 M0-0B 验收范围
- 已知风险：当前只支持并验证 SQLite/aiosqlite；M1 才切换 PostgreSQL；请求级日志不包含后续 AgentRun/ToolRun 可观测能力，这些是已记录的后续阶段事项，不阻塞 M0-0B
- 下一步：M0-0C 前置条件已满足；从最新 `main` 创建 `codex/m0-0c-nanobot-core`，只迁移唯一且业务无关的最小 Nanobot Core，完成后交回主控验收

#### 2026-07-21｜M0-0C｜待验收

- 分支：`codex/m0-0c-nanobot-core`
- 基线：`07cd4578e390ceb026b16e7f44827f7be68db9e6`（包含已验收 M0-0B `6cd56463fda6fd55b12570fceed0e7aef84e8f86`）
- 提交：阶段提交将在最终暂存检查通过后创建，实际完整哈希见最终交接报告
- 完成内容：建立唯一的 `backend/nanobot_core`，提供 `AgentRunner`、无持久化 `AgentLoop`、业务无关 `AgentContext`、严格 Pydantic `ToolInput`、确定性 `ToolRegistry`、结构化 `ToolResult`、`ModelProvider`/`ModelResponse`/`ToolCall` 抽象；Runner 支持直接文本、单次/多轮/单响应多工具调用、未知工具、参数错误、执行异常、空响应和循环上限，并隔离调用者原始消息
- 迁移来源及改造：实际读取只读学习目录中基于 `06f47fa54032d539b215c4b58d82564a6fa4aa48` 的 `runner.py`、`loop.py`、`context.py`、Tool/Registry、Provider 基类、对应教学测试和 `LICENSE`；保留 model → tool → model 核心思想，改用结构化错误、Pydantic Schema、稳定序列化与显式依赖注入；舍弃文件工具、workspace、Markdown MemoryStore、JSONL SessionStore、CLI 和真实 OpenAI-compatible Provider
- 主要文件：`backend/nanobot_core/*`、`backend/tests/core/*`、`backend/pyproject.toml`、`NOTICE.md`、`README.md`、`backend/README.md`、`docs/DEV_STATUS.md`
- 验证环境：仓库根目录被 Git 忽略的 `.venv`，Python 3.13.5；`backend[dev]` 已安装且 `python -m pip check` 通过；测试不读取真实 `.env`，不使用数据库文件、模型/高德密钥或网络
- 验证命令：修改前执行 `python -m ruff check .`、`python -m mypy app migrations`、`python -m pytest -q`（13 项基线通过）；实现后执行 `python -m pip install -e './backend[dev]'`、`python -m pip check`、`python -m ruff check .`、`python -m mypy app migrations nanobot_core`、`python -m pytest -q`、`python -m pytest tests/core -q`，并从仓库外目录导入 `nanobot_core`；使用 `python -m pip wheel --no-deps` 构建临时 wheel 并检查核心模块与 Nanobot MIT License 均被打包；另执行 `git diff --check`、范围和重复核心搜索、静态反向依赖扫描、真实 Provider/网络/文件工具扫描、凭证扫描、生成物与数据库残留检查、许可证全文检查及只读学习源 SHA-256 复核
- 验证结果：editable 重装、仓库外导入、临时 wheel 构建和依赖完整性检查通过；实现后 Ruff 通过；mypy 对 20 个源文件无问题；pytest 共 58 项全部通过、0 失败、0 跳过，其中核心 45 项全部通过且重复运行一致；M0-0B 原有 13 项保持通过；未调用真实或付费 API
- 异常、边界与安全覆盖：覆盖 Provider 直接文本、单次/多轮/单响应多工具调用、未知工具、非法 JSON、缺少/未知/错误类型参数、工具异常脱敏、Provider `None`/空白响应、输入消息深拷贝、`max_iterations` 零值/负值/最小值/精确边界、ToolResult 状态不变量、重复注册与稳定工具定义顺序；静态测试禁止核心导入 FastAPI、SQLAlchemy、Alembic、aiosqlite、httpx、openai、`app` 或 `pathlib`
- 未完成：等待主控独立验收；未实现真实模型 Provider、Provider 供应商错误映射、AgentRun/ToolRun、trace_id、Token/费用/超时、数据库持久化、业务工具或任何 M0-1 内容
- 已知风险：`max_iterations` 当前定义为 Provider/工具循环轮数；单次模型响应可以按要求包含多个工具调用，绝对工具调用总数与总时长限制属于后续 M0-1C；本窗口在 Python 3.13.5 上验证，尚未在 Python 3.11/3.12 和 Windows 上复测
- 下一步：主控窗口在全新 Python 3.11+ 环境独立复测、审阅来源和边界并决定是否集成；本窗口停止开发，不合并 `main`，不开始 M0-1

#### 2026-07-21｜M0-0C｜已完成（主控验收）

- 分支：`main`（由 `codex/m0-0c-nanobot-core` 快进集成）
- 提交：`5c4a8fbf68deaf6dbc5336cef7a2a0abbac9b8a5`
- 完成内容：主控任务确认阶段分支、指定提交和 `07cd4578e390ceb026b16e7f44827f7be68db9e6` 基线一致；复核唯一 `AgentRunner`、`AgentLoop`、`AgentContext`、`Tool`/`ToolRegistry`/`ToolResult` 和 `ModelProvider` 契约，确认没有真实 Provider、数据库运行记录、拾光业务或 M0-1 提前实现；阶段提交已快进集成到 `main`
- 主要文件：`backend/nanobot_core/*`、`backend/tests/core/*`、`backend/pyproject.toml`、`NOTICE.md`、`README.md`、`backend/README.md`、`docs/DEV_STATUS.md`
- 来源与许可证：只读学习仓库 HEAD 为 `06f47fa54032d539b215c4b58d82564a6fa4aa48`；NOTICE 列明实际参考和改写文件，正式包内包含 Nanobot MIT License 全文；许可证副本与只读来源正文一致，仅补充末尾换行；QA 未修改只读学习目录
- 验证环境：指定提交的独立 `git archive` 快照、全新 Python 3.13.5 虚拟环境和重新安装的 `backend[dev]`；`pip check` 无破损依赖；未读取真实密钥，未调用真实或付费 API
- 验证命令：`python -m pip install -e '<快照>/backend[dev]'`、`python -m pip check`、`python -m ruff check .`、`python -m mypy app migrations nanobot_core`、`python -m pytest -q`、使用两个不同 `PYTHONHASHSEED` 分别重复 `python -m pytest tests/core -q`、`python -m pip wheel --no-deps` 和 wheel 内容检查；另执行提交/范围/重复核心/反向依赖/真实 Provider/网络/文件系统/密钥/生成产物扫描及独立离线异常脚本；合并后重复 Ruff、mypy 和完整 pytest
- 验证结果：全新环境安装、依赖检查和 wheel 构建通过，wheel 包含全部核心模块及 Nanobot MIT License；Ruff 通过；mypy 对 20 个源文件无问题；完整 pytest 58 项全部通过、0 失败、0 跳过；核心 pytest 45 项在两个哈希种子下均通过；合并未产生冲突或额外代码变化，合并后 58 项再次全部通过；没有未关闭的 P0/P1
- 异常、边界、幂等与安全：覆盖直接文本、单次/多轮/单响应多工具、未知工具、非法 JSON、缺失/额外/错误类型参数、工具异常及无效返回脱敏、Provider `None`/空白响应、消息深拷贝、零值/负值/最小值/精确循环边界、重复注册、确定性工具定义与 ToolResult 序列化；在禁用网络连接并设置假密钥标记的环境中补充验证，无网络调用和敏感输入/异常泄漏；本阶段没有数据库或业务写操作，业务幂等不适用，重复注册和重复离线执行结果保持确定
- 未完成：未实现真实模型 Provider、真实 Tool Calling、Provider 供应商适配、AgentRun/ToolRun、trace_id、总时长、绝对工具调用数、Token/费用持久化或数据库迁移；这些分别属于 M0-1B/M0-1C
- 已知风险：`max_iterations` 目前限制 Provider/工具循环轮数，单次响应允许多个工具调用；绝对工具调用数和 60 秒总时长将在 M0-1C 实施；QA 使用 macOS/Python 3.13.5，未在 Python 3.11/3.12 或 Windows 复测，这不阻塞 Python 3.11+ 阶段要求
- 下一步：M0-1A 前置条件已满足；从最新 `main` 创建 `codex/m0-1-agent-runtime`，只扩展 Provider 契约和离线错误分类，完成后交回主控验收

#### 2026-07-21｜M0-1A｜待验收

- 分支：`codex/m0-1-agent-runtime`
- 基线：`94618d1be0b2e4618fc3ec19d5e22c6b1539ba44`（包含已验收 M0-0C `5c4a8fbf68deaf6dbc5336cef7a2a0abbac9b8a5`）
- 提交：本交接记录随 M0-1A 阶段提交一并创建，实际完整哈希见开发窗口最终交接报告
- Provider 响应字段：`ModelResponse` 必填 `model_name`、`usage`、`latency_ms`、`finish_reason`，保留 `content` 与 `tool_calls`；`provider_request_id` 可为 `None` 表示供应商未提供，空白 ID 非法；耗时以非负整数毫秒表示，零值合法
- Token 契约：`TokenUsage` 是响应必填对象，`input_tokens`、`output_tokens`、`total_tokens` 均可独立为 `None` 表示未知，零值合法，负数和布尔值非法；两项分量均已知而总量未知时自动求和，显式总量不得小于任一已知分量，三项齐全时必须严格满足总量等于两分量之和
- 完成原因：`FinishReason` 只暴露 `stop`、`tool_calls`、`length`、`content_filter`、`unknown` 五种供应商无关语义；原始供应商字符串不进入公共 DTO；存在工具调用时必须使用 `tool_calls`，该原因也必须至少包含一个工具调用
- Provider 错误：统一 `ProviderError` 携带强类型 `ProviderErrorCode`、固定安全摘要、`retryable` 和可选 `retry_after_seconds`；`PROVIDER_TIMEOUT` 与 `PROVIDER_RATE_LIMITED` 可重试，`PROVIDER_AUTHENTICATION_FAILED`、`PROVIDER_INVALID_RESPONSE` 与 `PROVIDER_ERROR` 不可重试；retry-after 仅限限流且必须为有限非负数；`to_public_dict()` 不包含异常链、原始响应、密钥或堆栈
- Fake Provider：单一离线 `FakeProvider` 可按队列依次返回完整文本响应、完整 Tool Calling 响应、`None` 边界结果，或抛出五类 `ProviderError`/`asyncio.CancelledError`；每次调用继续深拷贝保存 messages 和 tools，调用者后续修改不影响历史快照；`fake_response` 只提供确定性测试元数据，不复制真实 Provider 算法
- Runner 兼容：`AgentRunner` 无需生产代码修改；既有直接文本、单次/多轮/单响应多工具、失败与循环边界行为全部保持，Provider 错误不会变成成功回答，`asyncio` 取消不会被吞掉
- 主要文件：`backend/nanobot_core/providers/base.py`、`backend/nanobot_core/providers/__init__.py`、`backend/nanobot_core/__init__.py`、`backend/tests/core/fakes.py`、`backend/tests/core/test_provider_contract.py`、既有 Runner/Loop 测试、`README.md`、`backend/README.md`、`docs/DEV_STATUS.md`
- 验证环境：仓库根目录被 Git 忽略的 `.venv`，macOS、Python 3.13.5；使用现有已安装的 `backend[dev]`，`python -m pip check` 无破损依赖；测试通过既有配置禁止读取真实 `.env`，全部使用 Fake、Stub 和固定 Fixture
- 验证命令：修改前在 `backend` 执行 `python -m pip check`、`python -m ruff check .`、`python -m mypy app migrations nanobot_core`、`python -m pytest -q`、`python -m pytest tests/core -q`；实现后重复前四项，并分别以 `PYTHONHASHSEED=11` 和 `PYTHONHASHSEED=29` 执行核心测试；另执行仓库外导入、`git diff --check`、变更范围、重复公共契约、反向依赖、真实 Provider/SDK/网络、硬编码端点/凭证、配置/依赖/迁移变化及 tracked 缓存/数据库扫描
- 验证结果：修改前全量 58 项、核心 45 项全部通过；实现后 Ruff 通过，mypy 对 20 个源文件无问题，全量 pytest 99 项全部通过、0 失败、0 跳过，核心 pytest 86 项全部通过且两个哈希种子结果一致；公共导出可从仓库外目录导入；只存在一套 `ModelProvider`、`ModelResponse`、`ProviderError`、`AgentRunner` 和 `ToolRegistry`
- 异常、边界与安全覆盖：覆盖完整文本/工具元数据、未知/零/正常 Token、自动总量、负数/布尔 Token、分项不一致、负数/布尔耗时、缺失/存在/空白请求 ID、五种完成原因及工具原因不变量、五类错误与重试语义、retry-after 边界、错误公共序列化脱敏、Fake 混合结果顺序、深拷贝快照、Runner 错误及取消透传；静态测试禁止核心导入 FastAPI、SQLAlchemy、Alembic、aiosqlite、httpx、openai、dashscope、常见网络客户端、底层网络模块或 `app`
- 依赖、配置与迁移：均未修改；未新增模型名、API Base、密钥或超时配置；未修改 `NOTICE.md`，因为没有新增或迁移第三方代码；没有数据库或 Alembic 变化
- 未完成：等待主控独立验收；未实现 M0-1B 真实百炼/OpenAI-compatible Provider、真实 Tool Calling、供应商 SDK 错误映射或网络调用；未实现 M0-1C AgentRun、ToolRun、trace_id、费用/Token 持久化、总时长、绝对工具调用数、自动重试或数据库迁移
- 已知风险：尚未用真实百炼响应验证 M0-1B 的字段和错误映射；固定安全摘要当前为英文，后续应用层可按稳定错误码本地化；本窗口仅在 macOS/Python 3.13.5 复测，未在 Python 3.11/3.12 或 Windows 验证
- 主控复测范围：从指定基线确认阶段分支只包含 M0-1A 授权改动；在干净 Python 3.11+ 环境复现安装与所有规定命令；重点复核 Token 一致性、完成原因归一化、固定摘要无敏感泄漏、Fake 顺序/快照、Runner 异常透传、唯一公共契约及无真实 SDK/网络/配置/迁移边界
- 下一步：主控验收通过后再决定是否快进集成并另开 M0-1B；本开发窗口停止，不合并 `main`，不实现后续子阶段

#### 2026-07-21｜M0-1A｜已完成（主控验收）

- 分支：`main`（由 `codex/m0-1-agent-runtime` 快进集成）
- 提交：`4036c10205038b27f530873d32a2c5fcca0ade4f`
- 完成内容：主控任务确认阶段分支、指定提交和 `94618d1be0b2e4618fc3ec19d5e22c6b1539ba44` 基线一致；复核 `ModelResponse` 元数据、`TokenUsage`、`FinishReason`、五类 `ProviderError`、公开脱敏表示及唯一离线 `FakeProvider`，阶段提交已快进集成到 `main`
- 主要文件：`backend/nanobot_core/providers/base.py`、`backend/nanobot_core/providers/__init__.py`、`backend/nanobot_core/__init__.py`、`backend/tests/core/fakes.py`、`backend/tests/core/test_provider_contract.py`、现有 Runner/Loop 测试、`README.md`、`backend/README.md`、`docs/DEV_STATUS.md`
- 范围与冗余：只扩展既有唯一 `ModelProvider` 和 `ModelResponse`，没有新增第二套 Provider、Runner、ToolRegistry、DTO 或错误枚举；根包与 providers 包仅做公共 API 重导出，不复制实现；`fake_response` 集中消除了既有 Runner/Loop 测试的重复元数据构造；未发现无用兼容层、死代码、大规模复制或 M0-1B/M0-1C 提前实现
- 验证环境：指定提交的独立 `git archive` 快照、全新 Python 3.13.5 虚拟环境和重新安装的 `backend[dev]`；`pip check` 无破损依赖；未读取真实密钥，未调用真实或付费 API
- 验证命令：`python -m pip install -e '<快照>/backend[dev]'`、`python -m pip check`、`python -m ruff check .`、`python -m mypy app migrations nanobot_core`、`python -m pytest -q`、分别以 `PYTHONHASHSEED=11` 和 `PYTHONHASHSEED=29` 执行 `python -m pytest tests/core -q`、仓库外隔离导入；另执行提交/范围/重复契约/反向依赖/真实 SDK/网络/硬编码端点/凭证/配置/迁移/tracked 产物扫描及独立离线异常脚本；合并后重复 Ruff、mypy 和完整 pytest
- 验证结果：全新环境安装和依赖检查通过；Ruff 通过；mypy 对 20 个源文件无问题；完整 pytest 99 项全部通过、0 失败、0 跳过；核心 pytest 86 项在两个哈希种子下均通过；公共契约可从仓库外导入；合并未产生冲突或额外代码变化，合并后 99 项再次全部通过；没有未关闭的 P0/P1
- 异常、边界、幂等与安全：覆盖未知/零/正常/部分 Token、自动总量、负数/布尔值及不一致总量、负数/布尔耗时、空白模型名和请求 ID、五种完成原因及工具原因不变量、五类错误与 retry-after 的零值/负值/布尔/NaN/Infinity、错误公共 JSON 脱敏、Fake 混合顺序和深拷贝快照、Runner 错误与取消透传；在设置假密钥并禁用网络连接的环境中补充验证，无外部访问或敏感标记泄漏；本阶段没有数据库或业务写操作，业务幂等不适用，重复构造和不同哈希种子结果确定
- 依赖、配置与迁移：均未修改；没有真实模型名、API Base、密钥、SDK、数据库或 Alembic 变化
- 未完成：未实现或验证 M0-1B 真实百炼/OpenAI-compatible Provider、真实文本/Tool Calling、SDK 错误映射或网络行为；未实现 M0-1C AgentRun、ToolRun、trace_id、费用/Token 持久化、总时长、绝对工具调用数或数据库迁移
- 已知风险：供应商原始完成原因、Token 和错误到统一契约的真实映射仍需 M0-1B 验证；固定安全摘要当前为英文；QA 使用 macOS/Python 3.13.5，未在 Python 3.11/3.12 或 Windows 复测，这不阻塞 Python 3.11+ 阶段要求
- 下一步：M0-1B 前置条件已满足；将现有 `codex/m0-1-agent-runtime` 安全快进到最新 `main` 后，只实现真实百炼/OpenAI-compatible Provider；真实调用仍需用户明确授权

#### 2026-07-21｜M0-1B｜待验收（真实验证未执行）

- 分支：`codex/m0-1-agent-runtime`
- 基线：`26d2b53315ca260772537cf0d3ed74765e4a0c23`（包含已验收 M0-1A `4036c10205038b27f530873d32a2c5fcca0ade4f`）
- 提交：本交接记录随 M0-1B 阶段提交一并创建，实际完整哈希见开发窗口最终交接报告
- 完成内容：在 `backend/app/providers/openai_compatible.py` 实现唯一应用层真实模型适配器，使用受约束的官方 OpenAI SDK `AsyncOpenAI` 非流式 Chat Completions、显式配置与 `max_retries=0`；映射响应模型、Token、单调时钟耗时、完成原因、官方请求 ID、文本和有序 function tool calls；工具参数原始 JSON 字符串只交给现有 `ToolRegistry` 解析；建立独立 `real_provider` marker 和无副作用确定性加法 Tool Calling 入口
- 配置与安全：新增 `MODEL_API_BASE`、`MODEL_API_KEY`、`MODEL_NAME`、`MODEL_TIMEOUT_SECONDS` 和测试门禁 `RUN_REAL_MODEL_TESTS`；模型配置缺失不影响应用与健康检查，只有构造真实 Provider 时要求完整配置；密钥使用 `SecretStr`，Base URL 禁止内嵌凭证/query/fragment，超时要求有限正数；错误只暴露 M0-1A 固定摘要，异常链、响应正文、请求消息、API Key 和 Authorization 不进入公开错误或日志
- 错误映射：`APITimeoutError` → `PROVIDER_TIMEOUT`；429/`RateLimitError` → `PROVIDER_RATE_LIMITED` 且只接受有限非负数字 Retry-After；401/`AuthenticationError` → `PROVIDER_AUTHENTICATION_FAILED`；SDK 校验失败、空 choices、空模型名、损坏工具结构和无法构造公共响应 → `PROVIDER_INVALID_RESPONSE`；其他 API/连接/4xx/5xx → `PROVIDER_ERROR`；`asyncio.CancelledError` 原样传播
- 主要文件：`backend/app/config.py`、`backend/app/providers/*`、`backend/pyproject.toml`、`backend/tests/unit/test_openai_compatible_provider.py`、`backend/tests/integration/test_openai_compatible_real.py`、`backend/tests/test_config.py`、`.env.example`、`README.md`、`backend/README.md`、`docs/DEV_STATUS.md`
- 当前离线验证：Ruff 通过；strict mypy 对 22 个源文件无问题；`python -m pytest -q -m "not real_provider"` 为 148 通过、0 失败、1 deselected；核心回归 86 通过、0 失败、0 跳过；M0-1A 之前的完整离线基线 99 项全部保持通过；未读取真实 `.env`，未调用真实、付费或外部 API
- 全新环境验证：在临时 Python 3.13.5 虚拟环境执行 `python -m pip install -e './backend[dev]'`，解析到 OpenAI SDK 2.46.0；`python -m pip check` 无破损依赖；再次执行 Ruff、strict mypy、148 项离线 pytest 和 86 项核心回归，结果全部通过；临时环境随后移入系统废纸篓
- 真实验证：未运行，原因是本窗口没有真实或付费调用授权；准确命令为 `RUN_REAL_MODEL_TESTS=1 python -m pytest -q -m real_provider -rs`，只在四项模型配置完整时运行一个测试用例，SDK 无自动重试且 Runner 最多发出两次非流式 Chat Completions 请求
- 依赖与迁移：新增正式依赖 `openai>=2.46,<3`；没有数据库、Alembic、AgentRun、ToolRun、trace_id、费用持久化、总 Run 时长、绝对工具调用数或业务模型变化
- 范围与冗余：未修改 `nanobot_core`；`ModelProvider`、`ModelResponse`、`TokenUsage`、`FinishReason`、`ProviderError`、`AgentRunner`、`ToolRegistry` 和 `ToolResult` 仍各只有一个正式定义；没有第二套工具参数解析、SDK 客户端、百炼封装、错误码或响应 DTO；无 DashScope SDK、自动重试、兼容层或学习项目整套复制
- 未完成：等待主控独立复测和用户授权后的真实百炼 Tool Calling；真实响应字段、百炼兼容性和实际延迟/Token 尚未验证，因此 M0-1B 不得标记完成，M0-1C 不得开始
- 已知风险：离线测试验证 OpenAI-compatible 协议和 SDK 行为，但真实百炼部署的模型能力、Tool Calling 稳定性、响应字段及网络环境仍需最多两次真实请求确认；当前开发复测环境为 macOS/Python 3.13.5，尚未在 Python 3.11/3.12 或 Windows 验证；当前无已知 P0/P1
- 下一步：主控/QA 在全新 Python 3.11+ 环境复核阶段范围与全部离线命令；获得用户明确授权后仅运行上述真实 marker，并在验证成功后更新 M0-1B 状态。本开发窗口停止，不合并 `main`、不推送、不进入 M0-1C

#### 2026-07-21｜M0-1B 验收阻断修复｜待验收（真实验证未执行）

- 分支：`codex/m0-1-agent-runtime`
- 修复内容：应用层 `OpenAICompatibleProvider` 的普通文本与带 tools 两条 Chat Completions 请求均固定发送 `enable_thinking=false`，不增加可开启思考模式的配置
- 离线覆盖：MockTransport 直接校验两条请求路径的 `model`、`messages`、`tools`、`stream` 与 `enable_thinking`，并校验 AgentRunner Tool Calling 两轮请求、单次 HTTP、输入隔离、重复调用和敏感信息边界
- 安全处理：禁止 OpenAI SDK 输出会包含完整请求消息的 DEBUG 请求选项记录；未读取真实 `.env`，未运行 `real_provider`，未调用真实或付费 API
- 范围：未修改 `nanobot_core`、配置、依赖、迁移或 M0-1C；未新增 Provider、Runner、Registry、ToolResult、响应 DTO、重试或兼容层
- 未完成：M0-1B 仍为待验收，真实百炼兼容性继续等待用户明确授权

#### 2026-07-21｜M0-1B｜已完成（主控验收）

- 分支：`main`（由 `codex/m0-1-agent-runtime` 纯快进集成）
- 开发提交：`4a632dacb911671e84da81b007fa2efa8ab77402`；非思考模式修复及集成 HEAD：`4b0210d7de0bc72a579d6a100cc8d32daf1613b2`
- 集成结果：主控确认阶段提交直接包含 `26d2b53315ca260772537cf0d3ed74765e4a0c23` 基线；修复提交直接基于原开发提交；纯快进合并无冲突、无额外代码变化
- 完成内容：应用层唯一 OpenAI-compatible Provider 使用 `qwen3.7-plus` 非思考模式完成真实 Tool Calling；模型配置延迟加载，SDK `max_retries=0`，普通文本和带 tools 请求均固定 `stream=false` 与 `enable_thinking=false`
- 离线验证环境：指定提交的独立 `git archive`、全新 Python 3.13.5 虚拟环境、OpenAI SDK 2.46.0；安装及 `pip check` 通过，Ruff 通过，strict mypy 对 22 个源文件无问题
- 离线测试结果：非真实测试 148 通过、0 失败、1 deselected；核心回归 86 通过、0 失败、0 跳过；默认全集 148 通过、0 失败、1 skipped；封锁全部 socket 连接后非真实测试再次 148 通过、0 失败、1 deselected
- 真实验证：用户在当前主控任务明确授权最多两次非流式 Chat Completions 请求；`qwen3.7-plus` 使用确定性无副作用加法工具完成一次 Tool Call、工具结果回传和最终包含 `42` 的文本回复，共两次模型请求、零 SDK 重试；真实测试 1 通过、0 失败、0 跳过，未输出密钥、完整请求或完整响应
- 环境说明：第一次使用未安装完整开发依赖的系统 Python 时在 pytest 收集阶段因缺少 asyncio 插件退出，测试函数未执行且真实请求为 0；随后使用已通过离线基线的全新 QA 虚拟环境完成真实验收
- 范围与冗余：未修改 `nanobot_core`、数据库或迁移，未实现 M0-1C/M0-2；`ModelProvider`、Provider 实现、`AgentRunner`、`ToolRegistry`、`ToolResult`、响应 DTO 和 SDK 客户端构造均保持唯一；未发现无用兼容层、重复生产算法或整份学习代码复制
- 安全与边界：无配置时应用和离线测试正常；错误映射、取消透传、一次 chat 一次 HTTP、输入深拷贝、重复调用隔离、非法响应、Token/完成原因/请求 ID 边界及日志脱敏通过；`.env` 未被 Git 跟踪，真实测试工具无文件、数据库、消息或外部 API 写入
- 合并后验证：Ruff 通过，strict mypy 对 22 个源文件无问题，非真实测试 148 通过、0 失败、1 deselected；因纯快进且代码树未变化，没有重复真实付费调用
- 验收结论：没有未关闭的 P0/P1；M0-1B 已完成，M0-1C 前置条件已满足
- 下一步：从本次状态文档提交后的最新 `main` 创建 `codex/m0-1c-run-tracking`，只实现 AgentRun、ToolRun、trace_id、运行限制、费用估算、Repository/服务和第一批数据库迁移；未经新授权不得再次调用真实或付费 API

#### 2026-07-21｜M0-1C｜待验收

- 分支：`codex/m0-1c-run-tracking`
- 指定基线：`80554c2e278048e8bc0a9b038ca36ce90d699838`（包含已验收 M0-1B）；阶段提交随本记录创建，完整 SHA 见开发窗口最终交接报告
- 完成内容：原位扩展唯一 `AgentRunner`，增加不含 Prompt、回复正文或原始参数的供应商无关观察事件；增加单次 Run 最多 8 次绝对工具执行、总时限最多 60 秒、同工具与规范化 JSON 参数 SHA-256 重复识别；应用层增加唯一 AgentRun/ToolRun 状态契约、不可推测 ID/trace、Repository、执行/查询服务、每次模型调用安全摘要、Token/费用聚合与所有终结路径持久化
- 数据模型：`agent_runs` 保存命名 trace 唯一约束、可选 user/session、intent/workflow、状态、模型调用 JSON 安全摘要、模型名、Token 汇总、Decimal 估算费用与来源、耗时、错误码和 UTC 时间；`tool_runs` 保存外键、Run 内命名唯一 sequence、安全 tool_call_id/name、参数指纹、结构化输入/输出摘要、状态、耗时、错误码和 UTC 时间；不包含 User、Session、Message 或其他 M0-2 表
- 状态与终结：AgentRun 契约覆盖 `queued`、`running`、`waiting_user`、`succeeded`、`partially_succeeded`、`failed`、`cancelled`；执行服务先分别提交 queued 和 running，再将成功、五类 Provider 错误、工具错误、空响应、模型循环边界、工具上限、重复调用、总超时、外部取消和内部异常落为唯一终态；取消记录后继续传播 `CancelledError`，数据库终结提交失败会向调用方抛出且不会保留成功状态
- ToolRun：允许的 Tool Call 按模型给出的绝对顺序执行；单响应多调用逐个计数；第 9 次记录 blocked/`RUN_TOOL_CALL_LIMIT` 且不执行；等价 JSON 的键顺序和无意义空白得到同一指纹，重复记录 blocked/`RUN_REPEATED_TOOL_CALL` 且不执行；不同参数不误判；输入/输出只保留类型、字段/条目数量、长度、成功与来源数量等 512 字符内结构摘要
- 时限：Runner 使用单调时钟、剩余预算和可注入 timeout runner 包裹每次 Provider/Tool await；默认通过 `asyncio.wait_for` 取消正在等待的调用；可配置值只能降低到 `(0, 60]`，边界前允许完成、边界处停止，测试无需真实等待 60 秒；Provider 自身独立 timeout 和零 SDK 重试行为未修改
- Token 与费用：每个成功模型事件直接复用 M0-1A `TokenUsage`，按 Run 汇总每一项；任一调用某项未知则该汇总项保持未知，合法零值保留；模型名按首次出现顺序去重；每次调用及总费用使用每百万 Token 的可注入/配置 Decimal 单价并按 8 位小数 half-up，缺少 Token、任一价格或模型名不匹配时费用为未知并保留明确原因，不伪造零费用
- 迁移：新增 `20260721_0002`，`down_revision=20260721_0001`；upgrade 只创建 `agent_runs`、`tool_runs` 及唯一/外键/检查约束，不创建与唯一约束重复的普通索引；downgrade 回上一 revision 完整删除两表；升级、回滚、再升级已在临时 SQLite 验证；应用 SQLite 连接统一开启外键，不使用 `Base.metadata.create_all`
- 配置：新增 `MODEL_INPUT_PRICE_PER_MILLION_TOKENS`、`MODEL_OUTPUT_PRICE_PER_MILLION_TOKENS`、`MODEL_COST_CURRENCY`、`MODEL_PRICING_SOURCE`、`AGENT_MAX_TOOL_CALLS`、`AGENT_TIMEOUT_SECONDS`；价格拒绝负数、bool、float、NaN 和 Infinity；工具上限只允许 `1..8`，总时限只允许有限 `(0, 60]`；变量名和安全说明已同步 `.env.example` 与 README
- 主要文件：`backend/nanobot_core/agent/events.py`、`runner.py`、`backend/app/domain/runs/*`、`backend/app/application/pricing.py`、`run_tracking.py`、`backend/app/infrastructure/db/models/runs.py`、`repositories/runs.py`、`backend/migrations/versions/20260721_0002_agent_run_tracking.py`、相关核心/单元/集成/迁移测试、`.env.example`、两份 README、`docs/DEV_STATUS.md`
- 当前验证：修改前 Ruff、strict mypy、148 个非真实测试、86 个核心测试和 1 个迁移测试全部通过；实现后依赖检查、Ruff 通过，strict mypy 对 37 个源文件无问题，215 个非真实测试通过且 1 个真实测试 deselected，98 个核心测试通过，2 个迁移测试通过，默认全集 215 通过且 1 个真实测试 skipped；封锁 socket 后 215 个非真实测试再次通过；Alembic CLI 升级、回滚到 `20260721_0001`、再次升级成功，最终只含 `agent_runs`、`tool_runs` 与 `alembic_version`
- 安全与冗余：模型正文、系统 Prompt、思维链、完整消息、原始工具参数/结果、异常对象/堆栈、Provider 原始响应、Authorization、Cookie 和伪 secret 均不进入事件、数据库、公开摘要或 repr；应用基础设施/Repository 不直接导入 `nanobot_core`，核心不导入 SQLAlchemy、FastAPI 或 `app`；AgentRunner、ToolRegistry、Provider、TokenUsage、ToolResult、状态枚举和 Repository 均保持单一正式定义
- 未完成：等待主控独立离线 QA、提交范围审阅和集成决定；没有新增 GET AgentRun API、SSE、审批、自动重试/退避/限流/熔断/每日额度、PostgreSQL/Redis/Celery、前端或 M0-2 模型；未运行真实百炼或任何外部/付费 API
- 已知风险：当前只在 macOS/Python 3.13.5 与 M0 SQLite 复测，未在 Python 3.11/3.12、Windows 或 PostgreSQL 验证；模型调用明细按本阶段两表限制保存为 AgentRun 内安全 JSON，后续如果需要高基数模型调用查询再通过独立阶段决策演进；当前无已知 P0/P1
- 主控复测范围：从指定基线确认阶段提交只含 M0-1C；全新 Python 3.11+ 环境复现安装、Ruff、mypy、全部非真实/核心/迁移测试；重点检查 8/9 次边界、单响应多调用、等价/不同 JSON、Provider/Tool 活跃取消、外部取消传播、五类错误、终结数据库故障、Token 未知/零、多模型费用、迁移约束与往返、安全数据库 dump、socket 封锁、唯一契约和反向依赖
- 下一步：主控验收通过后才可纯快进集成并另开 M0-2；本分支到此停止，不自行标记已完成、不合并、不推送

#### 2026-07-21｜M0-1C 主控验收缺陷修复｜待验收

- 分支：`codex/m0-1c-run-tracking`；修复直接基于验收失败提交 `e8f18becffe1af23b9baff3c4e03db43c2a7496a`，指定 `main` 基线仍为 `80554c2e278048e8bc0a9b038ca36ce90d699838`
- Runner 硬上限：在 `nanobot_core` 定义单一公共常量 `MAX_TOOL_CALLS_PER_RUN=8` 与 `MAX_RUN_TIMEOUT_SECONDS=60.0`；唯一 `AgentRunner` 构造时只接受整数 `1..8` 和有限数字 `(0, 60]`，执行路径再次以公共常量封顶；bool、0、负数、9、60.001、NaN、正负 Infinity 均被拒绝，8 与 60 合法；`max_iterations` 语义未改变
- 配置复用：应用 Settings 的默认值、上界校验和错误信息复用核心公共常量，不再维护第二份 `8/60` 上限；没有增加 Runner 包装层或第二套执行循环
- 索引修复：ORM 与尚未集成的 `20260721_0002` revision 原位移除 `ix_agent_runs_trace_id`、`ix_tool_runs_agent_run_id` 及 downgrade 对应显式删除；保留 `uq_agent_runs_trace_id` 和 `uq_tool_runs_run_sequence(agent_run_id, sequence)`，其唯一索引继续覆盖 trace 与 ToolRun 前缀/顺序查询
- 自动化覆盖：Runner 聚焦测试 30 通过；配置聚焦测试 22 通过；迁移测试 2 通过；非真实测试 241 通过、1 deselected；核心测试 118 通过；默认全集 241 通过、1 个真实测试 skipped；全部退出码 0
- 静态与依赖验证：editable 安装、`pip check`、Ruff 与 strict mypy 均通过；mypy 检查 38 个源文件；没有放宽断言、删除测试或增加 skip
- Alembic 往返：仓库外临时 SQLite 上 `upgrade head`、`downgrade 20260721_0001`、再次 `upgrade head` 均成功；最终 revision 为 `20260721_0002`，只含 `agent_runs`、`tool_runs`、`alembic_version`；仅有主键/唯一约束 autoindex，唯一列分别为 `trace_id` 和 `agent_run_id,sequence`
- 离线与安全：同时封锁 socket connect/connect_ex/create_connection 与 DNS 后，241 个非真实测试再次通过、1 deselected；所有测试显式移除真实测试开关并使用 `APP_ENV=test`，未读取真实 `.env`，真实或付费 API 调用为 0
- 范围与冗余：只修改 Runner 硬上限/公共常量、Settings 复用、ORM/revision 冗余索引、对应测试和本状态交接；未修改 Provider、AgentRunService 或业务状态枚举，未增加 API/SSE/User/Session/Message/收藏及任何 M0-2 能力；AgentRunner、ToolRegistry、Provider、Repository 和状态契约仍各自唯一
- 未完成：M0-1C 继续保持待验收；M0-2 继续保持未开始且不允许开始；本分支不合并、不推送，不执行任何真实或付费调用
- 主控复测范围：构造器非法值与 1/8、60 边界；默认和直接构造下第 9 次工具调用不可执行；60 秒边界与活跃 Provider/Tool 取消；Settings 与核心常量一致性；两个唯一约束、额外普通索引缺失、trace/ToolRun 查询；Alembic 升降升；socket 封锁、范围、密钥/生成物和唯一公共实现扫描
- 下一步：等待主控在本修复提交上独立复验；通过前停止开发，不进入 M0-2

#### 2026-07-21｜M0-1C｜已完成（主控验收）

- 分支：`main`（由 `codex/m0-1c-run-tracking` 纯快进集成）
- 开发提交：`e8f18becffe1af23b9baff3c4e03db43c2a7496a`；硬上限与索引修复及集成 HEAD：`731e563a45353fc1ba7ecfc130be7a3477e6e6e1`
- 集成结果：主控确认修复提交直接基于原开发提交，阶段分支包含指定 `main` 基线 `80554c2e278048e8bc0a9b038ca36ce90d699838`；纯快进合并无冲突、无额外代码变化，合并前后代码树哈希一致
- 验收环境：指定 commit 的独立 `git archive`、全新 Python 3.13.5 虚拟环境；editable 安装与 `pip check` 通过，Ruff 通过，strict mypy 对 38 个源文件无问题
- 自动化结果：非真实测试 241 通过、0 失败、1 deselected；核心测试 118 通过；迁移测试 2 通过；默认全集 241 通过、1 个真实测试 skipped；封锁 socket 连接和 DNS 后非真实测试再次 241 通过、1 deselected；合并后 Ruff、mypy 和 241 项非真实测试再次通过
- 硬上限复验：直接构造只接受整数 `1..8` 和有限 `(0, 60]`；bool、0、负数、9、60.001、NaN 与正负 Infinity 被拒绝；默认第 9 次工具调用记录 blocked 且不执行；59.999 秒可完成、60 秒边界终止，活动 Provider/Tool 调用可取消
- 数据与迁移：`20260721_0002` 升级、回滚至 `20260721_0001`、再次升级均成功；最终只新增 `agent_runs` 与 `tool_runs`，外键、检查和唯一约束生效；trace 与 `(agent_run_id, sequence)` 查询使用唯一索引，没有重复普通索引
- 异常、边界、幂等与安全：Provider 五类错误、空响应、工具失败、循环/工具/重复限制、总超时、外部取消、数据库终结失败、未知/零 Token、多模型费用、trace 冲突和终态幂等均通过；Prompt、消息正文、原始工具参数/结果、异常细节、密钥、Authorization、Cookie 和完整供应商响应未进入数据库、公开摘要或 repr
- 范围与冗余：未实现 M0-2、GET AgentRun API、SSE、Approval、自动重试/退避/熔断、PostgreSQL、前端或业务模型；AgentRunner、ToolRegistry、ModelProvider、OpenAI-compatible Provider、TokenUsage、ToolResult、AgentRun Repository 和 SDK 客户端构造均保持唯一，核心无应用/数据库反向依赖
- 真实 API：本阶段没有真实集成要求，主控未读取本机 `.env`，未运行 `real_provider`，真实或付费调用为 0；此前 M0-1B 的单次授权不延续到本阶段或后续阶段
- 验收结论：没有未关闭的 P0/P1；原 P1 硬上限和 P2 冗余索引均已关闭，M0-1C 完成标准满足
- 已知风险：本轮仅在 macOS/Python 3.13.5 与 SQLite 验证，未在 Python 3.11/3.12、Windows 或 PostgreSQL 复测；这些不阻塞当前 M0 SQLite 阶段
- 下一步：从本交接文档提交后的最新 `main` 创建 `codex/m0-2-text-collection`，只实施 M0-2A 领域模型；M0-2B 及后续仍不得提前开始
