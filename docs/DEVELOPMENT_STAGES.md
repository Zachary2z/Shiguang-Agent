# 拾光｜完整开发阶段与 Codex 协作指南

| 文档项 | 内容 |
|---|---|
| 项目 | Shiguang_Nanobot |
| 产品 | 拾光｜把收藏变成行动的个人生活 Agent |
| 文档版本 | v1.0 |
| 日期 | 2026-07-21 |
| 状态 | 后续开发执行基线 |
| 仓库 | /Users/zhangzihao/Documents/Shiguang_Nanobot |
| 当前阶段 | M0-0A 项目基线与资料迁移 |

---

## 1. 文档用途

本文供后续所有 Codex 开发窗口读取，使新窗口在没有完整对话历史的情况下也能理解：

- 产品要解决什么问题；
- 当前阶段允许做什么、不允许做什么；
- Nanobot 核心如何迁移和复用；
- M0、M1、M2、M3 分别如何开发；
- 每个阶段依赖什么、交付什么、如何验收；
- 多窗口如何协作而不产生重复代码；
- 如何测试、提交、交接和更新开发状态。

本文是执行路线，不替代 PRD、用户流程和技术方案。实现产品行为时必须回到上游文档核对。

## 2. 上游资料与迁移目标

### 2.1 当前只读参考资料

在 M0-0A 完成前，以下目录是只读参考：

| 内容 | 路径 |
|---|---|
| 产品文档 | /Users/zhangzihao/Documents/Nanobot 学习/产品文档 |
| UX HTML 原型 | /Users/zhangzihao/Documents/Nanobot 学习/shiguang-ux-prototype |
| Nanobot 最小核心 | /Users/zhangzihao/Documents/Nanobot 学习/nanobot |

不得在正式开发任务中修改这些参考目录。

### 2.2 M0-0A 完成后的唯一事实来源

迁移完成后，本仓库中的资料成为正式维护版本：

    Shiguang_Nanobot/
    ├── docs/
    │   ├── product/
    │   ├── technical/
    │   ├── DEVELOPMENT_STAGES.md
    │   └── DEV_STATUS.md
    └── prototypes/
        └── ux/

旧学习目录保留为归档，不再双向同步。后续产品和技术文档只修改本仓库中的版本。

## 3. 产品目标和稳定边界

### 3.1 产品目标

用户把想去、想做或想吃的地点和活动发给拾光。拾光将内容整理成结构化收藏，并在用户提供空闲时间和活动范围后，结合收藏、路线、天气和费用生成可以执行的深圳同城计划。

核心闭环：

    内容输入
      → 识别与地点匹配
      → 结构化收藏
      → 修改或撤销
      → 提供时间与范围
      → 生成计划草案
      → 调整与确认
      → 路线、日历和提醒
      → 完成反馈

### 3.2 已确认范围

- 首发城市：深圳。
- 用户：在校大学生与年轻职场人共用同一流程。
- 端：Web/H5 先行，微信 ClawBot 后接。
- 主导航：Agent、收藏、计划、我的。
- 输入：普通文字、文本 URL、截图。
- 收藏类型：Place 和用户主动提交的 Event。
- 外部补充：高德只补充 Place，MVP 不自动检索 Event。
- 规划必填：连续空闲时间和活动范围。
- 预算：可选，但计划必须展示费用估算。
- 计划：一个主方案，最多两个备选。
- 检索：PostgreSQL 结构化字段、标签和关键词，首版不使用向量数据库。
- 后台任务：PostgreSQL Job、Worker、APScheduler；首版不使用 Redis 和 Celery。
- 产品定位：个人项目和作品集，不实现商业化能力。

### 3.3 不可破坏的产品规则

1. 收藏优先，现有收藏能满足需求时不外搜。
2. 只识别出店名时不能保证定位准确。
3. 高德排序第一不等于自动匹配成功。
4. 待选择和待补充地点不能进入正式计划。
5. 外部 Place 进入计划不等于加入收藏。
6. 计划草案不等于执行，必须明确确认。
7. 预算不填也能规划，但必须展示费用。
8. 临时要求不自动写入长期记忆。
9. 推断偏好必须由用户确认。
10. Web 和微信共用业务逻辑，只改变呈现。
11. Demo 与真实用户数据隔离。
12. 工具失败、不确定和缺失信息必须明确展示，不得编造。

## 4. 总体技术路线

### 4.1 技术栈

| 层级 | 技术 |
|---|---|
| Web/H5 | Next.js + TypeScript |
| API | Python 3.11+ + FastAPI |
| Agent | 迁移并扩展现有 Nanobot 最小核心 |
| Schema | Pydantic |
| ORM/迁移 | SQLAlchemy + Alembic |
| 数据库 | M0 SQLite；M1 PostgreSQL |
| 实时状态 | SSE |
| 测试 | pytest、前端组件测试、核心 E2E |
| 本地环境 | Docker Compose |
| 公开部署 | Caddy + Docker Compose |
| 地图和天气 | 高德 Web 服务 API |
| 模型 | 阿里云百炼 OpenAI 兼容接口 |

### 4.2 运行结构

    Web / H5 / ClawBot
             ↓
        FastAPI API
             ↓
      Application Workflows
             ↓
       Nanobot Agent Core
      Loop → Runner → Tools
             ↓
         Domain Services
             ↓
       Database / Providers

### 4.3 分层原则

- Nanobot Core 只负责通用 Agent 运行能力。
- 拾光 Application 负责编排收藏、消歧、规划、确认和反馈。
- Domain 负责状态机、权限、幂等、约束和版本。
- Provider 封装模型、高德、存储和任务实现。
- API 不直接调用模型或高德。
- 前端不直接访问数据库和第三方 API。
- 模型不能执行任意 SQL、网络请求或文件操作。

## 5. 目标仓库结构

    Shiguang_Nanobot/
    ├── AGENTS.md
    ├── README.md
    ├── NOTICE.md
    ├── .env.example
    ├── .gitignore
    ├── backend/
    │   ├── pyproject.toml
    │   ├── nanobot_core/
    │   │   ├── agent/
    │   │   ├── tools/
    │   │   └── providers/
    │   ├── app/
    │   │   ├── api/
    │   │   ├── schemas/
    │   │   ├── application/
    │   │   ├── domain/
    │   │   ├── providers/
    │   │   ├── infrastructure/
    │   │   ├── channels/
    │   │   └── worker/
    │   ├── migrations/
    │   └── tests/
    │       ├── core/
    │       ├── unit/
    │       ├── integration/
    │       ├── contract/
    │       └── evals/
    ├── frontend/
    ├── docs/
    │   ├── product/
    │   ├── technical/
    │   ├── adr/
    │   ├── DEVELOPMENT_STAGES.md
    │   └── DEV_STATUS.md
    ├── prototypes/
    │   └── ux/
    ├── infra/
    └── scripts/

目录按阶段逐步创建，不为了看起来完整而预先创建大量空文件。

## 6. Nanobot 核心迁移规则

### 6.1 需要迁移

从学习项目迁移以下通用能力：

- agent/runner.py
- agent/loop.py
- agent/context.py
- agent/tools/base.py
- agent/tools/registry.py
- providers/base.py
- providers/openai_compat_provider.py
- 与上述模块对应的测试
- LICENSE

### 6.2 不原样迁移

- JSONL SessionStore：替换为数据库 Repository。
- Markdown MemoryStore：替换为结构化 Memory 表。
- 文件系统通用读写工具：产品不允许模型任意访问文件。
- 命令行学习入口：只在 M0 技术验证需要时重写最小入口。
- 与拾光无关的学习文档和示例。

### 6.3 迁移后的改造

| 学习版能力 | 产品版要求 |
|---|---|
| 工具返回字符串 | 统一 ToolResult Schema |
| 简单 JSON 参数检查 | Pydantic 入参和出参 |
| 无用户隔离 | 所有业务 Repository 强制 user_id |
| 无运行日志 | AgentRun、ToolRun、trace_id |
| 无权限分类 | 工作流工具白名单与 Approval |
| 无超时成本 | 调用上限、超时、Token、费用和耗时 |
| 文件会话记忆 | 数据库会话和结构化记忆 |

### 6.4 防止重复核心

- 仓库中只允许一个 AgentRunner。
- 仓库中只允许一个通用 ToolRegistry。
- 模型厂商通过 ModelProvider 接口扩展，不复制 Runner。
- Web 和微信不得各建一套 Agent Loop。
- 测试 Stub 实现 Provider 接口，不复制生产业务逻辑。
- 学习目录中的代码迁移后不再同步修改。

## 7. 多窗口开发模式

### 7.1 窗口角色

| 窗口 | 主要职责 | 是否写业务代码 |
|---|---|---|
| 主控/集成窗口 | 阶段规划、合并、冲突决策、状态更新 | 少量集成代码 |
| 当前阶段开发窗口 | 完成一个阶段或子阶段 | 是 |
| QA 窗口 | 在集成版本上测试、复现和报告 | 默认否；测试代码用独立分支 |

不同时开启 M0-0 到 M0-5 六个窗口并行开发。存在依赖的阶段必须串行。

### 7.2 可以并行的任务

- 文档整理与独立测试 Fixture；
- 后端 Provider Stub 与不依赖业务模型的测试工具；
- 已稳定 API 契约后的前端组件；
- QA 回归与下一阶段只读调研。

### 7.3 不应并行的任务

- 数据模型与依赖这些模型的 API；
- Nanobot 核心迁移与另一个窗口修改 Runner；
- Alembic 迁移与另一个窗口修改同一批表；
- ToolResult 契约与大量工具实现；
- 计划状态机与计划确认 API；
- 同一文件或同一公共接口的多个实现。

### 7.4 Git 分支

| 阶段 | 分支 |
|---|---|
| M0-0A | codex/m0-0a-project-baseline |
| M0-0B | codex/m0-0b-backend-scaffold |
| M0-0C | codex/m0-0c-nanobot-core |
| M0-1 | codex/m0-1-agent-runtime |
| M0-2 | codex/m0-2-text-collection |
| M0-3 | codex/m0-3-poi-matching |
| M0-4 | codex/m0-4-url-image |
| M0-5 | codex/m0-5-planning |
| M0 QA | codex/m0-regression |
| M1 | codex/m1-子阶段名称 |
| M2 | codex/m2-子阶段名称 |
| M3 | codex/m3-子阶段名称 |

阶段分支从最新已验收的集成分支创建，不从另一个未合并的开发分支随意分叉。

### 7.5 每个开发窗口的开始动作

1. 确认工作目录是 Shiguang_Nanobot。
2. 完整阅读 AGENTS.md。
3. 阅读本文和 docs/DEV_STATUS.md。
4. 阅读本阶段关联的产品、流程和技术章节。
5. 执行 Git 状态检查，识别用户已有改动。
6. 运行当前测试基线。
7. 写出本阶段实施计划。
8. 只修改本阶段授权范围。

### 7.6 每个开发窗口的结束动作

1. 运行与改动相称的 lint、类型检查、测试和迁移检查。
2. 更新 docs/DEV_STATUS.md。
3. 说明改动文件、验证结果、已知风险和未完成项。
4. 不把未完成阶段标记为完成。
5. 不自动进入下一阶段。
6. 需要提交时使用清晰的阶段提交。

## 8. 全局完成标准

任何阶段只有同时满足以下条件才可标记为已完成：

- 实现范围符合阶段说明，没有提前扩展下一阶段；
- 新增行为有自动化测试；
- 原有测试仍通过；
- 外部服务有 Stub 或 Fixture；
- 错误路径和恢复路径得到验证；
- 重要写操作具备幂等或版本保护；
- 密钥和敏感数据未进入仓库；
- 文档、配置示例和状态记录已更新；
- 代码不存在已知重复核心实现；
- QA 能根据文档独立复现阶段成果。

若真实 API 暂时缺少密钥，阶段可以标记为待验收，不能假装真实集成已通过。

## 9. 阶段依赖总览

    M0-0A 项目基线
       ↓
    M0-0B 后端骨架
       ↓
    M0-0C Nanobot 核心
       ↓
    M0-1 模型和运行记录
       ↓
    M0-2 文字收藏
       ↓
    M0-3 地点匹配
       ↓
    M0-4 URL 与截图
       ↓
    M0-5 计划验证
       ↓
    M0-Gate
       ↓
    M1 Web 核心闭环
       ↓
    M1-Gate
       ↓
    M2 微信完整 MVP
       ↓
    M2-Gate
       ↓
    M3 公开作品集

M0-4 与 M0-5 的部分 Fixture 准备可以并行，但正式合并仍按顺序进行。

---

## 10. M0：技术验证

M0 的目标不是做出完整页面，而是证明最危险的技术链路可行：

- Nanobot 核心可以作为拾光运行引擎；
- 模型可以稳定地产生结构化工具调用；
- 文字、URL 和截图可以进入统一收藏流程；
- 仅店名输入可以正确进入唯一匹配、待选择或待补充；
- 收藏可以在确定性规则下生成计划草案；
- 失败、超时和重复请求不会污染数据。

### 10.1 M0-0A：项目基线与资料迁移

#### 目标

让新仓库成为可以独立交付和继续开发的唯一项目位置。

#### 允许修改

- 仓库根目录；
- docs；
- prototypes；
- Git 配置文件。

#### 任务

1. 创建 README.md，说明产品、当前阶段和本地开发入口。
2. 创建适用于 Python、Node、macOS、Windows、IDE 和环境变量的 .gitignore。
3. 创建 NOTICE.md，记录 Nanobot 来源和许可证要求。
4. 将确认版产品文档复制到 docs/product。
5. 将技术方案复制到 docs/technical。
6. 将 HTML UX 原型复制到 prototypes/ux。
7. 检查迁移后的相对链接和文件名称。
8. 不迁移 PRD 的旧 Word 文件，除非明确需要归档。
9. 不创建正式业务代码。

#### 必须迁移的文档

- 拾光_PRD_v1.0.md
- 拾光_核心用户流程_v1.0.md
- 拾光_竞品分析_v1.0.md
- 拾光_MVP技术方案_v0.1.md

#### 交付物

- README.md
- .gitignore
- NOTICE.md
- docs/product/*
- docs/technical/*
- prototypes/ux/*
- 更新后的 docs/DEV_STATUS.md

#### 验收

- 新仓库内不存在指向用户个人临时目录的运行依赖；
- UX 原型可以直接打开；
- 文档中的主要相对链接有效；
- Git 状态中没有缓存、密钥和系统文件；
- 学习目录没有被修改；
- README 能让新开发窗口知道下一步是 M0-0B。

#### 不做

- 不安装依赖；
- 不创建数据库；
- 不迁移 Agent 代码；
- 不接模型和高德。

### 10.2 M0-0B：后端工程骨架

#### 目标

建立可以启动、测试、迁移数据库的最小 FastAPI 后端。

#### 前置条件

M0-0A 已验收。

#### 任务

1. 创建 backend Python 包和 pyproject.toml。
2. 配置 Python 3.11+。
3. 添加 FastAPI、Uvicorn、Pydantic Settings、SQLAlchemy、Alembic。
4. 添加 pytest、pytest-asyncio、ruff 和必要类型检查工具。
5. 创建 Settings，支持 .env，但测试不依赖真实密钥。
6. 创建 FastAPI app factory 或稳定应用入口。
7. 创建 GET /healthz。
8. 创建 SQLite 异步连接与数据库 Session。
9. 初始化 Alembic。
10. 建立基础日志格式和 request_id。
11. 提供 .env.example。
12. 建立最小 Dockerfile 或将其推迟到 M0-Gate，并在状态中记录。

#### 建议依赖

- fastapi
- uvicorn
- pydantic
- pydantic-settings
- sqlalchemy
- alembic
- aiosqlite
- httpx
- pytest
- pytest-asyncio
- ruff

不在此阶段安装 Next.js、PostgreSQL Driver、Celery、Redis 或向量依赖。

#### 交付物

- backend/pyproject.toml
- backend/app/main.py
- backend/app/config.py
- backend/app/infrastructure/db/*
- backend/migrations/*
- backend/tests/*
- .env.example

#### 测试

- 健康检查返回 200；
- 测试配置不会读取开发者真实 .env；
- SQLite 可以创建并关闭连接；
- Alembic 可以升级到最新并回滚；
- ruff 和 pytest 通过。

#### 验收

全新环境按照 README 可以安装依赖、运行迁移、启动 API 和运行测试。

### 10.3 M0-0C：Nanobot 最小核心迁移

#### 目标

在新仓库中建立唯一、可测试、与拾光业务解耦的 Nanobot Core。

#### 前置条件

M0-0B 已验收。

#### 任务

1. 迁移 Runner、Loop、Context、Tool、ToolRegistry 和 Provider 接口。
2. 迁移相关单元测试。
3. 移除通用文件系统工具。
4. 不迁移 Markdown Memory 和 JSONL Session 的产品依赖。
5. 保留 Fake Provider 测试。
6. 引入统一 ToolResult 的最小契约。
7. 明确最大工具循环次数。
8. 在 NOTICE 中记录迁移来源。
9. 确保 nanobot_core 不导入 FastAPI。
10. 确保拾光业务模块暂时不写入 Runner。

#### 交付物

- backend/nanobot_core/*
- backend/tests/core/*
- 更新后的 NOTICE.md

#### 测试

- 无工具回复；
- 单次工具调用；
- 多次工具调用；
- 工具不存在；
- 参数不合法；
- 工具执行失败；
- 达到循环上限；
- Provider 返回无内容。

#### 验收

Fake Provider 可以驱动 Runner 调用工具并生成最终回答；核心测试独立于数据库、模型密钥和高德密钥。

### 10.4 M0-1：模型接入与运行记录

#### 目标

证明真实模型可通过统一 Provider 完成 Tool Calling，并且每次运行都可追踪、可限制、可恢复。

#### 子阶段

##### M0-1A：Provider 契约

- 扩展模型响应：模型名、Token、耗时、完成原因、供应商请求 ID；
- 分类超时、限流、鉴权、格式和供应商错误；
- Fake Provider 覆盖全部结果；
- Provider 配置不写死模型名称和 Base URL。

##### M0-1B：真实百炼接入

- 实现 OpenAI 兼容 Provider；
- 使用一个无副作用测试工具完成真实 Tool Calling；
- 真实测试通过显式环境开关运行；
- 不把真实响应全文写入公开日志。

##### M0-1C：AgentRun 与 ToolRun

- 创建 AgentRun、ToolRun Schema 和第一批数据库表；
- 建立 trace_id；
- 记录状态、工具、耗时、Token、费用估算和错误码；
- 最大 8 次工具调用、总时长 60 秒；
- 相同工具参数的异常重复调用可被识别。

#### 交付物

- ModelProvider 正式契约；
- OpenAI 兼容实现；
- AgentRun、ToolRun 数据模型与迁移；
- Fake 和真实集成测试；
- 最小终端或测试入口。

#### 验收

- 无密钥时普通测试全部通过；
- 有密钥且显式开启时真实模型完成一次工具调用；
- 失败调用有明确错误码；
- 可以通过 trace_id 查询完整运行摘要；
- 不展示或保存模型思维链。

#### 用户参与

用户需要在本机 .env 配置百炼密钥。Codex 不创建账号、不代替付费授权、不提交密钥。

### 10.5 M0-2：文字收藏闭环

#### 目标

让纯文字输入可以成为结构化、可修改、可撤销、可追踪的收藏。

#### 子阶段

##### M0-2A：领域模型

- User、Session、Message；
- Source；
- CollectionItem；
- CollectionSource；
- 收藏状态机；
- Repository 接口；
- 用户隔离。

##### M0-2B：结构化抽取

- 定义 Place/Event 候选 Schema；
- 抽取标题、城市、区域、地址线索、类型、价格、标签和不确定项；
- 只接受深圳 MVP 范围；
- 不支持内容返回明确原因；
- 结构输出错误最多修复一次。

##### M0-2C：自动保存与可逆操作

- 自动保存结构化结果；
- 自动保存必须有 Undo Token；
- 支持修改允许字段；
- 支持逻辑删除；
- 幂等键防止重复消息和重复收藏；
- 同一来源重试不生成重复数据。

##### M0-2D：最小接口

- 创建 Demo 用户和 Session；
- POST Session Message；
- GET AgentRun；
- GET、PATCH、DELETE Collection；
- POST Undo。

#### 状态

    recognizing
      → active
      → pending_selection
      → pending_details
      → failed

failed 不创建有效收藏。active、pending_selection 和 pending_details 的数据含义必须区分。

#### 测试

- 明确深圳地点；
- 只有店名；
- 过于通用的名称；
- 非深圳地点；
- Event 文本；
- 不支持的菜谱或多日旅游需求；
- 空输入；
- 重复请求；
- 修改和撤销；
- 不同用户数据隔离。

#### 验收

文字输入在不需要前端的情况下可以完成：

    输入 → 识别中 → 结构结果 → 自动保存 → 修改或撤销

### 10.6 M0-3：高德地点匹配与消歧

#### 目标

让 Place 收藏绑定准确 POI，并在不确定时主动进入候选或补充流程。

#### 子阶段

##### M0-3A：MapProvider Stub

- 定义内部 POI DTO；
- 定义 search_poi、get_poi、route、weather 和 URI 接口；
- 实现唯一结果、多个结果、无结果、超时 Fixture；
- 领域层不得使用高德原始字段名。

##### M0-3B：真实高德适配

- 只在服务端使用 API Key；
- 深圳城市限制；
- 记录 provider、poi_id 和 GCJ-02；
- 设置超时、有限重试和响应校验；
- 真实集成测试显式开启。

##### M0-3C：匹配评分和候选

- 名称和分店名；
- 行政区和商圈；
- 地址、地标和地铁站；
- 电话；
- POI 类型；
- 原文上下文；
- 最多返回三个候选；
- 记录匹配证据和置信度；
- 用户选择或选择“以上都不是”。

#### 状态

    unmatched
      → searching
      → matched
      → ambiguous
      → needs_context
      → not_found

#### 测试样本

- 深圳当代艺术与城市规划馆；
- 至少两个存在多分店的连锁品牌；
- 同名但不同区域地点；
- 高德无结果地点；
- 原文区域与候选冲突；
- 用户选择第二个候选；
- 用户选择“以上都不是”。

#### 验收

- 不确定时不会自动绑定第一个结果；
- 待选择条目不能进入正式计划；
- 用户选择后保存确认来源；
- 相同用户的相同 POI 可以复用地点；
- 不同分店保持独立。

#### 用户参与

用户需要在本机 .env 配置高德开发 Key，并确认真实 API 调用可能产生额度消耗。

### 10.7 M0-4：URL、截图与文件存储

#### 目标

让文本 URL 和截图进入与纯文字相同的收藏状态机，并建立安全的失败降级。

#### 子阶段

##### M0-4A：私有文件存储

- StorageProvider 接口；
- 本地私有目录实现；
- 随机 file_key；
- 类型和大小限制；
- 生命周期信息；
- 测试文件自动清理。

##### M0-4B：网页解析

- HTTP(S) 白名单；
- 禁止本机、内网、云元数据和非 HTTP(S) 地址；
- httpx 获取；
- trafilatura 或 BeautifulSoup 抽取；
- 标题、正文、元数据和最终 URL；
- 超时或访问失败转文字或截图。

##### M0-4C：截图识别

- 图片上传；
- 多模态模型抽取；
- OCR 和视觉字段统一进入候选 Schema；
- 低置信字段显式标记；
- 不直接相信截图中的价格、营业时间和位置。

##### M0-4D：统一输入流水线

- TextInput、UrlInput、ImageInput；
- 统一 Source；
- 统一 Collection 状态；
- 统一 AgentRun 和 ToolRun；
- 来源保留；
- 同一内容重试使用幂等键。

#### 测试

- 普通公开网页；
- 无法访问网页；
- 重定向网页；
- 过长页面；
- 非法或内网 URL；
- 清晰地点截图；
- 只有店名截图；
- 图片模糊；
- 非图片文件；
- 超过大小限制。

#### 验收

- 三种输入最终进入同一收藏流程；
- URL 失败后只提供可恢复路径，不反复空转；
- 截图不确定字段不会被静默写成已确认；
- 上传文件不暴露公共路径；
- SSRF 防护测试通过。

### 10.8 M0-5：计划技术验证

#### 目标

证明结构化收藏可以在确定性约束下生成可解释、可修改的计划草案。

#### 子阶段

##### M0-5A：PlanConstraints

- city；
- start_at、end_at；
- activity area 或 origin；
- budget 可为 null；
- pace；
- transport modes；
- include、exclude；
- collection_only；
- 临时约束有效期。

时间和范围缺失时只追问缺失项。

##### M0-5B：结构化检索和规则

- 城市；
- 行政区；
- Place/Event；
- 收藏状态；
- 时间；
- 预算；
- 标签和关键词；
- 用户排除；
- 路线可达；
- 天气适配。

硬约束不满足时直接过滤，不能只降低分数。

##### M0-5C：草案生成

- 一个主方案；
- 最多两个备选；
- 默认一个核心地点加最多一个辅助地点；
- 交通缓冲 10–20 分钟；
- 结束留白 15–30 分钟；
- 时间、路线、费用、来源和风险；
- 选择理由和排除原因；
- 生成后再次执行确定性校验。

##### M0-5D：收藏不足与高德补充

- 收藏满足时不外搜；
- 有核心收藏但缺必要环节时可只读补充少量 Place；
- 主要依赖外部地点时创建 Approval；
- 用户拒绝后只用现有收藏或提示继续添加；
- 外部 Place 标记“高德补充 · 未收藏”；
- Event 不自动外搜；
- 确认计划不自动收藏外部 Place。

#### 状态

    generating
      → draft
      → waiting_approval
      → failed

M0 只验证草案，不实现完整正式确认、分享和提醒。

#### 测试

- 时间或范围缺失；
- 预算未设置；
- 收藏完全满足；
- 局部缺口；
- 无符合收藏；
- 只使用收藏；
- 少走路；
- 排除日料；
- 下雨天室内；
- 活动不足但禁止外搜 Event；
- 路线超时；
- 硬约束冲突；
- 调整一项条件且其他条件保留。

#### 验收

- 20 组计划 Fixture 中硬约束违反数为 0；
- 预算为 null 时仍展示费用；
- 不为填满时间而外搜；
- 计划能解释使用和排除收藏的原因；
- 工具失败时返回部分结果或恢复选择；
- 同一失败任务不会覆盖更新后的计划版本。

### 10.9 M0-Gate：技术验证总验收

#### 必须通过

1. Fake Provider 普通测试全通过。
2. 真实模型完成文本回复和 Tool Calling。
3. 文字、URL、截图各至少三个样本得到结构化结果。
4. 至少五个深圳地点覆盖唯一、多候选和无结果。
5. 模糊地点不会擅自选择第一个候选。
6. 重复执行不产生重复收藏。
7. 固定收藏可以生成满足约束的计划草案。
8. 20 组计划 Fixture 硬约束违反数为零。
9. 模型、高德、网页和图片失败有恢复路径。
10. 每条关键链路可以通过 trace_id 找到运行记录。
11. 仓库、日志和 API 响应中没有密钥。
12. 新环境可以根据 README 运行。

#### 阶段报告

输出 docs/technical/M0_VALIDATION_REPORT.md，至少包含：

- 环境；
- 测试数量；
- 通过与失败；
- 真实 API 验证范围；
- 延迟、Token 和费用；
- 未解决风险；
- 是否允许进入 M1。

M0-Gate 未通过时不得以开发页面掩盖底层链路问题。

---

## 11. M1：Web/H5 核心闭环

M1 的目标是不用微信也能完成完整 C 端闭环。正式前端参考 UX HTML，但不直接把原型脚本作为生产代码。

### 11.1 M1-0：PostgreSQL 与任务基础

#### 任务

- 将正式数据库切换到 PostgreSQL；
- SQLite 继续用于部分单元测试；
- 建立 PostgreSQL Job、Worker 和 APScheduler；
- 行锁、领取、重试、取消和幂等；
- Agent 运行进度通过 SSE 输出；
- 服务重启后任务可恢复；
- 配置本地 Docker Compose。

#### 验收

- API、Worker、PostgreSQL 可通过 Compose 启动；
- 重复 Worker 不会重复执行任务；
- SSE 断线可以从 sequence 继续；
- 失败最多重试三次；
- 测试环境不需要 Redis 和 Celery。

### 11.2 M1-1：Web 会话与 Demo 身份

#### 任务

- Web Session；
- Demo Session；
- 用户、会话和消息隔离；
- Demo 数据与真实数据分离；
- 不实现手机号密码；
- 为未来一次性微信绑定预留 ChannelIdentity。

#### 验收

- 不同浏览器会话不能读取彼此数据；
- Demo 不能执行外部写操作；
- Session 恢复与过期行为明确。

### 11.3 M1-2：正式前端基础

#### 任务

- 初始化 Next.js + TypeScript；
- 建立颜色、字体、间距和组件 Token；
- 实现响应式移动端和桌面框架；
- 实现四项主导航；
- 建立 API Client、错误处理和 SSE Client；
- 加入可访问性、键盘焦点和减少动画支持；
- 从 HTML 原型提取视觉规则，不复制 Mock 业务状态。

#### 验收

- Agent、收藏、计划、我的四个空路由可访问；
- 移动端和桌面端无横向溢出；
- API 错误和加载状态统一；
- 前端测试和类型检查通过。

### 11.4 M1-3：Agent 与内容导入页面

对应 UX M01、M02。

#### 任务

- 首次引导；
- 主输入；
- 文字、URL、截图上传；
- 识别中 SSE 状态；
- 已收藏、待选择、待补充和失败；
- 修改、撤销、继续添加；
- Agent 工具过程按需展开；
- 不展示思维链。

#### 验收

- 三分钟内可以完成首次收藏；
- 处理中不提前显示成功；
- 修改和撤销首屏可见；
- 上传失败有最短恢复路径。

### 11.5 M1-4：收藏库与地点消歧

对应 UX M03、M04。

#### 任务

- 收藏列表；
- 搜索、分页和筛选；
- Place/Event 和状态；
- 详情编辑；
- 多候选选择；
- “以上都不是”；
- 删除和撤销；
- 待确认内容禁止进入正式计划。

#### 验收

- 用户只看到自己的收藏；
- 筛选条件与后端一致；
- 候选线索足以区分分店；
- 修改后 Agent 对话中读取同一数据。

### 11.6 M1-5：计划生成、调整和确认

对应 UX M05。

#### 任务

- 时间和活动范围输入；
- 预算可选；
- 条件确认卡；
- 计划生成进度；
- 时间光轨；
- 主方案和备选；
- 费用、交通、来源和风险；
- 外部补充授权；
- 自然语言调整；
- 计划版本；
- 明确确认。

#### 验收

- 修改一个条件不覆盖其他条件；
- 旧任务不覆盖新版本；
- 外部 Place 清晰标记；
- 未确认计划不能生成执行动作；
- 确认计划不自动收藏外部 Place。

### 11.7 M1-6：执行入口与手动反馈

对应 UX M06。

#### 任务

- 生成一个完整计划的 iCalendar 文件；
- 生成高德地点和路线入口；
- 计划完成、部分完成、未完成；
- 部分完成逐项选择；
- 更新实际到访收藏；
- 外部未收藏地点只更新 PlanItem；
- 生成长期偏好建议，但不自动写入。

#### 验收

- .ics 可导入主流日历；
- 时间、时区和地址正确；
- 三种反馈状态更新规则正确；
- 反馈不会错误修改未到访收藏。

### 11.8 M1-7：我的、记忆和数据控制

对应 UX M07。

#### 任务

- 查看长期记忆；
- 查看来源与确认状态；
- 修改和删除；
- 推断偏好确认；
- 临时约束过期；
- 数据导出基础；
- 提醒设置只展示未实现或关闭状态，避免误导。

#### 验收

- 删除记忆后下一次计划不再使用；
- 推断偏好未经确认不可参与计划；
- 精确敏感位置不自动成为长期记忆。

### 11.9 M1-8：只读分享能力

对应 UX M08，属于 P1，可在核心闭环稳定后实现。

#### 任务

- 只分享最新确认版本；
- 脱敏计划快照；
- 随机 Token，只存哈希；
- 只读、可撤销；
- 计划结束七天后失效；
- 取消、撤销和过期状态；
- 分享链接不具备登录能力。

#### 验收

- 未登录访客只能读取单份分享计划；
- 无私人收藏、记忆、消息和内部 ID 泄露；
- 撤销立即失效；
- 分享 Token 不能兑换用户 Session。

### 11.10 M1-Gate

必须在不接微信的情况下完成：

    输入
      → 收藏
      → 修改或消歧
      → 收藏检索
      → 计划生成
      → 调整
      → 确认
      → 路线和日历
      → 手动反馈

质量要求：

- 核心流程自动化成功率目标不低于 95%；
- 20 组计划硬约束违反数为 0；
- 收藏查询目标 P95 不超过 500 毫秒；
- 文本完整回复目标 P95 不超过 12 秒；
- 图片和网页解析目标 P95 不超过 20 秒；
- 任务重试不产生重复收藏、计划或文件；
- Demo 与真实数据隔离。

---

## 12. M2：微信 ClawBot 完整 MVP

M2 只在 M1 Web 核心闭环稳定后开始。

### 12.1 M2-0：ClawBot 技术 Spike

#### 验证

1. 微信文字进入 Adapter。
2. Adapter 转换为 InboundMessage。
3. FastAPI/Nanobot 处理。
4. OutboundMessage 返回微信。
5. 截图下载、解密、私有存储和解析。
6. 用户、会话、消息 ID 和 trace_id 映射。
7. 重复消息、断线和发送失败恢复。
8. 凭证存储在持久化私有目录。

Spike 不通过时不得开始完整微信功能。

### 12.2 M2-1：Channel Adapter

- 只做身份和消息格式转换；
- 支持文字、图片、文件和数字选项；
- 业务动作仍调用同一 Application；
- 微信按钮不可用时使用数字选项和自然语言；
- Adapter 不维护第二套状态机。

### 12.3 M2-2：微信与 Web 关联

- 10 分钟单次登录链接；
- 服务端兑换 30 天 Web Session；
- Token 只能使用一次；
- URL 不继续携带长期凭证；
- 设备可撤销；
- 复杂编辑从微信进入 H5；
- 分享链接与登录链接严格分离。

### 12.4 M2-3：主动计划和提醒

- 默认关闭；
- 开启后默认周四 19:30 询问；
- 不擅自生成或确认计划；
- 行前提醒按单份计划授权；
- 默认建议提前 60 分钟；
- 可取消、去重和重试；
- 失败时 Web 显示真实状态。

### 12.5 M2-4：主动反馈

- 计划结束后询问完成情况；
- 用户可关闭；
- 完成、部分完成和未完成；
- 长期偏好泛化前再次确认；
- 避免对同一计划重复询问。

### 12.6 M2-Gate

- 微信文字、截图和文件闭环成功；
- Web 与微信看到同一收藏、计划和记忆；
- 重复消息不产生重复数据；
- 断线恢复不会覆盖新状态；
- 主动消息有授权、取消和失败记录；
- 凭证、Cookie 和密钥不进入日志；
- 完成真实设备测试后才称为 C 端 MVP。

---

## 13. M3：公开作品集版本

### 13.1 M3-0：公开 Demo 沙盒

- 无需登录；
- 深圳虚拟用户数据；
- 内置文字、URL 结果和截图样例；
- 每个会话约十轮 Agent 操作；
- 每位访客每天最多五次完整 Agent 任务；
- 两小时自动清理；
- 高德、天气和路线优先使用缓存；
- 禁止真实外部写操作；
- 与真实用户数据库和凭证分离。

### 13.2 M3-1：Agent 工作过程展示

展示：

- 输入摘要；
- 意图；
- 使用的收藏、偏好和临时约束；
- 工具名称和成功状态；
- 来源与查询时间；
- 排除原因；
- Token、耗时和估算费用；
- 授权和最终执行动作。

不展示：

- 思维链；
- 系统 Prompt；
- 密钥；
- Cookie；
- 敏感原始参数；
- 无关用户原文。

### 13.3 M3-2：作品集案例

- 产品背景与问题；
- 竞品分析；
- PRD 和决策过程；
- UX 原型和迭代；
- 系统架构；
- Nanobot 核心复用；
- Agent 评测；
- 异常和降级案例；
- Dogfooding 结果；
- 演示视频；
- 已验证事实与市场假设的边界。

### 13.4 M3-3：部署和安全

- 腾讯云香港轻量服务器；
- Caddy HTTPS 和反向代理；
- Docker Compose 运行 Web、API、Worker、PostgreSQL 和微信网关；
- COS 私有桶；
- 限时签名下载；
- Demo 与真实环境分离；
- 每日数据库备份，保留最近七天；
- 限流、成本上限和熔断；
- 健康检查和恢复说明。

### 13.5 M3-Gate

- 公开 Demo 不依赖真实私人数据；
- 作品集案例可以独立说明产品与技术；
- 演示失败时可以切换预置案例；
- 仓库和线上环境通过密钥扫描；
- 数据备份和恢复至少演练一次；
- 对外明确“已验证功能与体验，尚未验证市场价值”，除非存在真实用户证据。

---

## 14. 测试窗口执行规范

### 14.1 QA 窗口职责

- 在最新集成版本上运行测试；
- 根据阶段验收标准设计测试；
- 复现并记录问题；
- 判断问题属于产品、实现、环境还是外部 Provider；
- 不在测试报告中虚构未执行的结果；
- 默认不修改生产业务代码。

### 14.2 测试层级

| 层级 | 目标 |
|---|---|
| Unit | 状态机、规则、评分、幂等、时间预算 |
| Integration | Repository、Provider Stub、数据库、存储 |
| Contract | API、ToolResult、SSE、Provider DTO |
| Agent Eval | 意图、结构抽取、工具选择、失败恢复 |
| E2E | 输入到反馈的完整闭环 |
| Real Provider | 显式开启的模型、高德和存储验证 |

### 14.3 默认测试规则

- 普通测试不调用真实付费 API；
- 模型和高德使用 Fake、Stub 或录制 Fixture；
- 真实 API 测试单独标记；
- 时间测试固定时钟和 Asia/Shanghai；
- 失败场景验证数据库没有多余写入；
- 测试不能依赖执行顺序；
- 测试数据必须按用户和会话隔离；
- 不通过删除断言、扩大容差或跳过测试制造绿色结果。

### 14.4 缺陷报告格式

    标题：
    阶段：
    严重程度：
    环境：
    前置条件：
    操作步骤：
    预期结果：
    实际结果：
    日志或 trace_id：
    是否稳定复现：
    可能影响：
    建议负责窗口：

### 14.5 缺陷严重程度

| 级别 | 说明 |
|---|---|
| P0 | 数据泄露、越权、数据损坏、核心流程完全不可用 |
| P1 | 核心流程错误、硬约束违反、重复写入、错误地点 |
| P2 | 有恢复路径的功能问题、明显体验问题 |
| P3 | 文案、样式、低风险易用性问题 |

P0、P1 未关闭时不能通过阶段 Gate。

## 15. 安全、密钥和外部操作

### 15.1 密钥

- 仅存放在本机 .env；
- .env 必须被 Git 忽略；
- .env.example 只写变量名；
- 测试输出不打印密钥；
- Provider 错误先脱敏再记录；
- 不把密钥发到文档和对话。

### 15.2 需要用户参与

- 申请百炼、高德、腾讯云和 ClawBot 账号；
- 配置本机密钥；
- 确认可能产生费用的真实测试；
- 登录外部控制台；
- 授权云部署、域名、公开分享和外部消息；
- 确认改变产品行为的重要决策。

### 15.3 Codex 可以直接完成

- 工程、代码、测试和迁移；
- Fake、Stub、Fixture；
- 本地 Docker；
- API 和 Provider 适配代码；
- 文档和开发状态；
- 在授权范围内运行本地测试；
- 诊断真实 API 返回的技术错误。

## 16. 防止代码冗余和架构漂移

新窗口实现前必须使用代码搜索确认是否已有：

- 相同 Schema；
- 相同 Repository；
- 相同 Provider；
- 相同工具；
- 相同状态机；
- 相同错误类型；
- 相同 API 路由；
- 相同测试 Fixture。

发现类似实现时优先扩展公共模块。只有在语义确实不同、测试能证明边界时才新增。

### 16.1 公共契约归属

| 契约 | 唯一归属 |
|---|---|
| AgentRunner | backend/nanobot_core |
| Tool、ToolRegistry、ToolResult | backend/nanobot_core/tools |
| ModelProvider | backend/nanobot_core/providers |
| MapProvider、StorageProvider、JobQueue | backend/app/providers |
| 收藏状态机 | backend/app/domain/collections |
| POI 匹配 | backend/app/domain/places |
| 计划状态和规则 | backend/app/domain/plans |
| API Schema | backend/app/schemas |
| 前端 API Client | frontend/lib |

### 16.2 禁止行为

- 在路由中复制领域规则；
- 在前端重新判断后端状态；
- 为微信复制 Web 业务服务；
- 为测试复制生产算法；
- 在多个目录定义同名状态枚举；
- 通过复制整个模块绕开循环依赖；
- 因为“以后可能用”提前实现第二套 Provider；
- 将第三方原始响应直接作为领域模型。

## 17. 文档和状态维护

### 17.1 每阶段必须更新

- docs/DEV_STATUS.md；
- 与本阶段有关的 README；
- 新增或改变的环境变量；
- API 契约或 OpenAPI；
- 数据迁移说明；
- 已知风险；
- 下一阶段前置条件。

### 17.2 需要 ADR 的变化

以下变化不能只改代码，必须增加 docs/adr：

- 改为微服务；
- 改变数据库或任务队列；
- 引入向量检索；
- 改变 Web/微信共享模型；
- 改变 Agent 写操作授权方式；
- 改变 Demo 数据隔离方式；
- 新增第二家地图或模型路由；
- 让外部 Event 自动检索进入 MVP。

### 17.3 交接摘要

每个阶段的最终回复和 DEV_STATUS 记录必须回答：

1. 完成了什么；
2. 修改了哪些关键文件；
3. 运行了哪些验证；
4. 哪些真实集成没有验证；
5. 是否有数据迁移；
6. 是否有新的配置；
7. 已知风险是什么；
8. 下一窗口应该做什么；
9. 是否满足阶段完成标准。

## 18. 建议提交边界

示例：

    chore: establish project documentation baseline
    build: scaffold FastAPI backend
    feat: import minimal nanobot core
    feat: add model provider and run tracing
    feat: implement text collection workflow
    feat: add amap poi resolution
    feat: support url and image ingestion
    feat: generate rule-validated plan drafts
    test: complete m0 regression suite

一个提交不要同时包含大规模格式化、无关重命名和业务功能。

## 19. 第一条开发任务

下一个开发窗口应收到以下任务：

    当前仓库是拾光正式项目。请先完整阅读 AGENTS.md、
    docs/DEVELOPMENT_STAGES.md 和 docs/DEV_STATUS.md。
    然后只实施 M0-0A：项目基线与资料迁移。
    不创建后端业务代码，不接模型或高德。
    完成后执行阶段验收，更新 DEV_STATUS，并汇报改动和验证结果。

M0-0A 验收通过后，主控窗口再安排 M0-0B。

## 20. 最终完成定义

项目只有在以下结果全部存在时才视为达到作品集完成状态：

- Web/H5 独立完成完整核心闭环；
- 微信通道通过真实设备验证；
- 收藏、地点、计划、记忆和授权具备可靠状态机；
- 文字、URL、截图有统一输入和降级；
- 计划硬约束评测无违反；
- 关键链路有可解释运行记录；
- Demo 与真实数据隔离；
- 公开部署具备安全、限流、备份和失败降级；
- 产品文档、技术文档、验证报告和演示视频齐全；
- 对外展示真实验证结果，不虚构用户和指标。

开发过程中始终优先完成当前最小闭环，而不是追求功能数量。
