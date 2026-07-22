# 拾光开发状态

| 项目 | 当前值 |
|---|---|
| 当前总阶段 | M0 技术验证 |
| 当前子阶段 | M0-5A PlanConstraints |
| 状态 | 待验收 |
| 当前分支 | codex/m0-5-planning |
| 最近更新 | 2026-07-23 |
| 阻塞项 | 无；M0-5A 前置条件已满足 |

## 当前任务

M0-4A 至 M0-4D 均已通过主控验收并集成到 `main`，M0 的输入、收藏与地点匹配技术验证前置链路已经闭合。M0-5A PlanConstraints 已在独立阶段分支实现，当前等待主控验收；M0-5B 结构化检索、M0-5C 草案生成、M0-5D 外部地点补充以及后续阶段仍未开始且不得提前开发。

## M0 状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| M0-0A 项目基线与资料迁移 | 已完成 | 主控验收通过，阶段提交 `79848c7` 已集成到 `main` |
| M0-0B 后端工程骨架 | 已完成 | 主控验收通过，阶段提交 `6cd5646` 已集成到 `main` |
| M0-0C Nanobot 核心迁移 | 已完成 | 主控验收通过，阶段提交 `5c4a8fb` 已集成到 `main` |
| M0-1 模型与运行记录 | 已完成 | M0-1A、M0-1B、M0-1C 均已通过主控验收 |
| M0-2 文字收藏 | 已完成 | M0-2A、M0-2B、M0-2C、M0-2D 均已通过主控验收 |
| M0-3 地点匹配 | 已完成 | M0-3A、M0-3B、M0-3C、M0-3D 均已通过主控验收 |
| M0-4 URL 与截图 | 已完成 | M0-4A、M0-4B、M0-4C、M0-4D 均已通过主控验收 |
| M0-5 计划技术验证 | 进行中 | M0-5A 待主控验收；M0-5B/C/D 未开始 |
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
- M0-2A 已完成：收藏领域模型、识别/收藏状态边界、强制用户隔离、六表迁移和安全持久化约束已通过主控验收。
- M0-2B 已完成：严格 Place/Event 候选、一次结构修复、任意城市收藏线索、`0004` 城市契约迁移、异常安全与离线回归已通过主控验收。
- M0-2C 已完成：自动保存、消息/来源幂等、允许字段修改、并发安全的逻辑删除、一次性 Undo 和 `0005` 可逆写入迁移已通过主控验收。
- M0-2D 已完成：Demo Session、同步纯文字消息、AgentRun 安全查询、Collection 查询/修改/删除和路径绑定 Undo 的 `/api/v1` 契约已通过主控验收。
- M0-3A 已完成：供应商无关 MapProvider、严格内部地点契约、深圳/广州离线 Stub、城市隔离和安全导航 URI 已通过主控验收。
- M0-3B 已完成：唯一服务端高德 Web 服务适配、严格配置与响应边界、错误/重试/取消映射、真实响应空数组兼容及 5 次零重试只读真实验收已通过主控验收。
- M0-3C 已完成：供应商无关的确定性匹配评分、可靠候选过滤、城市与分店硬冲突、四种结果和显式用户选择契约已通过主控验收。
- M0-3D 已完成：统一 PlaceTarget、具体地点与任意分店目标、持久化候选快照、正式 POI/品牌幂等、多选事务、规划解析边界和异常链安全均已通过主控验收。
- M0-4A 已完成：唯一 StorageProvider、本地私有目录、随机 key、类型/大小边界、生命周期元数据、原子排他发布、失败/取消清理和幂等删除已通过主控验收。
- M0-4B 已完成：唯一 WebContentProvider、网页成功/失败契约、集中 URL/SSRF 策略、DNS 连接绑定、显式重定向、响应/解压/文本边界、Cookie 零状态、HTTP 日志防泄漏和 BeautifulSoup 白名单抽取已通过主控验收。
- M0-4C 已完成：唯一 ImageRecognitionService、私有原图生命周期、多模态候选抽取、图片与模型载荷边界、不确定字段保护、失败清理和异常脱敏已通过主控验收。
- M0-4D 已完成：文字、URL 与图片已进入唯一 Message、Source、AgentRun/ToolRun、结构抽取和收藏写入流水线；MIME 幂等、可恢复状态重放、取消清理、用户/Session 隔离和统一约束已通过主控验收。

## 下一步

主控从精确阶段提交独立复验 M0-5A 的严格契约、缺失项顺序、过期边界、敏感信息安全、无副作用和完整离线回归。验收通过前不合并 `main`、不开始 M0-5B/C/D，也不调用真实模型、高德、路线、天气、网页或其他外部/付费 API。

## 已确认 M0-Gate 延迟与超时校准

- M0-Gate 增加正式的真实延迟基准与超时校准，不再仅凭配置值判断 5/20/30/60 秒是否足够；
- 分开测量文本抽取、结构修复、模型 → Tool → 模型、高德、普通/重定向网页和图片识别，记录单次调用及端到端 P50、P95、最大耗时、超时率、重试率和恢复结果；
- 样本不足时不得宣称 P95 已验证；真实取样必须在 Gate 当前任务中逐项取得授权并预先限定请求数和费用，普通测试继续完全离线；
- 正常 P95 建议只占硬超时的 60%–75%。接近上限时优先减少调用、补充逻辑总时限或转后台任务，不以无限提高超时掩盖架构问题；
- `M0_VALIDATION_REPORT.md` 必须记录样本条件、调整前后时限、Token/费用、未调整依据和剩余风险。该要求不改变当前 M0-4C 范围，也不授权任何真实调用。

## 已确认简洁实现与测试原则

- 测试用于证明产品行为与架构边界，不得通过持续增加特例、白名单、内部代理或重复校验来制造绿色结果；
- 必须区分 PRD 业务硬规则和框架内部细节，安全与错误映射集中放在真实的不可信输入、Application/API 和日志边界；
- 同一缺陷修复后再次出现旁路时停止追加补丁，重新检查抽象和边界，并删除被替代的旧保护层；
- 主控验收同时检查净复杂度、规则唯一性和框架耦合。全部测试通过但实现明显为了过检查堆叠代码时，阶段仍不得合并；
- 当前 M0-5A 的收敛修复按此原则执行：保留一份 PlanConstraints 业务校验，使用唯一安全解析边界，不继续替换或代理 Pydantic 内部 validator。

## 已确认跨城市收藏与后续升级

- 当前允许收藏其他城市的 Place 和用户主动提供的 Event；城市不再是收藏准入条件，明确其他城市内容不得返回范围外错误。
- 抽取与 CollectionItem 保存可空 `city_hint`；该字段只表示来源线索，标题/品牌中的城市词不能静默确认城市，缺失时进入“城市待确认”。
- 正式城市由统一 POI/地点引用或用户确认产生；当前深圳计划只读取正式城市为深圳、状态有效且位置已确认的收藏，其他城市和城市待确认条目继续保留。
- 收藏库后续增加城市分类/筛选和“城市待确认”，本次只更新产品、技术和阶段契约，不提前修改 UX 原型或前端。
- M0/M1 仍不提供运行时计划城市切换，不实现跨城多日计划；U1 只负责开放其他单城市计划和 Session 城市切换。
- 不建立第二套 CollectionItem、City Repository、Provider、地点匹配或规划流程；新增持久化变化使用 `0004` 向前迁移，不改写已集成 `0003`。

## 已确认连锁分店设计（不属于当前 M0-2B）

- 未确定分店且用户未授权灵活选择时，保持一条 `pending_selection` 收藏并展示最多 3 个候选；候选不是正式收藏。
- 用户明确选择“任意分店都可以”时，只保存一条有效品牌级 Place 收藏；规划时再按活动范围和路线解析具体分店，不批量创建收藏，也不永久改绑品牌收藏。
- 用户明确多选具体分店时，才按 POI 分别创建收藏并共享 Source；不同分店的地址、状态、到访和 POI ID 保持独立。
- M0-3D 负责唯一 PlaceTarget、候选复用和任意分店策略，M0-5B/C 负责规划时解析和 PlanItem 快照；当前 M0-2B 不实现该能力。
- 代码必须扩展现有 CollectionItem、POI 候选、MapProvider 和计划服务；禁止新增品牌版 Repository、BranchCandidate、第二套地点匹配或第二套规划流程。

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

#### 2026-07-21｜M0-2A｜待验收

- 分支：`codex/m0-2-text-collection`
- 指定基线：`7e4a016dc2a26abc4b74399a236d4df488166479`（`main`、`origin/main` 与任务开始时 HEAD 一致，包含已验收 M0-1C）；阶段提交随本记录创建，完整 SHA 见开发窗口最终交接报告
- 完成内容：建立唯一的 M0-2A 收藏领域契约，包含 User、Session、Message、Source、CollectionItem、CollectionSource、供应商无关 Place/Event 类型、严格收藏状态机、默认有效收藏过滤和计划资格边界；所有实体 ID 使用命名空间加服务端随机值并校验格式，所有领域时间归一到 UTC，CollectionItem 版本必须为正数
- 状态语义：完整覆盖 `recognizing → active / pending_selection / pending_details / failed`、`active → visited / archived / deleted`、`pending_selection → active / pending_details / deleted`、`pending_details → recognizing / deleted`；非法回退、越级和 failed/visited/archived/deleted 终态退出被拒绝；默认查询排除 recognizing、failed、archived、deleted，只有 active 具备后续计划资格，待选择与待补充保持可见但不可计划
- Repository 与用户隔离：定义单一 `CollectionRepository` Protocol 与 `SqlAlchemyCollectionRepository` 适配，全部公开查询和写入显式要求 `user_id`；Message 通过 Session 所有权查询；Source、CollectionItem 读写始终同时过滤实体 ID 与用户；CollectionSource 写入前分别验证所有权，并使用 `(collection_item_id, user_id)` 与 `(source_id, user_id)` 复合外键在数据库层阻止跨用户关联；不存在与跨用户资源统一返回空结果或安全的 `resource not found`，不存在仅凭业务实体 ID 的公共 Repository 方法
- 领域与安全字段：User 只允许 real/demo、深圳和 Asia/Shanghai；Session、Message、Source 使用稳定枚举；Source 抓取时间使用独立 UTC 列，元数据只允许媒体类型、大小、SHA-256 和 HTTP 状态，不提供 Authorization、Cookie、Header、原始正文或凭证字段；URL 禁止内嵌账号密码；Place/Event 使用内部稳定类型，Event 时间为独立列，不包含供应商原始 DTO
- 数据迁移：新增唯一 revision `20260721_0003`，`down_revision=20260721_0002`；只创建 `users`、`sessions`、`messages`、`sources`、`collection_items`、`collection_sources`，包含稳定命名的主键、外键、唯一/检查约束与必要复合索引；关联表复合主键防止重复，复合外键强制同一用户；未创建 PoiReference、Undo、Approval、Plan、Memory、Job、ProductEvent 或其他业务表，未修改 AgentRun/ToolRun 语义，未使用 `create_all()`
- 共享实现与主要文件：将既有运行 ID 和 UTC 逻辑原位收敛到 `backend/app/domain/identifiers.py` 与 `backend/app/domain/time.py`，运行记录继续复用且行为不变；主要新增 `backend/app/domain/collections/*`、`backend/app/infrastructure/db/models/collections.py`、`backend/app/infrastructure/repositories/collections.py`、`backend/migrations/versions/20260721_0003_collection_domain.py`、领域/Repository/迁移测试，并更新两份 README、迁移环境和本状态文档
- 修改前门禁：使用仓库根目录受忽略 `.venv` 的 Python 3.13.5；`pip check`、Ruff、strict mypy 全部退出 0；非真实测试 241 通过、1 deselected，核心测试 118 通过，默认全集 241 通过、1 skipped；默认系统 Python 缺少 Ruff，因此按历史状态记录切换到项目 `.venv` 后从第一条命令重新执行，代码修改前基线完整通过
- 最终安装与静态验证：规定的 `python -m pip install -e '.[dev]'` 最终退出 0并成功重装；`pip check`、Ruff、strict mypy 均退出 0，mypy 检查 46 个源文件。两个 `PIP_NO_INDEX=1` 诊断性安装尝试分别因隔离环境没有 setuptools 缓存、当前环境无法导入 build backend 退出 1/2；未改代码或依赖，随后规定原始安装命令成功
- 最终测试：`python -m pytest -q -m "not real_provider"` 为 337 通过、1 deselected；`python -m pytest -q tests/core` 为 118 通过；`python -m pytest -q tests/test_migrations.py` 为 4 通过；`python -m pytest -q` 为 337 通过、1 skipped；全部规定测试退出 0。领域聚焦测试 88 通过，Repository 集成测试 6 通过；封锁 socket connect/connect_ex/create_connection 及 DNS 后非真实测试再次 337 通过、1 deselected
- 迁移实测：仓库外临时 SQLite 上 `upgrade head → downgrade 20260721_0002 → upgrade head` 全部退出 0；HEAD 为 `20260721_0003` 且只比 M0-1C 多六张约定表，降级后只保留 `agent_runs`、`tool_runs`、`alembic_version`，再次升级恢复六表；关联表报告 4 行复合外键，应用 Database 连接 `PRAGMA foreign_keys=1`，`alembic check` 无待生成操作；自动化测试另验证降级后 AgentRun 可查询并可继续写入 ToolRun
- 数据库与回滚覆盖：六表字段、状态/版本/类型/时间顺序/价格成对约束、所有者外键、重复关联、跨用户关联、必要查询索引和无重复普通索引均通过；Repository 创建、读取、列表、状态更新、默认过滤往返通过；异常事务会回滚先前未提交的收藏写入，重复关联失败后只保留一条；测试数据库 dump 不包含 Authorization、Cookie、测试 secret 或 Source 原始内容字段
- 离线、安全与冗余结论：未读取或打印 `.env`，未运行 `real_provider`，真实模型、高德、消息发送或其他付费 API 调用为 0；`nanobot_core` 未导入 app、SQLAlchemy 或 FastAPI；AgentRunner、ToolRegistry、ModelProvider、OpenAI-compatible Provider、AgentRun Repository、Collection Repository 和 ORM Base 均保持唯一；Git 未包含 `.env`、数据库、缓存、虚拟环境或测试生成物
- 范围结论：没有实现 M0-2B 候选 Schema/抽取/模型调用/输出修复，M0-2C 自动保存/Undo/幂等消息/通用修改撤销，M0-2D API/Demo 初始化/Session 路由，或高德、POI、URL 抓取、截图、计划、SSE、前端、PostgreSQL、Redis、Celery、自动重试及新 Agent 运行机制；当前无已知 P0/P1
- 未验证与风险：仅在 macOS、Python 3.13.5、SQLite 复测，未在 Python 3.11/3.12、Windows 或 PostgreSQL 验证；M0-2A 只证明领域和持久化边界，尚未验证真实抽取结果、自动保存、API 或真实用户流程，这些均属于后续阶段且不应在本次验收中误判为已实现
- 主控复测范围：确认提交直接基于指定基线且只含 M0-2A；在全新 Python 3.11+ 环境重跑安装、Ruff、mypy、全部非真实/核心/迁移/默认测试；重点复核 ID/UTC/版本、全部合法与非法状态转换、failed/deleted 默认过滤、相同查询条件下用户隔离、跨用户 Message/Source/Collection/关联安全行为、复合外键与索引、异常回滚、安全 dump、迁移升降升及降级后 AgentRun/ToolRun 可用性、socket/DNS 封锁和唯一公共实现扫描
- 下一步：主控验收通过后才可纯快进集成并决定是否另开 M0-2B；本分支保持待验收，不合并 `main`、不推送、不开始 M0-2B、不执行真实或付费调用

#### 2026-07-21｜M0-2A QA 缺陷修复｜待验收

- 分支与提交关系：`codex/m0-2-text-collection`；问题提交 `5f7823896d77cf5fe738b1c2a37b647fcc50939b`，其直接父提交和指定基线均为 `7e4a016dc2a26abc4b74399a236d4df488166479`；修复提交为本记录所在提交，直接建立在问题提交之上，不 amend、不合并、不推送
- failed/未收藏边界：`CollectionStatus.FAILED` 仅保留为识别流程转换状态；普通领域构造会拒绝 failed CollectionItem，Repository 新增和状态转换再次拒绝，ORM 与 `20260721_0003` 的 `ck_collection_items_status` 也不包含 failed。失败 Source 可正常保存 `parse_status=failed`；测试同时验证 Repository 绕过构造、直接 SQL 插入及 recognizing→failed 持久化转换均不能留下 failed CollectionItem
- AgentRun 隔离：唯一 `AgentRunRepository.get_by_trace_id` 与公共 `AgentRunService.get_by_trace_id` 改为必填、仅关键字 `user_id` 和 `trace_id`；SQL 同时过滤两列，ToolRun 仅在父 Run 命中后加载。同用户返回摘要，跨用户与不存在 trace 均返回相同 `None`；当前执行流程不需要无用户查询，因此未保留或新增无范围内部入口，也未创建第二套 Repository
- Message 安全：M0-2A `MessageRole`、ORM 和迁移约束只允许 USER/ASSISTANT；SYSTEM 与 TOOL 在领域枚举、Repository 防绕过校验和数据库检查约束中均被拒绝，原始 system prompt/tool payload 的直接 SQL 尝试不会留下行；Message.content 设置 `repr=False`，测试验证敏感内容不进入 `repr` 或 `str`
- 渠道边界：`SessionChannel`、ORM 和迁移约束只保留 `web`、`demo`；领域与数据库测试确认二者合法，`wechat`、`clawbot` 均非法；未实现微信/ClawBot Adapter 或任何 M2 功能
- 迁移变化：仍使用未验收分支上的单一 revision `20260721_0003`，`down_revision=20260721_0002`，未新增 revision 或业务表；原位收紧三个检查约束的允许值。仓库外临时 SQLite 的 `upgrade head → downgrade 20260721_0002 → upgrade head` 全部退出 0，降级只保留 AgentRun/ToolRun/Alembic 表，再升级恢复六张 M0-2A 表；`alembic check` 报告无待生成操作
- 最终验证环境与数量：macOS、Python 3.13.5；`pip check`、Ruff、strict mypy（46 个源文件）均通过；非真实测试 343 passed、1 deselected，核心测试 118 passed，迁移测试 4 passed，默认全集 343 passed、1 skipped；同时封锁 socket connect/connect_ex/create_connection 和 DNS 后，343 个非真实测试再次通过、1 deselected
- 安全、范围与冗余：未读取或打印 `.env`，未运行 `real_provider`，真实模型、高德、外部消息或付费调用为 0；`nanobot_core` 仍不导入 app、SQLAlchemy 或 FastAPI；AgentRunner、ToolRegistry、ModelProvider、OpenAI-compatible Provider、AgentRun Repository、Collection Repository 和 ORM Base 保持唯一；Git 未新增 `.env`、数据库、缓存、虚拟环境或测试生成物
- 阶段范围：仅修复上述 QA 缺陷；未实现 M0-2B 抽取/候选 Schema、M0-2C 自动保存/Undo/幂等消息、M0-2D API/Demo 初始化/Session 路由，也未实现 POI、高德、URL 抓取、截图、前端、SSE、微信或 ClawBot；M0-2A 和 M0-2 整体状态不变，M0-2B 继续未开始
- 已知验证边界：仅在 SQLite 与 Python 3.13.5 验证，未覆盖 PostgreSQL、Python 3.11/3.12、Windows；真实抽取、自动保存与 API 属于后续阶段，不作为本次 QA 修复完成项
- 主控复测范围：核对新提交直接父提交为问题 commit；重点重跑 failed Source 与零 CollectionItem、SYSTEM/TOOL 领域/Repository/直接 SQL 拒绝、Message repr 脱敏、AgentRun 同用户/跨用户/不存在 trace、web/demo 与 wechat/clawbot、迁移升降升、封网非真实全集、反向依赖与唯一实现扫描；验收前不开始 M0-2B、不合并、不推送、不执行真实调用

#### 2026-07-21｜M0-2A recognizing 幽灵行 P1 修复｜待验收

- 分支与提交关系：`codex/m0-2-text-collection`；本修复直接建立在问题提交 `d0975236c1e3062f0af4ac4f3ec7acf75ff66958` 之上，直接父提交保持该 SHA；修复提交为本记录所在提交，不 amend、不合并 `main`、不推送
- 修复语义：`CollectionStatus` 只包含 `active`、`pending_selection`、`pending_details`、`visited`、`archived`、`deleted` 六种真实收藏状态；`RecognitionStatus` 单独表达 `recognizing`、`failed` 识别流程。识别成功后才创建真实 CollectionItem，识别最终失败只把 Source 更新为 `parse_status=failed`（AgentRun 仍可承载运行失败与恢复信息），`collection_items` 数量保持 0；此前“拒绝 recognizing→failed 但保留 recognizing 行”的测试语义已删除，任何残留 recognizing CollectionItem 均不再视为正确结果
- 三层持久化边界：直接 `CollectionItem` 实体只接受 `CollectionStatus`；Repository 对 `model_construct` 绕过再次拒绝 recognizing/failed，状态转换入口也不能把真实收藏转为识别流程状态；ORM 检查约束和数据库迁移只允许六种真实收藏状态，直接 SQL 写 recognizing/failed 均失败。active、pending_selection、pending_details 等既有合法状态及全部合法工作流转换继续通过
- 用户隔离与事务：失败 Source 更新始终以 `source_id + user_id` 查询；跨用户和不存在 ID 返回相同 `resource not found`，跨用户既不能触发失败更新也不能观察对方 Source，两侧 CollectionItem 列表均为空；同一事务先写 failed Source、再尝试绕过写 recognizing CollectionItem 时整体回滚，Source 和 CollectionItem 均不留下部分数据
- 迁移变化：M0-2A 最终只保留单一 `20260721_0003`（`down_revision=20260721_0002`）；六种真实 CollectionItem 状态直接写入该未发布 revision 的 `ck_collection_items_status`，recognizing/failed 从建表起即不可写入，不增加兼容迁移、数据删除或业务表
- 完整验证：macOS、Python 3.13.5；`pip check`、Ruff、strict mypy（46 个源文件）均通过；非真实测试 348 passed、1 deselected，核心测试 118 passed，迁移测试 5 passed，默认全集 348 passed、1 skipped；封锁 socket connect/connect_ex/create_connection 和 DNS 后，348 个非真实测试再次通过、1 deselected
- 迁移实测：仓库外全新临时 SQLite 执行 `upgrade head → downgrade 20260721_0002 → upgrade head` 全部成功，最终 revision 为 `20260721_0003`，只包含既有 M0-1C 三表与 M0-2A 六表；最终 `collection_items` 状态约束不含 recognizing/failed，`alembic check` 报告无待生成操作
- 保持项与安全：AgentRun `user_id + trace_id` 隔离、USER/ASSISTANT Message 限制、Message repr 脱敏和 web/demo 渠道限制均保持并由全集回归覆盖；未读取或打印 `.env`，未运行 `real_provider`，未调用真实模型、高德、外部消息或付费 API
- 阶段范围与冗余：只修改识别/收藏状态边界、单一建表迁移、对应测试和交接文档；未实现 M0-2B 抽取/候选 Schema、M0-2C 自动保存/Undo/幂等消息、M0-2D API，也未实现 POI、高德、URL 抓取、前端、微信或 ClawBot；AgentRunner、ToolRegistry、ModelProvider、AgentRun Repository、Collection Repository 和 ORM Base 均保持唯一，`nanobot_core` 仍无 app/SQLAlchemy/FastAPI 反向依赖
- 已知验证边界：仅在 SQLite 与 Python 3.13.5 验证，未覆盖 PostgreSQL、Python 3.11/3.12、Windows；该分支尚未发布，因此直接收敛 `20260721_0003`，不提供已发布数据库的兼容升级路径
- 主控复测范围：确认迁移收敛提交直接父提交为 `6f195b0cd3024c60101edd0ba14e99d02bfebda9`；从全新数据库升级至 `20260721_0002` 后再升级 head，检查六种真实状态可直接 SQL 写入、recognizing/failed 均被拒绝；重跑直接实体、Repository 绕过、跨用户/不存在同结果、事务回滚、其他合法转换、完整命令、封网全集、迁移升降升与 `alembic check`，并复核 M0-2B 未开始、反向依赖和唯一公共实现
- 下一步：等待主控在最新修复提交上独立验收；通过前保持 M0-2A 待验收和 M0-2B 未开始，不合并、不推送、不执行真实调用

#### 2026-07-21｜M0-2A 迁移结构收敛｜待验收

- 分支与提交关系：`codex/m0-2-text-collection`；本提交直接建立在 `6f195b0cd3024c60101edd0ba14e99d02bfebda9` 之上，不 amend、不合并 `main`、不推送
- 收敛内容：由于 M0-2A 尚未合并或发布，最终迁移只保留紧接 `20260721_0002` 的 `20260721_0003`；CollectionItem 六种真实状态直接进入建表检查约束，不增加后续 revision，不执行数据删除或表重建
- 约束测试：自动化测试显式先升级到 `20260721_0002` 再升级 head，验证 active、pending_selection、pending_details、visited、archived、deleted 均可写入，recognizing 与 failed 的直接 SQL 写入均失败；既有领域、Repository、用户隔离、回滚、Message 和渠道安全测试保持不变
- 阶段状态：M0-2A 继续待验收，M0-2B 继续未开始；没有新增抽取、自动保存、Undo、API、POI、URL 抓取、前端或渠道 Adapter
- 主控复测：核对 revisions 目录只有 `0001`、`0002`、`0003`，Alembic head 为 `20260721_0003`；在全新临时库完成 `head → 20260721_0002 → head` 和 `alembic check`，确认降级保留 AgentRun/ToolRun、升级只新增 M0-2A 六表，再运行完整离线测试与范围/唯一性扫描

#### 2026-07-21｜M0-2A｜已完成（主控验收）

- 集成：`codex/m0-2-text-collection` 已以 `--ff-only` 纯快进合并到 `main`；最终开发提交 `1a2518b524bfc9cf7eceb2120cc0a7a835785710`，包含原开发提交 `5f7823896d77cf5fe738b1c2a37b647fcc50939b` 及三轮 QA 修复；合并无冲突、无额外代码变化
- 验收环境：对最终提交使用独立 `git archive` 与全新 Python 3.13.5 虚拟环境；editable 安装、`pip check`、Ruff 和 strict mypy（46 个源文件）全部通过
- 自动化结果：非真实测试 348 passed、1 deselected；核心测试 118 passed；迁移测试 5 passed；默认全集 348 passed、1 skipped；封锁 socket 连接和 DNS 后非真实测试再次 348 passed、1 deselected；6 项主控绕过探针全部通过
- 领域与安全：RecognitionStatus 的 recognizing/failed 不属于可持久化 CollectionItem；失败 Source 可留痕但收藏表保持空；实体、Repository 绕过和直接 SQL 三层均拒绝瞬态识别状态；Message 只持久化 USER/ASSISTANT 且正文不进入 repr；SessionChannel 只允许 web/demo；AgentRun trace 查询同时要求 user_id
- 用户隔离与异常：Message 经 Session 校验所有权，Source、CollectionItem 和 CollectionSource 始终按 user_id 隔离；跨用户与不存在资源使用相同安全结果；跨用户关联、重复关联、非法状态、事务部分失败和回滚均通过
- 迁移：M0-2A 仅有 `20260721_0003` 且 `down_revision=20260721_0002`，只新增约定六表；`upgrade head → downgrade 20260721_0002 → upgrade head` 与 `alembic check` 均通过，降级保留 AgentRun/ToolRun，最终状态约束只允许六种真实收藏状态
- 范围与冗余：未实现 M0-2B 抽取、M0-2C 自动保存/Undo/幂等、M0-2D API、POI、高德、URL/截图、SSE、前端或微信；AgentRunner、ToolRegistry、ModelProvider、OpenAI-compatible Provider、AgentRun Repository、Collection Repository 和 ORM Base 均保持唯一，核心无应用层反向依赖
- 真实 API：未读取或打印 `.env`，未运行 `real_provider`，真实模型、高德、外部消息及付费 API 调用均为 0；此前阶段的真实调用授权不延续
- 验收结论：所有已发现 P1/P2 均已关闭，没有未关闭的 P0/P1；M0-2A 完成标准满足，M0-2B 允许开始
- 下一步：在本交接文档提交后的最新 `main` 上继续使用 `codex/m0-2-text-collection` 开发 M0-2B；只实现结构化抽取，不提前进入自动保存、Undo 或 API

#### 2026-07-21｜M0-2B｜待验收

- 分支与指定基线：`codex/m0-2-text-collection`；开始时 `main` HEAD 与任务指定基线均为 `76cbc96f9aa802496113f6e4216280691edb74ce`，阶段分支以 `git merge --ff-only main` 快进到同一提交且无额外代码变化；门禁时 `main` 比 `origin/main` 领先 5 个既有未推送提交，只记录、未推送；任务期间本地远端跟踪引用由外部更新到同一基线，本窗口未执行 fetch、push 或发布；本记录随单一阶段提交创建，完整 SHA 见开发窗口最终交接报告
- 候选契约：新增供应商无关、strict、`extra="forbid"`、不可变的 `PlaceCandidate`、`EventCandidate`、判别联合 `ExtractionCandidate` 与 `ExtractionResult`；继续复用 M0-2A 唯一 `CollectionKind`、`SupportedCity` 和 `event_start_at/event_end_at` 语义，不新增第二套收藏状态、城市、金额或时间枚举；标题、地址线索、商圈、地标、地铁、时间线索、价格/币种、标签、缺失字段和逐字段不确定原因均有长度、数量、唯一性及语义约束，单次最多 10 个抽取对象且不静默合并
- 结果与错误码：`ExtractionOutcome` 明确区分候选成功、信息不足、不支持和模型结构无效；稳定原因码为 `INPUT_EMPTY`、`INPUT_UNSUPPORTED`、`OUT_OF_SCOPE_CITY`、`INSUFFICIENT_INFORMATION`、`MODEL_INVALID_OUTPUT`，并以 `UnsupportedReason` 细分商品、菜谱、跨城多日旅行、复杂户外路线、过长内容及其他不支持内容；任何错误结果都不能携带候选或伪装为空成功
- 深圳及内容边界：明确深圳 Place/Event 可形成候选；只有店名时保留待核验 Place，若原文没有深圳或深圳行政区证据则 `city=None`，只保留 `search_scope_city=shenzhen` 并标记城市未确认；过于通用名称返回最小补充建议；明确非深圳城市返回范围外；Event 缺少精确起止时间时保留线索并强制进入缺失/不确定项，不编造时间；商品、菜谱、跨城多日旅行和复杂户外路线确定性返回不支持；未调用高德或生成 POI 候选
- 抽取服务与调用上限：新增唯一 `TextExtractionService`，构造函数只注入现有 `nanobot_core.providers.ModelProvider`，每次调用创建独立消息与结果状态；空白、明显不支持、范围外、过于通用和过长输入在确定性预检后零 Provider 请求，普通合法结构严格 1 次 `Provider.chat`，只有 JSON/Schema/判别联合/字段语义或意外 Tool Call 错误才执行第 2 次结构修复，代码中只有两个顺序 await 点且没有循环或第三次调用；连续两次无效返回稳定 `MODEL_INVALID_OUTPUT`
- 异常与安全：五类 `ProviderError` 均原样传播且不触发自动重试，修复调用中的 ProviderError 也不会产生第三次请求，`asyncio.CancelledError` 原样传播；Pydantic 错误摘要只含最多 8 个路径与错误类型并显式排除 input/context/URL；服务不记录完整输入、Prompt、响应或修复原文，不导入日志、数据库、文件、网络 SDK、真实 Provider、Runner、ToolRegistry 或 ToolResult，不把原文或供应商字段写入候选结果、异常、repr 或公开错误字典
- 主要文件：`backend/app/domain/collections/extraction.py`、`backend/app/domain/collections/__init__.py`、`backend/app/application/text_extraction.py`、`backend/tests/unit/test_text_extraction_contracts.py`、`backend/tests/unit/test_text_extraction_service.py`、`docs/DEV_STATUS.md`
- 修改前门禁：完整读取规定文档与现有 M0-2A/Provider/Fake/Runner/Registry/测试；工作区干净，指定基线包含已验收 M0-2A，revisions 仅 `0001/0002/0003`，RecognitionStatus/CollectionStatus/CollectionItem 和用户隔离边界唯一；项目 `.venv`、macOS、Python 3.13.5 下 `pip check`、Ruff、strict mypy 通过，非真实测试 348 passed/1 deselected，核心 118 passed，迁移 5 passed，默认全集 348 passed/1 skipped
- 最终验证命令与数量：`python -m pip install -e ".[dev]"`、`python -m pip check`、`python -m ruff check .`、`python -m mypy app migrations nanobot_core`、`python -m pytest -q -m "not real_provider"`、`python -m pytest -q tests/core`、`python -m pytest -q tests/test_migrations.py`、`python -m pytest -q` 全部退出 0；mypy 检查 48 个源文件，新增候选/服务聚焦测试 68 passed，非真实全集 416 passed/1 deselected，核心 118 passed，迁移 5 passed，默认全集 416 passed/1 skipped
- 离线与副作用检查：临时 `/tmp` pytest 插件同时封锁 `socket.connect`、`connect_ex`、`create_connection` 与 DNS `getaddrinfo` 后，全部 416 个非真实测试再次通过、1 deselected；测试只使用 FakeProvider、固定 JSON Fixture 和受控异常，不写数据库、文件、消息或外部系统；未读取或打印本机 `.env`，未运行 `real_provider`，真实模型、百炼、高德、消息发送和其他付费 API 调用均为 0
- 迁移、范围与冗余：revisions 仍只有 `20260721_0001`、`0002`、`0003`，本阶段未修改迁移、ORM、Repository、配置、依赖、`nanobot_core` 或真实 Provider；未实现 CollectionItem 创建/修改/删除、自动保存、Undo、幂等键、重复收藏、M0-2D 路由/Demo/Session、GET AgentRun、POI/坐标/匹配评分、高德、URL/HTML、图片/OCR、SSE、前端或微信；AgentRunner、ToolRegistry、ToolResult、ModelProvider、CollectionKind、SupportedCity、CollectionStatus、RecognitionStatus、CollectionItem、PlaceCandidate、EventCandidate、ExtractionResult 和抽取服务均各有唯一正式定义，核心无应用层反向依赖；Git 未包含 `.env`、数据库、缓存、虚拟环境或测试产物
- 已知风险与未验证：按任务禁令未用真实模型验证 Prompt 遵循率、供应商结构输出稳定性、真实延迟或 Token/费用；显式城市和不支持类型的离线预检采用保守固定规则，当前 Fixture 范围已通过但更广语言覆盖仍需后续评测集扩充；只在 macOS/Python 3.13.5 验证，未在 Python 3.11/3.12、Windows 或 PostgreSQL 复测；这些不构成当前纯离线 M0-2B 的已知 P0/P1
- 主控复测范围：核对阶段提交直接父提交为指定基线且只含上述 6 个文件；全新 Python 3.11+ 环境复现安装、静态检查、68 项聚焦测试、非真实/核心/迁移/默认全集和 socket/DNS 封锁；重点复核缺失/不确定字段、Place/Event 时间边界、无城市不伪造深圳、明确非深圳/四类不支持、多个及混合候选、1/2 次 Provider 边界、连续无效输出、五类 ProviderError、取消透传、敏感输入/Prompt/响应脱敏、零持久化副作用、迁移数量、范围和唯一实现扫描
- 下一步：等待主控独立验收并决定是否纯快进集成；验收通过前 M0-2B 保持待验收，M0-2A 保持已完成，M0-2C 保持未开始且暂不允许开始；本分支不合并 `main`、不推送、不执行任何真实或付费调用

#### 2026-07-21｜M0-2B 预检误判 P1 修复｜待验收

- 分支与提交关系：`codex/m0-2-text-collection`；本修复直接建立在验收失败提交 `993d41bb0a35963651bf0f4ba5bfa03a8aa4b2db` 之上，该提交的直接父提交与已验收 `main` 基线均为 `76cbc96f9aa802496113f6e4216280691edb74ce`；修复提交为本记录所在提交，不 amend、不合并、不推送
- 误判修复：移除以单个无上下文关键词或任意城市子串直接拒绝整个输入的预检方式；菜谱、商品、跨城多日旅行和复杂户外路线仅在对象、请求意图及必要上下文形成高置信组合证据时零调用拒绝；非深圳范围只接受明确城市陈述或具有出行语义的确定地标，不再把 Place、品牌或 Event 标题中的城市词当作城市事实；歧义输入进入既有 Provider 抽取和 canonicalization
- 原始失败样例：`想收藏深圳菜谱文化主题展` 返回 1 个 `EventCandidate`、Provider 1 次；深圳一日游来源中的博物馆与莲花山收藏请求返回 2 个独立 `PlaceCandidate`、Provider 1 次；`上海宾馆` 返回仅店名 `PlaceCandidate`、Provider 1 次，并被 canonicalization 收敛为 `city=None`、`search_scope_city=shenzhen` 和城市未确认项
- 保持的确定性边界：空白与超长输入继续零调用；番茄炒蛋食谱、商品型号参数和购买链接、深圳到广州三日游、梧桐山复杂徒步路线及 GPX 继续分别以稳定原因零调用拒绝；`周末想去广州塔看夜景` 继续零调用返回 `OUT_OF_SCOPE_CITY`；合法 Event 标题包含“菜谱”“产品参数”“徒步路线”以及上海宾馆、北京饭店、广州酒家等名称均严格只调用 Provider 1 次
- Provider 与安全：普通有效结构仍只有第 1 次调用；仅 JSON/Schema 结构错误可执行第 2 次修复，连续无效或修复阶段 ProviderError 均无第 3 次调用；ProviderError 与 `asyncio.CancelledError` 传播语义未变；输入消息快照不被修改，重复和并发歧义调用互不污染；未增加日志、原文、Prompt、响应、密钥、Header、Cookie 或供应商字段暴露
- 验证环境与结果：macOS、Python 3.13.5、项目 `.venv`；editable 安装、`pip check`、Ruff 均退出 0，strict mypy 对 48 个源文件无问题；候选契约与服务聚焦测试 77 passed，非真实全集 425 passed/1 deselected，核心测试 118 passed，迁移测试 5 passed，默认全集 425 passed/1 skipped，全部规定命令退出 0
- 封网与 QA 说明：临时 `/tmp` pytest 插件同时封锁 `socket.connect`、`connect_ex`、`create_connection` 和 DNS `getaddrinfo` 后，425 个非真实测试再次通过、1 deselected；首次封网命令因临时插件 hook 参数名不符合 pytest 9 规范而在收集前退出 1，项目测试未执行，修正插件后上述重跑退出 0，临时文件已删除
- 迁移、范围与冗余：revisions 仍仅有 `20260721_0001`、`0002`、`0003`；未修改候选契约、`nanobot_core`、Provider、Runner、ToolRegistry、ToolResult、Repository、ORM、迁移、依赖或配置；未实现 CollectionItem 写入、M0-2C/M0-2D、Undo/幂等、POI/高德、URL/OCR、SSE、前端或渠道 Adapter；抽取服务、Place/Event 候选及全部核心公共实现保持唯一，`nanobot_core` 无 app 反向依赖，Git 未新增 `.env`、数据库、缓存、虚拟环境或测试生成物
- 真实 API 与风险：未读取或打印本机 `.env`，未运行 `real_provider`，百炼、高德及其他真实/外部/付费 API 调用为 0；当前无已知未关闭 P0/P1。仍未验证真实模型对歧义标题的遵循率与更广自然语言表达，保守预检之外的内容分类依赖模型严格结构输出；仅在 Python 3.13.5/macOS 验证，未在 Python 3.11/3.12、Windows 或 PostgreSQL 复测
- 主控复测范围：确认新提交的直接父提交为 `993d41bb0a35963651bf0f4ba5bfa03a8aa4b2db` 且只包含预检、回归测试和本交接；重点复测三个原始失败样例、三类 Event 标题、带城市词 Place/品牌名、明确广州范围外与四类真实不支持、输入隔离、重复/并发、1/2 次和禁止第 3 次调用、ProviderError/取消传播、完整离线及封网测试、revisions 数量、反向依赖、唯一实现和越界扫描；M0-2B 继续待验收，M0-2C 仍未开始且不允许开始

#### 2026-07-21｜M0-2 城市边界产品调整｜待联合修复

- 决策：收藏与规划城市正式解耦；允许保存其他城市 Place/Event，当前计划、外部补充和 Demo 仍只启用深圳。此前 M0-2B 的 `OUT_OF_SCOPE_CITY`、非深圳预检及城市正则修复方向终止，不继续扩大关键字或地标白名单
- 数据语义：`User` 城市继续表示默认计划上下文；CollectionItem 使用可空 `city_hint` 保存来源线索，不再以只含深圳的 `SupportedCity` 和非空检查约束限制收藏；正式 `city_code` 由 M0-3 的唯一地点引用/POI 匹配或用户确认负责，`city_hint` 不具备计划资格
- 迁移要求：`20260721_0003` 已经主控验收并进入 main，不得 amend 或重写；联合修复必须新增 `20260721_0004` 向前迁移，安全迁移既有深圳值并提供 downgrade，Repository、ORM、领域实体和测试同步调整
- 抽取要求：M0-2B 候选改为可空 `city_hint`，移除 `search_scope_city` 和 `OUT_OF_SCOPE_CITY`；明确广州/上海等地点正常形成候选，一条输入可包含多城市对象；只有标题城市词时保持待确认；菜谱、商品、跨城多日规划请求和复杂户外路线仍返回稳定不支持原因
- 计划与界面边界：当前深圳计划只选正式城市为深圳且位置已确认的收藏；收藏库后续支持城市分类、城市筛选和“城市待确认”，本次不修改前端或 UX 原型
- 范围与冗余：联合修复只扩展现有 CollectionItem、单一 Repository、现有候选和 TextExtractionService；禁止新增 CityRepository、第二套收藏/抽取/地点模型、M0-2C 自动保存、M0-2D API、M0-3 POI 实现或 U1 城市切换
- 文档：README、PRD、核心用户流程、MVP 技术方案、开发阶段和本状态文档已按该决策同步；M0-2B 继续待验收，M0-2C 继续未开始
- 外部调用：本次为文档与任务重定义，没有读取 `.env`，没有运行 `real_provider`，真实模型、高德、外部消息和付费 API 调用均为 0
- 下一步：原 M0-2B 开发窗口从本记录所在最新提交开始执行 M0-2A/M0-2B 联合修复，提交一个新的可回滚修复 commit 后交回主控完整复验；通过前不合并、不推送

#### 2026-07-21｜M0-2 城市契约联合修复｜待验收

- 分支与起点：`codex/m0-2-text-collection`；修改前 HEAD 严格等于 `e4724bb4356b3e89d59b644bec560d9e986edeab`、工作区干净，且包含已验收 `main` 基线 `76cbc96f9aa802496113f6e4216280691edb74ce`；本记录与代码将形成一个直接建立在 `e4724bb...` 上的新提交，不 amend、不合并、不推送
- M0-2A 领域与持久化：唯一城市枚举由收藏准入语义收敛为 `PlanCity`，当前只含 `SHENZHEN`；`User.city` 改名为 `User.default_plan_city` 并同步 ORM/Repository；唯一 `CollectionItem.city` 改为经 trim 的可空 `city_hint: str | None`，长度 1–100，不表示正式城市或计划资格，`None`、深圳、广州、上海均完成实体与 Repository 往返覆盖；RecognitionStatus、CollectionStatus、用户隔离和六表归属保持不变
- 0004 迁移：新增唯一 `20260721_0004_collection_city_hints.py`，`down_revision=20260721_0003`；upgrade 将 `users.city` 重命名为 `default_plan_city` 并保留深圳规划检查，把 `collection_items.city` 重命名为可空 `city_hint`、扩长到 100 并以检查约束拒绝空白、首尾空格和超长值；既有 `shenzhen` 原值无损保留为线索。downgrade 在任何 DDL 前检查全部收藏，仅空表或全为 `shenzhen` 时回退；存在 `NULL`、广州、上海或其他值时稳定拒绝，不强转、不删除且 revision、表结构与数据均不改变
- M0-2B 候选与服务：现有唯一 Place/Event 候选改用可空字符串 `city_hint`，`CandidateField.CITY` 收敛为 `CITY_HINT`，移除 `search_scope_city` 与 `OUT_OF_SCOPE_CITY`；缺少城市线索必须进入 missing/uncertain，已有线索不得同时标缺失。抽取 Prompt 明确任意城市可收藏、标题/品牌城市词不是正式城市、跨城市对象分别输出且不得编造城市；服务删除深圳证据、非深圳拒绝列表、城市正则与城市 canonicalization，广州塔等明确其他城市内容同样进入 Provider 并可形成候选
- 保持边界：空白、超长和高置信菜谱/商品/跨城多日规划/复杂户外路线仍零 Provider 调用；正常有效结果严格 1 次，只有 JSON/Schema 结构错误执行一次修复，总计最多 2 次且代码只有两个顺序 `Provider.chat` await 点；ProviderError、`asyncio.CancelledError` 继续原样传播。未创建或修改 CollectionItem 工作流，未实现 M0-2C/M0-2D、Undo/幂等、CityRepository、POI/高德、URL/OCR、SSE、前端或渠道 Adapter
- 验证环境：仓库外全新 `/tmp/shiguang-m0-2-city-qa.U6pDpd/venv`，Python 3.14.0；`python -m pip install -e ".[dev]"` 和 `python -m pip check` 退出 0，Ruff 退出 0，strict mypy 对 49 个源文件无问题
- 自动化结果：规定聚焦命令 192 passed；全部非真实测试 434 passed、1 deselected；核心测试 118 passed；迁移测试 11 passed；默认全集 434 passed、1 skipped，所有命令退出 0。临时 `/tmp` pytest 插件同时封锁 `socket.connect`、`connect_ex`、`create_connection` 与 DNS `getaddrinfo` 后，非真实全集再次 434 passed、1 deselected
- 迁移实测：仓库外临时 SQLite 完成 `upgrade 0003 → 写入既有深圳数据 → upgrade head → downgrade 0003 → upgrade head`，用户规划城市与收藏线索均无损；`alembic heads` 仅 `20260721_0004`，`alembic check` 无待生成操作；加入 `city_hint=NULL` 后降级按设计非零退出，随后 revision 仍为 `0004` 且两条原数据完整。自动化另覆盖广州、上海、空白/超长约束和三种不兼容降级无局部变化
- 安全与副作用：服务不记录或公开完整输入、系统 Prompt、模型响应、修复原文、密钥、Authorization 或 Cookie，验证继续覆盖 repr/错误摘要/重复及并发隔离；未读取或打印 `.env`，未运行 `real_provider`，真实模型、百炼、高德、外部消息及其他真实/付费 API 调用为 0；除临时 SQLite 迁移探针外无数据库、文件、消息或外部系统副作用
- 范围与冗余：`0001`、`0002`、`0003` SHA-256 与修改前完全一致，revisions 仅 `0001`–`0004`；`PlanCity`、CollectionKind、CollectionStatus、RecognitionStatus、CollectionItem、CollectionRepository、TextExtractionService、PlaceCandidate、EventCandidate 与 ExtractionResult 均保持唯一；未修改 `nanobot_core`，核心无 `app`/SQLAlchemy/FastAPI 反向依赖；Git 未跟踪 `.env`、数据库、缓存、虚拟环境或测试生成物
- 已知风险：按禁令未验证真实模型对新版 Prompt 的遵循率、真实供应商结构输出稳定性、延迟或成本；迁移和 ORM 仅在 SQLite 验证，未在 PostgreSQL、Windows、Python 3.11/3.12 复测；`city_hint` 仍是来源线索，正式城市确认与深圳计划资格必须留给 M0-3/后续规划阶段，不能由本字段推断
- 主控复测范围：确认修复提交直接父提交为 `e4724bb...` 且只含本记录列出的 M0-2 城市契约文件；复跑 192 项聚焦、434 项非真实、118 core、11 migrations、默认与封网全集；重点审查 `PlanCity/default_plan_city/city_hint` 唯一语义、0003→0004 数据保留、兼容与不兼容 downgrade、Alembic 单 head/check、广州/上海/标题城市词/多城市对象、四类零调用拒绝、Provider 1/2 次及禁止第 3 次、异常和敏感信息边界、M0-2A 用户隔离、范围与反向依赖。M0-2B 仍为待验收，M0-2C 仍未开始且暂不允许开始

#### 2026-07-21｜M0-2B｜已完成（主控验收）

- 集成：最终开发提交 `05779ead8a285a6ef558e64583e17526510f226b` 直接建立在产品文档基线 `e4724bb4356b3e89d59b644bec560d9e986edeab` 上；`codex/m0-2-text-collection` 已以 `--ff-only` 纯快进合并到 `main`，无冲突、无额外代码变化
- 验收环境：对指定提交使用独立 `git archive` 和全新 Python 3.13.5 虚拟环境；editable 安装与 `pip check` 通过，Ruff 通过，strict mypy 对 49 个源文件无问题
- 自动化结果：阶段聚焦测试 192 passed；非真实全集 434 passed、1 deselected；核心 118 passed；迁移 11 passed；默认全集 434 passed、1 skipped；封锁 socket 连接与 DNS 后非真实全集再次 434 passed、1 deselected；合并后 Ruff、mypy 和 434 项非真实测试再次通过
- 独立边界探针：14 项通过，覆盖广州 Place/Event、标题城市词保持待确认、一条输入包含广州和上海两个候选、高置信不支持内容的零调用、连续无效输出最多两次调用，以及包含 User、Session、Message、Source、CollectionItem、CollectionSource 的完整关联数据在 `0003 → 0004 → 0003 → 0004` 往返中保持完整
- 迁移：Alembic 只有 `20260721_0004` 一个 head，`alembic check` 无待生成操作；既有深圳值无损迁移为线索，空表或全深圳数据可降级，不兼容的 NULL/其他城市数据在任何 DDL 前拒绝且 revision、结构和数据不变；`0001`–`0003` 未改写
- 范围与冗余：未实现 M0-2C 自动保存/Undo/幂等、M0-2D API、M0-3 POI/高德、URL/截图、SSE、前端或渠道 Adapter；AgentRunner、ToolRegistry、ModelProvider、OpenAI-compatible Provider、Collection Repository、TextExtractionService、Place/Event 候选及城市规划语义均保持唯一，`nanobot_core` 无应用层反向依赖
- 安全与真实调用：没有未关闭的 P0/P1；未读取或打印 `.env`，未运行 `real_provider`，真实模型、百炼、高德、外部消息及其他真实或付费 API 调用均为 0
- 已知风险：新版 Prompt 尚未通过真实模型验证；迁移与 ORM 仅在 SQLite/macOS/Python 3.13.5 验证，未在 PostgreSQL、Windows 或 Python 3.11/3.12 复测；这些不阻塞当前离线 M0-2B 完成
- 下一步：M0-2C 前置条件已满足；从本交接文档提交后的最新 `main` 继续使用 `codex/m0-2-text-collection`，只实现自动保存、幂等、允许字段修改、逻辑删除和 Undo，完成后交回主控验收

#### 2026-07-21｜M0-2C｜待验收

- 分支与基线：`codex/m0-2-text-collection`；开始门禁确认 `main`、`origin/main` 和 HEAD 均严格等于指定基线 `8d47d762020b4371c8bfbd62f9ff763921c0a150`，既有阶段分支从 `05779ead...` 以 `--ff-only` 纯快进到该基线，未删除或重建；工作区修改前干净。阶段提交在本记录完成后创建，完整 SHA 见最终交接报告
- 自动保存：新增唯一应用层 `CollectionWriteService`，只消费 `ExtractionOutcome.CANDIDATES`；Source、幂等操作、全部 CollectionItem、CollectionSource 与 Undo 操作条目在单个事务中提交，任一步失败整体回滚。多候选共享一个 Source，输入对象保持不变；非候选三类结果不创建收藏或写操作
- 候选与状态：原位扩展唯一 CollectionItem，持久化商圈、地标、地铁站、Event 起止时间线索、missing_fields 和 uncertainties；`city_hint` 继续可空且可保存深圳、广州、上海或其他合法文本，不生成正式 city_code。唯一确定性映射把 M0-3 前所有 Place 保存为 `pending_details`，不伪造 POI 或 `pending_selection`；Event 仅在精确起止时间齐全时映射为 `active`，否则为 `pending_details`
- 幂等与并发：请求只保存 Source 与 ExtractionResult 规范化内容的 SHA-256 指纹，不保存原文、Prompt、模型响应、Header 或密钥；数据库以 `(user_id, idempotency_key)` 和 `(user_id, source_id)` 两个唯一约束阻止重复消息、并发同 key 与同来源重试。相同有效请求返回原有有序条目，不新增 Source/收藏/关联/Undo 操作，也不再次返回明文 Token；不同载荷稳定返回幂等冲突；不同用户可复用相同 key
- Undo：使用 `secrets.token_urlsafe(32)` 生成不可预测 Token，默认有效期 10 分钟且最大允许 24 小时；首次成功结果使用 `SecretStr` 只返回一次，数据库只保存 SHA-256 哈希并对哈希唯一。Token 绑定 user 与操作组；有效 Undo 只通过既有状态机把本次新建条目逻辑删除，不删除 Source/CollectionSource；多条一次撤销、重复撤销、已删除条目、错误用户、随机 Token、到期临界和过期、单条失败全组回滚均有覆盖
- 修改与删除：新增 extra-forbid 的显式 `CollectionItemPatch`，只开放 title、city_hint、位置/时间线索、Event 起止时间、价格、标签、缺失字段与不确定项；禁止 id/user/kind/status/version/Source/幂等/Undo/正式城市/POI 等字段。Repository 使用条件 UPDATE 和 `expected_version` 防旧写覆盖，真实变化递增 version，无变化保持原版本与更新时间；非法价格配对、Event 时间、Place Event 字段、空标题与空白/超长 city_hint 继续由现有领域校验拒绝。删除只使用既有状态机进入 deleted，重复删除幂等，默认查询隐藏、include_inactive 可复核；跨用户和不存在资源保持同一安全结果
- 数据结构与迁移：只新增 `20260721_0005_collection_reversible_writes.py`，`down_revision=20260721_0004`，未修改 `0001`–`0004`。`collection_items` 增加七个候选元数据列；新增 `collection_write_operations` 和 `collection_write_operation_items`，使用命名主键、唯一、检查与复合所有权外键，操作内 sequence 保留原结果顺序。唯一索引覆盖 key、Source、Undo 哈希和操作顺序查询；不创建 M0-2D、POI、Job、Approval 或其他后续表
- 降级安全：`0005 → 0004` 在任何 DDL 前检查两张操作表与新增候选字段；存在任何可逆操作或不可表示候选数据时明确拒绝，revision、结构和数据保持不变；空操作且新字段为空的兼容数据可无损降级并再次升级。全新数据库 upgrade head、`0004 → 0005`、兼容数据往返、两类不兼容原子失败、约束/索引/外键、单一 head 与 `alembic check` 均有自动化覆盖
- 当前环境验证：项目 `.venv` 下 `pip check`、Ruff、strict mypy（53 个源文件）全部通过；规定阶段聚焦 215 passed；非真实全集 457 passed/1 deselected；core 118 passed；迁移 15 passed；默认全集 457 passed/1 skipped。M0-2C 单元/集成/迁移聚焦 34 passed
- 全新环境验证：仓库外 `/tmp/shiguang-m02c-qa.3kGwRt` 全新 Python 3.14.0 虚拟环境完成 `pip install -e ".[dev]"` 与 `pip check`；Ruff、strict mypy、215 项阶段聚焦、457 项非真实、118 项 core、15 项迁移和默认 457 项全部得到同样结果。临时 `/tmp` pytest 插件同时封锁 `socket.connect`、`connect_ex`、`create_connection` 与 DNS `getaddrinfo` 后，457 个非真实测试再次通过、1 deselected
- Alembic CLI：仓库外临时 SQLite 依次执行 `heads`、全新 `upgrade head`、`downgrade 20260721_0004`、再次 `upgrade head` 和 `check` 全部退出 0；唯一 head 为 `20260721_0005`，无待生成迁移
- 安全、范围与冗余：未读取或打印 `.env`，未设置真实测试开关，未运行 `real_provider`，百炼、高德、网络、外部消息和真实/付费 API 调用均为 0。未修改 AgentRunner、ToolRegistry、ModelProvider 或 `nanobot_core`；未实现 M0-2D 路由/Demo/HTTP Schema、M0-3 POI/正式城市/高德、URL/截图/OCR、计划、前端、SSE 或渠道 Adapter。CollectionWriteService、CollectionRepository、SqlAlchemyCollectionRepository、CollectionItem、TextExtractionService、AgentRunner、ToolRegistry 与 ModelProvider 均各只有一套正式实现；Git 未包含 `.env`、数据库、缓存、虚拟环境、Token 或响应快照
- 已知风险：当前 ORM、并发与迁移只在 SQLite、macOS、Python 3.14.0（另由现有 `.venv` 回归）验证，尚未在 PostgreSQL、Windows 或 Python 3.11/3.12 复测；并发 SQLite 测试证明数据库唯一约束收敛到单一结果，但更高负载锁竞争留待 M1 PostgreSQL 阶段验证。M0-3 前 Place 按要求保持 `pending_details`，正式地点确认和计划资格必须由后续唯一 PoiReference/匹配流程建立
- 下一步：主控使用阶段提交独立复查设计、范围与全部命令；通过前 M0-2C 保持待验收，M0-2D 保持未开始。本分支不合并 `main`、不推送、不开始下一阶段、不执行真实或付费调用

#### 2026-07-21｜M0-2C 主控 QA 并发幂等 P1 修复｜待主控复验

- 分支与提交关系：`codex/m0-2-text-collection`；修复直接建立在验收失败提交 `d11afb7fe932590d78d7dc5f1f8c128ebee56b3c` 上，该提交的直接父提交、`main` 与 `origin/main` 均为指定阶段基线 `8d47d762020b4371c8bfbd62f9ff763921c0a150`；本记录与代码形成一个独立修复提交，不 amend、不合并、不推送
- 并发 Undo：唯一 `CollectionWriteService` 不再先查询后认领；唯一 `SqlAlchemyCollectionRepository` 使用按 `user_id + undo_token_hash + undone_at IS NULL + undo_expires_at` 的条件 UPDATE 原子设置 `undone_at`。CAS 胜者在同一事务内删除整组 CollectionItem，任意条目失败时认领与此前条目修改一并回滚；CAS 败者使用 `populate_existing` 强制重读操作，只在数据库已提交 `undone_at` 时返回 `ALREADY_UNDONE`，有效期、用户和随机 Token 边界保持 `NOT_AVAILABLE`，真实条目版本冲突继续传播而不被吞掉
- 并发逻辑 DELETE：Repository 改为针对可删除状态和可选 `expected_version` 的单条条件 UPDATE，并由数据库表达式只递增一次 version；更新未命中后强制重新读取真实行，最终为 `deleted` 时即使携带删除前版本也按幂等成功返回，最终仍为其他状态且版本已变化时继续抛出 `VersionConflictError`。PATCH 的条件 UPDATE、允许字段和乐观锁逻辑未放宽
- 原子性与数据保留：`operation.undone_at` 与全组逻辑删除仍在同一事务；Source、CollectionSource 和操作关联不删除；未新增或修改数据库迁移，既有 `0005` 结构不变
- 新增确定性测试：使用两个独立 AsyncSession、`asyncio.Barrier`、`asyncio.Event` 和受控 Repository 钩子覆盖同 Token 并发 Undo 的 `UNDONE + ALREADY_UNDONE`、仅一次实际删除、Source/CollectionSource 保留；并发 Undo 第二条目失败后认领和所有条目回滚、已启动的另一请求随后成功；同条目同版本并发 DELETE 两次均返回 deleted 且最终 version 仅增加一次；DELETE CAS 未命中而另一 PATCH 已提交时保持 `VersionConflictError` 和未删除状态。既有顺序重复 Undo/DELETE、过期、跨用户、随机 Token、批量原子性测试全部保留
- 验证环境与结果：macOS、项目受忽略 `.venv`、Python 3.13.5；`python -m pip check`、Ruff、strict mypy（53 个源文件）全部通过；任务指定四文件聚焦测试 50 passed（原 46 + 新增 4）；M0-2 全聚焦 219 passed（原 215 + 新增 4）；非真实全集 461 passed、1 deselected；core 118 passed；migrations 15 passed；默认全集 461 passed、1 skipped；4 项新增并发测试连续重复 10 轮共 40 passed，全部退出码 0
- 离线、安全与范围：测试未启用 `real_provider`，未读取或打印 `.env`，未调用百炼、高德、网络、外部消息或任何真实/付费 API；未修改 `nanobot_core`、AgentRunner、ToolRegistry、ModelProvider、迁移、M0-2D API、POI/高德、URL/OCR、计划、前端、微信或渠道 Adapter；未新增第二套 Service、Repository、CollectionItem、Undo DTO 或状态机
- 已知风险：并发语义当前仅在 SQLite、macOS、Python 3.13.5 验证，尚未在 PostgreSQL、Windows 或 Python 3.11/3.12 复测；M1 切换 PostgreSQL 时仍需重跑相同 CAS、事务回滚和锁竞争测试。当前无已知未关闭 P0；本次两个 P1 等待主控独立复验后才能关闭
- 下一步：主控核对修复提交直接包含 `d11afb7...`，重跑 219 项 M0-2 聚焦、461 项非真实全集、118 项 core、15 项 migrations 和默认全集，重点复核并发 Undo/DELETE、Undo 回滚及真实版本冲突；全部通过且无未关闭 P0/P1 后才允许纯快进合并。M0-2C 当前保持待主控复验，M0-2D 保持未开始

#### 2026-07-21｜M0-2C｜已完成（主控验收）

- 集成：阶段提交 `d11afb7fe932590d78d7dc5f1f8c128ebee56b3c` 与并发幂等修复提交 `7ee418b0514d7d4b9d16b9b8d7e805eafec4617e` 均直接建立在约定提交链上；`codex/m0-2-text-collection` 已以 `--ff-only` 纯快进到 `main`，无冲突、无额外代码变化，合并前后代码树一致
- 验收环境：指定修复 commit 的独立 `git archive`、全新 Python 3.13.5 虚拟环境；editable 安装与 `pip check` 通过，Ruff 通过，strict mypy 对 53 个源文件无问题
- 自动化结果：修复四文件聚焦 50 passed；M0-2 聚焦 219 passed；非真实全集 461 passed、1 deselected；core 118 passed；migrations 15 passed；默认全集 461 passed、1 skipped；禁用真实测试开关并把全部代理指向不可达本机端口后，非真实全集再次 461 passed、1 deselected
- 独立竞态复验：不使用开发测试钩子的真实双 Session 探针连续 10 轮验证同 Token 并发 Undo 均返回 `UNDONE + ALREADY_UNDONE`，连续 10 轮并发 DELETE 均只递增一次 version 且两次返回 deleted；真实 PATCH 后的旧版本 DELETE 继续抛出 `VersionConflictError`。新增并发认领、回滚、DELETE 幂等和真实冲突 4 项测试连续 10 轮共 40 passed
- 原子性、边界与迁移：Undo 认领、整组逻辑删除和失败回滚保持同一事务；Source、CollectionSource 与操作关联保留；顺序重复、错误用户、随机/过期 Token、跨用户资源和真实版本冲突均通过。Alembic 仅有 `20260721_0005` 一个 head，空数据 `0005 → 0004 → 0005` 与 `alembic check` 通过，`0001`–`0005` 在修复提交中均未改写
- 范围、安全与冗余：没有实现 M0-2D 路由/Demo/HTTP Schema、M0-3 POI/高德、URL/OCR、计划、SSE、前端或渠道 Adapter；CollectionWriteService、CollectionRepository、SqlAlchemyCollectionRepository、CollectionItem、TextExtractionService、AgentRunner、ToolRegistry 与 ModelProvider 均保持唯一。未跟踪 `.env`、数据库、缓存、虚拟环境、Token 或响应快照；未读取本机 `.env`，未运行 `real_provider`，真实或付费 API 调用为 0
- 合并后检查：在 `main` 上再次执行 Ruff、strict mypy 和非真实全集，分别通过、53 个源文件无问题、461 passed/1 deselected
- 验收结论：原两个并发幂等 P1 已关闭，没有未关闭的 P0/P1；M0-2C 完成标准满足
- 已知风险：本轮并发与迁移只在 macOS、Python 3.13.5 和 SQLite 验证，未在 PostgreSQL、Windows 或 Python 3.11/3.12 复测；M1 切换 PostgreSQL 时必须重跑相同 CAS、回滚和锁竞争测试
- 下一步：M0-2D 前置条件已满足；从本次文档提交后的最新 `main` 继续使用 `codex/m0-2-text-collection`，只实现最小 API 和 Demo 初始化，完成后交回主控验收

#### 2026-07-21｜M0-2D｜待主控验收

- 分支与基线：`codex/m0-2-text-collection`；开始门禁确认修改前工作区干净，现有阶段分支以 `--ff-only` 从 `7ee418b...` 快进到指定基线 `5d52c820733f3072d732b65701f27f39aebcf792`，且 `main`、`origin/main` 与快进后的 HEAD 均严格等于该基线；`0005`、461 项非真实测试及 M0-2C 并发回归完整存在。阶段提交随本记录创建，完整 SHA 见开发窗口最终交接报告
- 路由与 Schema：新增严格 extra-forbid 的 `/api/v1` 契约：`POST /demo/sessions`、`POST /sessions/{session_id}/messages`、`GET /agent-runs/{trace_id}`、Collection 列表/详情/PATCH/DELETE 和路径绑定 Undo。消息接口只接受纯文字与必填幂等键，同步执行并返回真实终态，不返回虚假 `queued`；PATCH 请求的 `changes` 直接复用唯一 `CollectionItemPatch`，领域价格、Event 时间、Place/Event 字段和允许字段校验未复制到路由
- 身份与隔离：M0 使用服务端常量 `DEMO_USER_ID`，创建接口不接受客户端 `user_id`；每个 Repository、AgentRun 查询和应用服务调用仍显式携带该身份。Demo 初始化复用同一固定 Demo User、每次创建新的 Session；不存在与跨用户 Session、Collection、PATCH、DELETE 和 AgentRun 均返回相同 404。API 响应不公开内部 user/row ID、Undo 哈希、请求指纹、tool call ID 或参数指纹
- 唯一工作流与运行记录：新增唯一 `TextCollectionWorkflow`，只负责串接现有 `TextExtractionService`、`CollectionWriteService` 与原位扩展的唯一 `AgentRunService.execute_application()`；未新增 Runner、Provider、Repository、抽取、写入、状态机或运行记录实现。TextExtractionService 的可选观察器只上报既有 `ModelResponse` 元数据，AgentRun 不保存 Prompt、消息正文或完整模型响应；ProviderError 使用稳定公开码，`CancelledError` 落为 cancelled 后继续传播
- 消息幂等：Message ID、Source ID 和 trace ID 由服务端 `user_id + idempotency_key` 的 SHA-256 命名空间确定性派生，Message 主键与既有 `(user_id, idempotency_key)`、`(user_id, source_id)` 唯一约束共同防重复；同进程相同键请求串行进入数据库权威检查。顺序及并发重试只产生一个 Message、Source、CollectionItem 集合、CollectionSource 集合和 Undo operation，返回相同 message/trace/item ID，且明文 Undo Token 只在首次创建结果出现；同键不同正文或 Session 返回 409
- 查询与城市语义：`CollectionQueryService` 在应用层提供带 ID 决胜的稳定 created/updated 正反序分页，支持 `city_hint`、`city_pending`、district、kind、status、tags 与 `include_inactive`；显式 status 可查询 deleted/archived，默认仍隐藏 inactive。响应中的 `city_pending` 只由 `city_hint is None` 展示推导，未生成正式 city_code，也未改变深圳计划资格；广州、上海和城市待确认收藏均可保存、组合筛选和查看
- 修改、删除与 Undo：PATCH/DELETE 继续只调用唯一 `CollectionWriteService`，保留 no-op 版本、真实版本冲突和并发 DELETE 幂等。`undo_collection_item()` 在同一事务中先读取 Token 操作组并确认包含路径 item，再执行既有数据库 CAS 原子认领和全组逻辑删除；错误用户、随机、错误 item、过期 Token 统一为安全不可用，重复/并发有效 Undo 保持 `UNDONE + ALREADY_UNDONE`，Source 与 CollectionSource 不删除
- 错误与安全：请求 Schema 非法 422，不存在/跨用户 404，真实版本与幂等冲突 409，未注入 Provider 503，ProviderError 502，同步总时限 504；同一失败幂等请求保持原终态与稳定错误码。请求校验响应只包含字段路径和错误类型，不回显非法正文、Undo Token 或伪造 user ID。请求日志仍只含 request ID、方法、路径、状态和耗时，不记录查询、正文、Authorization 或 Cookie；公开运行摘要不含 Prompt、消息、完整响应、原始工具参数、异常链或堆栈
- 配置、迁移与范围：无新增配置变量或迁移，未修改 `0001`–`0005`；应用、`/healthz`、OpenAPI 与 Demo Session 在无模型配置时正常，文字接口只通过显式依赖注入使用离线 Fake，未自动构造真实 Provider。未实现 M0-3 POI/高德/正式城市/候选/分店、URL/HTML/OCR/文件、SSE/事件/取消、Job/Worker、正式身份、计划、前端、微信或渠道 Adapter
- 自动化覆盖：新增 16 项 M0-2D API 聚焦测试，覆盖无配置 Demo、客户端身份伪造、Place/Event/广州/上海/一条多收藏/标题城市词但待确认、四类输入/结构错误、顺序与并发幂等、同键载荷冲突、AgentRun 脱敏、筛选分页、PATCH/no-op/领域非法/版本冲突、并发 DELETE、随机/错误 item/过期/重复/并发 Undo、跨用户、ProviderError、CancelledError、同步总时限、事务中途失败回滚、OpenAPI 范围和响应/日志脱敏；既有 M0-2A/B/C 单元、集成、迁移与并发测试全部保留
- 验证环境与结果：macOS、仓库外最终快照、全新 Python 3.13.5 虚拟环境与重新安装的 `backend[dev]`；安装和 `pip check` 退出 0，Ruff 退出 0，strict mypy 对 62 个源文件无问题。API 聚焦 16 passed；M0-2A/B/C 聚焦 204 passed；非真实全集 477 passed/1 deselected；core 118 passed；migration 15 passed；默认全集 477 passed/1 skipped，全部退出 0。Alembic `heads` 仅 `20260721_0005`，全新 upgrade、`check`、空数据 downgrade `0004`、再次 upgrade 与 `check` 均通过且无待生成迁移；macOS `sandbox-exec` 系统级拒绝全部网络后非真实全集再次 477 passed/1 deselected
- 真实能力与风险：未读取本机 `.env`，未设置或运行 `RUN_REAL_MODEL_TESTS=1`，百炼、高德、其他网络、外部消息及真实/付费 API 调用均为 0；真实模型对抽取结构的遵循率、真实供应商错误与延迟仍沿用既有未验证边界。M0 固定 Demo User 是明确临时身份方案，不等于 M1 Web Session；同进程锁只优化同步并发响应，数据库唯一约束仍是数据一致性边界，M1 PostgreSQL/多进程需复跑相同并发契约
- 下一步：主控在完整开发 commit 上独立复测并审查范围；验收通过前本分支不合并、不推送，M0-3 保持未开始且不允许开始，不执行任何真实或付费调用

#### 2026-07-22｜M0-2D｜已完成（主控验收）

- 提交与集成：开发提交 `864cceedc80edbf8f45bbb757676794afc3794e8` 的直接父提交为指定基线 `5d52c820733f3072d732b65701f27f39aebcf792`，基线同时等于验收前 `main`、`origin/main` 和 merge-base；主控以 `--ff-only` 纯快进合并到 `main`，无冲突、无额外代码变化，合并前后代码树哈希均为 `a931524b9117476ae1054174b0d8a09ab98782f6`
- 验收环境：指定开发 commit 的仓库外 `git archive`、全新 Python 3.13.5 虚拟环境；editable 安装和 `pip check` 通过，Ruff 通过，strict mypy 对 62 个源文件无问题
- 自动化结果：M0-2D API 契约 16 passed；非真实全集 477 passed、1 deselected；core 118 passed；migrations 15 passed；默认全集 477 passed、1 skipped。macOS `sandbox-exec` 系统级拒绝全部网络后，非真实全集再次 477 passed、1 deselected；真实测试标记未运行
- 迁移与合并后检查：本阶段没有迁移变化；Alembic 只有 `20260721_0005` 一个 head，全新 `upgrade head`、`alembic check`、空数据 `downgrade 20260721_0004`、再次升级和检查均通过。纯快进合并后重新安装当前树，Ruff、strict mypy 和 477 项非真实测试再次通过
- 独立边界探针：并发创建 24 个 Demo Session 均返回唯一 Session，数据库只创建一个 M0 固定 Demo User；跨 Session 复用同一用户幂等键稳定返回 409 且不重复执行；开发测试及主控复核同时覆盖顺序/并发消息幂等、不同载荷冲突、跨用户 Session/Collection/AgentRun 404、路径错误/随机/过期/重复/并发 Undo、PATCH no-op 与版本冲突、并发 DELETE、ProviderError、`CancelledError`、同步超时、事务失败回滚、筛选分页、无配置启动、OpenAPI 和日志/响应脱敏
- 范围与冗余：实现严格限于 M0-2D 最小 API 和串接既有应用服务；没有新增迁移、真实 Provider、POI/高德、正式城市、候选评分、URL/OCR、计划、SSE、前端、Worker 或正式身份。AgentRunner、ToolRegistry、ModelProvider、OpenAI-compatible Provider、AgentRun Repository、Collection Repository、TextExtractionService、CollectionWriteService 和 API 路由均保持唯一，`nanobot_core` 无应用层反向依赖
- 安全与真实调用：Git 中没有 `.env`、数据库、缓存、虚拟环境、密钥或响应快照；主控未读取或打印本机 `.env`，未启用 `RUN_REAL_MODEL_TESTS`，未调用百炼、高德、网络、外部消息或任何真实/付费 API。请求正文、Undo Token、Authorization、Cookie、Prompt、完整模型响应、工具参数指纹和内部用户 ID 均未进入公开错误或请求日志
- 验收结论：同步文字收藏闭环、范围、异常、边界、幂等、用户隔离、安全和冗余标准满足，没有未关闭的 P0/P1，M0-2D 与整个 M0-2 完成
- 已知 P2 与风险：进程内 `IdempotencyLockRegistry` 当前会为已完成的唯一 key 保留锁对象，长时间高基数运行可能缓慢增长；它不影响数据库唯一约束和本阶段单进程正确性，不阻塞 M0 Gate，但 M1 正式身份/多进程设计或 M3 Demo 限流前必须改为引用计数清理或有界生命周期并补充并发回归。固定 Demo User、SQLite/macOS/Python 3.13.5 及单进程行为仍是 M0 临时边界，PostgreSQL、多进程和公开 Demo 的物理数据隔离需按既定后续阶段复验
- 下一步：M0-3A 前置条件已满足；从本次交接文档提交后的最新 `main` 创建 `codex/m0-3-poi-matching`，只实现供应商无关 MapProvider 契约、内部 POI DTO 和覆盖深圳及至少一个其他城市的离线 Stub/Fixture。M0-3B 真实高德、M0-3C 匹配评分、M0-3D 分店策略及其他后续能力不得提前开始

#### 2026-07-22｜M0-3A｜待主控验收

- 分支与基线：`codex/m0-3-poi-matching`；开始门禁确认修改前工作区干净，`HEAD`、`main`、`origin/main` 和 merge-base 均严格等于指定基线 `5b64a58526910561494f0c6381f7671ce80c30c3`，阶段分支此前不存在，M0-2D 提交 `864ccee...` 已集成。阶段提交随本记录创建，完整 SHA 见开发窗口最终交接报告
- 唯一契约与归属：`backend/app/domain/places/contracts.py` 是 `CityScope`、`Coordinate`、`Poi`、搜索/详情/路线/天气/导航请求响应 DTO 的唯一正式定义；`backend/app/providers/map.py` 是 `MapProvider`、`MapProviderError` 和 `MapProviderErrorCode` 的唯一正式定义。`search_poi`、`get_poi`、`route`、`weather`、`build_navigation_uri` 均接收各自 strict 请求对象，五类请求全部显式携带 `CityScope`；这是按最新阶段文档对技术方案早期简写签名的收敛，不读取或修改进程级当前城市
- DTO 语义：全部内部 DTO 使用 strict、extra-forbid、frozen、禁止 NaN/Infinity 且隐藏校验输入的 Pydantic 契约；稳定 `city_code` 与来源 `city_hint` 分离，坐标显式携带 `gcj_02/wgs_84`，路线端点必须同坐标系，距离/耗时分别为非负米/秒，天气为 `date` 和 `[-100, 100]` 摄氏温度摘要，导航 URI 只接受无凭证的 `geo/https`。POI 提供内部 ID、名称/分店名、城市、行政区、商圈、地址、坐标、内部类型及可选电话/营业摘要，不保存 `adcode/pname/cityname`、Key、Header、签名或供应商原始响应
- 离线 Stub 与 Fixture：唯一 `StubMapProvider` 直接实现正式接口，通过构造参数注入深拷贝后的不可变映射；无网络、环境变量、供应商 SDK、共享响应队列、全局城市、缓存、重试、退避或熔断。未配置搜索返回显式空结果，详情不存在和不可用能力使用固定安全错误，超时按请求 Fixture 决定；相同输入返回内容相等且对象独立的快照，不修改请求或调用者映射；`asyncio.CancelledError` 原样传播，测试 Hook 的内部异常不保留在公开错误上下文
- 城市与场景：共享 `backend/tests/fixtures/maps.py` 集中提供深圳和广州数据，覆盖两城唯一结果、深圳同名连锁两结果、无结果、超时、详情成功/不存在、两城路线、天气和导航 URI。深圳/广州连续、交错及 40 个并发调用按请求局部城市返回，无串值；查询文本出现“广州”等城市词不会覆盖显式深圳范围，也没有把默认深圳搜索范围写成正式城市
- 自动化覆盖：新增 35 项聚焦测试，覆盖 DTO 正常/未知字段/不可变、非法城市、坐标边界/非有限值、路线负数/布尔值/混合坐标系、天气日期/温度、导航 URI、混城/重复 POI、五类接口签名、唯一/多结果/无结果/超时、详情、路线/天气/导航、稳定快照、输入隔离、跨城顺序与并发、取消透传、内部异常收敛、校验/异常/repr/日志脱敏和供应商字段缺失
- 验证环境与结果：macOS、仓库受忽略 `.venv`、Python 3.13.5；最终 `pip install -e ".[dev]"` 与 `pip check` 退出 0，Ruff 退出 0，strict mypy 对 66 个源文件无问题；聚焦 35 passed；非真实全集 512 passed/1 deselected；core 118 passed；migrations 15 passed；默认全集 512 passed/1 skipped，全部退出 0。macOS `sandbox-exec` 系统级拒绝全部网络后，非真实全集再次 512 passed/1 deselected
- 迁移、依赖与配置：没有新增依赖、环境变量、数据库表、ORM、Repository 或 Alembic revision；`20260721_0001` 至 `0005` 未修改，仓库外 `/tmp` 数据库从空库 upgrade 后 `alembic heads` 仍仅 `20260721_0005`，`alembic check` 报告无待生成操作
- 安全、范围与冗余：未读取或打印本机 `.env`，未设置真实测试开关，百炼、高德、其他网络、外部消息及真实/付费 API 调用均为 0。未修改 `nanobot_core`、CollectionItem、收藏状态、M0-2 API、迁移或基础设施；未实现真实高德字段映射/配置/HTTP、匹配评分/置信度/最多三个候选、正式 POI 引用、exact/any_branch、用户选择、URL/OCR、计划、SSE、前端或 Worker。MapProvider、Stub、POI/坐标/路线/天气/导航 DTO 各有单一正式归属，深圳和广州复用同一 Provider 与同一 Fixture 构造，不复制生产算法
- 已知风险：M0-3A 只证明内部边界和确定性离线行为，尚未验证真实高德字段、坐标、POI ID、路线/天气响应、URI 格式、额度或错误映射；这些必须等待 M0-3B 的单独实现和用户明确真实调用授权。当前仅在 macOS/Python 3.13.5 复测，未在 Python 3.11/3.12、Windows 或真实供应商环境验证；当前没有已知未关闭 P0/P1
- 主控复测重点：确认提交直接基于指定 baseline，复核五类请求均显式城市作用域、DTO 不含供应商字段、Stub 无网络/环境/队列/城市状态、深圳与广州并发隔离、取消及异常脱敏、无迁移/配置/后续阶段越界；在干净 Python 3.11+ 环境重跑 35 项聚焦、512 项非真实、118 项 core、15 项 migrations、默认全集、Alembic head/check 与网络封锁
- 下一步：主控独立验收通过后才允许纯快进合并并另行安排 M0-3B；本开发窗口不合并 `main`、不推送、不调用真实高德、不进入 M0-3B/C/D

#### 2026-07-22｜M0-3A 验收 P1 修复｜待主控复验

- 分支与提交关系：`codex/m0-3-poi-matching`；修复直接建立在待修复提交 `576eea53d3096a2b5a5add068ceb54b7bba1b8d5` 上，不 amend。开始门禁确认该提交为干净工作区 HEAD，其直接父提交、`main` 和 `origin/main` 均为指定阶段基线 `5b64a58526910561494f0c6381f7671ce80c30c3`；修复提交随本记录创建，完整 SHA 见开发窗口最终交接报告
- P1 修复：唯一公开 `NavigationUri` 契约现在先拒绝空白、ASCII/Unicode 控制或格式字符、反斜杠及损坏百分号转义，再由 `urlsplit` 做结构拆分。HTTPS 必须有通过 IP/DNS/IDNA 标签校验的 hostname、无 username/password、端口可解析且不为 0；空 authority、缺失 hostname、损坏或越界端口均拒绝。geo 必须使用无 authority/fragment 的坐标 payload，纬度和经度恰好两项、均可解析且有限，并分别位于 `[-90, 90]` 与 `[-180, 180]`；可选参数必须是非空 `name=value`。`geo:`、`geo:?q=`、`https://`、`https:///missing-host`、NaN/Inf、越界坐标和损坏结构均不再通过
- 安全边界：URI 失败统一产生固定 `navigation URI is invalid` 的 Pydantic 校验错误，`uri` 不进入对象 repr；模型继续启用 `hide_input_in_errors`，公开错误字典按既有 `errors(include_input=False, include_context=False, include_url=False)` 生成。参数化安全测试确认伪 Authorization/secret、完整非法 URI和伪原始响应不进入异常字符串、repr、日志或公开字典。Provider 与 Stub 未新增 URI 校验，`NavigationUri` 仍是唯一校验路径
- city_code 去重：在同一个 `backend/app/domain/places/contracts.py` 内增加非导出的 `_CityCode = Annotated[str, Field(...)]`，由 `CityScope`、`Poi`、`PoiSearchResult`、`RouteResult`、`WeatherResult` 五类契约复用唯一 `_CITY_CODE_PATTERN`。没有新增公共模块、CityScope 或响应 DTO；当前合法代码继续原样通过，前后空白、大小写、过短及其他非法格式继续拒绝，JSON Schema 测试确认五类字段来自同一 pattern
- 测试覆盖：聚焦测试由 35 增至 73，新增参数化拒绝空 geo/HTTPS、空 hostname、凭证、无效 DNS、损坏/0/越界端口、非法百分号、换行/NUL/C1 控制字符、反斜杠、非法/缺失/多余/越界/NaN/Inf geo 坐标及 fragment；接受深圳/广州现有 URI、Stub fallback 实际生成的两城 URI、合法 HTTPS、IPv4/IPv6、`(-90,-180)` 与 `(90,180)` 边界、合法 geo 参数。另验证输入不变、重复构造稳定且对象独立，两城 Fixture、交错/并发隔离和既有 MapProvider 契约全部保持
- 验证环境与结果：macOS、仓库受忽略 `.venv`、Python 3.13.5；`python -m pip check`、Ruff、strict mypy（66 个源文件）全部退出 0；指定聚焦 73 passed；非真实全集 550 passed/1 deselected；core 118 passed；migrations 15 passed；默认全集 550 passed/1 skipped，全部退出 0。macOS `sandbox-exec` 系统级拒绝全部网络后，非真实全集再次 550 passed/1 deselected
- 范围、网络与真实调用：相对 `576eea53...` 只修改 POI/导航契约、两份对应测试及本 DEV_STATUS 记录；`app/providers`、`nanobot_core`、配置、依赖、数据库、迁移、CollectionItem 和收藏状态均未修改。未读取或修改 `.env`，未启用真实测试，网络请求、高德、百炼、外部消息及任何真实/付费 API 调用均为 0；没有 M0-3B 真实适配、M0-3C 评分/候选选择或 M0-3D exact/any_branch/分店业务
- 已知风险与结论：当前 URI 契约有意只接受标准坐标型 geo URI，不接受仅用自由文本 `q` 且没有坐标 payload 的非标准形式；现有 Stub 和 Fixture 不受影响。真实高德 URI 格式仍必须在 M0-3B 获得单独授权后映射和验证。本轮未在 Python 3.11/3.12 或 Windows 复测；P1 已由自动化覆盖关闭，当前没有已知未关闭 P0/P1
- 下一步：主控直接复核新修复提交与 `576eea53...` 的差异，重点重跑 73 项聚焦、550 项非真实、网络封锁和 URI 安全探针；复验通过前不合并、不推送、不开始 M0-3B/C/D

#### 2026-07-22｜M0-3A｜已完成（主控验收）

- 提交与集成：阶段实现提交 `576eea53d3096a2b5a5add068ceb54b7bba1b8d5`、P1 修复提交 `b72271bc6147fcac3be50defef3c09d482b016f5`；二者均建立在指定基线 `5b64a58526910561494f0c6381f7671ce80c30c3` 上。验收前 `main` 与 `origin/main` 均为该基线，主控以 `--ff-only` 纯快进到修复提交，无冲突或额外代码变化
- 修复复验：`NavigationUri` 已拒绝空 `geo`、无 hostname HTTPS、凭据、损坏端口/百分号、控制字符、非法 DNS、越界或非有限坐标；合法坐标型 `geo`、HTTPS、IPv4/IPv6 和边界坐标保持可用。`city_code` 由同文件内唯一共享约束提供，没有新增第二套 CityScope、响应 DTO 或校验路径，原 P1 已关闭
- 验收环境：修复 commit 的仓库外 `git archive` 与全新 Python 3.13.5 虚拟环境；安装、`pip check`、Ruff 和 strict mypy（66 个源文件）均通过
- 自动化结果：M0-3A 聚焦 73 passed；非真实全集 550 passed、1 deselected；core 118 passed；migrations 15 passed；默认全集 550 passed、1 skipped。系统级禁网后非真实全集再次 550 passed、1 deselected；真实测试未运行
- 迁移与合并后检查：本阶段无迁移变化；空 SQLite 数据库 `upgrade head`、`alembic check` 通过且 Alembic 仅有 `20260721_0005` 一个 head。纯快进合并后 Ruff、strict mypy 和 550 项非真实测试再次通过
- 独立边界探针：额外拒绝 9 个无效 URI、接受 5 个合法 URI；同一个 StubMapProvider 在深圳/广州的搜索、详情、路线、天气和导航之间完成 200 次并发调用，结果均保持请求局部城市且无状态污染
- 范围、冗余与安全：实现限于唯一 MapProvider、内部地点契约和离线 Stub/Fixture；没有真实高德适配、评分/候选、exact/any_branch、正式 POI 写入、数据库迁移或公共模块复制。MapProvider、StubMapProvider、AgentRunner 和 ToolRegistry 均保持唯一；Git 未跟踪 `.env`、数据库、缓存或虚拟环境。主控未读取本机 `.env`，网络、高德、百炼、外部消息及真实/付费 API 调用均为 0
- 验收结论：范围、契约、异常、边界、并发隔离、取消、安全和代码冗余检查满足要求，没有未关闭的 P0/P1，M0-3A 完成
- 下一步：M0-3B 前置条件已满足；从本次交接文档提交后的最新 `main` 创建阶段分支，只实现服务端高德 Web 服务适配并复用现有 MapProvider/DTO。默认测试必须离线；真实验收前由用户在本机 `.env` 配置 Web 服务 Key 并单独授权，高德真实调用不得默认执行

#### 2026-07-22｜M0-3B｜待主控验收

- 分支与基线：`codex/m0-3b-amap-provider`；开始门禁确认修改前工作区干净，`HEAD`、`main`、`origin/main` 与 merge-base 均严格等于指定基线 `33421205241461b94482a2390e3ca9b5f716bdcc`，阶段分支此前不存在，M0-3A 实现、P1 修复和主控交接均已集成。阶段提交随本记录创建，完整 SHA 见开发窗口最终交接报告
- 唯一契约与适配归属：`AmapMapProvider` 直接实现 M0-3A 唯一 `MapProvider`，完整复用 `CityScope`、POI、路线、天气和导航 DTO；没有创建第二套 AgentRunner、ToolRegistry、MapProvider、地点 DTO 或供应商通用层。高德字段、错误码、城市码和 HTTP 生命周期只收敛在 `backend/app/providers/amap.py`，通用 Provider 错误保持固定安全摘要
- 城市与字段映射：单一私有城市表支持深圳 `440300/0755` 与广州 `440100/020`，将行政区编码、城市编码、别名和行政区前缀校验集中管理；搜索与详情拒绝重复 POI、混城结果、错误 adcode、非法坐标及缺失关键字段。来源坐标明确标为 GCJ-02，POI 类型通过一份前缀映射转换为内部类型，不把高德原始响应、Key、请求 URL、Header 或签名带入内部 DTO
- 五类能力：搜索使用文本检索并显式限定请求城市，空结果保持空列表；详情严格校验唯一且匹配的 POI ID；步行、骑行、公交和驾车分别映射高德 v5 路线端点，只返回首个方案的总距离与总耗时；天气映射预报日期、昼间温度、最低/最高温和天气摘要；导航 URI 在本地构造无凭证的 `https://uri.amap.com/marker`，不发 HTTP 请求。端点与参数选择已按高德公开 Web 服务及 URI 文档核对，真实响应兼容性仍待授权验收
- HTTP、重试与取消：唯一 `create_amap_http_client` 构造受控 `httpx.AsyncClient`，禁止重定向并统一 base URL、超时和可注入离线 transport；Provider 支持显式关闭和异步上下文管理。每个逻辑请求最多重试 1 次，只覆盖超时、连接传输错误、429、选定 5xx 与高德限流/服务繁忙码；数字 `Retry-After` 经上限裁剪后交给可注入等待函数。鉴权、参数、数据不存在、响应结构错误和其他 4xx/5xx 不重试，`asyncio.CancelledError` 原样传播
- 配置与安全：新增 `AMAP_API_KEY`、HTTPS base URL、有限正数超时、`0..1` 重试及有限退避上限配置；Key 使用 `SecretStr`，仅在显式构造真实 Provider 时要求存在，默认应用启动与离线测试不需要 Key。`.env.example` 只提供空白占位和安全默认值；错误、repr、日志和公开字典均不保留 Key、Authorization、完整请求 URL、原始响应或恶意供应商文本
- 自动化覆盖：新增 93 项聚焦测试，连同既有配置测试合计 `114 passed`，真实入口 `1 skipped`；覆盖深圳/广州搜索、空结果、详情、四种路线、天气、导航、类型/字段/城市映射、重复与混城拒绝、超时、连接失败、429/Retry-After、选定 5xx、高德 infocode、鉴权/输入/其他 4xx/5xx 不重试、attempts 上限、取消透传、客户端关闭、输入隔离、并发无城市串值及多路径脱敏
- 最终验证：macOS、仓库受忽略 `.venv`、Python 3.13.5；`pip install -e ".[dev]"`、`pip check`、Ruff 与 strict mypy（67 个源文件）全部退出 0；聚焦 `114 passed/1 skipped`；非真实全集 `643 passed/2 deselected`；core `118 passed`；migrations `15 passed`；默认全集 `643 passed/2 skipped`。macOS `sandbox-exec` 系统级拒绝全部网络后，非真实全集再次 `643 passed/2 deselected`
- 真实测试入口与调用上限：`backend/tests/integration/test_amap_real.py` 默认跳过，只有进程环境严格设置 `RUN_REAL_MAP_TESTS=1` 后才读取根目录 `.env` 并要求有效高德配置；逻辑场景固定为深圳搜索、广州搜索、详情、路线、天气 5 次 HTTP 读取和本地导航，默认重试上限下理论最多 10 次 HTTP 尝试。本轮没有设置开关、没有读取或修改 `.env`、没有运行该入口，高德及其他真实/付费 API 调用均为 0
- 迁移、依赖、范围与冗余：没有新增运行时或开发依赖、数据库表、ORM、Repository 或 Alembic revision；现有 migration 未修改。未修改 `nanobot_core`、CollectionItem、收藏状态或 M0-2 API；未实现 M0-3C 匹配评分/置信度/最多三个候选，也未实现 M0-3D exact/any_branch/分店选择、正式 POI 写入、URL/OCR、计划、SSE、前端或 Worker
- 已知风险：真实高德 Key 类型、配额、字段差异、HTTP 状态与业务 infocode 的组合、路线/天气可用性和 POI 数据质量尚未通过线上响应验证；当前城市白名单仅深圳和广州，天气结果依赖高德预报中存在请求日期，路线只映射首个方案总量而不保存步骤。当前仅在 macOS/Python 3.13.5 复测，未在 Python 3.11/3.12、Windows 或真实供应商环境验证；当前没有已知未关闭 P0/P1
- 主控复测重点与下一步：先独立复核提交直接基于指定 baseline、唯一 MapProvider/客户端构造、深圳广州映射、每类错误的 attempts、取消/关闭/脱敏、无迁移/依赖/后续阶段越界，并重跑聚焦、非真实、core、migrations、默认全集与系统禁网测试。离线验收通过后，再由用户在本机 `.env` 放置 Web 服务 Key 并另行明确授权执行受限真实 QA；本开发窗口不合并 `main`、不推送、不调用真实高德、不进入 M0-3C/D

#### 2026-07-22｜M0-3B 主控验收 P1 修复｜待主控复验

- 分支与提交关系：修复在 `codex/m0-3b-amap-provider` 上直接基于待修复提交 `06834a4e3e14a6dc84c1d6d0da3b1fbe8b3adddb` 追加，不 amend；开始时工作区干净且 HEAD 精确等于该提交，`main`、`origin/main` 与 merge-base 均为阶段基线 `33421205241461b94482a2390e3ca9b5f716bdcc`。修复提交随本记录创建，完整 SHA 见开发窗口最终交接报告
- 官方 origin 锁定：`AmapProviderSettings` 是配置与直接 Provider 构造共享的唯一规范化门禁，只接受无凭证、无显式端口、无查询/fragment 且 path 为空或单个末尾 `/` 的 `https://restapi.amap.com`，并统一返回无末尾斜杠的 canonical origin；其他 hostname、`restapi.amap.com.evil.example`、userinfo、HTTP、443/其他显式端口、路径、查询、fragment、空白/控制字符、反斜杠和损坏 URL 均在 HTTP Client 创建前以固定错误拒绝，错误不回显 URL 或 Key。参数化测试确认非法配置不能完成 Provider 构造且 HTTP attempts 为 0
- 异常链清理：Timeout、Transport、JSON 解码、Pydantic/字段映射和可注入等待异常只在内部 handler 中转换为无敏感字段的状态，退出 `except` 后再新建并抛出固定 `MapProviderError`；不再依赖 `raise ... from None` 隐藏 context。公开错误的 `__context__` 与 `__cause__` 均为 `None`，属性、args、repr、公开字典和日志不保留 request、response、完整 URL、Key、原始正文、供应商 `info` 或恶意字段；`asyncio.CancelledError` 继续原样传播
- infocode 分类与 attempts：`10012 INSUFFICIENT_PRIVILEGES`、`10013 USER_KEY_RECYCLED` → `AUTHENTICATION_FAILED`、`retryable=false`、1 attempt；`10014 QPS_HAS_EXCEEDED_THE_LIMIT`、`10015 GATEWAY_TIMEOUT/QPS`、`10019 CQPS_HAS_EXCEEDED_THE_LIMIT` → `RATE_LIMITED`、`retryable=true`、失败时最多 2 attempts；`10016 SERVER_IS_BUSY`、`10017 RESOURCE_UNAVAILABLE` → `UNAVAILABLE`、`retryable=true`、失败时最多 2 attempts。上述可恢复码均覆盖第一次失败/第二次成功与两次均失败；权限码覆盖即使后续响应可成功也只尝试一次。`2xxxx` 与明确非法请求不重试，未知码保持 `INVALID_RESPONSE`，`3xxxx` 保持最多一次额外尝试，公开错误不使用 `info` 文本
- 稳定 provider 身份：在 M0-3A 唯一 `Poi` 上最小增加唯一受限枚举 `PoiProvider`，当前只允许 `AMAP="amap"`；Amap 搜索和详情都明确输出 `provider=amap`，并与供应商局部 `poi_id` 形成后续 `PoiReference` 可复用的稳定身份。搜索结果去重使用 `(provider, poi_id)`；正式 `city_code` 与 `coordinate_system=gcj_02` 继续保留。离线 Stub Fixture 明确选择模拟 Amap 来源，因此同样确定性携带 `provider=amap`；没有新增 Poi/PoiReference/候选 DTO、Repository、表或迁移
- 新增安全与契约覆盖：Base URL 覆盖域名混淆、端口、路径、凭证和控制字符；异常图测试分别构造 URL 含伪 Key 的 Timeout/ConnectError、正文含伪 secret 的非 JSON、字段含伪 secret 的 Pydantic 失败，并递归检查 context/cause/vars/args、str、repr、公开字典与日志；契约/Stub/Amap/真实入口静态断言搜索与详情保留 provider、poi_id、city_code 和 GCJ-02
- 验证环境与结果：macOS、仓库受忽略 `.venv`、Python 3.13.5；`pip install -e ".[dev]"`、`pip check`、Ruff 与 strict mypy（67 个源文件）均退出 0；用户指定聚焦集合 `237 passed/1 skipped`，其中 skip 是未授权真实高德入口；非真实全集 `693 passed/2 deselected`；core `118 passed`；migrations `15 passed`；默认全集 `693 passed/2 skipped`。系统级 `sandbox-exec` 拒绝全部网络后，非真实全集再次 `693 passed/2 deselected`
- 网络、安全与范围：所有测试均显式移除 `RUN_REAL_MAP_TESTS`/`RUN_REAL_MODEL_TESTS` 并设置 `APP_ENV=test`；未读取、打印或修改本机 `.env`，未运行 `real_map_provider`，高德、百炼、其他网络及真实/付费 API 调用均为 0。没有依赖或迁移变化，没有修改 `nanobot_core`、CollectionItem、收藏状态、M0-2 API、前端或基础设施；MapProvider、AmapMapProvider、StubMapProvider、HTTP Client 构造、城市表、Poi 和错误体系仍各有唯一归属
- 已知风险与下一步：真实高德响应、Key 权限、配额、线上 infocode/HTTP 组合、POI 字段质量及路线/天气兼容性仍未验证；当前 provider 枚举只包含本阶段唯一正式地图来源 Amap，未来新增供应商必须另行扩展同一枚举和契约，不得复制 DTO。当前仅在 macOS/Python 3.13.5 复测。主控修复复验通过后，仍需用户在本机 `.env` 配置 Web 服务 Key 并对受限真实验收单独授权；本分支不合并、不推送，且没有实现 M0-3C 评分/候选/用户选择或 M0-3D exact/any_branch/分店策略

#### 2026-07-22｜M0-3B 配置硬边界 P1 修复｜待主控复验

- 分支与提交关系：修复在 `codex/m0-3b-amap-provider` 上直接基于待修复提交 `e2412391533e8c111ef76f82475e2fe8865934d3` 追加，不 amend；开始门禁确认工作区干净，分支、HEAD 与该提交精确一致，`main`、`origin/main` 与 merge-base 均为阶段基线 `33421205241461b94482a2390e3ca9b5f716bdcc`。修复提交随本记录创建，完整 SHA 见开发窗口最终交接报告
- 唯一配置硬边界：`AmapProviderSettings.__post_init__()` 现在无条件重验并规范化全部五个字段；API Key 必须是解密后非空白的 `SecretStr`，base URL 继续只接受并规范化为 `https://restapi.amap.com`，timeout 必须为非 bool 有限数字且在 `(0, 30]`，max retries 必须为真正的 int 且在 `0..1`，Retry-After 上限必须为非 bool 有限数字且在 `[0, 5]`。直接构造、`Settings` 字段校验和 `Settings.require_amap_provider()` 复用同一组内部规则与固定安全文案，没有第二套范围常量或配置对象
- 错误与尝试上限：所有上述 Amap 配置失败均抛出固定、无输入回显的 `AmapConfigurationError`；Key 不进入错误、args、vars、repr 或日志，成功配置的 dataclass/Settings repr 继续由 `SecretStr` 脱敏。直接构造传入 `max_retries=2`、float 或 bool 均在 HTTP Client 创建前拒绝；合法直接构造的最大值只能是 1，因此单个逻辑请求最多 2 次 HTTP 尝试。新增 MockTransport 两次连续 500 用例断言 attempts 精确为 2
- 测试覆盖：新增直接构造的空白/缺失/非 `SecretStr` Key，timeout 的 0、负数、超过 30、NaN、Inf、字符串与 bool，max retries 的负数、2、float、字符串与 bool，以及 Retry-After 上限的负数、超过 5、NaN、Inf、字符串与 bool；同时覆盖 timeout 正边界与 30、retries 0/1、Retry-After 0/5、Settings 同边界、固定错误类型和 Key/非法值脱敏。原官方域名锁定、异常链清理、infocode 分类和 provider identity 回归均包含在指定聚焦与全集中
- 最终验证：macOS、仓库受忽略 `.venv`、Python 3.13.5；显式使用 `../.venv/bin/python` 后 `pip check`、Ruff 与 strict mypy（67 个源文件）均退出 0；指定聚焦 `268 passed/1 skipped`，其中 skip 是未授权真实高德入口；非真实全集 `724 passed/2 deselected`；core `118 passed`；migrations `15 passed`；默认全集 `724 passed/2 skipped`。macOS `sandbox-exec` 系统级拒绝全部网络后，非真实全集再次 `724 passed/2 deselected`
- 环境诊断说明：当前未激活 shell 的裸 `python` 指向 `/opt/anaconda3`，首次全量 mypy 在相对阶段基线未修改的 Collection Repository 报 3 个 `redundant-cast`，首次聚焦测试也因尝试仅覆盖 PATH 被登录 shell 重置而使用该解释器，出现 3 个 `tests.fixtures` 收集错误；两次均未运行或失败于本轮测试行为。改为显式仓库 `.venv/bin/python` 后所有规定命令按上条结果通过，本轮没有越界修改基线文件来掩盖环境差异
- 网络、安全、范围与风险：所有最终 pytest 命令均移除真实测试开关并设置 `APP_ENV=test`；未读取、打印或修改本机 `.env`，未运行 `real_map_provider`，高德、百炼、其他网络及真实/付费 API 调用均为 0。相对 `e241239...` 只修改 Amap 配置、两份直接相关离线测试和本记录；未修改 Provider 请求/映射、`nanobot_core`、依赖、数据库或迁移，没有实现 M0-3C 评分/候选/用户选择，也没有实现 M0-3D exact/any_branch/分店策略。已知风险仍是未获授权的真实 Key、配额、线上响应与字段兼容性；主控离线复验通过后，仍需用户配置 Key 并单独授权受限真实验收，本分支不合并、不推送

#### 2026-07-22｜M0-3B 真实响应兼容性 P1 修复｜待主控复验

- 分支与提交关系：修复在 `codex/m0-3b-amap-provider` 上直接基于待修复提交 `1d2da50d5a6948193b9c7928767cc0b4aeaea8cd` 追加，不 amend；开始门禁确认工作区干净，分支与 HEAD 精确一致，`main`、`origin/main` 与 merge-base 均为阶段基线 `33421205241461b94482a2390e3ca9b5f716bdcc`。修复提交随本记录创建，完整 SHA 见开发窗口最终交接报告
- 真实兼容边界：唯一 `_optional_text()` 现在把字段不存在、空字符串、纯空白字符串和精确空数组 `[]` 统一映射为 `None`，非空字符串继续按既有空白规范化返回；非空 list、dict、tuple、数字、bool、显式 `None` 及其他非字符串类型仍抛内部安全哨兵并公开收敛为 `MAP_PROVIDER_INVALID_RESPONSE`。没有把 list 拼接为文本，也没有为 `business_area` 和 `tel` 复制转换逻辑
- 必填与契约保持：`_required_text()` 未修改，`id`、`name`、`address`、`location`、省市区、`citycode`、`typecode` 继续不接受空数组或其他非字符串值；Amap 搜索仍输出 `provider=amap`、稳定 `poi_id`、正式 `city_code` 和 GCJ-02。唯一 Provider、HTTP Client、MapProvider、Poi、POI mapper 和响应错误体系均保持不变
- 离线 Fixture 与覆盖：只使用手写合成 POI Fixture，不包含真实响应或快照；覆盖搜索与详情中的 `business_area=[]`、`tel=[]`、两者同时为空数组、字符串/空数组混合批次、字段缺失、空/空白字符串、非空 list、dict、数字、bool、显式 `None`、必填 `address=[]`、输入对象不变，以及同一 Provider 12 路重复并发调用无状态污染。原配置硬边界、官方域名锁定、异常链脱敏、官方 infocode 分类、provider identity 和最多两次 HTTP 尝试测试全部随聚焦与全集回归通过
- 最终验证：macOS、仓库受忽略 `.venv`、Python 3.13.5；`pip check`、Ruff 与 strict mypy（67 个源文件）全部退出 0；指定聚焦 `287 passed/1 skipped`，其中 skip 是未获本窗口授权的真实高德入口；非真实全集 `743 passed/2 deselected`；core `118 passed`；migrations `15 passed`；默认全集 `743 passed/2 skipped`。macOS `sandbox-exec` 系统级拒绝全部网络后，非真实全集再次 `743 passed/2 deselected`
- 安全、范围与风险：所有 pytest 命令均显式移除真实测试开关并设置 `APP_ENV=test`；本窗口未读取、打印或修改 `.env`，未运行 `real_map_provider`，高德、百炼、网络及真实/付费 API 调用均为 0；主控此前为发现本缺陷使用的 3 次请求授权未被复用。相对 `1d2da50...` 只修改 Amap Provider 的唯一可选文本入口、直接相关离线测试和本记录；未修改配置、DTO、`nanobot_core`、依赖、数据库或迁移，未实现 M0-3C/M0-3D。已知风险只剩修复尚未通过新授权的真实响应复测；主控必须重新取得用户授权后再运行受限真实验收，本分支不合并、不推送

#### 2026-07-22｜M0-3B｜已完成（主控验收）

- 集成与提交：`codex/m0-3b-amap-provider` 最终提交 `0b92b55e7af4077b9f4321bb8979d58f88156f0f` 已从阶段基线 `33421205241461b94482a2390e3ca9b5f716bdcc` 以 `git merge --ff-only` 纯快进集成到 `main`；提交链包含初始开发 `06834a4e3e14a6dc84c1d6d0da3b1fbe8b3adddb`、主控 P1 修复 `e2412391533e8c111ef76f82475e2fe8865934d3`、配置硬边界修复 `1d2da50d5a6948193b9c7928767cc0b4aeaea8cd` 和真实响应空数组兼容修复 `0b92b55e7af4077b9f4321bb8979d58f88156f0f`；合并无冲突、无额外代码变化
- 隔离环境与静态检查：对最终提交使用仓库外 `git archive` 和全新 Python 3.13.5 虚拟环境，editable 安装与 `pip check` 通过；Ruff 通过，strict mypy 对 67 个源文件无问题。聚焦测试 `287 passed/1 skipped`，非真实全集 `743 passed/2 deselected`，core `118 passed`，migrations `15 passed`，默认全集 `743 passed/2 skipped`
- 封网、边界与幂等：临时 `/tmp` pytest 插件同时封锁连接、连接探测、连接创建和 DNS 后，非真实全集再次 `743 passed/2 deselected`；独立探针确认仅字段缺失、空/空白字符串和精确空数组 `[]` 可映射为可选字段缺失，非空 list、dict、tuple、数字、bool、显式 `None` 及必填 `address=[]` 均被拒绝，映射不修改输入；12 路重复并发覆盖无状态污染
- 真实高德验收：经用户在当前任务明确授权，先确认配置存在且 `AMAP_MAX_RETRIES=0`，随后只运行唯一 `real_map_provider` marker；深圳搜索、广州搜索、详情、步行路线和天气共 5 次只读非流式 HTTP 请求全部通过，没有重试，本地导航 URI 不发请求，结果为 `1 passed/744 deselected`。未运行 `real_provider`，百炼调用为 0；测试输出、异常、日志和本记录均不包含 Key、完整请求、原始响应或精确地点数据
- 范围、安全与冗余：M0-3B 只增加服务端高德适配、必要配置/文档及离线和显式真实测试；没有数据库或 Alembic 变化，没有修改 `nanobot_core`，没有实现 M0-3C 评分/候选或 M0-3D `exact / any_branch`/正式 POI 写入。Git 未跟踪 `.env`、数据库、缓存、虚拟环境或测试产物；MapProvider、AmapMapProvider、Poi、Provider 客户端构造、AgentRunner 和 ToolRegistry 均保持唯一，没有真实密钥匹配
- 合并后检查与结论：纯快进后代码树与已验收提交一致，因此未重复真实调用；合并后 Ruff、strict mypy 和非真实全集再次通过，结果为 `743 passed/2 deselected`。所有已发现 P1 均已关闭，没有未关闭的 P0/P1，M0-3B 完成标准满足
- 下一步：M0-3C 前置条件已满足；从本交接文档提交后的最新 `main` 创建 `codex/m0-3c-poi-matching`，只实现供应商无关的匹配评分、证据、置信度、最多 3 个候选及用户选择结果契约。复用现有 MapProvider、Poi、PlaceCandidate 和收藏状态；本阶段不新增迁移、不调用真实高德或模型，也不提前实现 M0-3D 的分店目标或正式 POI 写入

#### 2026-07-22｜M0-3C｜待主控验收

- 分支与基线：`codex/m0-3c-poi-matching`；开始门禁确认工作区干净，`HEAD`、`main`、`origin/main` 与 merge-base 均严格等于指定基线 `7ec83d64449c6a42aa12ca4e2fbad2973251459a`，该基线包含已验收 M0-3B 最终实现 `0b92b55e7af4077b9f4321bb8979d58f88156f0f`。完整开发提交为 `8ae61d4574ee6ab0f3bd0cc25329c3591a610b6e`；本记录使用独立文档提交追加，便于在状态中保留真实开发 SHA
- 唯一领域契约：新增唯一 `app/domain/places/matching.py`，复用既有 `PlaceCandidate`、`CityScope`、`Poi`、`PoiProvider` 和 GCJ-02 坐标；定义 `matched / ambiguous / needs_context / not_found`、高/中/低置信度、固定顺序结构化证据、`0..100` 有限分数、最多 3 个候选和 `(provider, poi_id)` 唯一身份。评分为纯函数，不修改输入、不访问 Provider/数据库/文件/消息，也不保留来源全文或供应商响应
- 评分与排序：按固定顺序评估名称、分店名、行政区、商圈、地址、地标、地铁站、电话、POI 类型和安全处理后的来源上下文；城市只作为硬边界且分值固定为 0，默认搜索城市不构成已确认城市的正向证明。候选按分数降序，只有同分时才使用供应商原始排名，再以 provider 与 poi_id 决胜；set/dict 顺序不影响结果。唯一自动匹配必须同时满足最低分数、第一二名最小差距且首位无城市、行政区、分店或电话硬冲突
- 唯一应用编排：新增唯一 `PlaceMatchingService`，每次请求显式携带 `CityScope`，只向注入的现有 `MapProvider.search_poi` 发送候选标题、城市和可选行政区；Event 在 Provider 调用前固定拒绝。Provider 结果在评分前重建并复验内部 `Poi`、重复身份、城市归属和 GCJ-02，损坏、混城、重复、非 GCJ-02 或 `model_construct` 绕过结果统一收敛为固定 `MAP_PROVIDER_INVALID_RESPONSE`；既有安全 MapProviderError 与 `asyncio.CancelledError` 原样传播
- 阈值与选择：唯一服务端入口 `Settings.place_matching_policy()` 读取 `PLACE_MATCH_UNIQUE_SCORE=75`、`PLACE_MATCH_MINIMUM_SCORE_GAP=12` 和 `PLACE_MATCH_CANDIDATE_SCORE=35`，拒绝 bool、NaN、Infinity、越界和候选阈值高于唯一阈值；证据权重只在同一策略对象定义。用户选择契约只表达当前候选集内一个具体 POI、显式 `any_branch` 或 `none_of_above`，不存在/不属于当前快照的身份与重复候选均拒绝；匹配结果本身不会自动产生 `any_branch`
- 自动化覆盖：新增 58 项 M0-3C 领域与应用测试及 17 项配置测试，共比指定基线增加 75 项。覆盖深圳当代艺术与城市规划馆唯一高置信、M Stand/星巴克两个连锁、多分店与同名异区、行政区冲突、名称/分店/商圈/地址/地标/地铁/电话/类型/上下文正负证据、四种结果、不把供应商第一名当确认、最多 3 项、重复身份、阈值和最小分差等于/略低/略高、同分确定排序、城市线索/城市结果冲突、搜索范围零分、深圳广州顺序及 40 路并发隔离、第二候选/任意分店/以上都不是选择、非法选择、输入隔离、重复调用、活动调用取消、全部 MapProvider 安全错误、恶意结果脱敏与零副作用
- 验证环境与精确结果：macOS、仓库受忽略 `.venv`、Python 3.13.5；`pip install -e ".[dev]"` 与 `pip check` 退出 0；Ruff 退出 0；strict mypy 对 69 个源文件无问题；非真实全集 `818 passed / 2 deselected`；core `118 passed`；migrations `15 passed`；默认全集 `818 passed / 2 skipped`。临时 `/tmp` pytest 插件同时封锁 `socket.connect`、`connect_ex`、`create_connection`、`getaddrinfo`、`gethostbyname` 与 `gethostbyname_ex` 后，非真实全集再次 `818 passed / 2 deselected`
- 离线、安全与副作用：全部最终命令先移除 `RUN_REAL_MODEL_TESTS` 与 `RUN_REAL_MAP_TESTS` 并设置 `APP_ENV=test`；未读取、打印或修改本机 `.env`，未运行 `real_provider`/`real_map_provider`，百炼、高德、DNS、网络、外部消息及其他真实/付费 API 调用均为 0。来源完整上下文使用 `SecretStr` 请求边界且只在内存生成必要证据，电话、伪密钥、恶意供应商载荷、异常链和完整响应不进入结果、异常、repr 或日志；离线测试未创建数据库、业务文件或消息
- 迁移与范围：未新增或修改 Alembic revision、ORM 表、Repository、持久化字段或依赖；`alembic heads` 仍只有 `20260721_0005`，`0001` 至 `0005` 相对指定基线无差异。未修改 Amap HTTP 实现、`nanobot_core`、CollectionItem、收藏状态或 M0-2 API；未新增路由、前端、计划、URL/OCR、Worker、消息渠道或外部发布
- 冗余结论：代码扫描确认 `AgentRunner`、`ToolRegistry`、`MapProvider`、`AmapMapProvider`、`StubMapProvider`、`Poi`、`PlaceCandidate`、`PlaceMatchingService`、评分函数和选择校验均各有唯一正式定义；没有 `PlaceTarget`、`BranchCandidate`、`BranchRepository`、第二套 Provider/匹配服务或品牌版 CollectionItem。API、抽取、收藏与计划模块未复制评分算法
- 已知风险：本阶段按禁令只使用手写 Fixture 与离线 Stub，未以真实高德数据评估阈值分布、供应商数据质量或更广中文别名；电话证据来自安全处理后的来源上下文，类型证据来自标题/标签/上下文，未扩展 M0-2B 候选 Schema。当前城市线索冲突识别覆盖现有 MapProvider Fixture 的深圳和广州；未来开放更多计划城市时必须复用 U1 唯一 CityCatalog，而不是在本模块继续扩城市目录。当前只在 macOS/Python 3.13.5 验证，未在 Python 3.11/3.12、Windows 或 PostgreSQL 复测；当前没有已知未关闭 P0/P1
- M0-3D 状态：仍未开始；没有实现 `PlaceTarget`、`exact / any_branch` 持久化、正式 POI 绑定、品牌归一/幂等、多分店收藏或计划时分店解析。主控验收通过并另行下达 M0-3D 任务前，本分支停止业务开发
- 主控复测重点：确认开发提交直接基于指定 baseline 且文档提交只修改本状态文件；重跑 editable 安装、依赖检查、Ruff、mypy、58 项 M0-3C 聚焦、非真实/core/migrations/默认全集和 `/tmp` socket/DNS 封锁；重点复核阈值/分差边界、供应商第一名、硬冲突、搜索城市零分、重复身份、具体/任意/以上都不是选择、深圳广州并发、取消与错误传播、`model_construct` 绕过、完整上下文/伪密钥/供应商载荷脱敏、无迁移/副作用/后续阶段越界及唯一实现扫描

#### 2026-07-22｜M0-3C 验收缺陷修复｜待主控复验

- 分支与提交关系：修复在 `codex/m0-3c-poi-matching` 上直接基于当前交接 HEAD `3d96dfc91fc2284428c562edcd9baaf2a4215501` 追加；该提交链包含指定 `main` 基线 `7ec83d64449c6a42aa12ca4e2fbad2973251459a` 和原开发提交 `8ae61d4574ee6ab0f3bd0cc25329c3591a610b6e`。开始门禁确认工作区干净、分支和 HEAD 精确一致，`main` 与 `origin/main` 仍严格等于指定基线。本轮生产代码、配置说明和回归测试修复提交为 `ae8d67edd358a5c3c5214720878a61cfdb9e1d23`，未 amend、未合并、未推送
- P1 零阈值关闭：唯一 `PlaceMatchingPolicy` 和 `Settings` 配置入口均要求唯一匹配分数、候选分数和最小分差为有限正数 `(0, 100]`，并继续要求候选阈值不高于唯一阈值；评分与分类入口增加运行时安全复验，`model_construct` 绕过零阈值也会被拒绝。同分候选另有显式正分差条件，即使后续校验变化也不能按供应商排名自动 `matched`；三份配置说明已同步合法范围
- P1 城市线索关闭：现有匹配模块使用单一 `_resolve_city_hint` 接入点区分“无提示”“已支持提示”“非空但未解析提示”，没有复制全国城市目录或提前实现 U1 CityCatalog。上海、北京和未知文本会形成固定 `city_hint_unresolved` 硬冲突，不能自动绑定深圳 POI；深圳、深圳市、shenzhen、广州、广州市和 canton 别名在正确显式 `CityScope` 下继续正常，支持别名与搜索范围冲突时同样阻止匹配。搜索范围仍只作零分调用上下文，不提升为已确认城市事实
- P2 通用店名关闭：唯一名称/分店证据逻辑共享一份通用业态后缀规则；“M Stand咖啡店”“星巴克咖啡店”“诚品书店”“海底捞餐厅”等不再被当成具体分店，也不会产生分店硬冲突。海岸城店、万象天地店、COCO Park店和卓悦中心店等可区分线索继续产生明确分店一致或冲突证据；没有新增第二套名称或分店算法
- P2 候选质量关闭：`classify_place_matches` 只公开得分达到 `candidate_score` 且没有任何硬冲突的候选，再按既有确定性规则最多保留 3 个；零分、略低阈值和城市/行政区/分店/电话硬冲突候选不进入公开选择契约。Provider 有 POI 但没有可靠候选时返回候选可为空的 `needs_context`，只有 Provider 真正空结果才为 `not_found`；恰好等于阈值的无冲突候选可见。`PlaceMatchResult` 只允许 `needs_context`/`not_found` 安全表达空候选，公开候选契约拒绝硬冲突；现有选择校验因此不能选择被隐藏的低质量或冲突 POI
- 自动化覆盖与数量：领域聚焦 `64 passed`，应用服务聚焦 `26 passed`，配置聚焦 `22 passed / 90 deselected`；新增和更新覆盖直接策略构造、环境变量零值、三类阈值零值、同分、`model_construct`、上海/北京/未知提示、深圳/广州别名及冲突、两个连锁品牌的通用/正确/错误分店、零分/略低/等于/高于候选阈值、硬冲突隐藏、空可靠集合和选择拒绝。既有唯一匹配、第二候选、任意分店、以上都不是、重复身份、输入不变、取消、并发城市隔离、错误脱敏和零副作用测试全部保留
- 最终验证环境与结果：macOS、仓库受忽略 `.venv`、Python 3.13.5；`pip install -e ".[dev]"` 与 `pip check` 退出 0，Ruff 退出 0，strict mypy 对 69 个源文件无问题；core `118 passed`，migrations `15 passed`。用户给出的精确 marker `not real_provider and not real_map` 得到 `856 passed / 1 skipped / 1 deselected`，其中仓库正式地图 marker 名为 `real_map_provider`；按正式 marker 运行纯非真实全集得到 `856 passed / 2 deselected`，默认全集 `856 passed / 2 skipped`
- 封网、安全与副作用：临时 `/tmp` pytest 插件同时封锁 `socket.connect`、`connect_ex`、`create_connection`、`getaddrinfo`、`gethostbyname` 和 `gethostbyname_ex` 后，纯非真实全集再次 `856 passed / 2 deselected`。所有测试均移除 `RUN_REAL_MODEL_TESTS` 与 `RUN_REAL_MAP_TESTS` 并设置 `APP_ENV=test`；未读取、打印或修改本机 `.env`，未运行任何真实 marker，百炼、高德、DNS、网络、外部消息及真实/付费 API 调用均为 0。来源全文、电话、伪密钥、供应商响应和硬冲突原始载荷均未进入公开候选、异常、repr 或日志；测试没有数据库、业务文件或消息副作用
- 迁移、范围与冗余：没有新增或修改依赖、数据库、ORM、Repository 或 Alembic revision；head 仍唯一为 `20260721_0005`，`0001`–`0005` 与指定基线无差异。未修改 `AmapMapProvider` HTTP 实现、`nanobot_core`、CollectionItem 或收藏状态；未实现 M0-3D `PlaceTarget`、`exact / any_branch` 持久化、品牌幂等、正式 POI 写入、多分店收藏或计划解析。扫描确认 `MapProvider`、`AmapMapProvider`、`StubMapProvider`、`Poi`、`PlaceCandidate`、`PlaceMatchingService`、评分函数、分类函数和选择校验均各有唯一正式定义，没有 `BranchCandidate`、`BranchRepository` 或第二套城市目录/匹配服务
- 已知风险与主控复测：当前只在 macOS/Python 3.13.5、手写 Fixture 与离线 Stub 上验证；更广城市别名必须等待 U1 的唯一 CityCatalog，不能继续扩充本模块目录；真实高德数据的阈值分布和名称质量仍未获本阶段授权验证。主控应重点复跑三类正阈值及绕过、同分、未解析城市提示、两个连锁通用/明确分店、候选质量五档、空 `needs_context`、选择拒绝、并发/取消/安全边界、迁移与唯一实现扫描；通过前 M0-3C 继续待验收，M0-3D 仍未开始

#### 2026-07-22｜M0-3C｜已完成（主控验收）

- 提交与集成：原开发提交 `8ae61d4574ee6ab0f3bd0cc25329c3591a610b6e`、生产修复提交 `ae8d67edd358a5c3c5214720878a61cfdb9e1d23` 和交接提交 `bcb27f5850c605ac7309eacbb1da41e2ae13f76c` 均包含指定基线 `7ec83d64449c6a42aa12ca4e2fbad2973251459a`。主控以 `git merge --ff-only` 将阶段分支纯快进集成到 `main`，无冲突、无额外代码变化，合并后代码树与已验收 HEAD 一致
- 验收环境与静态检查：对最终阶段 HEAD 使用仓库外 `git archive` 和全新 Python 3.13.5 虚拟环境；editable 安装、`pip check`、Ruff 均通过，strict mypy 对 69 个源文件无问题
- 自动化结果：领域聚焦 `64 passed`，应用服务聚焦 `26 passed`，配置聚焦 `22 passed / 90 deselected`，core `118 passed`，migrations `15 passed`；正式非真实 marker 全集 `856 passed / 2 deselected`，默认全集 `856 passed / 2 skipped`。临时测试插件封锁 socket 连接、连接创建及 DNS 后，非真实全集再次 `856 passed / 2 deselected`
- 独立边界与安全探针：仓库外 7 项 QA 探针全部通过，覆盖三类零阈值及 `model_construct` 绕过、同分候选、通用连锁店名、深圳范围与上海线索冲突、未解析城市线索、低分及硬冲突候选隐藏和不可选择；确认请求输入不变、重复调用无状态污染
- 缺陷关闭：原验收发现的两项 P1（零阈值可自动匹配、未解析城市线索可错误绑定）和两项 P2（通用业态后缀误判分店、低质量或硬冲突候选可公开选择）均由回归测试覆盖并关闭；当前没有未关闭的 P0/P1
- 范围、迁移与冗余：阶段未新增依赖、数据库、ORM、Repository 或 Alembic revision，唯一 head 仍为 `20260721_0005`；未修改 `nanobot_core`、Amap HTTP 实现、CollectionItem 或收藏 API，也未提前实现 M0-3D。AgentRunner、ToolRegistry、MapProvider、AmapMapProvider、StubMapProvider、PlaceMatchingService、评分/分类函数和选择校验均保持唯一，没有第二套城市目录、地点 DTO、候选或匹配服务
- 网络与密钥：主控未读取、打印或修改本机 `.env`，未运行 `real_provider` 或 `real_map_provider`；百炼、高德、DNS、外部消息和其他真实/付费 API 调用均为 0。Git 未跟踪 `.env`、数据库、虚拟环境、缓存、响应快照或测试产物
- 合并后检查：纯快进合并后再次运行 Ruff、strict mypy 和正式非真实全集，结果分别为通过、69 个源文件无问题、`856 passed / 2 deselected`；因代码树未变化，没有重复调用任何真实 API
- 验收结论与下一步：M0-3C 的范围、行为、异常、边界、幂等、并发、取消、安全和冗余要求全部满足。M0-3D 前置条件已满足；从本记录提交后的最新 `main` 创建 `codex/m0-3d-place-targets`，复用现有地点、候选和收藏契约，只实现 PlaceTarget、`exact / any_branch`、品牌幂等、正式 POI 绑定及必要迁移

#### 2026-07-22｜M0-3D｜待主控验收

- 分支与基线：`codex/m0-3d-place-targets`；开始门禁确认工作区干净，`HEAD`、`main`、`origin/main` 与 merge-base 均严格等于指定基线 `3dd8139a5caeb83e34a19a0e4a372ea6b12ae928`，Alembic 当时唯一 head 为 `20260721_0005`。本交接的业务、测试和文档使用一个可回滚提交，最终 SHA 见窗口交付
- 唯一领域边界：新增唯一 `app/domain/places/targets.py`，定义 `exact / any_branch` PlaceTarget、稳定且已确认的品牌身份、候选查询快照、确认来源/时间和 exact/any_branch/unconfirmed 规划解析结果。exact 绑定一个正式 Poi，保留 provider、poi_id、正式 city_code、GCJ-02 坐标、匹配状态、置信度和证据摘要；低置信或硬冲突候选不能提升为 exact。any_branch 只接受用户显式选择和稳定品牌命名空间/ID，显示名归一只用于展示/检索，不作为合并证明
- 收藏、状态与应用编排：在现有 CollectionItem、状态机和 Repository 上最小增加 target/snapshot；未选择时保存最多 3 项候选及 queried_at 并保持 `pending_selection`，具体选择成为 `active + exact`，显式任意分店成为 `active + any_branch`，“以上都不是”进入 `pending_details`。通用 Repository 禁止把无确认目标的 pending Place 直接切为 active；现有 legacy active 收藏保持可读。公开 CollectionItem 响应同步返回允许字段化的 target/snapshot，不包含来源全文或供应商原始响应
- 多选、幂等与事务：用户多选的每个不同 POI 形成独立 exact CollectionItem，复用同一 Source，并在单一事务内提交；第二分店失败会完整回滚。若原条目来自 M0-2C 自动保存，新分店追加到同一写入操作组，原 Undo 会原子删除全部拆分分店但保留 Source。相同用户的 `(provider, poi_id)` 与稳定品牌身份分别由部分唯一索引保护；不同幂等键仍会收敛到同一品牌收藏，并发唯一冲突回滚后回读/重试；选择操作以 `(user_id, idempotency_key)` 持久化稳定重放和 payload 冲突检测
- 持久化与迁移：新增唯一向前 revision `20260722_0006`，直接 down_revision `20260721_0005`；仅扩展既有 collection_items 并新增选择幂等记录，不建立品牌版 CollectionItem、BranchCandidate 或 BranchRepository。扁平身份/确认列与统一 JSON 契约并存，数据库检查约束限制 exact/any_branch 形状、候选数量和 Event 边界，复合外键限制 Source/收藏/操作同一用户，部分唯一索引阻止同用户重复 POI/品牌。旧 active 数据升级后 target 为空且继续可读；存在 M0-3D 数据时 downgrade 在任何 DDL 前拒绝，兼容空数据可 0006→0005→0006 往返。历史 `0001`–`0005` 未修改，head 保持唯一
- 自动化覆盖：M0-3D 领域 `6 passed`，M0-3D 应用/持久化 `12 passed`，Repository/写入/目标综合回归 `41 passed`，migrations `20 passed`，core `118 passed`。覆盖合法/损坏 exact、显式/缺失品牌 any_branch、第二候选、多选、none、queried_at、候选不制造收藏、低分/硬冲突拒绝、待选不可规划、输入不变、同/不同稳定身份、同/不同用户、同 POI 复用、并发品牌收敛、同键重放/冲突、不同键品牌去重、用户隔离、version、第二写失败回滚、Undo 整组回滚、迁移约束及兼容/拒绝往返
- 环境与验证：macOS、仓库受忽略 `.venv`、Python 3.13.5；editable install 和 `pip check` 退出 0；Ruff 退出 0；strict mypy 对 73 个源文件无问题；正式非真实 marker 全集 `879 passed / 2 deselected`，默认全集 `879 passed / 2 skipped`。Alembic `heads`、仓库外临时 SQLite `upgrade head`、`check`、`downgrade 20260721_0005`、再次 `upgrade head` 和 `current` 全部退出 0，最终为 `20260722_0006 (head)`。补充 `/tmp` pytest 插件封锁 socket connect/connect_ex/create_connection 与 DNS 后，非真实全集再次 `879 passed / 2 deselected`；首次误把插件文件路径直接传给 `-p` 的补充命令在测试收集前退出 1，改用 `PYTHONPATH=/tmp` 和模块名后成功，不涉及产品代码或外部调用
- 安全与范围：本窗口未读取、打印或修改 `.env`，始终移除真实测试开关并设置 `APP_ENV=test`；未运行 `real_provider`/`real_map_provider`，百炼、高德、DNS、HTTP、文件上传、外部消息和其他真实/付费 API 调用均为 0。未修改 `nanobot_core`、Amap HTTP 实现或依赖；未实现 M0-4 URL/截图/文件/OCR、M0-5 Plan/路线/动态选店、U1 城市切换、前端、Worker、重试服务、缓存或消息渠道
- 冗余结论与主控复测：扫描确认 AgentRunner、ToolRegistry、MapProvider、AmapMapProvider、StubMapProvider、PlaceMatchingService、Poi、CollectionItem 和 Collection Repository 均保持唯一；PlaceTarget 与 PlaceTargetSelectionService 各只有一个正式定义，没有品牌专用收藏/Repository/状态机、BranchCandidate、BranchRepository、第二套 Provider/匹配/规划或城市目录。主控应重点复测 exact 正式城市/GCJ-02/证据、pending 不可规划、显式 any_branch、并发与不同键品牌去重、多用户/同名异身份隔离、多选半失败、Undo 组、直接 SQL 约束、0006 往返/拒绝及完整非真实封网回归。验收前当前允许阶段仍为 M0-3D，M0-4A 未开始

#### 2026-07-22｜M0-3D 验收缺陷修复｜待 QA

- 分支与提交关系：修复直接追加在 `codex/m0-3d-place-targets` 的失败验收提交 `85da862fcf3c1889daaec5c03a9800548c7ed31c` 上，不 amend；开始门禁确认工作区干净、分支与 HEAD 精确一致，指定阶段基线 `3dd8139a5caeb83e34a19a0e4a372ea6b12ae928` 是该提交祖先，`main` 与 `origin/main` 仍停留在该基线。独立修复提交完整 SHA 见本窗口最终交接
- 唯一自动匹配：`record_candidates` 现在按匹配状态而不是候选是否非空决定结果；只有恰好一个、HIGH 置信度、无硬冲突的 `MATCHED` 可在单一事务中通过现有 `exact_target_from_candidate` 转成 `active + exact + AUTO_UNIQUE_MATCH`，并保留正式 POI、完整候选快照、证据、置信度和确认/查询时间。非法多候选、中置信或硬冲突 `MATCHED` 明确拒绝且零写入；`AMBIGUOUS` 保持 `pending_selection`，`NEEDS_CONTEXT`、`NOT_FOUND` 与空候选保持 `pending_details`，没有选择模糊首项
- 持久化快照权威：`apply_selection` 不再接收调用方提交的 `PlaceMatchResult`；请求只提交选择、持久化快照 SHA-256 指纹和 `queried_at`。服务在事务内读取 `CollectionItem.place_candidate_snapshot`，核对收藏状态、目标状态、查询时间、完整快照指纹，并使用既有 `validate_place_selection` 验证 provider/poi_id；伪造 POI、过期时间、不同快照和用户未见候选均在写入前拒绝。相同操作重放仍由持久化操作记录返回稳定结果，没有新增候选 DTO、匹配结果或第二套验证模型
- 并发幂等：正常 CAS `VersionConflictError` 会先 rollback，再按同一用户和幂等键查询持久化操作；只有操作存在且请求指纹相同才重放，同键不同参数继续抛幂等冲突，没有操作则保留真实版本冲突。新增 `asyncio.Barrier` 同步屏障测试确定性覆盖两个并发请求同时到达 CAS、一个写入和另一个稳定重放；没有概率 sleep、网络重试、退避或吞掉通用版本冲突
- JSON/索引列一致性：所有写入仍唯一从 `PlaceTarget` / `PlaceCandidateSnapshot` 派生。Repository 读取时核对 scope、provider、poi_id、city_code、经纬度、坐标系、品牌命名空间/ID、match status、确认来源/时间、candidate_count 和 queried_at；任何 JSON/扁平列矛盾统一抛固定安全的 `collection data integrity violation`。未合并的 `0006` 与 ORM 同步增加两项 JSON 一致性检查约束，使用 SQLite JSON/julianday 保护 POI、品牌、坐标、确认元数据、候选数量和查询时间；`0001`–`0005` 未修改
- 测试补充与路径：按验收命令将地点应用测试归档到 `tests/application/test_place_target_service.py`，迁移测试归档到 `tests/integration/test_migrations.py`；M0-3D 应用测试从 12 增至 35，迁移测试从 20 增至 21。新增覆盖自动 exact/AUTO 元数据、非法 MATCHED、三类待补充、持久化快照伪造/过期/不同、顺序与屏障并发重放、真实版本冲突、exact/品牌隔离、POI/城市/坐标/确认/候选数量/查询时间/品牌一致性、SQLite 约束、用户隔离和事务完整回滚
- 最终验证：macOS、仓库受忽略 `.venv`、Python 3.13.5；editable install、`pip check`、Ruff 和 strict mypy（73 个源文件）全部退出 0；地点领域 `6 passed`、地点应用 `35 passed`、迁移 `21 passed`、core `118 passed`、正式非真实全集 `903 passed / 2 deselected`、默认全集 `903 passed / 2 skipped`。首次非真实全集在新增合法 `pending_details → active` 后由旧非法迁移矩阵产生 1 个失败；只把这条产品要求的迁移加入合法集合、未删除或弱化其他断言，随后单元与两套全集均通过
- 迁移验证：仓库外全新临时 SQLite 从空库 `upgrade head`、`alembic check`、空数据 `downgrade 20260721_0005`、再次 `upgrade head`、再次 `alembic check` 和 `current` 全部退出 0，最终为唯一 `20260722_0006 (head)`；新增直接约束测试确认 JSON 与 POI、品牌、坐标、确认来源、候选数量和查询时间不一致会被 SQLite 拒绝
- 安全、范围与冗余：本轮未读取、打印或修改 `.env`，所有最终 pytest 命令都移除真实模型/地图开关并使用 `APP_ENV=test`；未运行 `real_provider`/`real_map_provider`，百炼、高德、DNS、HTTP、消息、发布及其他真实/付费 API 调用均为 0。未修改 `nanobot_core`、Amap Provider 或依赖，未实现 M0-4/M0-5、路线、推荐排序、业务 API、前端、Worker 或云部署；扫描确认 AgentRunner、ToolRegistry、MapProvider、PlaceMatchingService、PlaceTarget、PlaceTargetSelectionService、CollectionItem 和 Collection Repository 仍各有唯一正式实现
- 阶段状态：M0-3D 继续待 QA，不提前标记完成；本分支不合并 `main`、不推送，M0-4/M0-5 仍未开始

#### 2026-07-22｜M0-3D 异常链安全修复｜待 QA

- 分支与提交关系：本轮直接建立在 `codex/m0-3d-place-targets` 的待修复提交 `99d97615737b275b804c87d1dc13079aebcc6fa2` 上；开始门禁确认工作区干净、分支与 HEAD 精确一致，指定阶段基线 `3dd8139a5caeb83e34a19a0e4a372ea6b12ae928` 是该提交祖先。本轮只追加独立修复提交，不 amend、不合并、不推送
- P1 安全修复：`SqlAlchemyCollectionRepository._collection_item` 对 `place_target_json` 和 `place_candidate_snapshot_json` 的 Schema/结构解析失败先转换为内部布尔状态，退出 `except` 后才创建并抛出全新的固定 `CollectionDataIntegrityError`；公开异常的 `__context__` 与 `__cause__` 均为 `None`，不再保留 Pydantic `ValidationError`。JSON 与扁平 POI、品牌、候选数量或查询时间不一致仍返回同一固定 `collection data integrity violation`
- 安全回归：新增 7 个参数化场景，覆盖地点目标 JSON 伪 secret、候选快照 JSON 伪 secret、非法 JSON 结构，以及 POI、品牌身份、候选数量和查询时间不一致；逐项断言固定 `str/repr/args`、空 `vars`、空异常链，并递归遍历公开异常参数/属性，确认伪 secret、原始持久化 JSON 和供应商伪内容不进入异常对象或日志。安全聚焦结果为 `7 passed / 35 deselected`
- 最终验证：macOS、仓库受忽略 `.venv`、Python 3.13.5；editable install、`pip check`、Ruff 和 strict mypy（73 个源文件）全部退出 0；地点领域 `6 passed`、地点应用 `42 passed`、迁移 `21 passed`、core `118 passed`、正式非真实全集 `910 passed / 2 deselected`、默认全集 `910 passed / 2 skipped`，全部退出 0
- 迁移、范围与真实调用：未修改 `0001`–`0006`、ORM、依赖、`nanobot_core` 或 Amap Provider；迁移 fresh upgrade、downgrade、re-upgrade 与 Alembic check 继续由 21 项迁移测试覆盖并全部通过。未读取、打印或修改 `.env`，未启用或运行真实 Provider marker，百炼、高德及其他外部/真实/付费 API 调用均为 0；未实现 M0-4/M0-5、业务 API、前端、路线、规划、重试或第二套 Repository/错误/JSON DTO
- 阶段状态：M0-3D 继续待 QA，不提前标记完成；修复提交完整 SHA 见本窗口最终交接，M0-4/M0-5 仍未开始

#### 2026-07-22｜M0-3D｜已完成（主控验收）

- 提交与集成：初始阶段提交 `85da862fcf3c1889daaec5c03a9800548c7ed31c`、行为/并发/一致性修复 `99d97615737b275b804c87d1dc13079aebcc6fa2`、异常链安全修复 `f9f0d62583044a7dedb47e267dbc85bb2f9f4bbd` 均包含指定基线 `3dd8139a5caeb83e34a19a0e4a372ea6b12ae928`。主控以 `git merge --ff-only` 将 `codex/m0-3d-place-targets` 纯快进集成到 `main`，无冲突、无额外代码变化，合并前后树哈希均为 `1051cb32fd023afa697023b933426487a9d10bf2`
- 验收环境与静态检查：对最终阶段 HEAD 使用仓库外 `git archive` 和全新 Python 3.13.5 虚拟环境；`pip install -e "./backend[dev]"`、`pip check`、Ruff 均通过，strict mypy 对 73 个源文件无问题
- 自动化结果：地点领域 `6 passed`、地点应用/持久化 `42 passed`、迁移 `21 passed`、core `118 passed`；正式非真实 marker 全集 `910 passed / 2 deselected`，默认全集 `910 passed / 2 skipped`。临时插件同时封锁 socket connect/connect_ex/create_connection 和 DNS 后，非真实全集再次 `910 passed / 2 deselected`
- 独立对抗复验：仓库外 15 项 QA 探针全部通过，覆盖唯一高置信匹配自动形成 `active + exact`、伪造未展示 POI 拒绝、扁平 POI 身份矛盾拒绝、地点目标与候选快照两类损坏 JSON 的异常链/伪 secret 脱敏，以及 10 轮两个真实数据库 Session 同键并发收敛；原验收发现的唯一匹配、持久化快照权威、并发幂等、JSON/扁平列一致性和异常链泄漏缺陷均已关闭
- 迁移：唯一 Alembic head 为 `20260722_0006`；仓库外临时 SQLite 完成 fresh `upgrade head`、`alembic check`、`downgrade 20260721_0005`、再次 `upgrade head`、再次 `alembic check` 和 `current`，最终仍为 `20260722_0006 (head)`；历史 `0001`–`0005` 未修改
- 范围、冗余与安全：M0-3D 只扩展现有 CollectionItem、地点领域、应用服务、Repository、API Schema 和必要 `0006` 迁移；未修改 `nanobot_core`、高德 HTTP 适配或依赖，未提前实现 M0-4/M0-5、URL、截图、文件存储、路线、前端或 Worker。AgentRunner、ToolRegistry、MapProvider、PlaceMatchingService、PlaceTarget、PlaceTargetSelectionService、CollectionItem 和 Collection Repository 均保持唯一，没有品牌专用收藏/Repository、BranchCandidate、第二套 Provider、匹配或规划流程
- 网络与密钥：主控未读取、打印或修改本机 `.env`，Git 未跟踪 `.env`、数据库、虚拟环境、缓存或响应快照；未运行 `real_provider` 或 `real_map_provider`，百炼、高德、DNS、HTTP、外部消息及其他真实/付费 API 调用均为 0
- 合并后检查：在 `main` 再次执行 Ruff、strict mypy 和正式非真实全集，结果分别为通过、73 个源文件无问题、`910 passed / 2 deselected`；当前没有未关闭的 P0/P1
- 验收结论与下一步：M0-3D 的范围、状态、错误/边界、幂等、并发、事务、迁移、安全和冗余要求全部满足，M0-3 地点匹配阶段完成。M0-4A 前置条件已满足；从本记录提交后的最新 `main` 创建 `codex/m0-4-url-image`，只实现私有文件存储，不提前实现 M0-4B/C/D 或 M0-5

#### 2026-07-22｜M0-4A 私有文件存储｜待主控验收

- 分支与门禁：开发分支为 `codex/m0-4-url-image`；开始时工作区干净，`HEAD`、`main`、`origin/main` 和 merge-base 均严格等于指定基线 `d9b6e1355ef49b6625957b11f6785816a963309b`。M0-3D 已完成，Alembic 唯一 head 为 `20260722_0006`，仓库原先不存在 StorageProvider 或本地存储实现；阶段提交随本记录创建，完整 SHA 见最终交接报告
- 唯一契约与适配器：新增唯一供应商无关 `StorageProvider`，只定义 `put_private`、受控 `get_private_access` 和幂等 `delete`；新增唯一本地 `LocalPrivateStorageProvider`，从现有 `Settings` 注入配置。复用现有 `Source.file_key`，没有新增 Source、附件/文件实体、Repository、文件状态机、下载路由、文件系统 Tool 或云存储适配器
- 定位、访问与生命周期：文件只能通过 `secrets.token_urlsafe` 产生的 ASCII 不透明随机 key 定位，key 不包含扩展名、用户、原始文件名或目录；原始文件名不参与路径、不保存也不回显。公开 DTO 只含创建时间、字节数、标准 MIME、保留策略、可选过期时间和 SHA-256；本地访问契约只返回“需要未来应用下载路由”或“已过期”，不返回 `file://`、公共 URL、绝对路径、真实目录或内部临时名
- 类型、大小与写入安全：允许类型和 JPEG/PNG/WebP 最小签名校验集中在唯一存储策略模块；大小在异步分块写入时执行，零字节拒绝，恰好上限允许，超过一字节立即失败。私有根、对象、元数据、临时和预留目录为 `0700`，文件为 `0600`；根目录拒绝 public/static 和符号链接，所有文件操作使用受控目录句柄、`O_NOFOLLOW`、规则文件校验、排他预留与排他发布，碰撞不覆盖，数据和元数据均准备完成后才公开最终对象
- 错误、清理、并发与幂等：Provider 错误使用稳定枚举码和固定安全摘要，公开字典、异常链、日志与 DTO 不包含内容、原始文件名或完整磁盘路径；`asyncio.CancelledError` 原样传播。超限、签名错误、流异常、发布异常和取消均清理临时、预留及半发布文件；两个并发写入和模拟 key 碰撞不会相互覆盖，同一实例重复调用不保留请求状态。删除不存在的合法 key 返回 `deleted=false`，重复删除幂等；非法 key、分隔符、绝对路径、Unicode 混淆和符号链接对象均安全拒绝
- 配置与变更边界：新增无敏感默认值的 `STORAGE_PRIVATE_ROOT=./data/private`、`STORAGE_MAX_FILE_SIZE_BYTES=10000000` 和 `STORAGE_ALLOWED_CONTENT_TYPES=image/jpeg,image/png,image/webp`，并同步 `.env.example`；配置公开 repr 隐藏根路径，允许类型和硬上限复用集中策略。没有读取或修改本机 `.env`，没有数据库/Alembic 变化，没有修改 `0001`–`0006`，没有新增依赖
- 覆盖与验证环境：全部使用 `tmp_path`、手写最小签名字节和离线异步流，覆盖允许小文件、零字节、精确上限、两种超过上限、禁用 MIME、声明/签名不一致、恶意原始名、随机 key、碰撞、并发、写入异常、取消、删除/重复删除、非法/缺失 key、符号链接逃逸、生命周期/过期、输入不变、重复调用、权限、异常/日志/repr/字典脱敏、无 socket/数据库/消息副作用及临时目录清理。macOS、仓库受忽略 `.venv`、Python 3.13.5；editable install、`pip check`、Ruff 和 strict mypy（77 个源文件）均退出 0；存储聚焦 `64 passed`、core `118 passed`、迁移 `21 passed`、非真实全集 `986 passed / 2 deselected`、默认全集 `986 passed / 2 skipped`，全部退出 0。临时 pytest 插件同时封锁 socket connect/connect_ex/create_connection 与 DNS 后，非真实全集再次 `986 passed / 2 deselected`，退出 0；插件随后删除
- 网络、范围与风险：未启用或运行 `real_provider`/`real_map_provider`，百炼、高德、COS、网页、DNS、HTTP、消息和其他真实/付费 API 调用均为 0；未实现 M0-4B 网页抓取/SSRF、M0-4C 上传/OCR/多模态、M0-4D 统一输入、M0-5、FastAPI 上传下载路由、前端、Worker 或定时清理。已知风险是本地适配器只在 macOS/Python 3.13.5 验证，未来下载路由、云适配、真实截图和到期清理调度均有意留待后续阶段；当前没有已知未关闭 P0/P1
- 主控复测重点：在仓库外隔离环境确认唯一契约/适配器/配置入口，私有根和文件权限，key 碰撞与并发发布，符号链接对抗，分块超限和签名校验，取消/异常残留，过期访问和幂等删除，安全异常链与公开 DTO，Git 不跟踪上传/临时/.env/数据库/缓存文件，以及完整非真实禁网回归。M0-4A 验收前状态保持“待验收”，M0-4B 保持“未开始”，本分支不合并、不推送

#### 2026-07-22｜M0-4A 发布原子性与 reservation 清理修复｜待主控复验

- 分支与提交关系：修复直接追加在 `codex/m0-4-url-image` 的待修复提交 `76463d98cafc0dc2ab08c3d1669b1f3e61479cc4` 上，不 amend；开始门禁确认工作区干净、当前 HEAD 精确等于该提交且包含指定阶段基线，`main`、`origin/main` 和 merge-base 均仍严格等于 `d9b6e1355ef49b6625957b11f6785816a963309b`。独立修复提交随本记录创建，完整 SHA 见最终交接
- 发布所有权修复：每次数据和元数据发布使用独立请求内 `_PublicationState`；`os.link` 排他成功后立即记录本请求拥有最终目录项，再执行目标目录 `fsync`。只有数据、元数据发布和目录同步全部完成才标记整个写入成功；此前任一步失败或取消，按元数据后数据的顺序删除本请求已拥有的最终项，再清理 `.tmp` 和 `.reservations`。`os.link` 建立目录项前失败时所有权保持 false，因此不会误删调用前对象或其他请求对象；fsync、排他发布与 key 碰撞语义均未放宽
- reservation 修复：`_reserve_file_key` 在 `O_EXCL` 创建成功的同一时刻记录本请求拥有的 reservation，并单独跟踪 reservation 文件描述符；在 objects/metadata 任一存在性探测、关闭、碰撞清理或其他步骤失败且尚未向 `put_private` 交付所有权时，使用已打开的受控目录句柄优先清理，必要时通过同一受控目录重试。只有本请求排他创建的名字可被该路径删除，预先存在或属于其他请求的 reservation 保持不变；随机 key 和最多 16 次碰撞重试未改变
- 安全与取消：清理和只读目录描述符关闭均使用不抛出底层异常的内部安全辅助，发布失败继续统一收敛为固定 `STORAGE_WRITE_FAILED`，异常链、公开字典和日志不包含文件路径、内容或底层错误；发布目录项已建立后产生的 `asyncio.CancelledError` 原样传播，同时清除数据、元数据、临时文件和 reservation
- 正式回归：新增 5 个测试函数、共 7 个故障注入 case，覆盖数据硬链接后 objects 目录 fsync 失败、元数据硬链接后 metadata 目录 fsync 失败、objects 探测异常、metadata 探测异常、链接建立前失败且既有对象保留、清理后同 key 成功复用，以及硬链接后取消传播；探测失败测试同时放置其他请求的既有 reservation，确认只删除本请求 reservation。原碰撞、并发、流异常、取消、超限、类型/签名、符号链接、生命周期与幂等删除测试全部保留
- 验证环境与结果：macOS、仓库受忽略 `.venv`、Python 3.13.5；`pip check`、Ruff、strict mypy（77 个源文件）及全部 pytest 命令退出 0。仓库实际存储测试路径 `tests/contract/test_storage_provider_contract.py tests/integration/test_local_private_storage.py` 为 `71 passed`，core 为 `118 passed`，实际迁移路径 `tests/integration/test_migrations.py` 为 `21 passed`；正式非真实全集为 `993 passed / 2 deselected`，默认全集为 `993 passed / 2 skipped`。临时插件封锁 socket connect/connect_ex/create_connection 与 DNS 后，非真实全集再次 `993 passed / 2 deselected`，随后删除插件
- 范围、迁移与风险：只修改唯一本地存储适配器、直接相关正式离线测试和本交接记录；StorageProvider、LocalPrivateStorageProvider、Source 与配置入口仍各自唯一。没有迁移或依赖变化，没有修改 AgentRunner、ToolRegistry、ModelProvider、MapProvider、`.env`、数据库或 `0001`–`0006`；未实现 M0-4B/C/D、M0-5、云存储、上传下载 API 或真实 Provider，网络及真实/付费 API 调用为 0。一般性不可恢复硬件/文件系统故障仍可能阻止物理清理，但公开错误继续固定安全；当前实现只在 macOS/Python 3.13.5 验证，主控应在隔离 Linux 文件系统重点复测两个 post-link fsync 故障、reservation 探测故障、清理失败脱敏、同 key 重试、取消、碰撞和并发。M0-4A 仍为“待验收”，M0-4B 仍“未开始”，本分支不合并、不推送

#### 2026-07-22｜M0-4A｜已完成（主控验收）

- 提交与集成：阶段提交 `76463d98cafc0dc2ab08c3d1669b1f3e61479cc4` 和原子发布/reservation 清理修复 `2d3710e9010b36e878c4a2af08a78c79f0e7b795` 均直接包含已验收基线 `d9b6e1355ef49b6625957b11f6785816a963309b`；主控以 `git merge --ff-only` 将 `codex/m0-4-url-image` 纯快进集成到 `main`，无冲突、无额外代码变化，合并前后树哈希均为 `bc3afaec8507a4dc89fc6dfd9dcc2bf91f26bb28`
- 验收环境与自动化：对最终阶段 HEAD 使用仓库外 `git archive` 和全新 Python 3.13.5 虚拟环境；editable 安装、`pip check`、Ruff 均通过，strict mypy 对 77 个源文件无问题。存储契约/集成测试 `71 passed`、core `118 passed`、迁移 `21 passed`；正式非真实全集 `993 passed / 2 deselected`，默认全集 `993 passed / 2 skipped`；封锁 socket connect/connect_ex/create_connection 和 DNS 后非真实全集再次 `993 passed / 2 deselected`
- 缺陷关闭与独立对抗：原验收发现的两个 P1 已关闭。仓库外 7 项独立探针全部通过，覆盖 objects/metadata 两个硬链接后目录 `fsync` 失败、objects/metadata 两个 reservation 探测失败、链接建立前失败不误删既有对象、清理后同 key 可重试，以及硬链接后 `CancelledError` 传播与无残留；固定公开错误不包含注入的路径或伪 secret
- 存储、安全与冗余：StorageProvider、LocalPrivateStorageProvider、Source、AgentRunner、ToolRegistry、ModelProvider 和 MapProvider 均保持唯一；未发现第二套存储契约、适配器、配置入口或 SDK 客户端。私有路径、随机 key、类型/签名/流式大小边界、0700/0600 权限、符号链接拒绝、排他发布、碰撞与并发、过期访问、幂等删除、异常链脱敏和测试自动清理均满足 M0-4A；Git 未跟踪 `.env`、上传文件、数据库、缓存、临时文件或响应快照
- 迁移、外部调用与合并后检查：M0-4A 没有依赖或 Alembic 变化；临时 SQLite 完成 fresh upgrade、check、downgrade `20260721_0005`、re-upgrade、check 和 current，最终仍为唯一 `20260722_0006 (head)`。未读取本机 `.env`，未运行真实 marker，百炼、高德、网页、COS、DNS、HTTP、消息及其他真实/付费 API 调用均为 0。合并后 Ruff、77 文件 mypy 和非真实全集再次通过（`993 passed / 2 deselected`）
- 验收结论与下一步：没有未关闭的 P0/P1，M0-4A 完成标准满足。M0-4B 前置条件已满足；从本次状态提交后的最新 `main` 创建 `codex/m0-4b-web-parsing`，只实现安全网页获取与内容抽取，不提前实现截图识别、统一输入、计划、前端或真实网络验收

#### 2026-07-22｜M0-4B 安全网页解析｜待主控验收

- 分支与门禁：开发分支为 `codex/m0-4b-web-parsing`，严格从指定且已验收的 `main` 基线 `2a6872e1752baadd5a42cfab1d7adec0bda58ee2` 创建；开始时工作区干净，`HEAD`、`main`、`origin/main` 与 merge-base 均等于该 SHA。M0-4A 已完成，Alembic 仍只有 `20260722_0006 (head)`；开始前扫描确认仓库没有网页获取、URL SSRF 或正文抽取实现，StorageProvider、AgentRunner、ToolRegistry、ModelProvider 和 MapProvider 各自唯一。阶段提交随本记录创建，完整开发 commit SHA 见最终交接报告
- 唯一公共契约：新增 `app.domain.web` 作为唯一网页领域归属，严格不可变成功对象只包含规范化原始 URL、最终 URL、标题、清理正文、固定白名单元数据、Content-Type、UTC 获取时间和有界诊断；失败对象区分非法 URL、安全阻止、DNS、连接、超时、重定向阻止/循环/超限、HTTP 状态、类型不支持、响应过大、不可读、格式损坏和未知错误。固定失败摘要与 retryable 语义不包含 URL/query、HTML、Header、凭证、DNS 细节、路径、异常文本或异常链，并声明未来可请求用户补充文字或截图；未实现对应工作流
- SSRF、重定向与连接绑定：唯一 `app.domain.web.security` 规范化大小写、尾点和 IDN，只允许无 userinfo 的 HTTP/HTTPS 标准端口，拒绝控制/格式字符、坏百分号、反斜杠、混淆整数/十六/八进制 IP、本机/内网/链路本地/组播/未指定/保留/IPv4-mapped IPv6、云元数据主机和地址。DNS 答案必须每个地址都为全局地址，公开/私有混合答案整体拒绝；每次请求与每个重定向都重新执行 URL 和 DNS 策略，实际 httpx 请求 URL 使用已验证 IP，逻辑 hostname 只保留在 Host 与 HTTPS SNI 中，且发送 `Connection: close` 避免连接池跨目标复用。301/302/303/307/308 由应用显式处理，最多 5 跳、检测循环；非法或安全阻止的下一跳返回固定可恢复失败
- HTTP 与内容边界：唯一 `HttpxWebContentProvider` 显式注入 `AsyncClient`、Resolver、配置与时钟；唯一客户端工厂固定 `trust_env=False`、无认证/Cookie、无自动重定向、无自动重试、无 keepalive，并设 5 秒连接、10 秒读取、20 秒总边界；`asyncio.CancelledError` 原样传播。只接受 `text/html`、`application/xhtml+xml`、`text/plain`，流式限制线上及解压后实际内容为 2,000,000 字节，只接受 identity/gzip/deflate，正文确定性截断至 50,000 字符；严格处理 Content-Type、Content-Length、BOM/header/meta charset 及冲突。唯一 BeautifulSoup 抽取器移除 script/style/nav/header/footer/aside/noscript/template/svg 和 hidden 内容，元数据只允许 description、canonical、Open Graph title/description/site_name
- 依赖、迁移与范围：唯一新增运行依赖为 `beautifulsoup4>=4.12,<5`，原因是需要一套容错 HTML 树解析与清理能力，标准库没有可维护的等价抽取器；没有加入 trafilatura 或第二套解析器。没有新增环境变量、配置文件项、数据库表、Repository、Alembic revision 或 Source 写入；没有修改 `.env`、历史 `0001`–`0006`、StorageProvider、`nanobot_core` 或高德 Provider；没有实现 FastAPI URL 路由、自动收藏、M0-4C 上传/OCR/多模态、M0-4D 统一输入、M0-5、浏览器自动化、登录抓取、缓存、Worker、前端或通用网络 Tool
- 验证环境与命令：macOS、仓库受忽略 `.venv`、Python 3.13.5。为遵守禁网要求，editable 安装使用 `PIP_NO_INDEX=1 PIP_FIND_LINKS=<本机临时 wheelhouse> python -m pip install -e '.[dev]'`，构建依赖和 BeautifulSoup 均来自本机缓存，退出 0；`python -m pip check`、`python -m ruff check .`、`python -m mypy app migrations nanobot_core` 分别退出 0，mypy 检查 81 个源文件。网页聚焦命令退出 0，`143 passed`；存储契约/集成命令退出 0，`71 passed`；core 命令退出 0，`118 passed`；迁移命令退出 0，`21 passed`；正式非真实全集退出 0，`1136 passed / 2 deselected`；默认全集退出 0，`1136 passed / 2 skipped`
- 禁网、安全与幂等验证：所有网页测试只使用 httpx MockTransport、Stub Resolver 和固定 HTML，覆盖公开 HTTP/HTTPS、规范化/IDN、协议/userinfo/端口/混淆 URL、IPv4/IPv6/元数据、私有及混合 DNS、安全/危险重定向、全部重定向状态、循环/上限、DNS 重绑定、代理/认证/Cookie 隔离、HTML/plain text/charset、类型/状态、分块/精确大小/超一字节/解压炸弹、连接/DNS/超时/取消、截断、不可读、未知错误、单跳单请求、无自动重试、重复与并发隔离，以及 HTML/query secret/伪凭证不进入失败对象、日志、repr 或公开字典。临时 `/tmp` pytest 插件首次加载因 pytest 9 hook 参数名不匹配而在收集前退出 1，未运行项目测试；修正临时插件后封锁 socket connect/connect_ex/create_connection 与 DNS，非真实全集退出 0，仍为 `1136 passed / 2 deselected`。真实 DNS、socket、网页、模型、地图、对象存储、消息和付费 API 调用均为 0，临时 QA 文件未写入仓库
- 扫描与结论：Ruff、strict mypy、`git diff --check`、依赖检查、迁移 head、范围/敏感信息/重复定义扫描均通过；WebContentProvider、HttpxWebContentProvider、URL/SSRF 策略和成功/失败内容 DTO 各只有一套正式实现，既有 StorageProvider、AgentRunner、ToolRegistry、ModelProvider 与 MapProvider 仍保持唯一。没有未关闭的 P0/P1，没有 Git 跟踪的 `.env`、响应快照、HTML、数据库、上传、缓存或临时文件
- 已知风险与主控复测重点：实现仅在 macOS/Python 3.13.5 和离线 transport/resolver 上验证；按授权禁令没有用真实 TLS、DNS、代理环境或畸形线上服务器复验。正文清理是面向静态 HTML 的确定性启发式规则，不执行 JavaScript，也不会读取登录态页面；复杂站点可能得到较少正文并返回可恢复失败。主控应在仓库外隔离环境重点复测混淆 URL/IPv6、混合 DNS 与连接 pinning、逐跳重定向、代理/凭证隔离、压缩流边界、charset 冲突、异常链与伪 secret 脱敏、取消/并发及全量封网。验收前 M0-4B 保持“待验收”且为当前允许阶段；本分支不合并、不推送，不开始 M0-4C

#### 2026-07-22｜M0-4B 验收缺陷修复｜待主控复验

- 分支与提交关系：修复直接追加在 `codex/m0-4b-web-parsing` 的待修复提交 `28b3b0527087688426a5a1d16649727a06ec1a54` 上，不 amend；开始门禁确认工作区干净且 HEAD 精确等于该提交，`main`、`origin/main` 和 merge-base 均仍为指定基线 `2a6872e1752baadd5a42cfab1d7adec0bda58ee2`。独立修复提交随本记录创建，完整 SHA 见最终交接
- HTTP 日志修复：把高德 Provider 原有的 httpx/httpcore 日志等级保护最小抽取为唯一共享 `app.providers.http_logging.enforce_safe_http_client_logging`，高德与网页 Provider 共用；网页 Provider 构造时将两个第三方 logger 至少提升到 WARNING，因此应用 root 为 INFO 或 DEBUG 时，初始与重定向请求的完整绑定 URL/query、访问令牌和伪 secret 均不会进入日志。请求仍携带原始 query 到 MockTransport；未把完整 URL 改写到其他应用日志。正式测试同时验证固定失败对象、repr、公开字典和日志不含初始 query、重定向 query 或响应正文 secret
- Cookie 修复：每次底层 send 无论成功、HTTP 错误、异常或取消都清空共享 `AsyncClient` CookieJar；请求继续使用独立构造且无 Cookie 的 `httpx.Request`，因此响应 `Set-Cookie` 不会进入下一跳、重复或并发请求。单一共享 Provider/客户端的重定向、重复和并发测试确认所有出站 Cookie header 为空、最终 CookieJar 为空且 Cookie 内容不进入 DEBUG 日志；未通过逐请求新建 Provider/客户端规避状态问题
- BeautifulSoup、清理与 charset 修复：依赖下限收紧为 `beautifulsoup4>=4.15,<5`，移除已失效的 `import-untyped` ignore，并按 4.15 官方类型定义显式收窄 Tag、属性和 `find_all` overload，strict mypy 无宽泛绕过。噪声及 hidden 清理只操作仍挂在当前树上的节点，父节点 decompose 后跳过已分解子节点；多层 header/nav、hidden、aria-hidden、display:none、visibility:hidden 与相邻可见节点可稳定抽取，全部隐藏页面返回 `CONTENT_UNREADABLE`。charset 不再扫描原始字节伪正则，而只遍历真实 meta 元素的 charset 或 `http-equiv=Content-Type` content；注释、script 文本、data-charset、其他标签伪属性均忽略，属性大小写/顺序、UTF-8、GB18030、Windows-1252 及 header/BOM/meta 冲突规则保持
- 配置修复：`max_redirects`、`max_response_bytes`、`max_text_characters` 在构造时只接受 `type(value) is int`，稳定拒绝 bool、float（含整数值小数）、Decimal、字符串、NaN 和 Infinity；三个 timeout 只接受非 bool 的原生 int/float 且必须有限、为正，总时限继续不超过 20 秒。非法值统一在构造阶段抛出固定 ValueError，不会延迟到比较、请求、解压或切片
- 全新环境与静态验证：严格使用新建 `/tmp/shiguang-m04b-fix-venv`，`python3 -m venv` 与 `python -m pip install -e './backend[dev]'` 均退出 0；实际为 Python 3.13.5、BeautifulSoup 4.15.0、mypy 1.20.2。`pip check`、Ruff、strict mypy 全部退出 0，mypy 检查 82 个源文件；没有复用仓库 `.venv` 或旧 BeautifulSoup 缓存制造绿色结果
- 正式回归数量：全新环境网页契约/URL 安全/实现聚焦命令退出 0，`195 passed`；M0-4A 存储契约/集成命令退出 0，`71 passed`；core 退出 0，`118 passed`；迁移退出 0，`21 passed`；正式非真实全集退出 0，`1188 passed / 2 deselected`；默认全集退出 0，`1188 passed / 2 skipped`。新增 52 项正式 case 覆盖 INFO/DEBUG 初始和重定向 query、共享 CookieJar、嵌套/相邻/全隐藏内容、注释/data/script/其他标签伪 charset、合法 http-equiv/大小写/顺序，以及三项整数限制和 timeout 的严格类型边界
- 禁网、范围与安全：临时 `/tmp` pytest 插件封锁 socket connect/connect_ex/create_connection 与 DNS 后，非真实全集再次退出 0，`1188 passed / 2 deselected`。所有网页用例仍只使用 MockTransport、Stub Resolver 和固定 HTML；真实网页、模型、高德、对象存储、消息和付费 API 调用均为 0。没有迁移、配置变量、数据库/Source 写入、路由或新解析器；没有修改 StorageProvider、AgentRunner、ToolRegistry、ModelProvider 或地图业务行为，只把高德已有日志保护抽成共享安全函数。没有实现 M0-4C/M0-4D/M0-5，没有删除测试、放宽断言或增加跳过，当前没有已知未关闭 P0/P1
- 剩余风险与主控复测：共享日志保护是进程级 logger 下限，避免第三方库在 INFO/DEBUG 输出敏感请求细节；若未来业务确需低级 HTTP 诊断，必须引入经过审计的结构化脱敏事件，不能恢复原始 httpx/httpcore URL/header 日志。实际网页/TLS/DNS 仍按授权禁令未验证；静态 HTML 启发式抽取仍不执行 JavaScript 或登录态。主控应在隔离环境重点复测两个 root 日志级别、重定向 query、异常链、Set-Cookie 并发、BeautifulSoup 4.15 strict mypy、嵌套 decompose、meta charset 伪装及全量封网；M0-4B 继续“待验收”并保持当前允许阶段，本分支不合并、不推送、不开始 M0-4C

#### 2026-07-22｜M0-4B｜已完成（主控验收）

- 提交与集成：阶段提交 `28b3b0527087688426a5a1d16649727a06ec1a54` 与修复提交 `475ba0ca8d7d9361073cfadf6612fc5645e8e162` 均直接包含已验收基线 `2a6872e1752baadd5a42cfab1d7adec0bda58ee2`；主控以 `git merge --ff-only` 将 `codex/m0-4b-web-parsing` 纯快进集成到 `main`，无冲突、无额外代码变化，阶段分支与合并后树哈希均为 `6889323930821bbe4e798d89ba979552f1f25f42`
- 验收环境与自动化：对最终阶段 HEAD 使用仓库外 `git archive` 和全新 Python 3.13.5 虚拟环境，实际解析 BeautifulSoup 4.15.0、mypy 1.20.2、pytest 9.1.1；editable 安装、`pip check`、Ruff 均通过，strict mypy 对 82 个源文件无问题。网页聚焦测试 `195 passed`、存储 `71 passed`、core `118 passed`、迁移 `21 passed`；正式非真实全集 `1188 passed / 2 deselected`，默认全集 `1188 passed / 2 skipped`；封锁 socket connect/connect_ex/create_connection 和 DNS 后非真实全集再次 `1188 passed / 2 deselected`
- 缺陷关闭与独立对抗：原验收发现的 2 个 P1 与 4 个 P2 全部关闭。旧 8 项缺陷复现和另写的 16 项独立探针均通过，覆盖 INFO/DEBUG 下初始及重定向 query/响应正文脱敏、BeautifulSoup 4.15 clean-env 类型检查、预置/响应/重定向/重复/并发 Cookie 零状态、嵌套噪声与 hidden 节点、注释/script/data 属性伪 charset、合法 http-equiv charset，以及整数限制和 timeout 的精确类型边界
- 范围、安全与冗余：WebContentProvider、HttpxWebContentProvider、URL/SSRF 策略、BeautifulSoup 抽取器、StorageProvider、AgentRunner、ToolRegistry、ModelProvider 和 MapProvider 均保持唯一；高德与网页适配器只共享一处 HTTP 日志安全边界，没有第二套客户端构造、解析器或响应 DTO。没有截图识别、图片上传、统一输入、Source/Collection 写入、路由、自动重试、缓存、Worker、前端或 M0-5；Git 未跟踪 `.env`、数据库、HTML 响应、Cookie、缓存或临时文件，当前没有未关闭 P0/P1
- 迁移、外部调用与合并后检查：M0-4B 没有数据库变化；临时 SQLite 完成 fresh upgrade、check、downgrade `20260721_0005`、re-upgrade、check 和 current，最终仍为唯一 `20260722_0006 (head)`。未读取本机 `.env`，未运行真实 marker，真实 DNS、网页、百炼、高德、对象存储、消息及其他真实/付费 API 调用均为 0。纯快进合并后 Ruff、82 文件 mypy 和非真实全集再次通过（`1188 passed / 2 deselected`）
- 验收结论与下一步：M0-4B 的范围、依赖、SSRF、逐跳重定向、大小/解压/charset、异常、取消、幂等、并发、日志脱敏与 Cookie 隔离要求满足。M0-4C 前置条件已满足；从本次状态提交后的最新 `main` 创建 `codex/m0-4c-image-recognition`，复用唯一 StorageProvider、ModelProvider/Runner 和候选 Schema，只实现私有图片输入与多模态字段抽取，不提前实现 M0-4D 或真实调用

#### 2026-07-22｜M0-4C 截图识别｜待主控验收

- 分支、基线与提交：开发分支 `codex/m0-4c-image-recognition` 从唯一允许基线 `2cd2036a88da1a2858756c3b88c3227f3db579d7` 创建；开始时 `HEAD`、`main`、`origin/main` 均严格等于该 SHA，工作区干净，最终功能提交 `e7f153dd53765c87393687a307fb93cd1dd019d0` 的直接父提交及 merge-base 均为该 SHA。开发期间另一个窗口将 `main`/`origin/main` 推进至 `2c425817cceabeaf11ea943d4d50b19d52ef86e3`，共享工作树因此一度令未集成的功能提交串入该文档提交；交付前已将本分支自身提交无冲突重放回指定基线并排除外部提交，未修改、合并或推送 `main`
- 开始门禁与基线：完整读取 AGENTS、阶段/状态文档、PRD 内容输入/截图/置信度/降级、核心收藏流程、技术方案内容导入/错误/安全/M0-4，以及现有 StorageProvider、LocalPrivateStorageProvider、ModelProvider、OpenAICompatibleProvider、TextExtractionService 和 ExtractionResult。确认 M0-4A/B 已完成、M0-4C 唯一允许、Alembic 只有 `20260722_0006 (head)`，且 Storage、ModelProvider、OpenAI-compatible Provider、AgentRunner、ToolRegistry、Place/Event 候选和 ExtractionResult 均保持唯一。项目 `.venv` 基线安装、`pip check`、Ruff、82 文件 strict mypy 全部退出 0，非真实基线 `1188 passed / 2 deselected`
- 环境说明：首次按未激活 shell 的系统 Anaconda `python` 运行基线时，环境中旧 mypy/SQLAlchemy typing 组合报告 4 个既有 redundant-cast，且已安装的顶层 `tests` 包遮蔽仓库测试包导致收集前 16 个 ImportError；该次没有运行项目测试、没有代码改动或外部 API 调用。随后按仓库历史标准使用受忽略的项目 `.venv` 从安装开始完整重跑并通过，后续所有正式结果均来自该隔离解释器
- 私有接收与生命周期：新增唯一应用层 `ImageRecognitionService`，接收受限异步字节流并复用 `StorageProvider.put_private`；使用现有 JPEG/PNG/WebP MIME、签名及注入的 StorageProviderSettings 大小边界，使用 `ORIGINAL_SCREENSHOT` 和明确 30 天 expires_at。成功只返回既有 `PrivateFileMetadata + ExtractionResult` 元组，不返回本地路径、`file://`、公开 URL、原始文件名、Base64 或第二套响应 DTO；没有扩展 StorageProvider，因为最多 20 MB 的受限输入可在应用层一次安全缓冲、验证后将同一不可变字节交给存储和模型，无需绕过 Provider 读取私有路径
- 图片安全：唯一新增正式依赖为 `Pillow>=11,<13`，最终环境为 Pillow 12.3.0；标准库没有 JPEG/PNG/WebP 完整解码器，无法可靠检查损坏、截断、格式伪装、解码完整性、动画、尺寸及像素炸弹。服务在保存与模型调用前执行签名、Pillow verify+完整 load、声明 MIME/实际格式一致、静态单帧、宽高各不超过 12000、总像素不超过 4000 万；不读取 EXIF 位置。空文件、非法 chunk、非图片、MIME/签名不符、损坏、截断、超限、异常尺寸和像素输入均使存储与模型调用为 0
- 多模态与共享抽取：复用唯一供应商无关 `Message` 字典、ModelProvider 与 OpenAICompatibleProvider，通过 text + image_url content parts 发送内存 data URL；未修改 `nanobot_core`，未新增 VisionProvider、Runner 或模型配置。SDK 继续 `stream=false`、`enable_thinking=false`、`max_retries=0`；MockTransport 直接确认多模态成功请求只有 1 次，503 也只有 1 次且无 SDK 重试。将文字抽取原有 JSON 长度、Tool Call 拒绝、Schema 校验、安全错误路径、修复消息和 canonicalization 小型收敛到 `extraction_output.py`，文字 80 项行为回归保持通过；图片结构错误同样最多修复 1 次，两次无效返回现有 `MODEL_INVALID_OUTPUT`
- 候选与不确定性：OCR/视觉信息只进入现有 PlaceCandidate、EventCandidate、CandidateField、Uncertainty 和 ExtractionResult；清晰地点/活动形成候选，只有店名时保留标题并显式标记所有缺失字段，多个地点保持分离，模糊图返回信息不足。应用层不信任模型的确认标记，对截图中所有存在的价格、city_hint、行政区、地址、商圈、地标和地铁线索强制增加 uncertainty；候选 Schema 不含正式 city_code、POI、坐标或营业时间，Prompt 也禁止把营业时间写成 Event 时间或读取 EXIF 作为地点
- 失败、清理、幂等与并发：输入校验和存储失败零模型调用；五类既有 ProviderError 语义原样传播，`asyncio.CancelledError` 原对象传播。存储成功后的 ProviderError、修复阶段错误、意外异常和取消都调用唯一 StorageProvider 删除本次 file_key；测试确认 objects/metadata/tmp/reservation 无残留、既有文件不被删除。顺序重复得到独立 key 和相同候选，12 路并发无共享状态；输入 chunks 不变。意外流/模型异常退出 except 后才生成固定 ImageRecognitionError，`__context__`/`__cause__` 为空；Fake 请求快照字段 `repr=False`，原图、Base64、伪 secret、文件名和路径不进入公开结果、异常、repr 或日志
- 实际文件：`backend/app/application/image_recognition.py`、`backend/app/application/extraction_output.py`、`backend/app/application/text_extraction.py`、`backend/pyproject.toml`、`backend/tests/fixtures/images.py`、`backend/tests/unit/test_image_recognition_service.py`、`backend/tests/unit/test_openai_compatible_provider.py`、`backend/tests/core/fakes.py`、`README.md`、`backend/README.md`、`docs/DEV_STATUS.md`
- 最终环境与静态验证：macOS、项目 `.venv`、Python 3.13.5、Pillow 12.3.0；`python -m pip install -e ".[dev]"`、`python -m pip check`、`python -m ruff check .`、`python -m mypy app migrations nanobot_core` 全部退出 0，strict mypy 检查 84 个源文件
- 最终测试数量：精确命令 `python -m pytest -q tests/unit/test_image_recognition_service.py tests/unit/test_openai_compatible_provider.py tests/unit/test_text_extraction_service.py` 退出 0，`120 passed`；此前交接误记的 `148 passed` 实际包含额外文件，现按 README 规定的三个文件更正。M0-4A 存储契约/集成退出 0，`71 passed`；core 退出 0，`118 passed`；`tests/integration/test_migrations.py` 退出 0，`21 passed`；正式非真实全集退出 0，`1223 passed / 2 deselected`；默认全集退出 0，`1223 passed / 2 skipped`。仓库外临时 pytest 插件封锁 socket connect/connect_ex/create_connection 与 DNS getaddrinfo 后，非真实全集再次退出 0，`1223 passed / 2 deselected`
- 迁移、配置与范围：没有新增或修改数据库、ORM、Repository、配置变量或 `0001`–`0006`；Alembic 仍只有 `20260722_0006 (head)`。没有上传 HTTP 路由、TextInput/UrlInput/ImageInput、统一 Source/Collection/AgentRun/ToolRun 编排、POI 搜索/正式城市/坐标、M0-4D、M0-5、SSE、前端、Worker、OCR SDK、外部 OCR 服务、自动重试/退避/断路器/队列或真实视觉测试入口
- 安全、真实调用与冗余：未读取、打印或修改本机 `.env`，未设置真实测试开关，未运行 `real_provider`/`real_map_provider`，也未创建或运行 `real_vision_provider`；百炼、高德、网页、DNS、对象存储、消息及任何真实/付费 API 调用均为 0。扫描确认 StorageProvider、LocalPrivateStorageProvider、ModelProvider、OpenAICompatibleProvider、AgentRunner、ToolRegistry、TextExtractionService、ImageRecognitionService、PlaceCandidate、EventCandidate 和 ExtractionResult 各只有一套正式定义；Git 不含 `.env`、数据库、上传原图、Base64、缓存或响应快照，当前无已知未关闭 P0/P1
- 已知风险与主控复测：当前只在 macOS/Python 3.13.5/Pillow 12.3.0、固定小图、Fake Provider 和 MockTransport 上验证，未在 Python 3.11/3.12、Windows/Linux 或真实多模态供应商响应上复测。图片在内存中受现有最大 20 MB 硬上限约束，M1 如转后台任务仍应复用同一服务而不是新增图片 Provider。主控应在仓库外干净 Python 3.11+ 环境重跑全部命令，重点复核 Pillow 解码炸弹/截断、exact size、价格/位置 uncertainty、工具响应拒绝、1/2 次调用、ProviderError/取消清理、既有文件保护、异常链/Base64/路径脱敏、OpenAI MockTransport 零重试、无迁移/配置/后续阶段越界及唯一实现扫描
- 下一步：等待主控独立验收；通过前 M0-4C 保持待验收且仍为唯一允许阶段，M0-4D/M0-5 保持未开始。本分支不合并 `main`、不推送、不执行真实视觉或其他外部调用

#### 2026-07-22｜M0-4C 验收阻断修复｜待复验

- 分支与提交关系：继续使用 `codex/m0-4c-image-recognition`，开始时工作区干净且 HEAD 精确为交接提交 `6ab9405d7192d94fbc8045cef4aa6c51fafdb803`；原功能提交仍为 `e7f153dd53765c87393687a307fb93cd1dd019d0`，原阶段基线仍为 `2cd2036a88da1a2858756c3b88c3227f3db579d7`。`main` 与 `origin/main` 全程保持 `2c425817cceabeaf11ea943d4d50b19d52ef86e3`，未合并、变基或修改；独立修复提交随本记录创建，完整 SHA 见最终交接
- 模型载荷边界：非法 MIME 在消费 AsyncIterable 前固定拒绝，因此 chunk、存储和模型调用均为 0。原图继续按配置上限完成签名、Pillow verify/load、单帧和 12000×12000/4000 万像素安全验证；模型侧进一步要求宽高均至少 11、比例不超过 200:1。普通合规小图直接使用已验证字节；超过模型侧 4096 最长边、400 万像素或 data URL 上限的合法图片，只在内存中转换为无 EXIF 使用的确定性 RGB JPEG 推理副本，按固定质量和最多 6 轮有界缩放收敛；完整 ASCII data URL 在 Provider 调用前计算并断言严格小于 10,000,000 字符，已知不合规请求不会到达真实 Provider
- 原图与推理副本生命周期：约 8.7 MB 的不可高度压缩合法 PNG 测试确认原 PNG 是唯一写入现有 StorageProvider 的对象，返回 metadata 的 MIME、原始 byte_size、摘要、`ORIGINAL_SCREENSHOT` 和 30 天 expires_at 均对应原图；模型只收到小于限制的内存 JPEG，推理副本不保存、不返回、不写日志。没有扩展 StorageProvider，没有第二份存储实现、VisionProvider、ModelProvider、图片候选、OCR DTO 或重复校验流程
- 取消与清理脱敏：识别主流程先捕获 Provider/取消/固定业务错误，退出原异常上下文后仅用本次 `file_key` 清理。ProviderError 后 delete 新发生 CancelledError 时传播该取消；Provider 原始 CancelledError 在清理成功或固定 StorageProviderError 后仍传播原对象，不转换成业务错误。delete 的其他意外异常只产生固定 `IMAGE_PROCESSING_FAILED`，其 str、repr、公开字典、日志、cause 和 context 均不保留异常文本、伪 secret、原图、文件名或路径；清理始终不触碰预先存在文件
- 离线覆盖：新增确定性内存用例覆盖约 8.7 MB 不可压缩 PNG 推理副本、模型 data URL 精确阈值和多一原始字节、10×10/短边等于 10/比例超过 200:1 拒绝及精确 200:1 接受、JPEG/PNG/WebP 正常、原图唯一存储与 30 天 metadata、非法 MIME 零 chunk、已知非法载荷零 Provider、ProviderError 后清理取消、原 Provider 取消、带伪 secret 的 RuntimeError 清理失败、既有文件保护、一次成功/最多两次结构修复、输入不变、重复与 12 路并发、Base64/文件名/路径/伪密钥脱敏，以及文字抽取共享逻辑完整回归。修复前 README 三文件精确聚焦命令实测为 `120 passed`，已更正原交接误记的 `148 passed`
- 全新环境与规定命令：使用仓库外 `/tmp/shiguang-m04c-fix-qa.LvnBC6/venv`、Python 3.13.5、Pillow 12.3.0；`python -m pip install -e ".[dev]"`、`python -m pip check`、`python -m ruff check .`、`python -m mypy app migrations nanobot_core` 均退出 0，mypy 检查 84 个源文件。修复后三文件聚焦退出 0，`130 passed`；存储契约/集成退出 0，`71 passed`；core 退出 0，`118 passed`；迁移退出 0，`21 passed`；正式非真实全集退出 0，`1233 passed / 2 deselected`；默认全集退出 0，`1233 passed / 2 skipped`
- 禁网、安全与范围：`/tmp` pytest 插件封锁 socket connect/connect_ex/create_connection 和 DNS getaddrinfo 后，正式非真实全集再次退出 0，`1233 passed / 2 deselected`。未读取、打印或修改本机 `.env`，未设置或运行任何真实 marker；真实模型、地图、网页、DNS、对象存储、消息和其他付费/外部 API 调用均为 0。Git/敏感文件/范围/重复定义扫描通过，Alembic 仍只有 `20260722_0006 (head)`；没有迁移、配置密钥、上传路由、Source/Collection/AgentRun 编排、M0-4D、M0-5、前端、OCR SDK、缓存、数据库、原图、Base64 或响应快照
- 已知风险与下一步：推理副本为保证供应商载荷上限可能对超大高熵截图执行 JPEG 转换或缩放，真实截图 OCR 质量和百炼响应仍因本轮禁止真实调用而未验证；边界与失败语义已由 Fake Provider、MockTransport 和 Pillow 固定图片完整离线覆盖。当前仍为 M0-4C 待主控复验，不合并、不推送、不开始 M0-4D 或 M0-5

#### 2026-07-22｜M0-4C 存储前处理异常边界修复｜待复验

- 分支与提交关系：继续使用 `codex/m0-4c-image-recognition`，开始时工作区干净且 HEAD 精确为待修复提交 `c08fe0de975fc4200876171fbcf9089c599ecc30`；原阶段基线仍为 `2cd2036a88da1a2858756c3b88c3227f3db579d7`。`main` 与 `origin/main` 全程保持 `2c425817cceabeaf11ea943d4d50b19d52ef86e3`，未修改、合并、变基或推送；本轮独立修复提交随本记录创建，完整 SHA 见最终交接
- 缺陷与修复：`ImageRecognitionService.recognize()` 现将图片完整校验、推理副本准备、注入时钟调用、UTC aware 校验及 30 天 `expires_at` 计算全部纳入同一存储前安全边界。既有 `ImageRecognitionError` 保留原对象、错误码和语义，`asyncio.CancelledError` 保留原对象传播；其他未预期 `Exception` 在退出原异常上下文后统一转换为固定 `IMAGE_PROCESSING_FAILED`，公开异常的 cause/context 均为空，不携带原异常文本、伪 secret、文件名、图片/Base64 或私有路径
- 零副作用与覆盖：正式参数化用例分别注入 `_validate_image`、`_prepare_inference_image`、clock 和 `require_aware_utc` 的私密 RuntimeError 与取消，并单独验证已知图片错误；所有存储前失败均断言 `put_private=0`、`delete=0`、模型调用为 0，且 objects、metadata、临时和 reservation 目录无残留。原有 ProviderError、Provider/清理取消、清理 RuntimeError、既有文件保护、大图载荷压缩、真实素材离线预处理、JPEG/PNG/WebP、30 天原图保存和文字抽取共享逻辑测试继续通过
- 策略与范围：本轮未改变现有图片 MIME、签名、尺寸、比例、像素、data URL 上限、确定性 JPEG 推理副本或原图 30 天保存策略；未修改 `nanobot_core`、ModelProvider、OpenAICompatibleProvider、StorageProvider 契约、候选 Schema、文字抽取、配置、数据库或迁移。未新增 Provider、Storage 实现、DTO、上传路由或统一输入编排，未实现 M0-4D/M0-5
- 验证结果：项目 `.venv` 的 `python -m pip check`、`python -m ruff check .`、`python -m mypy app migrations nanobot_core` 均退出 0，mypy 检查 84 个源文件；三文件聚焦回归退出 0，`139 passed`；存储契约/本地集成退出 0，`71 passed`；core 退出 0，`118 passed`；迁移退出 0，`21 passed`；正式非真实全集退出 0，`1242 passed / 2 deselected`；默认全集退出 0，`1242 passed / 2 skipped`
- 禁网与安全：仓库外 `/tmp` 临时 pytest 插件同时封锁 socket connect/connect_ex/create_connection 与 DNS getaddrinfo 后，正式非真实全集再次退出 0，`1242 passed / 2 deselected`。未读取本机 `.env`，未启用真实 marker，真实模型、高德、网页、DNS、对象存储、消息及其他真实/付费 API 调用均为 0；Git 敏感文件、范围和重复定义扫描通过。本阶段仍待主控复验，不合并、不推送、不开始 M0-4D

#### 2026-07-22｜M0-4C｜已完成（主控验收）

- 提交与集成：功能提交 `e7f153dd53765c87393687a307fb93cd1dd019d0`、第一轮加固 `c08fe0de975fc4200876171fbcf9089c599ecc30` 和存储前异常边界修复 `b8f493b70f07075b4f08150066ef0e675e08ea8c` 均直接包含原阶段基线 `2cd2036a88da1a2858756c3b88c3227f3db579d7`。由于 `main` 已包含独立的 M0-Gate 延迟校准文档提交，主控以无冲突非快进合并集成，合并提交为 `cd1e53920ec158eef0f581d3d67365a2c85c9534`；最终后端树与已验收阶段 HEAD 完全一致，额外差异只有 `main` 原有的三份 Gate 文档。
- 验收环境与静态检查：对精确修复 HEAD 使用仓库外 `git archive`、全新 Python 3.14.0 虚拟环境和重新安装的 `backend[dev]`；Pillow 12.3.0，`pip check`、Ruff 和 strict mypy 均退出 0，mypy 检查 84 个源文件。
- 自动化结果：M0-4C/Provider/文字抽取聚焦测试 `139 passed`；存储契约与本地集成 `71 passed`；core `118 passed`；迁移 `21 passed`；正式非真实全集 `1242 passed / 2 deselected`；默认全集 `1242 passed / 2 skipped`；封锁 socket connect/connect_ex/create_connection 与 DNS 后非真实全集再次 `1242 passed / 2 deselected`。
- 独立对抗与真实素材离线检查：仓库外 6 项独立探针全部通过，覆盖图片完整校验、推理副本、时钟和 UTC 校验的私密未预期异常、预处理取消原对象传播，以及用户提供的 16-bit PNG 原图保留和模型 data URL 边界。原验收发现的载荷超限、模型尺寸/比例、非法 MIME 流消费、清理取消、清理异常泄漏和存储前异常泄漏均已关闭；错误前存储、删除和模型调用为 0，固定异常不保留 cause/context 或私密文本。
- 范围、安全与冗余：M0-4C 只新增应用层唯一 ImageRecognitionService、共享抽取校验、固定图片 Fixture 和 Pillow 依赖；StorageProvider、LocalPrivateStorageProvider、ModelProvider、OpenAICompatibleProvider、AgentRunner、ToolRegistry、TextExtractionService、Place/Event 候选和 ExtractionResult 均保持唯一。没有迁移、配置变量、上传路由、统一输入编排、M0-4D/M0-5、前端、Worker、OCR SDK、自动重试或第二套 DTO；Git 不含 `.env`、数据库、原图、Base64、缓存或响应快照。
- 合并后验证：在合并后的 `main` 使用 Python 3.13.5 重新安装 editable 包；`pip check`、Ruff、84 文件 mypy、139 项聚焦测试和正式非真实全集 `1242 passed / 2 deselected` 再次通过。合并没有冲突，代码树没有额外变化。
- 真实调用与剩余验证：本轮未读取 `.env`，真实视觉、百炼、高德、网页、DNS、对象存储、消息和其他外部/付费调用均为 0。真实截图内容识别质量、P50/P95、成本与超时校准按既定要求留到 M0-Gate，在对应当前任务中逐项取得授权后执行，不阻塞 M0-4C 完成。
- 验收结论与下一步：没有未关闭的 P0/P1；M0-4C 已完成，M0-4D 前置条件已满足。下一阶段只统一三种输入与现有 Source、Collection 状态、AgentRun/ToolRun 和幂等流程，不复制 M0-2/M0-4 服务，不提前实现 M0-5 或真实外部调用。

#### 2026-07-22｜M0-4D 统一输入流水线｜待主控验收

- 分支与基线：`codex/m0-4d-unified-input` 从指定 `main` 基线 `c6d8ac570983c5bd9fd6d73e672030ba65644b7b` 创建；开始时 `HEAD`、`main`、`origin/main` 均精确等于该 SHA，工作区干净，M0-4A/B/C 已完成，M0-4D 是唯一允许阶段。开始门禁确认 Source、CollectionWriteService、TextCollectionWorkflow、AgentRunService、WebContentProvider、ImageRecognitionService、TextExtractionService 各只有一套正式实现
- 统一契约与编排：新增严格冻结、互斥的 `TextInput`、`UrlInput`、`ImageInput`；现有 `TextCollectionWorkflow` 原位演进为唯一三类输入流水线，兼容原 M0-2D 文字 `submit()` 和 JSON API。三类输入统一创建用户 Message、AgentRun、Source，复用唯一 TextExtractionService/ExtractionResult、CollectionWriteService、Repository、收藏状态映射和 Undo；没有新增第二套 Runner、Registry、Provider、Source、CollectionItem、工作流或响应 DTO
- URL：扩展现有消息路由接收判别 URL JSON；单次只调用一次现有 WebContentProvider，成功时只把最多 20,000 字符的有界清理正文交给 TextExtractionService；Source 保存首次原始 URL、最终 URL、解析状态、抓取时间、允许的 HTTP/MIME/大小/重定向/截断元数据。读取、SSRF、重定向、大小或可读性失败时模型调用为 0，保存 failed Source，AgentRun 终结为 `partially_succeeded`，固定返回补充文字或截图；不自动重试或空转
- 图片：消息路由接收带 `Idempotency-Key` 的有界 JPEG/PNG/WebP 原始请求体，不接收或返回 Base64、公开 file_key 或路径。输入按内容 SHA-256 指纹，只调用一次现有 ImageRecognitionService；原图继续使用唯一私有 StorageProvider 和 30 天策略，Source 只保存不透明 file_key、MIME、大小与 SHA-256。图片不确定字段继续沿现有候选 uncertainty；信息不足不创建收藏并返回补充文字/重传动作
- AgentRun、ToolRun 与预算：最小扩展既有应用 Run observer，使真实网页获取和图片识别步骤写入现有 ToolRun，输入/输出只保存固定结构摘要与 SHA-256 指纹；模型调用继续复用既有安全摘要、Token、费用和耗时。URL/图片外层 Run 逻辑预算固定取现有设置与 20 秒较小值；超时、外部取消、Provider 失败、业务失败和重放均终结或复用同一 AgentRun，取消原对象传播
- 幂等与隔离：Message、Source、trace 由 `user_id + session_id + idempotency_key` 稳定派生；同用户同 key 在统一锁中串行，同 Session 顺序/并发重放不重复消息、来源、收藏、Run、网页、模型或文件。URL 使用安全规范化值比较，图片使用内容摘要而非文件名；同 key 不同类型/正文/URL/图片摘要稳定 409。不同用户沿既有 Repository 强制隔离，不同 Session 的相同外部 key 生成独立 ID、trace 和写入作用域，不会错误串联
- 生命周期与失败：ImageRecognitionService 内部失败继续只清理自己的新文件；识别已返回后若收藏/数据库写入失败、超时或取消，统一工作流再删除本次新文件，重放不重新存储也不删除既有对象。URL 失败保留可恢复 Source；数据库 Integrity/SQLAlchemy 异常对外收敛为固定码。新增覆盖非法图片、信息不足、结构修复既有回归、Provider/存储错误既有回归、URL 总超时、取消、数据库回滚和文件清理；清理失败使用固定 `IMAGE_CLEANUP_FAILED`
- 安全：Source 的 URL 与 file_key、输入 URL、图片 payload、消息正文继续 `repr=False`；API/Run/Tool 摘要不包含 URL query、网页正文、图片、Base64、Prompt、模型响应、Cookie、Authorization、密钥、私有路径或原异常文本。请求日志仍只记录方法和 path；URL query 在 JSON body 中，不进入普通日志。数据库安全测试确认原始网页标记和图片字节不落库；图片 API 响应不公开 file_key
- API：原 `/api/v1/sessions/{session_id}/messages` 是唯一入口；保留 `{"idempotency_key","content"}` 文字兼容，新增 `text`/`url` 判别 JSON 与三类 raw image media type。统一响应增加输入类型、Source 安全摘要、恢复动作与稳定错误码；OpenAPI 明确 JSON 与 binary 请求体，不新增平行业务路由、SSE、Worker、队列或前端
- 迁移、依赖与配置：没有新增 Alembic revision、依赖或配置；head 仍为 `20260722_0006`。现有 Source 列与受限 JSON 元数据足以表达原始/最终 URL、失败码、抓取/HTTP 信息及图片 MIME/大小/摘要；现有 Message、AgentRun/ToolRun 和幂等表可直接复用，因此无需创建 `0007`、重复索引或第二套表
- 主要文件：`backend/app/application/input_contracts.py`、`text_collection_workflow.py`、`run_tracking.py`、`backend/app/api/{router,dependencies,errors}.py`、`backend/app/domain/collections/entities.py`、`backend/app/schemas/api.py`、`backend/app/main.py`、`backend/tests/contract/test_m0_4d_unified_input.py`、两份 README 与本状态文档
- 基线环境：macOS、仓库受忽略 `.venv`、Python 3.13.5。首次按附件原样使用系统 Anaconda Python 安装、pip check 与 Ruff 通过，但其旧 mypy/SQLAlchemy typing 组合复现状态文档已记录的 4 个既有 `redundant-cast`；尚未执行测试链即切换到项目 `.venv` 并从安装命令完整重跑。未为环境假阳性修改生产代码或放宽检查
- 验证结果：项目 `.venv` 的 editable 安装、`pip check`、Ruff 与 strict mypy（85 个源文件）均退出 0；core `118 passed`，迁移 `21 passed`，M0-4D 新增契约 `10 passed`，完整非真实 `1252 passed / 2 deselected`，默认全集 `1252 passed / 2 skipped`。仓库外 pytest 插件封锁 socket connect/connect_ex/create_connection 与 DNS getaddrinfo 后，完整非真实再次 `1252 passed / 2 deselected`
- 真实调用、范围与风险：未读取、打印或修改本机 `.env`，未设置真实 marker，真实模型、高德、网页、DNS、对象存储、消息及任何外部/付费调用均为 0。没有 M0-5 计划/路线/天气/评分、真实外部地点补充、前端、SSE、Worker、Redis、Celery、COS、OCR SDK、浏览器自动化、自动重试/退避/熔断或后台任务。当前验证限于 macOS/Python 3.13.5、SQLite、Fake/Stub/Fixture；多进程跨进程锁与真实链路延迟留待后续对应阶段，当前无已知未关闭 P0/P1
- 下一步：主控在独立干净 Python 3.11+ 环境复核提交范围和完整离线命令，重点复核三类统一状态映射、URL 零额外请求、图片零重复存储/失败清理、成功/失败/取消/超时重放、跨用户/Session 隔离、Source 元数据、20 秒预算、ToolRun 真实性、API/OpenAPI 脱敏、无迁移依据、唯一实现和反向依赖；通过前本分支不合并、不推送、不进入 M0-5

#### 2026-07-22｜M0-4D 主控 QA 缺陷修复｜待主控复验

- 分支与提交关系：修复直接追加在 `codex/m0-4d-unified-input` 的问题提交 `80b3f9d6a3b2b41062868ced9dc7ee828710ffeb` 上，不 amend、不 rebase；开始门禁确认工作区干净、分支与 HEAD 精确一致，指定阶段基线 `c6d8ac570983c5bd9fd6d73e672030ba65644b7b` 同时为 `main` 和 merge-base。未检出、修改或合并 `codex/ux-composer-dock`，独立修复提交完整 SHA 见本窗口最终交接
- 图片 MIME 幂等：`ImageInput` 在冻结契约入口规范化 media type；消息安全投影、请求指纹和图片 ToolRun 参数指纹统一包含输入类型、规范 MIME 与内容 SHA-256，但不包含图片、Base64、文件路径或原文件名。同 key、同字节、不同 MIME 在第二次请求进入 Provider/存储前稳定返回 `IDEMPOTENCY_CONFLICT`；JPEG、PNG、WebP 的同 MIME 同字节顺序重放复用原 Message、Source、AgentRun/ToolRun、模型、文件与收藏
- 恢复状态重放：复用现有 Source 受限 JSON metadata，新增显式、强类型、可验证的 Extraction 结果摘要与固定恢复动作；不保存网页正文、图片、Prompt、完整模型响应或异常原文。文字不支持/信息不足、URL 抓取失败、URL 抽取信息不足、图片信息不足和成功收藏均从首次持久状态确定性恢复 source_parse_status、error_code、恢复动作、必要 Extraction 摘要与收藏；图片信息不足保持 `supply_text + reupload_image`，URL 失败保持 `supply_text + send_screenshot`。Provider 失败、超时和取消继续从同一终态 Run 重放且不再次执行副作用
- 取消与清理：图片识别完成后收藏/数据库阶段的原始 `asyncio.CancelledError` 会先触发本次新文件删除；固定 StorageProviderError 或其他非取消清理错误不会覆盖原取消对象，Run 仍终结为 `cancelled / RUN_CANCELLED`。清理期间新发生的 CancelledError 按既有 ImageRecognitionService 契约传播新取消；非取消路径仍固定映射 `IMAGE_CLEANUP_FAILED`，响应、Run、ToolRun、repr 和日志不保留 file_key、路径、Authorization、URL query、清理异常或伪 secret
- 幂等约束收敛：`app/domain/collections/writes.py` 现在是 idempotency_key 长度、正则、Pydantic 类型、直接校验器和 JSON Schema 的唯一归属；旧文字 JSON、新 text/url JSON、图片 Header、CollectionWriteService、TextCollectionWorkflow 与手写 OpenAPI 共同复用。图片 Header 直接通过共享 TypeAdapter 校验，不再构造无关文字请求 DTO
- 测试覆盖：M0-4D 契约由 `10 passed` 增至 `19 passed`，新增 PNG 字节 MIME 冲突、JPEG/PNG/WebP 规范 MIME 重放、文字/URL/图片恢复状态重放、Provider/取消重放、取消时固定删除错误、非取消清理异常脱敏、跨用户/Session 隔离、冻结输入、一次 URL 抓取及一次图片识别/存储。图片服务 `52 passed`、旧 M0-2D API `16 passed`、core `118 passed`、迁移 `21 passed`；正式非真实全集 `1261 passed / 2 deselected`，默认全集 `1261 passed / 2 skipped`，全部退出 0
- 静态、迁移与范围：editable 安装、`pip check`、Ruff、strict mypy（85 个源文件）均退出 0；根 README 的迁移命令已修正为 `tests/integration/test_migrations.py`。本轮没有新增迁移、依赖、配置、表、Repository、Runner、Registry、Provider、工作流、响应 DTO 或 `nanobot_core` 修改；Alembic head 保持唯一 `20260722_0006`
- 真实调用与下一步：未读取、打印或修改本机 `.env`，未启用真实 marker；真实模型、高德、网页、DNS、对象存储、消息及任何真实/付费 API 调用均为 0。M0-5、计划、路线、天气、前端、SSE、Worker、队列和后台清理均未开始。当前状态保持待主控复验，本分支不合并、不推送

#### 2026-07-23｜M0-4D｜已完成（主控验收）

- 提交与集成：阶段功能提交 `80b3f9d6a3b2b41062868ced9dc7ee828710ffeb`、修复提交 `24e0901412b1939a887b80193339843d1a0a34e6`，均直接包含指定基线 `c6d8ac570983c5bd9fd6d73e672030ba65644b7b`。验收前 `main` 与 `origin/main` 均精确位于该基线；主控以 `--ff-only` 无冲突快进到修复提交，代码树没有额外变化。独立 UX 提交 `3000c2b` 保持在 `codex/ux-composer-dock`，未混入本阶段。
- 修复复验：上一轮图片 MIME 未纳入幂等身份、可恢复 Extraction/恢复动作重放丢失、取消被清理失败覆盖、README 迁移路径错误和幂等约束重复五项缺陷均已关闭。JPEG/PNG/WebP MIME 与摘要共同构成安全身份；文字、URL、图片和网页失败均从持久状态确定性重放；原始取消在固定清理失败后仍以同一对象传播，Run 为 `cancelled / RUN_CANCELLED`。
- 隔离环境与静态检查：对精确修复提交使用仓库外 `git archive` 和全新 Python 3.13.5 虚拟环境重新安装 `backend[dev]`；`pip check`、Ruff 与 strict mypy 均退出 0，mypy 检查 85 个源文件。工作区、提交父链、main/origin/main 关系、Git 敏感文件和差异范围均通过门禁。
- 自动化结果：M0-4D 契约 `19 passed`；图片服务 `52 passed`；旧 M0-2D API `16 passed`；Core `118 passed`；迁移 `21 passed`；正式非真实全集 `1261 passed / 2 deselected`；默认全集 `1261 passed / 2 skipped`；封锁 socket connect/connect_ex/create_connection 与 DNS 后非真实全集再次 `1261 passed / 2 deselected`，全部退出 0。
- 独立对抗与迁移检查：仓库外 4 项独立探针全部通过，覆盖同字节不同 MIME 冲突且零额外副作用、信息不足状态完整重放、取消与固定存储清理失败竞争，以及图片契约与 OpenAPI 共用同一幂等约束。Alembic `upgrade head`、`check`、`downgrade base`、再次 `upgrade head` 均通过；迁移文件仍为 6 个，唯一 head 为 `20260722_0006`。无外部 Provider 配置时健康检查正常。
- 范围、安全与冗余：M0-4D 只原位扩展既有文字收藏工作流、运行记录、Source 元数据和唯一消息 API；AgentRunner、ToolRegistry、ModelProvider、WebContentProvider、StorageProvider、TextExtractionService、ImageRecognitionService、CollectionWriteService、Repository 和响应 DTO 均保持唯一。没有新依赖、配置、迁移、M0-5、路线、天气、前端、SSE、Worker、队列、自动重试或后台任务；Git 不含 `.env`、数据库、图片、响应快照、缓存或虚拟环境。
- 真实调用与结论：本轮未读取、打印或修改本机 `.env`，未启用真实 marker；真实模型、高德、网页、DNS、对象存储、消息及任何真实/付费 API 调用均为 0。没有未关闭的 P0/P1，M0-4D 与 M0-4 已完成，M0-5A 前置条件满足；下一阶段只实现 PlanConstraints，不提前实现 M0-5B/C/D。

#### 2026-07-23｜M0-5A PlanConstraints｜待主控验收

- 分支与基线：`codex/m0-5-planning` 从指定 `main` 基线 `eb8e1a7ab83a0c784508943020db06fb6aea9b44` 创建；开始时 `HEAD`、`main`、`origin/main` 均精确等于该 SHA，工作区干净，M0-4D 已完成且 M0-5A 是唯一允许阶段。独立 `codex/ux-composer-dock` 仅有自身 UX 原型差异，未检出、合并、变基或拣选到本阶段
- 唯一契约：新增 `app.domain.plans.PlanConstraints` 作为严格、冻结、供应商无关的唯一完整计划约束；显式复用 `PlanCity.SHENZHEN`、`CityScope`、`Coordinate`、`TransportMode` 和 `require_aware_utc`，没有复制城市、交通、坐标、金额或时间类型。公共交通继续使用既有 `transit`，未复制技术文档早期示例 `public_transit`
- 约束边界：完整契约显式携带 `city_code=shenzhen`、aware UTC 规范化后的 `start_at/end_at`、`ActivityArea` 或敏感 `origin`、严格 `Decimal | None` budget、pace、交通方式、include/exclude、`collection_only` 及 `created_at/expires_at`。结束时间必须更晚，精确 24 小时允许且超过即拒绝；预算 `None`、合法零和正数保持不同语义，不伪造默认值；区域、标签和要求具有空白、长度、数量、重复与 include/exclude 冲突校验
- 缺失项与过期：纯函数 `resolve_plan_constraints()` 输入冻结的 `PlanConstraintInput`，只返回完整 `PlanConstraints` 或一个 `MissingPlanConstraintInfo`；固定先询问 `time_window`，再询问 `activity_range`，预算、交通和特殊要求缺失均不阻塞。临时约束只在 `[created_at, expires_at)` 有效，到达过期时刻后整组输入按不可用处理，不继续用于计划，也没有任何长期记忆写入路径
- 安全与副作用：`origin` 不进入 repr 或公开序列化；活动范围和 include/exclude 不进入 repr。`PlanConstraints`/`PlanConstraintInput` 保持原生 Pydantic 校验，底层 `ValidationError` 只允许存在于唯一不可信输入解析边界内部；Application、API、未来模型解析和日志必须使用 `parse_plan_constraint_input*`/`parse_plan_constraints*`，失败只得到固定 `INVALID_PLAN_CONSTRAINTS` 安全异常，不含原始 input/JSON、Pydantic 消息/context/URL 或异常链。解析函数不导入或调用 Repository、数据库、Provider、模型、地图、路线、天气、文件或网络，不修改输入；本阶段没有 API、Worker、队列、前端、缓存、Prompt、Tool Calling 或 `nanobot_core` 改动
- 主要文件：`backend/app/domain/plans/__init__.py`、`backend/app/domain/plans/contracts.py`、`backend/tests/unit/test_plan_constraints.py`、`README.md`、`docs/DEV_STATUS.md`
- 验证环境与命令：macOS、项目 `.venv`、Python 3.13.5；从 `backend` 执行 `python -m pip install -e ".[dev]"`、`python -m pip check`、`python -m ruff check .`、`python -m mypy app migrations nanobot_core`、`python -m pytest -q tests/unit/test_plan_constraints.py`、`python -m pytest -q tests/core`、`python -m pytest -q tests/integration/test_migrations.py`、`python -m pytest -q -m "not real_provider and not real_map_provider"`、`python -m pytest -q`，均显式设置 `APP_ENV=test` 和两个真实测试开关为 `0`
- 验证结果：editable 安装退出 0；`pip check`、Ruff、strict mypy 均退出 0，mypy 检查 87 个源文件；M0-5A 聚焦 `45 passed`、Core `118 passed`、迁移 `21 passed`、非真实全集 `1306 passed / 2 deselected`、默认全集 `1306 passed / 2 skipped`，全部退出 0。新增用例覆盖完整/缺失条件、显式深圳、时间与 24 小时边界、area/origin、预算类型、交通去重、include/exclude、严格布尔、稳定追问、临时有效期、冻结/extra、输入不变、脱敏和 I/O 禁止
- 迁移与范围：没有新增或修改 ORM、Repository、表、依赖、配置或 `0001`–`0006`；`python -m alembic heads` 仍为唯一 `20260722_0006 (head)`。没有 M0-5B 检索/过滤/分店解析、M0-5C Plan/PlanItem/草案、M0-5D 高德补充/Approval 或外部调用
- 冗余、安全与风险：扫描确认 PlanConstraints 只有本阶段一套，PlanCity、CityScope、TransportMode、Coordinate、AgentRunner、ToolRegistry 和 Provider 均沿用既有唯一实现；Git 未包含 `.env`、数据库、缓存、虚拟环境、响应快照或独立 UX 改动。未读取、打印或修改本机 `.env`，真实模型、高德、路线、天气、网页、DNS、对象存储、消息及任何外部/付费 API 调用均为 0；当前没有已知未关闭 P0/P1
- 已知风险与主控复测：当前只在 macOS/Python 3.13.5 和纯领域 Fixture 上验证；主控应重点复核严格 Python/JSON 输入差异、`origin` 公开序列化排除、临时约束边界、过期输入固定回到时间追问、Decimal 上限/精度及 M0-5B 后续只通过 `city_scope` 显式传递深圳。本阶段状态保持待验收，不提前标记完成、不合并、不推送、不开始 M0-5B

#### 2026-07-23｜M0-5A PlanConstraints P1 异常脱敏修复｜待主控验收

- 分支与提交关系：修复在 `codex/m0-5-planning` 上直接追加到待修复提交 `2fb9e53ceee3e35bc22728fa0778738c351fc4d2`，不 amend；开始门禁确认工作区干净、分支与 HEAD 精确一致，该提交包含指定 `main`/`origin/main` 基线 `eb8e1a7ab83a0c784508943020db06fb6aea9b44`。未合并、变基或拣选其他分支
- 阻断根因与当时修复：原实现只依赖 `hide_input_in_errors=True`，因此 `str(ValidationError)` 已隐藏输入，但 `errors()` 与 `json()` 仍持有跨字段校验收到的完整模型输入。提交 `4bbb45263756656c16f4494ef3eb491c50c7a544` 增加共享错误重建函数，并覆盖直接构造、`model_validate` 与单独 override 的 `model_validate_json`；后续主控确认其 `json_schema` 未经过相同 core 边界，`TypeAdapter(PlanConstraints).validate_json()` 仍可旁路，因此该提交的 P1 结论已被后续记录取代
- 回归覆盖：新增合法精确 `Coordinate` 配合无关非法时间窗口、非法临时有效期和 include/exclude 私人冲突；逐项断言 `str`、`repr`、`errors()`、`json()`、普通日志和异常链不含 origin 字段、哨兵经纬度、私人活动范围、私人要求或原始完整输入，结构化错误 `input` 恒为 `None`。同时覆盖直接构造、`model_validate`、`model_validate_json`、重复结果稳定、Python/JSON 原输入不变，以及成功对象的 `model_dump()`/`model_dump_json()` 继续排除精确 origin
- 验证结果：`pip install -e ".[dev]"`、`pip check`、Ruff 和 strict mypy（87 个源文件）均退出 0；M0-5A 聚焦 `50 passed`、Core `118 passed`、迁移 `21 passed`、非真实全集 `1311 passed / 2 deselected`、默认全集 `1311 passed / 2 skipped`，全部退出 0。所有 pytest 命令均使用 `APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0`
- 迁移、范围与安全：没有新增或修改迁移、ORM、Repository、API、Provider、依赖、配置、前端、检索、候选过滤、评分、分店解析、计划草案或外部补充；Alembic 唯一 head 保持 `20260722_0006`。冗余扫描确认 PlanConstraints/PlanCity/CityScope/TransportMode/Coordinate/AgentRunner/ToolRegistry/Provider 均沿用唯一既有实现，未发现 `public_transit` 或 `CURRENT_CITY` 依赖；Git 敏感与产物扫描干净
- 真实调用与主控复测：未读取、打印或修改本机 `.env`，真实模型、高德、路线、天气、网页、DNS、对象存储、消息及其他外部/付费 API 调用均为 0。当时仍存在后续确认的 TypeAdapter JSON P1 旁路；其修复和复测结论见下一条交接记录。状态仍为 M0-5A 待主控验收，M0-5B/C/D 保持未开始，本分支不合并、不推送

#### 2026-07-23｜M0-5A PlanConstraints TypeAdapter P1 旁路修复｜待主控验收

- 分支与提交关系：本轮在 `codex/m0-5-planning` 上直接追加到问题提交 `4bbb45263756656c16f4494ef3eb491c50c7a544`，不 amend、不 rebase；开始门禁确认 HEAD 与指定提交精确一致、工作区干净，且提交链包含指定 `main`/`origin/main` 基线 `eb8e1a7ab83a0c784508943020db06fb6aea9b44`。未合并、拣选或推送任何分支
- 根因与统一 core validator 边界：上一修复只包装 `json_or_python_schema` 的 Python 分支，JSON 分支直接使用原始 schema；BaseModel 的单独 `model_validate_json` override 能脱敏，但 `TypeAdapter(PlanConstraints).validate_json()` 直接复用 core validator，因而可旁路。当前删除自定义 `__get_pydantic_core_schema__` 分叉和 `model_validate_json` override，改为在每个 `PlanContract` 的 Pydantic 构建完成钩子中仅包装一次编译后的 `__pydantic_validator__`；直接构造、BaseModel 与 TypeAdapter 共用该 validator，其 `validate_python`、`validate_json`、`validate_strings` 和 `validate_assignment` 统一捕获并调用既有唯一错误重建函数
- 原生语义与安全：安全代理只委托原 Pydantic core validator，不在 JSON 对象解析后重新走 Python schema，因此 strict Python 输入保持严格，合法 JSON 的 ISO datetime、JSON 数字到 `Decimal`、字符串城市/pace/交通/坐标枚举继续使用 Pydantic 原生转换，malformed JSON 解析失败也在同一 validator 外层被截获。安全 `ValidationError` 的每项 `input=None`，context 仅含固定 `ValueError` 消息，不含原始异常或输入；敏感/未知位置和非白名单消息被替换，并在捕获块外抛出以保证 cause/context 原异常链为空。没有第二套 ValidationError、PlanConstraints、Coordinate 或校验算法
- 正式回归：聚焦测试增至 `64 passed`，覆盖直接构造、`PlanConstraints.model_validate()`、`PlanConstraints.model_validate_json()`、`TypeAdapter.validate_python()`、`TypeAdapter.validate_json()`；对非法时间、非法临时有效期、include/exclude 私人冲突及两条 malformed JSON 路径逐一检查 `str`、`repr`、`errors()`、`json()`、日志、结构化 context 和异常链，并验证每条入口重复结果稳定且不修改 Python/JSON 输入。成功 JSON 同时断言 datetime、Decimal、字符串枚举解析及公开 dump 继续排除精确 origin
- 完整验证：editable 安装、`pip check`、Ruff、strict mypy（87 个源文件）均退出 0；M0-5A `64 passed`、Core `118 passed`、迁移 `21 passed`、非真实全集 `1325 passed / 2 deselected`、默认全集 `1325 passed / 2 skipped`，全部退出 0，pytest 均设置 `APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0`
- 迁移、范围与下一步：未新增或修改迁移、ORM、Repository、API、Provider、数据库、依赖、配置、前端、M0-5B 检索、M0-5C 草案或 M0-5D 外部补充；Alembic head 保持唯一 `20260722_0006`。未读取、打印或修改 `.env`，真实模型、高德、路线、天气、网页、对象存储、消息及外部/付费 API 调用均为 0。后续主控确认 `PlanConstraintInput.model_rebuild(force=True)` 会替换代理并恢复原始错误泄漏，因此该实现已由下一条收敛修复记录取代；状态保持 M0-5A 待主控验收，不合并、不推送、不开始 M0-5B/C/D

#### 2026-07-23｜M0-5A PlanConstraints 安全解析边界收敛｜待主控验收

- 分支与提交关系：本轮在 `codex/m0-5-planning` 上直接追加到问题提交 `e0daab89b68f52f8f50c142196a331f026f68842`，不 amend、不 rebase；开始门禁确认 HEAD、分支和干净工作区精确符合任务要求，提交链包含指定 `main`/`origin/main` 基线 `eb8e1a7ab83a0c784508943020db06fb6aea9b44`。未合并、拣选或推送其他分支
- 边界收敛：删除 `_RedactingSchemaValidator`、`__pydantic_on_complete__`、`__pydantic_validator__` 运行时替换、错误消息/位置白名单、Pydantic `ValidationError` 重建、Python/JSON schema 分叉及重复 `model_validate_json` 入口。`PlanConstraints`、`PlanConstraintInput` 和其他计划契约恢复为严格、冻结的原生 Pydantic 模型；不再承诺调用方可公开底层 `ValidationError`，也不再为 TypeAdapter、model rebuild 或其他 Pydantic 内部调用方式打补丁
- 唯一安全解析边界：`app.domain.plans` 公开 `parse_plan_constraint_input()`、`parse_plan_constraint_input_json()`、`parse_plan_constraints()` 与 `parse_plan_constraints_json()`，四个类型化入口只负责选择原生 Python/JSON validator，并共用唯一 `_parse_untrusted_plan_contract()` 捕获映射，不复制任何业务校验。原始 `ValidationError` 只在该内部辅助的捕获块内存在；失败在捕获块外抛出冻结的 `PlanConstraintParseError`，固定 code 为 `INVALID_PLAN_CONSTRAINTS`、固定摘要为 `Plan constraints are invalid.`，公开字典只含 code/summary，无原始 input/JSON、Pydantic msg/context/URL、字段位置、异常链或内部模型结构
- 行为与成功路径：全部原有 M0-5A 业务测试保留；显式深圳、aware UTC、正且不超过 24 小时、area/origin、严格 `Decimal | None`、pace/交通/要求/严格布尔、临时约束 `[created_at, expires_at)`、固定缺失项顺序、冻结输入和纯函数行为不变。安全 Python/JSON 入口重复解析稳定且不修改输入；JSON ISO datetime、数字到 Decimal 和字符串枚举继续使用 Pydantic 原生行为；成功对象的 origin 继续从 repr、日志、`model_dump()` 与 `model_dump_json()` 排除
- 安全回归：聚焦测试 `57 passed`，覆盖合法 Python/JSON、完整与部分约束入口、非法/超 24 小时时间窗口、非法临时有效期、include/exclude 私人冲突、缺少 area/origin、错误 Python 类型、malformed JSON、非法嵌套 Coordinate 和 extra 字段。每个失败结果检查固定 code/摘要、冻结状态、`str`/`repr`/`args`/`vars`/公开字典/日志、cause/context 和原输入不变；连续两次 `PlanConstraintInput.model_rebuild(force=True)` 后同一公开入口仍安全，证明安全性来自外部解析边界而非 Pydantic 内部代理
- 完整验证：editable 安装、`pip check`、Ruff、strict mypy（87 个源文件）均退出 0；M0-5A `57 passed`、Core `118 passed`、迁移 `21 passed`、非真实全集 `1318 passed / 2 deselected`、默认全集 `1318 passed / 2 skipped`，全部退出 0；所有 pytest 均设置 `APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0`
- 迁移、冗余与下一步：未新增或修改迁移、ORM、Repository、API、Provider、数据库、依赖、配置、`nanobot_core`、M0-5B 检索、M0-5C 草案或 M0-5D 外部补充；Alembic head 保持唯一 `20260722_0006`。扫描确认 PlanConstraints、PlanCity、Coordinate、TransportMode、AgentRunner、ToolRegistry、Provider 和安全解析映射各自唯一。未读取、打印或修改 `.env`，真实模型、高德、路线、天气、网页、对象存储、消息及其他外部/付费 API 调用均为 0；当前无已知未关闭 P0/P1，阶段继续为 M0-5A 待主控验收，不合并、不推送、不开始 M0-5B/C/D
