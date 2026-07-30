# 拾光开发状态

| 项目 | 当前值 |
|---|---|
| 当前总阶段 | M1 Web/H5 核心闭环 |
| 当前子阶段 | M1-Gate 稳定化修复 |
| 状态 | 待主控验收 |
| 当前分支 | main |
| 最近更新 | 2026-07-30 |
| 阻塞项 | M1-Gate 地点确认、Event 时间交互与计划闭环仍待分项修复；M2-0 未开始且阻塞 |

## 2026-07-30 阶段状态纠正

真实运行复验确认截图导入、收藏补充与地点确认、Place/Event 和日期语义、组合输入、
Retry 及计划入口仍存在核心闭环缺陷。因此此前“M1 正式关闭、无 P0/P1、允许开始
M2-0”的结论只保留为历史验收记录，不再代表当前 Gate 状态。

- M1-Gate 稳定化修复：待主控验收；
- M2-0：未开始，阻塞于主控复验；
- 本分支修复完成后最多标记为“待主控验收”，不得自行重新关闭 M1 或允许开始 M2。

## 2026-07-30 稳定化候选

- “M1 语义确认闭环”生产修复已完成，等待主控复验。收藏详情页现作为唯一 Event
  时间确认入口：仅 Event 展示有效开始/结束日期与准确开始/结束时间，预填服务端
  返回的模型建议，并通过既有 `PATCH /collections/{item_id}` 显式提交当前字段；
  前端不提交 `uncertainties` 或 `missing_fields`，也没有新增 API Client、Event
  DTO、确认服务或第二套编辑流程。
- `datetime-local` 展示和提交固定使用 `Asia/Shanghai` 语义：服务端时间按 UTC
  瞬间转换为上海本地控件值，提交时显式生成 `+08:00` ISO 8601，不读取浏览器所在
  时区。前端拒绝倒置日期和结束不晚于开始的准确时段；409、422、超时或取消保留
  用户草稿，不显示伪成功。
- 用户不修改建议直接点击“确认并保存”也会提交所有当前非空时间字段。服务端响应
  始终替换本地 item 和 version；部分确认、缺少完整准确时段或准确 POI 未确认时
  继续显示不可规划，只有服务端返回 `planning_eligible=true` 才显示可参与计划。
  Agent 结果卡不复制表单，只为待确认 Event 链接到
  `/collections?item=<collection_item_id>`。
- 后端补充回归证明清空 metadata 不能绕过时间确认、单字段 PATCH 只确认对应字段、
  完整确认清除相应 uncertainty、无准确 POI 时仍保持 `pending_details`、重复确认
  稳定且旧 version 冲突继续拒绝。指定后端聚焦集 `127 passed`；非真实 Provider/
  Map marker 全集 `1692 passed, 16 skipped, 2 deselected`；Alembic 唯一 head
  仍为 `20260729_0017`。前端 `lint/typecheck/test/build` 均通过，Vitest
  `97 passed`。
- 状态继续保持“M1-Gate 稳定化修复待主控验收”；本窗口不关闭 M1，不允许开始
  M2，未新增迁移，也未进行真实模型、地图或网页调用。
- 本轮“语义理解与可信确认边界收敛”生产修复完成，等待主控复验。此前文字抽取的
  `source_evidence`、候选标题切片、中文日期/钟点正则和格式解析表已从正式
  Schema、Prompt、解析及 canonicalization 全部删除；模型不再用自报
  `candidate_index/value/quote` 证明自己的时间结论，应用也不再实现第二套自然
  语言时间解析器。
- 文字、URL 和截图现在共用唯一 extraction canonicalization：模型提出的每个
  非空 Event 日期/准确时刻原值都保留用于展示和编辑，同时逐字段自动加入
  uncertainty。年份缺失、模糊时间、截图状态栏、多个 Event、重复或改写标题均不
  再由代码猜测语义；在用户确认前收藏保持 `pending_details`，Event 类型不变且
  不能进入计划。
- 用户继续通过既有收藏 PATCH 显式保存日期/时刻。被保存字段从 missing 和
  uncertainty 中移除；未触及字段的时间 uncertainty 不能被客户端直接改写元数据
  绕过。已有准确地点且准确场次起止均满足、所有已提出时间字段均确认后，既有状态
  机才转为 `active`。地点选择、API `planning_eligible`、结构检索和地图计划事实
  统一复用 `event_schedule_is_confirmed`，没有新增确认服务、Repository 或计划
  流程。
- 生产语义硬编码审计删除了“咖啡店/餐厅/展览/活动”等 `_GENERIC_INPUTS` 词表，
  这些输入改由模型按统一语义契约判断。保留的文字预检仅包括空输入、长度上限和
  PRD 明确不支持类型的高置信组合判定；既有测试继续证明标题中单独出现菜谱、商品
  或路线字样不会被预检拒绝。该组合判定仍是后续主控应审视的有限维护风险。
- 本轮最终离线复验：`pip check`、Ruff、strict mypy（140 个源文件）均退出码 0；
  后端全量 `1691 passed, 18 skipped`；仓库外插件封锁 DNS 与
  `connect/connect_ex/create_connection` 后，语义、图片、统一输入、内容导入、
  收藏 PATCH、计划和 Memory 聚焦集 `340 passed`；Alembic 唯一 head 仍为
  `20260729_0017`。前端未改生产代码，`lint/typecheck/test/build` 均退出码 0，
  单测 `87 passed`；因此本轮未额外运行 Playwright。
- 状态保持“M1-Gate 稳定化修复待主控验收”；本窗口不宣布 Event 时间证据 P1
  关闭，不关闭 M1，也不允许开始 M2。
- 候选 `d60975814a1d4d0ae35d246bb6e6d44e1babb58d` 复验发现临时
  `source_evidence` 的候选序号、字段值和原文片段仍全部来自同一次模型响应；仅验证
  片段存在和字段值相等，无法证明片段确实表达该日期/时刻或属于当前候选。
- Event 时间证据信任边界的生产修复完成，等待主控复验。唯一结构输出解析边界现把
  模型证据只视为原文定位提示：应用侧集中解析片段中的明确日期和钟点，按
  `Asia/Shanghai` 核对规范化字段值，并要求片段位于当前候选唯一、精确标题所在的
  原文分句。无时间内容、值不一致、跨候选交换/借用、重复标题和改写标题均保守清空
  时间事实并登记 uncertainty；Event 类型不变。该临时证据仍在领域 DTO 前删除，
  不进入数据库、日志或公开响应。
- 本轮没有增加 Prompt 关键词、标题/样本特例、并行结构抽取流程或第二套 Candidate、
  Provider、Runner；模型 initial 和唯一 repair 共用同一个应用侧可信验证函数。
- Event 时间证据 P1 的生产修复已完成，等待主控复验。候选
  `8c7cd71924012b46f8f0573bc24c5f00b2774ef7` 使用标题位置切片并手写年月日/
  钟点格式，无法可靠处理日期位于标题前、中文上午/下午、重复或改写标题以及多个
  Event。该路径现已删除。
- 文字模型的同一结构输出现携带临时 `source_evidence`：每条证据绑定候选序号、
  单个 Event 时间字段、该字段的原始结构值和原文逐字片段。唯一结构输出信任边界
  先校验原有严格候选结构，再核对字段值、原文片段和跨候选片段占用；证据随后立即
  删除，不进入 `EventCandidate`、数据库或公开 DTO。无可靠证据的时间事实保守清空
  并登记 uncertainty；Event 类型不变。没有新增 Candidate、Parser、Provider、
  Runner、迁移、日期格式表、时间格式表或标题特例。
- 候选 `e3eeb90b1e25aac6d22ad03c7842b3786d5c1f86` 复验发现两个 P1：
  文字抽取后置规则用有限活动关键词把 Event 改成 Place，并用整段文字共享的年份/
  时刻布尔值污染多个候选；前端则为每次 Retry 生成新幂等键，使响应丢失、超时或
  取消后的不确定重放失去服务端去重身份。另有一个 P2：所有截图存储错误均返回
  HTTP 500，包括类型、签名、空文件和大小等客户端输入错误。
- P1 修复删除 Event 活动关键词白名单和 Event → Place 后置改型；模型输出类型继续
  受唯一语义契约约束，时间事实只在当前 Event 标题绑定的原文证据范围内逐候选核验。
  无法证明的日期/时刻会保守清除并登记 missing/uncertainty，不改变候选类型，也
  不允许一个候选的年份或时刻授权另一个候选。
- P1 幂等修复在前端为未修改的准备输入保留一个提交键：网络断开、超时和取消后的
  主动 Retry 复用该键；权威终态识别失败后的 Retry，以及文字或截图被选择、删除、
  替换、编辑或“继续添加”后才生成新键。没有自动重试、前端重试循环或第二套幂等
  服务。离线重放确认 Message、AgentRun、Job、Source 各一条且模型最多调用一次。
- P2 修复把截图类型不允许、签名不符、空文件和文件过大分别稳定映射为
  415/422/400/413；写入失败、损坏对象和内部存储故障继续为 5xx。公开错误只保留
  安全 error code、固定消息和恢复动作，不包含文件名、路径、内容或异常链。
- API 与 Worker 现通过同一运行时构造入口获得既有 `StorageProvider`；截图准备、
  Message、AgentRun、Source 与 Job 的失败/取消补偿收敛到正式提交入口，失败不再
  遗留无 Job 的运行记录或私有文件，幂等重放只保留一份资源。
- 现有收藏写入口在补充字段后重新计算 `missing_fields`/`uncertainties`，随后调用
  既有 `PlaceMatchingService` 和 `PlaceTargetSelectionService`：明确唯一地点可
  `active`，多候选保持 `pending_selection` 直至用户确认。
- Place/Event 与日期证据在现有结构化抽取规范化边界收敛；周末访问偏好不再单独
  形成 Event，无明确年份不保存完整日期，无明确时刻不保存精确时间。
- Agent 支持“截图 + 可选补充文字”、显式删除截图和一次主动 Retry；收藏保存失败
  恢复服务端权威数据，保存成功自动展示既有地点候选；计划按钮进入既有计划页。
- 没有新增迁移、Provider、Runner、Storage、Parser、匹配器、收藏 Repository 或
  计划流程；没有样本标题、店名或城市白名单。
- 最新离线复验：`pip check`、Ruff 和 strict mypy（140 个源文件）退出码均为 0；
  指定 Event/API/统一输入/检索/计划聚焦集 `257 passed`，后端全量
  `1697 passed, 18 skipped`；仓库外插件封锁 DNS/socket 后的语义、统一
  输入和内容导入聚焦集 `136 passed`；前端单测 `87 passed`、生产构建和浏览器
  E2E `29 passed`，覆盖
  320/390/768/1024/1440 宽度；Alembic 唯一 head 仍为 `20260729_0017`。
- Event 时间证据 P1 不在本窗口自行宣布关闭；生产修复完成，等待主控复验。既有
  P2 仍为 npm 开发依赖 audit 和跨浏览器覆盖限制。状态只到“待主控验收”，M1
  未重新关闭。

## 2026-07-30｜M1-Gate 稳定化修复 1｜等待主控验收

- 分支：`codex/m1-gate-provider-runtime-wiring`；提交随本记录创建，完整 SHA 见
  开发窗口最终交接。
- 运行配置接线修复完成，等待主控验收。`compose.yaml` 现以逐项白名单方式向 API
  和 Worker 一致透传既有模型配置、模型价格/结构输出配置、Agent 运行上限及高德
  配置；未使用宽泛 `env_file`，未新增 Settings、Provider 工厂或配置加载器。
- 可选配置未设置或留空时不会让空字符串进入 Settings，模型与高德 Provider 保持
  未配置，API、Worker 和两套 PostgreSQL 均正常启动；提供仓库外非敏感占位配置
  时，两进程均通过 timeout、structured output、价格、重试和 Provider 构造断言，
  API 既有计划地图配置门禁可用。启动和健康检查不发送外部请求。
- `RUN_REAL_MODEL_TESTS` 和 `RUN_REAL_MAP_TESTS` 在 API、Worker 中继续固定为 `0`。
  本轮真实模型、高德、网页或其他外部 API 调用为 0；未读取本机 `.env`，未打印
  Compose 展开配置或容器完整环境，未把密钥写入镜像、代码、文档、测试或 Git。
- 验证：`pip check`、Ruff、strict mypy（140 个源文件）均通过；
  `tests/test_config.py` 为 `131 passed`；非真实 Provider/Map 全集为
  `1692 passed, 16 skipped, 2 deselected`。空配置和假配置均使用独立 Compose
  project、独立端口和临时 volume；四服务 healthy、`/healthz` 为 200、restart
  count 为 0，随后正常关闭并只清理本任务容器、镜像、网络、volume 和 `/tmp`
  文件。
- M1-Gate 继续保持打开，本窗口不宣布 M1 重新关闭；M2-0 继续保持未开始且阻塞。
  下一项仍为地点确认闭环修复，本窗口未开始地点修复或 M2。

## 2026-07-30｜M1-Gate 稳定化修复 1｜主控验收通过

- 主控确认 `codex/m1-gate-provider-runtime-wiring` 的候选提交
  `7debcd01a5cf03c826546317bf1431c198bd4585` 直接基于
  `cf0b1a481a0b972c330e912cfd7382667a913a1a`，且只修改
  `compose.yaml`、`.env.example`、`README.md` 和本状态文档；未修改生产业务
  Python、前端、迁移或 M2 范围。该候选已通过 `--ff-only` 集成到 `main`。
- `pip check`、Ruff、strict mypy（140 个源文件）和 `tests/test_config.py`
  （`131 passed`）通过；非真实 Provider/Map 全集为
  `1692 passed, 16 skipped, 2 deselected`。
- 主控另以两个独立 Compose project 验收空配置与仓库外假配置：API、Worker 和
  两套 PostgreSQL 均 healthy、restart count 为 0，`/healthz` 返回 200；空配置
  不把可选 Provider 变量留在运行进程，假配置在 API 与 Worker 中得到一致的模型、
  价格、Agent 上限和高德 Settings，并能构造既有唯一 Provider。两套运行均固定
  `RUN_REAL_MODEL_TESTS=0`、`RUN_REAL_MAP_TESTS=0`，启动期间外部 HTTP 连接为 0。
- 本轮未读取本机 `.env`，真实模型、高德、网页和付费 API 调用均为 0；未发现密钥、
  完整响应、缓存、数据库或临时 QA 资源进入 Git。Compose QA 只清理本轮创建的
  project、镜像、容器、网络和 volume。
- 本项没有未关闭 P0/P1，配置接线修复已完成。M1-Gate 仍保持打开，下一项必须从
  最新 `main` 修复地点确认完整闭环；Event 时间控件和计划闭环继续留给后续独立
  修复，M2-0 仍未开始且阻塞。

## 历史验收摘要（不代表当前 Gate 状态）

M0-0A 至 M0-5D、M0-Gate、Event 日期粒度和富输入截止策略均已通过主控验收，M0
保持正式完成。M1-0 已通过主控验收：先关闭 `IdempotencyLockRegistry` 无界增长
及取消清理竞态，再完成 PostgreSQL、持久化 JobQueue、Worker、APScheduler、
RunEvent/SSE replay 和最小 Docker Compose。M1-1 已通过主控验收：浏览器
Session、稳定 CSRF、并发安全 Demo 恢复、跨浏览器所有权过滤及 Demo/真实物理
隔离均已复核。M1-2 正式前端基础、响应式布局、统一 API/SSE Client 和可访问性
边界已通过主控验收。M1-3 也已通过主控验收：正式 Agent 首页已接通 202 Job、
SSE 和权威结果查询，支持文字、URL、截图、会话恢复、多收藏并发安全修改、撤销、
恢复与继续添加。M1-4 收藏库与地点消歧也已通过主控验收：列表、组合筛选、详情
编辑、地点消歧、删除恢复、规划隔离、来源迁移及真实 JSON 标签边界均已复核。
M1-5 也已通过主控验收：计划创建、后台生成、外部补充授权、不可变版本、异步自然
语言调整、明确确认和前端恢复均已复核。M1-6 已通过主控验收：确认后日历与导航、
三态可更正反馈、收藏到访来源重算、PostgreSQL 并发幂等、关系所有权及前端迟到
响应隔离均已复核。M1-7 也已通过主控验收：结构化 Memory、可审计偏好候选、当前
请求优先的 pace 默认、城市无关粗区域、有效检索与使用记录、M07 控制页及私有导出
均已复核。M1-8 已通过主控验收并纯快进集成：行程级 256-bit 哈希分享、创建前脱敏
预览、同键并发重放、最新确认版本快照、即时撤销/重建、七天过期、取消状态、匿名
只读边界、标准地图入口和 M08 Web/H5 均已复核。M1-Gate 现也已完成：高德候选
隔离 P1、时间夹具稳定性、普通/封网全集和有限真实地图复测均通过。M1 正式关闭，
当前无未关闭 P0/P1，唯一允许开始的阶段为 M2-0。

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
| M0-5 计划技术验证 | 已完成 | M0-5A、M0-5B、M0-5C、M0-5D 均已通过主控验收 |
| M0-Gate 阶段验收 | 已完成 | 完整离线、封网、迁移、本地启动、真实链历史证据、容器、安全与冗余主控复核通过 |

## M1 历史状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| M1-0 PostgreSQL 与任务基础 | 已完成 | 主控独立复验锁生命周期、PostgreSQL、Job/Worker、SSE replay、Compose、安全和净复杂度通过 |
| M1-1 Web Session | 已完成 | 主控复核稳定凭据、CSRF、并发恢复、隔离、PostgreSQL 与 Compose 通过 |
| M1-2 Next.js 前端 | 已完成 | 主控复核响应式、可访问性、API/SSE 错误边界、离线测试、构建和浏览器 E2E 通过 |
| M1-3 Agent 与内容导入 | 已完成 | 主控复核 202 Job、SSE、权威结果、会话恢复、多收藏并发更新、离线浏览器闭环与安全边界通过 |
| M1-4 收藏库与地点消歧 | 已完成 | 主控复核列表/筛选、详情编辑、消歧、来源迁移、迟到响应隔离和 JSON 标签边界通过 |
| M1-5 计划生成、调整和确认 | 已完成 | 主控复核异步生成/调整、版本隔离、确认边界、外部补充、幂等并发、离线浏览器闭环与代码唯一性通过 |
| M1-6 执行入口与手动反馈 | 已完成 | 主控复核 iCalendar、导航、反馈更正、收藏到访重算、PostgreSQL 并发/外键、迟到响应与真实离线 M06 闭环通过 |
| M1-7 我的、记忆和数据控制 | 已完成 | 主控复核 Memory 授权、建议终态、pace 优先级、粗区域、计划使用、并发幂等、私有导出及 M07 竞态通过 |
| M1-8 只读分享能力 | 已完成 | 主控复核哈希 bearer、创建前脱敏预览、并发重放、取消后撤销、七天过期、匿名 GET、PostgreSQL 与 M08 响应式页面通过 |
| M1-Gate 核心闭环验收（2026-07-29 历史） | 已完成 | 历史主控复核完整闭环、离线/封网全集、高德候选隔离、时间稳定性及 7 次零重试真实地图复测通过；该结论已被 2026-07-30 真实运行复验重新打开 |

状态只允许使用：未开始、进行中、待验收、待主控验收、已完成、阻塞。

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
- M0-5B 已完成：唯一结构化收藏检索入口、正式城市和状态边界、硬约束过滤、动态事实、请求级任意分店解析、同 POI 去重、安全错误及只读幂等均已通过主控验收。
- M0-5C 已完成：唯一确定性草案生成与复核入口、主方案及最多两个备选、交通与结束缓冲、费用/来源/风险、任意分店快照、20 组零硬约束违反 Fixture，以及中国场景下严格的 `None + None` 或 `Decimal + CNY` 价格契约均已通过主控验收。
- M0-5D 已完成：收藏优先、显式 Place 缺口、外部补充 Approval、拒绝/collection-only/Event 零外搜、候选消歧、外部来源与风险、统一排程和已知/未知 CNY 费用均已通过主控验收。
- M0 关闭后 Event 日期粒度修正已完成：有效自然日期与准确场次时间使用独立字段，
  date-only Event 可收藏但保持待补充且不进入计划；没有样本白名单或第二套解析链。
- 富输入截止策略收敛已完成：URL/图片只使用 60 秒应用层共享硬截止，
  Provider/transport 使用 75 秒异常安全上限；固定样本 03 在约 47.1 秒成功返回，
  正确保留展期日期并保持精确时刻为空，实际 1 次请求、0 repair、0 重试。
- M1-0 开发实现已完成：幂等锁注册表可在最后参与者退出后安全淘汰；正式运行支持
  PostgreSQL；唯一 JobQueue、Worker 和 APScheduler 创建适配已建立；既有 AgentRun
  增加持久化安全事件和 SSE 断线重放；本地 Compose 提供 PostgreSQL、API、Worker。
- M1-1 开发实现已完成：浏览器凭据只以哈希持久化，Cookie/CSRF、绝对过期、当前
  设备撤销和稳定恢复集中在唯一身份边界；Session Token 在普通恢复中保持稳定，
  CSRF 由 Token 确定性派生，恢复 Cookie 使用数据库剩余寿命；每个浏览器拥有独立
  Demo User、消息 Session 与 Web Session，Demo 和真实数据分别进入独立数据库及
  私有存储。

## 下一步

由主控在本分支复验截图 Compose 等价运行、收藏补充/候选确认、语义证据、组合输入、
Retry、计划入口、完整离线闭环、封网和净复杂度。主控明确验收并重新关闭 M1-Gate
之前，不得创建 M2 分支或开始 ClawBot；M2-0 保持未开始且阻塞。

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

#### 2026-07-23｜M0-5A PlanConstraints｜已完成（主控验收）

- 提交与集成：阶段功能提交 `2fb9e53ceee3e35bc22728fa0778738c351fc4d2`，最终安全边界收敛提交 `67982c6558b44d7b8d72951c291a348e6a5496a0`；提交链直接包含 `main`/`origin/main` 基线 `eb8e1a7ab83a0c784508943020db06fb6aea9b44`。主控确认工作区干净后以 `--ff-only` 无冲突快进，合并后 tree 与精确待验收提交完全一致，没有额外代码变化。
- 功能与边界结论：唯一 `PlanConstraints`/`PlanConstraintInput` 覆盖显式深圳、时间与活动范围、可空预算、pace、交通、include/exclude、`collection_only` 和临时有效期；缺失项固定先时间、后范围。原生 Pydantic 业务校验保持一份，不可信 Python/JSON 只通过共享安全解析边界进入；失败只公开固定 `INVALID_PLAN_CONSTRAINTS`，不带输入、底层校验细节或异常链。
- 简洁性复核：最终修复删除 `_RedactingSchemaValidator`、Pydantic 内部属性替换、错误消息/位置白名单、`ValidationError` 重建和 Python/JSON schema 分叉；相对上一问题提交净减少代码，没有为测试追加业务特例。PlanConstraints、安全错误映射、AgentRunner、ToolRegistry、MapProvider、ModelProvider、Collection Repository 与 PlaceTarget 均保持唯一，无重复校验算法或第二套规划入口。
- 独立环境：主控从精确 `67982c6` 使用 `git archive` 建立仓库外副本和全新 Python 3.13.5 虚拟环境，重新安装 `backend[dev]`。`pip check`、Ruff、strict mypy 均退出 0，mypy 检查 87 个源文件；Alembic 仍为唯一 `20260722_0006 (head)`。
- 自动化结果：M0-5A 聚焦 `57 passed`；Core `118 passed`；迁移 `21 passed`；非真实全集 `1318 passed / 2 deselected`；默认全集 `1318 passed / 2 skipped`；封锁 socket connect/connect_ex/create_connection 与 DNS 后非真实全集再次 `1318 passed / 2 deselected`，全部退出 0。
- 独立安全探针：仓库外脚本验证合法 Python/JSON、重复解析不修改输入、连续两次重建 `PlanConstraints` 和 `PlanConstraintInput` 后安全入口仍有效，以及非法 Python、畸形 JSON、非法 UTF-8、异常 `str/repr/args/vars/to_dict`、标准 traceback 日志和 cause/context 均不泄露私人哨兵或底层 Pydantic 信息。
- 合并后检查：在 `main` 使用项目 `.venv` 再次执行 Ruff、strict mypy、M0-5A 聚焦和非真实全集，分别为退出 0、退出 0、`57 passed`、`1318 passed / 2 deselected`。没有未关闭 P0/P1。
- 范围、安全与下一步：未新增迁移、ORM、Repository、API、Provider、依赖、配置、前端或 M0-5B/C/D 功能；Git 不含 `.env`、数据库、缓存、虚拟环境或响应快照。未读取、打印或修改本机 `.env`，真实模型、高德、路线、天气、网页、对象存储、消息及任何外部/付费 API 调用均为 0。M0-5A 已完成，M0-5B 前置条件满足且是下一唯一允许阶段，M0-5C/D 保持未开始。

#### 2026-07-23｜M0-5B 结构化检索和规则｜待主控验收

- 分支与基线：`codex/m0-5-planning` 按任务要求从干净工作区切换，经 `git merge --ff-only main` 快进到精确基线 `78f2ae65de09d13a22e7d4cef4bbcee6b3734ab7`；开始时 `main` 与 `origin/main` 均精确等于该 SHA，M0-5A 已完成且 M0-5B 是唯一允许阶段。未 reset、rebase、amend、合并或拣选其他分支
- 唯一入口与规则：新增唯一 `StructuredCollectionRetrievalService`，显式 `user_id` 调用既有 `CollectionRepository.list_collection_items(include_inactive=True)`，复用 M0-5A `PlanConstraints`、既有 `PlaceTarget`、`PlaceMatchingService` 与 `MapProvider`。规则集中判断 active/删除/待选择/待补充、正式城市、位置、Place/Event、Event 时间、行政区、活动范围、标签/关键词、include/exclude、预算、路线、天气与营业；硬冲突直接排除，未知和离线失败进入待核验，预算为 null 不过滤已知价格，未知价格保持 `None` 与 `PRICE_UNKNOWN`
- 正式城市与动态事实：精确 Place 的正式城市只来自已确认 POI；Event 通过请求级 `CollectionPlanningFacts.formal_city: CityScope` 携带已核验正式城市和位置状态；`city_hint` 不参与计划资格。冻结的 `PlanningFactSnapshot` 为路线、天气、营业和 Event 位置提供供应商无关事实，缺失默认 unknown，不读取环境或调用外部服务
- 任意分店与去重：`any_branch` 只在本次请求按 `PlanConstraints.city_scope`、单一行政区、敏感 origin 和路线事实调用既有地点匹配入口；不创建分店收藏、不改绑品牌收藏、不写数据库。无候选、证据不足、Provider 失败和没有满足已知硬约束的分店均有稳定原因。品牌与精确收藏解析到同一 `provider + poi_id` 时合并为一个候选，保留全部来源收藏 ID 和任意分店来源 ID
- 结果与安全：公开结果只有 `included / excluded / verification_required` 三种结论；原因码按固定枚举顺序输出并映射固定安全摘要。Repository 异常和防御性跨用户返回统一映射为无 cause/context 的 `COLLECTION_RETRIEVAL_FAILED`；结果不包含精确 origin、密钥、完整 Provider 响应或其他用户数据。输入契约、事实快照、Repository 返回和原收藏均不被修改，重复调用结果一致
- 主要文件：`backend/app/domain/plans/retrieval.py`、`backend/app/application/structured_collection_retrieval.py`、既有 `place_matching.py` 的请求级范围扩展、`backend/tests/application/test_structured_collection_retrieval.py`、`README.md`、`docs/DEV_STATUS.md`。另增加 `backend/tests/__init__.py`，防止第三方顶层 `tests` 包遮蔽 Core 测试；不改变产品行为
- 测试环境与结果：macOS、项目 `.venv`、Python 3.13.5；所有 pytest 使用 `APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0`。editable 安装、`pip check`、Ruff、strict mypy（89 个源文件）均退出 0；M0-5A `57 passed`、M0-5B 聚焦 `24 passed`、Core `118 passed`、迁移 `21 passed`、非真实全集 `1342 passed / 2 deselected`、默认全集 `1342 passed / 2 skipped`，全部退出 0 且无 warning
- 覆盖范围：当前/其他用户隔离、深圳/其他城市/城市待确认与 city_hint、active/inactive/deleted/pending 状态、Place/有效与结束 Event、时间边界、district/area/origin、标签/关键词/include/exclude、预算 null/超限/未知、路线可达/不可达/未知/离线失败、天气适配/冲突/未知/失败、营业可用/冲突/未知、任意分店成功/空结果/证据不足/Provider 失败/无硬约束候选、同 POI 去重、输入与数据库不变、重复调用确定性、网络封锁和安全错误
- 迁移、依赖与范围：未新增或修改 ORM、表、迁移、依赖、配置、API、前端、SSE、Worker、队列、AgentRunner、ToolRegistry、Collection Repository、PlaceTarget、MapProvider 或地点匹配算法；Alembic 唯一 head 保持 `20260722_0006`。没有 Plan、PlanItem、草案、主/备方案、时间组合、交通缓冲、结束留白、外部高德补充、Approval、Prompt、Tool Calling、向量/Embedding、自动重试/退避/断路器或 M0-5C/D 代码
- 真实调用与风险：未读取、打印或修改本机 `.env`；真实模型、高德、路线、天气、网页、DNS、对象存储、消息及其他外部/付费 API 调用均为 0。当前验证限于 SQLite、Fake/Stub/Fixture 和请求级动态事实；真实路线/天气事实采集与完整 Provider 延迟不属于本阶段且未验证
- 主控复测重点：确认 Event 正式城市来自显式已核验事实而非 city_hint；所有 included 候选已知硬约束均满足；unknown 不会变成 included；任意分店只做请求级解析且同 POI 来源合并；Repository 实际只读且用户隔离；稳定原因/摘要无敏感泄漏；净复杂度没有第二套规则或测试特例。验收前 M0-5B 保持待验收，M0-5C/D 未开始，不合并 main、不推送

#### 2026-07-23｜M0-5B 主控验收 3 个 P1 边界修复｜待主控复验

- 分支与提交关系：修复直接追加在 `codex/m0-5-planning` 的待修复提交 `6aa7aec1f7228cb6ff2d1b78580f3fb505dfbe39` 上，不 amend、不 rebase、不 reset；开始门禁确认当前分支、HEAD 和干净工作区精确符合任务要求，`main` 与 `origin/main` 均为基线 `78f2ae65de09d13a22e7d4cef4bbcee6b3734ab7`，未合并 main
- 三个根因：唯一 `retrieve()` 未执行临时约束有效期门禁；路线只用整个计划时长判断，未把 Event 结束时间纳入候选到达期限；`_branch_candidate()` 将品牌收藏残留的旧分店 district/address/business_district/landmark/metro_station 等字段复制为新分店匹配证据，导致本次计划范围内的有效分店被旧行政区硬冲突排除
- 有效期统一修复：`retrieve()` 现在强制显式接收确定性 aware `now`，入口第一步复用 `PlanConstraints.is_active()`；`expires_at` 前一微秒仍有效，到达或超过 `expires_at` 固定返回 `PLAN_CONSTRAINTS_EXPIRED`，非法时间固定返回 `INVALID_RETRIEVAL_TIME`。两者复用既有唯一 `StructuredCollectionRetrievalError` 安全边界，无原约束、origin、底层异常或 cause/context，并在 Repository、PlaceMatchingService 和 MapProvider 前零 I/O 停止；Repository/MapProvider 的原始 `CancelledError` 对象继续透传
- 路线期限统一修复：删除原先 `route_duration >= constraints.duration` 的单一计划窗口比较，改为一个纯到达期限函数；Place 的排他期限仍为计划结束，Event 为计划结束与 Event 结束中的较早者。从计划开始出发的到达时刻必须严格早于期限，等于或晚于 Event 结束均直接 `ROUTE_EXCEEDS_TIME_WINDOW`；没有加入访问时长、缓冲、多地点组合或 M0-5C 排序
- 任意分店统一修复：`_branch_candidate()` 只从已确认 `BrandIdentity.display_name` 构造品牌身份，删除旧分店位置、价格、标签和描述字段复制；搜索城市、district 和 origin 只通过既有 `search_district/search_location` 从本次 PlanConstraints 传入。普通 exact 匹配与行政区硬冲突规则未放宽，解析后仍走同一份城市、范围、路线、天气、营业和预算规则；原收藏不清空、不改绑、不写回，同 POI 去重和来源关系不变
- 测试与验证：macOS、项目 `.venv`、Python 3.13.5，全部 pytest 显式设置 `APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0`。editable 安装、`pip check`、Ruff、strict mypy（89 个源文件）均退出 0；M0-5B 聚焦 `38 passed`，指定 PlanConstraints/地点匹配/MapProvider/PlaceTarget 相关回归 `204 passed`，Core `118 passed`，迁移 `21 passed`，非真实全集 `1356 passed / 2 deselected`，默认全集 `1356 passed / 2 skipped`，均退出 0
- 迁移、依赖与净复杂度：未新增迁移、ORM、依赖、配置、API、前端、Worker、队列、重试或外部调用；Alembic 唯一 head 仍为 `20260722_0006`。生产代码只增加一个入口门禁和两个小型纯路线函数，并删除旧分店字段复制及被替代的路线判断；一个 retrieve、一个安全错误边界、一份候选规则、一个路线期限、一个 any_branch 输入构造、一个 PlaceMatchingService 和一个 MapProvider 的结构保持不变
- 范围与主控复测：M0-5B 继续保持待主控验收，M0-5C/D 未开始；真实模型、高德、路线、天气、网页、DNS、消息及其他外部/付费 API 调用均为 0。主控重点复测 `expires_at` 排他边界和零 I/O、取消对象透传、Event 到达等号边界、旧南山线索到本次福田分店解析、exact 行政区冲突、解析后动态硬规则及 exact/any_branch 同 POI 去重；本分支不合并、不推送

#### 2026-07-23｜M0-5B 生产默认匹配策略 P1 修复｜待主控复验

- 分支与门禁：修复直接追加在 `codex/m0-5-planning` 的提交 `7cb33b8c1afd5a0f846fc3e2e0f7d92ea354a290` 上；开始时 HEAD 精确一致、工作区干净，`main` 与 `origin/main` 均为基线 `78f2ae65de09d13a22e7d4cef4bbcee6b3734ab7` 且该基线是当前提交祖先。未 amend、rebase、reset、合并或推送
- 根因与收敛修复：测试帮助函数原先手写 `30/5/20` 宽松阈值，掩盖生产默认 `75/12/35` 下品牌候选分数 35 会形成 `NEEDS_CONTEXT + candidates` 的路径；检索层又把所有 `NEEDS_CONTEXT` 提前判为证据不足。现删除该过宽状态早退：`NOT_FOUND` 仍独立失败，只有 `PlaceMatchResult.candidates` 为空才返回 `BRANCH_EVIDENCE_INSUFFICIENT`，非空候选不论 `MATCHED/AMBIGUOUS/NEEDS_CONTEXT` 均继续进入既有动态事实、硬约束和确定性路线排序。未改阈值、分数、PlaceMatchingService、匹配算法或 DTO
- 旧分店线索：any_branch 的可检索值现在按既有 `PlaceTarget.scope` 天然排除收藏残留 district/address/business_district/landmark/metro_station；unresolved 结果不再把旧 district 作为本次行政区事实，因此不会错误产生 `DISTRICT_MISMATCH` 或由旧地址触发明确排除。exact 目标仍沿用原位置证据和行政区硬冲突；原收藏、输入和 Provider 结果均不修改
- 测试策略与覆盖：M0-5B `_service()` 统一改用 `Settings(_env_file=None, app_env="test").place_matching_policy()`，并显式锁定生产默认 `75/12/35`，不再手写宽松阈值。聚焦 `41 passed`，覆盖单个 `NEEDS_CONTEXT + candidates` 有效分店纳入、空 candidates 证据不足、多候选按路线选择、旧行政区不限制新分店、unresolved 不产生旧位置冲突、exact 行政区冲突、解析后路线/天气/营业/预算、重复调用与输入不变、Provider fail-closed 及同 POI 去重
- 验证结果：Python 3.13.5；`pip check`、Ruff、strict mypy（89 个源文件）均退出 0；指定相关回归 `204 passed`、Core `118 passed`、正式迁移入口 `tests/integration/test_migrations.py` 为 `21 passed`。任务清单中的 `tests/migrations` 路径在仓库不存在，原样命令退出 4 且无测试被收集，未为修正命令制造重复测试目录；任务给出的 `not real_provider and not real_map` 因仓库 marker 实名为 `real_map_provider` 得到 `1359 passed / 1 skipped / 1 deselected`，随后使用正式排除表达式得到 `1359 passed / 2 deselected`，全部实际执行测试均离线
- 范围与冗余：未修改 `app/config.py` 默认阈值，未新增匹配、评分、分店 Repository/DTO/Provider、迁移、依赖、API、M0-5C/D 或重试逻辑；Alembic head 保持 `20260722_0006`。生产改动只删除一个过宽早退并收敛 any_branch 旧位置读取，唯一 `StructuredCollectionRetrievalService`、`PlaceMatchingService`、`score_place_candidate`、`classify_place_matches` 和 `MapProvider` 保持不变。真实或付费 API 调用为 0，M0-5B 继续待主控验收且尚未集成

#### 2026-07-23｜M0-5B 结构化检索和规则｜已完成（主控验收）

- 提交与集成：阶段提交 `6aa7aec1f7228cb6ff2d1b78580f3fb505dfbe39`、边界修复 `7cb33b8c1afd5a0f846fc3e2e0f7d92ea354a290`、默认生产策略修复 `4013fc8dc8e0583528d14211afd3ed50ec8e7a0b` 均直接建立在约定链上并包含已验收基线 `78f2ae65de09d13a22e7d4cef4bbcee6b3734ab7`。主控以 `--ff-only` 将阶段分支快进集成到 `main`，无冲突、无额外代码变化，合并前后 tree 完全一致。
- 独立验收环境：对精确 `4013fc8` 使用 `git archive` 建立仓库外副本和全新 Python 3.13.5 虚拟环境，重新安装 `backend[dev]`；`pip check`、Ruff、strict mypy 均退出 0，mypy 检查 89 个源文件，Alembic 保持唯一 `20260722_0006 (head)`。
- 自动化结果：M0-5B 聚焦 `41 passed`；指定 PlanConstraints、地点匹配、MapProvider 与 PlaceTarget 相关回归 `204 passed`；Core `118 passed`；迁移 `21 passed`；非真实全集 `1359 passed / 2 deselected`；默认全集 `1359 passed / 2 skipped`；封锁 socket connect/connect_ex/create_connection 与 DNS 后非真实全集再次 `1359 passed / 2 deselected`，全部退出 0。
- 缺陷关闭：临时约束过期门禁、Event 到达期限、旧分店位置污染和生产默认 `75/12/35` 策略下的单个 `NEEDS_CONTEXT + candidates` 路径均已复验关闭。独立探针确认品牌名称分数为默认候选阈值 35 时，会复用现有候选进入动态硬约束并解析到具体分店；空候选仍返回证据不足，旧收藏位置不产生错误行政区或用户排除原因。
- 异常、边界、幂等与安全：覆盖过期和非法 `now` 的零 I/O、Repository/Provider 失败、取消透传、Event 等号边界、其他城市/城市待确认、待选择/待补充、预算 null/未知/超限、路线/天气/营业未知和冲突、任意分店无结果/证据不足/硬约束失败、exact/any_branch 同 POI 去重、跨用户隔离、输入不变及重复调用确定性。公开结果和错误不包含精确 origin、密钥、完整 Provider 响应或底层异常。
- 范围与冗余：没有 Plan、PlanItem、草案、主/备方案、外部高德补充、Approval、迁移、依赖、API、前端、SSE、Worker、自动重试或 M0-5C/D 代码；`StructuredCollectionRetrievalService`、`PlaceMatchingService`、地点评分/分类、MapProvider、CollectionRepository、AgentRunner 和 ToolRegistry 均保持唯一，没有为测试增加平行规则或重复公共模块。
- 合并后检查：在 `main` 再次执行 Ruff、strict mypy 和正式非真实全集，结果分别为退出 0、89 个源文件无问题、`1359 passed / 2 deselected`。没有未关闭 P0/P1；本轮未读取或打印 `.env`，真实模型、高德、路线、天气、网页、对象存储、消息及其他真实/付费 API 调用均为 0。
- 已知边界与下一步：当前验证限于 macOS、Python 3.13.5、SQLite、Fake/Stub/固定事实，未验证真实路线/天气延迟和 PostgreSQL；这些留待既定后续阶段，不阻塞 M0-5B。M0-5C 前置条件已满足，是下一唯一允许阶段；从本记录提交后的最新 `main` 开始，只实现草案生成与确定性复核，M0-5D 继续未开始。

#### 2026-07-23｜M0-5C 确定性计划草案｜待主控验收

- 分支与门禁：`codex/m0-5-planning`；开始时工作区干净，`main`、`origin/main` 与原 `HEAD` 均精确等于指定基线 `952c94bdf0a7d9b4465e30d85f1b7c74d78e5ff9`，阶段分支经 `git merge --ff-only main` 快进到同一提交。M0-5B 已完成，M0-5C 是唯一允许阶段；Alembic 为唯一 `20260722_0006 (head)`。未 amend、rebase、reset、合并或推送
- 唯一契约与入口：在 `app/domain/plans/drafts.py` 增加最小冻结草案与显式事实契约；唯一 `PlanDraftService` 同时负责生成和生成后复核，直接消费 M0-5A `PlanConstraints` 与 M0-5B `StructuredCollectionResult.included`。`PlanDraftFactSnapshot` 只接受供应商无关的访问时长、Event 时间、POI 查询时间及出发点/地点间路线事实，不创建 Provider、规则引擎、Repository 或第二套检索
- 生成行为：确定性生成一个主方案和最多两个备选，每个方案最多一个核心地点与一个辅助地点；pace 分别映射为 10/15/20 分钟切换缓冲与 15/20/30 分钟结束留白。短窗口或缺少地点间路线时只生成合法单地点方案；缺少候选访问时长、首段路线、Event 固定时间、任意分店查询时间，或无法形成任何可执行组合时不猜测并返回稳定不可生成原因
- 时间、路线与预算：所有 PlanItem 位于 PlanConstraints 窗口内，Event 访问必须完整位于明确活动时间内，首段和地点间路线方式必须属于本次允许方式。已知费用以 Decimal/CNY 求和且不超过预算；费用未知保持 `None` 和 `PRICE_UNKNOWN` 风险，不伪造为 0；已知预算下费用无法证明合规的组合不生成。排序使用首段路线时长、规范化标题、POI 身份和收藏 ID 稳定破同分，不依赖输入顺序或哈希种子
- 来源与任意分店：每项展示访问时间、入站路线/距离/方式、单项和总费用、收藏来源、风险和稳定选择理由。任意分店保存本次具体 POI、全部来源 CollectionItem ID、品牌级来源 ID 和查询时间，固定标记为 `collection_derived`；不改绑收藏、不写数据库、不标为外部补充。M0-5B 已合并的 exact/any_branch 同 POI 来源只生成一个 PlanItem
- 生成后复核：`validate()` 重新核对方案/角色数量、来源必须属于 included、候选和访问事实、路线与 M0-5B 首段事实、交通方式、时间/Event 边界、切换缓冲、结束留白、费用/预算、风险、任意分店快照和同方案 POI 唯一性。生成入口强制调用该复核；篡改时间、费用、来源或事实会返回稳定违反码
- 测试与 Fixture：新增 M0-5C 聚焦 `40 passed`，覆盖无 included、单/多候选、主/备数量、每方案地点上限、短窗口、10/20 与 15/30 分钟等号边界、Event 到达边界、budget null/已知、超预算组合、未知费用、excluded/verification 排除、任意分店快照与来源标记、同 POI 单项、稳定同分顺序、输入不变、幂等、缺时长/路线降级、非法交通方式和篡改校验。`tests/fixtures/plans.py` 明确提供 20 组计划 Fixture，全部生成后再次校验为 0 条硬约束违反
- 当前验证：macOS、项目受忽略 `.venv`、Python 3.13.5；editable 安装和 `pip check` 通过，Ruff 通过，strict mypy 对 91 个源文件无问题。M0-5A `57 passed`、M0-5B `41 passed`、M0-5C `40 passed`、Core `118 passed`、迁移 `21 passed`；正式非真实全集 `1399 passed / 2 deselected`，默认全集 `1399 passed / 2 skipped`，封锁 socket connect/connect_ex/create_connection 与 DNS 后非真实全集再次 `1399 passed / 2 deselected`，全部退出 0
- 测试环境提示：两次非真实全集在全部 1399 项通过后各报告 1 条既有 aiosqlite worker 于事件循环关闭后的 `PytestUnhandledThreadExceptionWarning`，落点均为 M0-5B 测试但不稳定对应具体用例；M0-5B 单独 41 项、迁移 21 项和默认全集均无 warning。本阶段不修改数据库生命周期或既有检索测试以掩盖环境级竞态，主控应在隔离新环境复核是否复现
- 迁移、依赖与外部调用：没有新增依赖、环境变量、ORM、数据库表、Plan/PlanItem Repository 或 Alembic revision；未修改历史 `0001`–`0006`，head 保持 `20260722_0006`。所有测试显式设置 `APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0`，未读取、打印或修改 `.env`；真实模型、高德、路线、天气、网页、DNS、对象存储、消息及其他真实/付费 API 调用均为 0
- 范围、冗余与安全：未修改 `nanobot_core`、AgentRunner、ToolRegistry、Provider、Collection Repository、M0-5B 检索/去重或地点匹配；没有 M0-5D 外部地点补充、Approval、Prompt、Tool Calling、API、SSE、Worker、队列、前端、正式确认/调整、日历、提醒、分享或反馈。PlanDraftService、草案契约和事实快照各只有一份正式实现，没有为测试复制生产算法，当前无已知未关闭 P0/P1
- 已知风险与主控复测：当前仅验证 macOS/Python 3.13.5、不可变内存契约和固定离线事实，未验证 Python 3.11/3.12、Windows、PostgreSQL 或真实路线/天气数据采集；后者不在本阶段授权范围。主控应重点复测 Event 到达起止等号、两类缓冲最小/最大与结束等号、已知预算加总、未知费用、缺少地点间路线的单地点降级、任意分店具体 POI/查询时间/来源标记、篡改校验、20 组 Fixture、输入隔离、重复调用、禁网、迁移 head、唯一实现和上述 aiosqlite warning
- 下一步：等待主控独立验收；M0-5C 保持待验收，M0-5D 保持未开始。本分支不合并 `main`、不推送、不执行任何真实或付费调用

#### 2026-07-23｜M0-5C 主控验收未知价格 P1 修复｜已由下一条价格契约修复收敛

- 分支与门禁：修复直接追加在 `codex/m0-5-planning` 的待修复提交 `9afb408d178eea6a39c9299460fe66ceb28eedc2` 上；开始时工作区干净、分支和 HEAD 精确一致，`main` 与 `origin/main` 均为指定基线 `952c94bdf0a7d9b4465e30d85f1b7c74d78e5ff9` 且是当前提交祖先。未 amend、rebase、reset、合并或推送
- 根因与唯一价格门禁：M0-5B 的 `_candidate_decision()` 原先在预算判断前无条件把金额或币种缺失标为 `PRICE_UNKNOWN`，使候选进入 `verification_required`，导致只消费 `StructuredCollectionResult.included` 的 M0-5C 无法触达既有价格风险。现将价格可比较性检查收敛到 `constraints.budget is not None` 分支：无预算时不因缺金额、缺币种或非 CNY 过滤；有预算时这些事实仍为 `PRICE_UNKNOWN/verification_required`，已知 CNY 超预算仍为 `BUDGET_EXCEEDED/excluded`
- 当时的草案兼容（已撤销）：该提交让候选决策和 PlanItem 携带半完整金额/币种，并让缺金额、缺币种和非 CNY 统一输出 `PRICE_UNKNOWN`；这部分不符合正式领域契约，已由下一条人民币价格契约修复删除。`PlanDraftService` 始终只消费 `included`，从未读取或放宽 `verification_required`
- 跨阶段自动化：在真实 `StructuredCollectionRetrievalService → StructuredCollectionResult → PlanDraftService` 链路增加参数化测试，覆盖完整未知、缺金额、缺币种、非 CNY 四种价格事实；逐项证明无预算时 M0-5B included、M0-5C generated 且总费用未知并带风险，有预算时保持 verification_required 且不进入草案。另覆盖无预算的已知 500 CNY 不排除、已知 CNY 超预算继续排除、输入不变以及检索和草案重复调用结果一致
- 验证环境与结果：macOS、项目受忽略 `.venv`、Python 3.13.5；editable 安装和 `pip check` 退出 0，Ruff 退出 0，strict mypy 对 91 个源文件无问题。M0-5B 聚焦 `45 passed`，M0-5C 聚焦 `40 passed`，迁移 `21 passed`；正式非真实全集 `1403 passed / 2 deselected`，默认全集 `1403 passed / 2 skipped`，全部退出 0。临时 QA 插件同时封锁 socket connect/connect_ex/create_connection 和 DNS 后，非真实全集再次 `1403 passed / 2 deselected`
- 既有环境提示：部分非真实、默认和封网全量运行在所有测试通过后报告 1 条既有 aiosqlite worker 于事件循环关闭后的 `PytestUnhandledThreadExceptionWarning`，落点在不同 M0-5B 用例，和前次 M0-5C 交接记录一致；最终默认全集复跑以及 M0-5B/M0-5C 聚焦、迁移测试均无 warning。本修复没有修改数据库生命周期或增加静默 skip
- 迁移、范围与冗余：Alembic 仍只有 `20260722_0006 (head)`；未新增或修改迁移、ORM、Repository、依赖、配置、API、前端、Provider、重试、M0-5D 或后续能力。生产变化只有一个既有价格门禁、两个不可变传递契约和一个被生成/复核共用的风险函数；`StructuredCollectionRetrievalService`、`PlanDraftService`、价格判断和风险映射各保持唯一，没有第二套过滤、测试专用生产分支或白名单
- 安全与下一步：Git 未包含 `.env`、密钥、数据库、缓存或虚拟环境；未读取本机 `.env`，真实模型、高德、路线、天气、网页、DNS、消息及其他外部/付费 API 调用均为 0。M0-5C 继续保持待主控复验，M0-5D 保持未开始；主控重点复测四种未知价格形态的预算有/无分支、原始字段保留、总费用 `None`、`PRICE_UNKNOWN` 风险、已知超预算、输入不变、重复调用、禁网和唯一实现

#### 2026-07-23｜M0-5C 人民币价格契约修复｜待主控复验

- 分支与门禁：修复直接追加在 `codex/m0-5-planning` 的提交 `7606f977db577db5160f7837ff1544739b7bd18a` 上；开始时工作区干净、分支和 HEAD 精确一致，`main` 与 `origin/main` 均为指定阶段基线 `952c94bdf0a7d9b4465e30d85f1b7c74d78e5ff9` 且是当前提交祖先。未 amend、rebase、reset、合并或推送
- 产品语义与契约收敛：当前产品只支持中国场景和人民币，用户无需输入或选择币种。正式金额只允许 `None + None`（未知）或 `Decimal + CNY`（已知）两种状态；`Decimal + None`、`None + CNY` 和非 CNY 均由同一领域校验拒绝。数据库 `price_currency` 字段继续保留为内部金额单位，不代表多币种功能；本阶段没有汇率换算、Currency Repository、汇率 Provider、币种选择或外币支持
- 唯一人民币默认入口：文字、URL 正文和图片继续复用既有 `parse_extraction_response()` 共享抽取边界；只有当模型已明确输出 `price_amount` 且缺少 `price_currency` 时，进入严格候选契约前统一补为 `CNY`。共享规则不会扫描原文数字或建立第二套价格解析器；明确免费可表示为 `Decimal("0") + CNY`，无法确认价格时保持 `None + None` 和既有 PRICE 不确定性。文字与图片 Prompt 复用同一人民币规则片段
- 收藏修改：既有唯一 `CollectionWriteService.patch()` 流程继续使用 `CollectionItemPatch`；只提交 `price_amount` 时自动配对 `CNY`，显式清空金额时同步清空币种。CollectionItem、数据库写入模型、M0-5B 候选决策、PlanItem 和方案总费用均未放宽为半完整价格
- 删除的错误兼容：撤销上一修复为生产数据无法产生的缺金额、缺币种和非 CNY 状态所增加的草案兼容分支，恢复 CollectionCandidateDecision、PlanItem 和 PlanOption 的严格金额/币种不变量；删除跨阶段测试中通过 `model_copy` 制造 `None + CNY`、`Decimal + None` 和非 CNY 候选的用例。M0-5B 不再需要判断半完整币种：有预算时仅完整未知价格进入 `PRICE_UNKNOWN/verification_required`，已知 CNY 超预算仍排除；无预算的 `None + None` 仍 included，M0-5C 仍生成总费用 `None` 且展示 `PRICE_UNKNOWN`
- 自动化覆盖：抽取契约、文字、图片和收藏写入聚焦 `144 passed`；M0-5B→M0-5C 应用链路 `85 passed`；收藏写入集成 `17 passed`。覆盖已识别“人均 50”式金额和免费补 CNY、不相关数字不猜价格、未知价格、两种半完整状态与外币拒绝、金额单字段修改、清空价格、预算有/无、已知加总和超预算、输入不变及重复调用一致
- 完整验证：Python 3.13.5；`pip check`、Ruff 和 strict mypy（91 个源文件）均退出 0。正式非真实全集 `1409 passed / 2 deselected`，默认全集 `1409 passed / 2 skipped`，全部退出 0。非真实全集出现 1 条既有 aiosqlite worker 在事件循环关闭后的 warning，默认全集、聚焦测试和写入集成均无 warning；本轮未修改数据库生命周期
- 迁移、范围与复杂度：Alembic 唯一 head 仍为 `20260722_0006`，未新增或修改迁移、ORM、Repository、依赖、配置、API、前端、Provider、重试、M0-5D 或后续能力。一个共享抽取入口、一个人民币默认函数、一个正式成对校验、一个收藏修改入口和一个 PlanDraftService 保持唯一；本轮以删除半完整兼容判断为主，没有为测试新增生产特例、白名单或平行价格规则
- 安全与下一步：未读取本机 `.env`，未启用真实 marker；真实模型、高德、路线、天气、网页、DNS、对象存储、消息及其他真实/付费 API 调用均为 0。原未知价格 P1 保持关闭，半完整价格契约已恢复严格；M0-5C 继续待主控复验，M0-5D 保持未开始。主控重点复测共享抽取补 CNY、明确免费、无关数字不推断、修改/清空价格、严格 DTO、无预算未知价格跨阶段链路、已知加总/超预算、输入隔离、幂等、迁移 head 与唯一实现

#### 2026-07-23｜M0-5C｜已完成（主控验收）

- 分支与提交：`codex/m0-5-planning`；初始阶段提交 `9afb408d178eea6a39c9299460fe66ceb28eedc2`，未知价格链修复 `7606f977db577db5160f7837ff1544739b7bd18a`，最终人民币契约修复 `5dce2de73ae0e0e09324440bb8d7fe7af531416a`。主控确认该 HEAD 精确包含基线 `952c94bdf0a7d9b4465e30d85f1b7c74d78e5ff9`，并以 `--ff-only` 快进集成到 `main`，无冲突、无额外代码变化
- 验收结论：唯一 `PlanDraftService` 在 M0-5A/M0-5B 已验收契约上确定性生成一个主方案和最多两个备选，每个方案最多一个核心地点加一个辅助地点，并在生成后复核时间、Event、路线、交通方式、缓冲、结束留白、预算、费用、来源、风险、任意分店快照和重复 POI。20 组固定 Fixture 的硬约束违反数为 0
- 人民币契约：当前中国场景只允许 `None + None`（未知）或 `Decimal + CNY`（已知）；用户无需输入或选择币种。文字、URL 正文和图片复用唯一 `parse_extraction_response()`，只为模型已识别但缺币种的本地金额补 `CNY`；不会扫描原文数字。金额单字段修改同步使用 CNY，清空金额同步清空币种；半完整价格和非 CNY 在共享领域边界拒绝
- 隔离验证：从最终提交 `5dce2de` 创建 `git archive`，在全新 Python 3.13.5 虚拟环境安装 `backend[dev]`。`pip check`、Ruff、strict mypy（91 个源文件）和 Alembic 唯一 head `20260722_0006` 均通过；价格抽取/写入 `144 passed`，M0-5B→M0-5C 链路 `85 passed`，写入集成 `17 passed`，Core/迁移 `139 passed`，M0-5C 单独 `43 passed`
- 全量与独立复核：非真实全集 `1409 passed / 1 skipped / 1 deselected`，默认全集 `1409 passed / 2 skipped`；封锁 DNS、socket connect/connect_ex 和 create_connection 后非真实全集仍为 `1409 passed / 1 skipped / 1 deselected`。`-W error::pytest.PytestUnhandledThreadExceptionWarning` 全量复跑 `1409 passed / 2 skipped`。`/tmp` 独立探针验证金额缺币种补 CNY、金额修改/清空、半完整/外币拒绝及重复解析一致
- 合并后复核：最终代码树未变化；`main` 上 Ruff、strict mypy、规划链 `85 passed`、价格与写入链 `161 passed`，非真实全集 `1409 passed / 1 skipped / 1 deselected`，全部退出 0。一次默认全量运行出现交接中已有的非稳定 aiosqlite 线程收尾 warning，目标用例、所属测试文件和全量 `-W error` 复跑均未复现；本阶段未改数据库生命周期，该提示不构成 M0-5C 缺陷
- 范围、冗余与安全：没有第二套 AgentRunner、ToolRegistry、Provider、Repository、检索、草案服务、价格解析器或价格校验；人民币默认和成对校验各只有一个共享实现。未新增迁移、依赖、配置、API、前端、持久化 Plan、Approval、M0-5D 外部补充或后续能力；Git 未包含 `.env`、缓存、虚拟环境、数据库、响应快照或真实密钥
- 外部调用与风险：未读取或打印本机 `.env`，真实模型、高德、路线、天气、网页、对象存储、消息及其他外部/付费 API 调用均为 0。当前没有未关闭 P0/P1；已知跨测试事件循环收尾 warning 保留为低风险测试基础设施观察项，不影响本次确定性业务结论
- 下一步：M0-5C 已完成；当前允许从最新 `main` 开始 M0-5D。M0-5D 必须复用既有 MapProvider、StructuredCollectionRetrievalService、PlanDraftService 和业务审批契约，只验证收藏不足时少量只读 Place 补充、Approval 与拒绝降级，不外搜 Event，不提前实现 M0-Gate、正式确认、SSE、Worker 或前端

#### 2026-07-23｜M0-5D 收藏不足与高德补充｜待主控验收

- 分支与门禁：`codex/m0-5d-external-place-supplement`；开始时工作区干净，`HEAD`、`main`、`origin/main` 与 merge-base 均精确等于指定基线 `7f9edf3294fef0864a5e609806b7a3c2a346c0e7`。M0-5A/B/C 已完成并集成，M0-5D 未提前实现，Alembic 为唯一 `20260722_0006 (head)`；阶段提交随本记录创建，完整 SHA 见开发窗口最终交接报告
- 唯一契约与编排：新增冻结的单个 `RequiredPlanGap`、与缺口完整语义哈希绑定的 Approval requirement/decision、稳定补充结果与恢复码；唯一 `ExternalPlaceSupplementService` 直接消费 M0-5B `StructuredCollectionResult`，组合既有 `PlaceMatchingService`、唯一 `MapProvider` 和唯一 `PlanDraftService.generate()/validate()`。没有自由文本扫描、Prompt、Tool Calling、第二套检索/匹配/规划/审批状态机或可变进程缓存
- 确定性行为：无显式必要缺口且收藏草案可执行时地图调用为 0；一个明确 Place 缺口最多调用一次 `search_poi`、最多保留 3 个供应商无关候选，并最多只向主方案加入一个外部 Place。无收藏核心时未授权或授权 ID 不匹配均返回既有 `AgentRunStatus.WAITING_USER` 语义且地图调用为 0；拒绝不重发授权，只返回收藏内草案或继续添加收藏。`collection_only` 与 Event 缺口在有/无收藏时均不外搜，不因剩余时间触发补充
- 候选与草案边界：复用地点匹配证据，不把供应商第一项直接当成功；错误城市、行政区/活动范围外、显式 include/exclude 不符、重复收藏 POI、同名歧义和无结果均不能进入草案。外部项固定为 `external_place` 和“高德补充 · 未收藏”，不含 CollectionItem ID，保留具体 POI、provider/poi_id、查询时间、补充原因、已知路线与严格 CNY 费用；未知价格和营业时间显示独立风险。半完整价格与非 CNY 继续由唯一价格契约拒绝
- 单一排程与复核：`PlanDraftService` 只增加外部候选适配，收藏项与外部项最终进入同一个 `_schedule_known_item` 时间/路线/预算/缓冲排程规则；生成后同一个 `validate()` 重新构造并核对外部项，禁止来源伪装、同 POI 重复、多个方案重复补充、时间/路线/预算和风险篡改。若外部项因预算、时间或路线事实不能加入，返回稳定恢复结果，不把未满足显式缺口的收藏内草案误报为补充成功
- 离线覆盖：M0-5D 聚焦 `22 passed`，覆盖收藏充分零调用、局部必要 Place、无收藏先授权及授权后一次搜索、错误 Approval ID、拒绝幂等、collection-only、Event、最多 3 个候选、同名分店、错误城市、范围外、重复 POI、空结果、搜索 timeout/rate-limit/unavailable/invalid response、路线失败/缺失、Event 核心缺 POI 时不以私人 origin 替代后续路线、搜索与路线取消、已知/未知价格和营业风险、CNY/预算、来源防伪、输入不变、重复调用，以及实际 `StructuredCollectionRetrievalService → 外部补充 → PlanDraftService` 跨阶段链路
- 最终验证：macOS、项目受忽略 `.venv`、Python 3.13.5；editable install、`pip check`、Ruff、strict mypy（93 个源文件）均退出 0；M0-5C `43 passed`、M0-5B `42 passed`、迁移 `21 passed`。封锁 DNS、socket connect/connect_ex/create_connection 后非真实全集 `1431 passed / 1 skipped / 1 deselected`；默认全集 `1431 passed / 2 skipped`，全部退出 0
- 测试基础设施提示：封网非真实全集在全部用例通过后出现 1 条 M0-5C 已记录的非稳定 aiosqlite worker/事件循环收尾 warning；随后默认全集无 warning，对应 M0-5B 目标用例使用 `-W error::pytest.PytestUnhandledThreadExceptionWarning` 独立复跑 `1 passed`。M0-5D 未修改数据库生命周期或通过 skip 隐藏问题，当前无已知未关闭 P0/P1
- 迁移、依赖、配置与副作用：未新增或修改依赖、配置、ORM、Repository、数据库表或迁移，历史 `0001`–`0006` 未改，head 保持 `20260722_0006`；不创建 Approval/Plan/PlanItem/缓存表，不写 CollectionItem 或数据库，不实现正式确认/加入收藏。未读取、打印或修改本机 `.env`，未运行真实 marker；真实模型、高德、路线、天气、网页、对象存储、消息及其他外部/付费 API 调用均为 0
- 范围、冗余与下一步：未修改 `nanobot_core`、AgentRunner、ToolRegistry、MapProvider/StubMapProvider/AmapProvider、Collection Repository、API、SSE、Worker、队列、前端、正式计划版本/确认、日历、提醒、分享、反馈、M0-Gate 或 M1。POI DTO、地点匹配、结构检索、CNY 规则、草案排程与 Run 状态保持唯一；主控应在隔离快照复核调用次数、Approval 绑定、拒绝/Event/collection-only、候选边界、外部来源/风险、20 组 M0-5C Fixture、禁网、迁移 head 和净复杂度。验收前不合并 `main`、不推送、不开始 M0-Gate

#### 2026-07-23｜M0-5D 主控验收候选与费用修复｜待主控验收

- 分支与门禁：修复直接追加在 `codex/m0-5d-external-place-supplement` 的待修复提交 `a87bdd3838b4d03a59d8b14c0a60e73725dd7483` 上；开始时分支与 HEAD 精确一致，工作区干净，指定阶段基线 `7f9edf3294fef0864a5e609806b7a3c2a346c0e7` 是当前提交祖先。修复提交随本记录创建，完整 SHA 见开发窗口最终交接报告
- 候选选择边界：`ExternalPlaceSupplementService` 继续直接复用 `PlaceMatchingService` 的 `MatchStatus` 和原始候选顺序。`MATCHED` 只允许采用原始首选；首选通过城市、行政区、活动范围、include/exclude 与收藏去重时直接采用，不再因较弱候选存在而重新判歧义；首选被任一硬约束过滤时不自动晋升后续候选，只返回经过范围过滤的安全选择或稳定恢复结果，并保持路线调用为 0。`AMBIGUOUS/NEEDS_CONTEXT` 仍只返回最多 3 个过滤后候选
- 单地点费用：外部地点作为唯一核心时复用既有 `_option_cost()` 汇总 `PlanOption`；已知 `20 CNY` 输出 `20 + CNY`，未知价格保持 `None + None` 与 `PRICE_UNKNOWN`。有预算时继续由既有 `_schedule_external_item()`/`_schedule_known_item()` 统一排程和预算规则决定是否生成，没有新增金额、币种或预算分支
- 回归覆盖：M0-5D 聚焦由原 22 项增至 `27 passed`，新增外部单地点已知费用、预算不足、原唯一高分首选与较弱候选共存、首选因收藏去重被过滤、首选因活动范围硬约束被过滤，并强化未知费用断言；主控临时复现文件 `/tmp/test_m05d_independent_qa.py` 为 `3 passed`。既有输入不变/重复调用、Event、collection-only、拒绝和零搜索边界继续通过
- 文档：README 已将 M0-5C 的 20 组 Fixture 与其草案测试入口独立说明，并把 M0-5D 聚焦入口修正为 `tests/application/test_external_place_supplement.py`
- 完整验证：Python 3.13.5；editable install、`pip check`、Ruff、strict mypy（93 个源文件）均退出 0；M0-5D `27 passed`、M0-5C `43 passed`、M0-5B `42 passed`、迁移 `21 passed`。非真实全集 `1436 passed / 1 skipped / 1 deselected`，默认全集 `1436 passed / 2 skipped`，全部退出 0
- 已知测试提示：两轮全量测试各报告 1 条此前 M0-5C/M0-5D 已记录的非稳定 aiosqlite worker/事件循环收尾 warning，目标落点为不同的既有 M0-5B 测试且所有用例均通过；本修复未修改数据库生命周期、测试跳过或 warning 策略
- 范围与下一步：没有修改评分阈值、复制匹配/排序/价格/规划逻辑，未新增代理层、迁移、依赖、配置、API、前端或 M0-Gate 功能；未读取或修改 `.env`，未调用真实高德、模型、网页或其他外部/付费 API。M0-5D 保持待主控验收，不合并 `main`、不推送、不开始 M0-Gate

#### 2026-07-23｜M0-5D｜已完成（主控验收）

- 提交与集成：阶段实现提交 `a87bdd3838b4d03a59d8b14c0a60e73725dd7483`、候选与费用修复提交 `28b6c1a31fa39b3a1f527e1278f907adff53f2e6`；二者直接建立在指定基线 `7f9edf3294fef0864a5e609806b7a3c2a346c0e7` 上。主控确认工作区干净，`main` 与 `origin/main` 均为该基线，并以 `--ff-only` 纯快进集成到 `main`，无冲突或额外代码变化
- 缺陷关闭：外部地点匹配继续复用唯一 `PlaceMatchingService` 的状态和原始顺序；唯一首选存在较弱候选时仍使用首选，首选被收藏去重或范围硬约束过滤时不自动晋升后续候选且路线调用为 0。外部地点作为唯一核心时复用 `_option_cost()`，已知 `20 CNY` 正确进入方案总费用，预算不足继续由唯一排程规则拒绝。上一轮仓库外独立探针由 `3 failed` 变为 `3 passed`
- 隔离验证：从最终修复 commit 创建仓库外 `git archive` 和全新 Python 3.13.5 虚拟环境；editable 安装、`pip check`、Ruff、strict mypy（93 个源文件）和 Alembic 唯一 head `20260722_0006` 均通过。M0-5D `27 passed`、M0-5C `43 passed`、M0-5B `42 passed`、迁移 `21 passed`
- 全量与禁网：非真实全集 `1436 passed / 1 skipped / 1 deselected`，默认全集 `1436 passed / 2 skipped`；封锁 DNS、socket connect/connect_ex 和 create_connection 后非真实全集仍为 `1436 passed / 1 skipped / 1 deselected`。封网运行出现一次历史已记录的 aiosqlite 事件循环收尾 warning，对应测试以 warning-as-error 单独复跑 `1 passed`
- 合并后复核：纯快进后代码树与验收 commit 一致；`main` 上 Ruff、strict mypy、M0-5D `27 passed` 和非真实全集 `1436 passed / 1 skipped / 1 deselected` 再次通过。合并后全量同样只出现上述非稳定 aiosqlite 收尾 warning
- 范围、复杂度与安全：实现严格限于 M0-5D，不包含 M0-Gate、正式确认、API、前端、SSE、Worker、队列、日历、提醒、分享、反馈或 M1。AgentRunner、ToolRegistry、MapProvider、PlaceMatchingService、StructuredCollectionRetrievalService、PlanDraftService、候选范围规则和 CNY 费用规则均保持唯一；修复没有新增评分、排序、价格特例、代理或测试专用生产分支
- 迁移与真实调用：未新增依赖、配置、ORM、Repository、数据库表或迁移，Alembic 仍为 `20260722_0006 (head)`。Git 未跟踪 `.env`、数据库、缓存、虚拟环境、响应快照或真实密钥；主控未读取或修改本机 `.env`，未调用真实模型、高德、路线、天气、网页、对象存储、消息或其他外部/付费 API
- 验收结论与下一步：上一轮两个 P1 和 README P2 均已关闭，没有未关闭的 P0/P1；M0-5D 与整个 M0-5 完成标准满足。M0-Gate 前置条件已满足，允许从本次文档提交后的最新 `main` 开始总验收；真实延迟取样仍须逐类取得当次授权，Gate 通过前不得开始 M1

#### 2026-07-23｜M0-Gate 真实验收｜阻塞

- 分支与门禁：从指定基线 `0ace869ae2708608d238b77b3ade3153b1307549` 创建 `codex/m0-regression`；开始时 `HEAD`、`main`、`origin/main` 完全一致，工作区干净，M0-0A 至 M0-5D 均已集成，Alembic 唯一 head 为 `20260722_0006`，没有提前实现 M1。
- 离线结果：全新 Python 3.13.5 环境安装和 `pip check`、Ruff、93 文件 strict mypy 均通过；非真实全集 `1436 passed / 1 skipped / 1 deselected`，默认全集 `1436 passed / 2 skipped`；core `118 passed`、迁移 `21 passed`、M0-4D `19 passed`、检索 `42 passed`、计划 `43 passed`、外部补充 `27 passed`、场景聚焦组合 `362 passed`。迁移升级/降级/再升级、Alembic check、封网功能断言和 README 健康检查通过。
- 真实授权与调用：用户在本任务授权六类并取消费用上限，但要求逐类硬请求上限与零重试。实际模型请求为文字 `5/6`、结构修复 `3/3`、Tool 链 `2/2`、图片 `5/6`，共 15 次且全部返回 Provider 契约；高德 `5/5` 全部 HTTP 200；网页 `4/14`，两个普通页面成功，两个重定向目标首 hop ReadTimeout。没有重试、补样本或追加调用。
- 真实功能结论：模型 → Tool → 模型 1/1 完成并得到固定结果；高德三次搜索、详情和步行路线均成功；普通网页 2/2 成功。文字、真实结构修复和图片服务均 3/3 返回 `ExtractionResult`，但仓库外 QA 汇总脚本错误使用不存在的 `ExtractionOutcome.MODEL_INVALID`，导致具体 outcome 与候选数丢失；两个重定向样本均未进入 redirect hop。
- 延迟与 Token：文本模型观测 P50/P95/max 为 `4.362/7.214/7.257s`，结构修复 `4.217/4.803/4.869s`，Tool 单次 `1.525/1.771/1.798s`、端到端 `3.052s`，高德逻辑调用 `176/300/304ms`，普通网页 `128/178/184ms`，重定向失败样本 `13.033/15.236/15.352s`，图片模型 `3.722/5.749/6.201s`、端到端最大 `7.671s`。模型共 `31,702` 输入、`2,394` 输出、`34,096` 总 Token；单价未配置，费用未知。小样本 P95 仅为观测值。
- 风险重评：锁注册表无界增长保持 P2，但登记为 M1 开始前必须解决；aiosqlite 偶发 worker warning 保持 P2，并要求数据库生命周期变更前以 warning-as-error 跑完整及封网全集，连续复现或伴随功能/数据失败时升 P1；M0-0B 延后的最小 Dockerfile 必须在关闭 Gate 前补齐并验证。
- 阻塞与下一步：QA 汇总证据丢失和真实重定向链未建立均按验收 P1 处理，但未发现对应生产 P0/P1。当前授权明确禁止追加调用，因此本任务停止 Dockerfile、提交、合并和推送。后续只能在新的明确授权下，分别复测文字/修复/图片的脱敏 outcome，以及两个受控重定向目标；不得重复已经通过的 Tool、高德和普通网页。完整复测 Prompt 见 `docs/technical/M0_VALIDATION_REPORT.md`。

#### 2026-07-23｜M0-Gate 真实结构结果补充复测｜阻塞

- 分支与基线：先将上轮未提交的 `DEV_STATUS` 与 `M0_VALIDATION_REPORT` 原样保存为独立文档提交 `fb7929e`，再创建 `codex/m0-gate-structured-retest`。生产代码 merge-base、`main` 和本地 `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`；本任务没有修改生产业务代码
- 离线门禁：仓库外 QA 汇总器仅位于 `/tmp`，使用生产枚举 `ExtractionOutcome.MODEL_INVALID_OUTPUT`；FakeProvider 覆盖 `candidates`、`insufficient_information`、`unsupported`、`model_invalid_output` 四种 outcome，并验证脱敏字段白名单、逐类 ModelProvider 外层硬计数熔断及生产 OpenAI SDK `max_retries=0`。汇总器 Ruff、strict mypy、自测均通过；相关生产回归 `172 passed / 1 deselected`
- 授权与实际调用：用户分别授权文本 3 个原样本最多 6 次、结构修复 3 个原样本最多 3 次、图片 3 个原样本最多 6 次，全部零重试。实际为文本 `5/6`、结构修复 `3/3`、图片 `5/6`，合计 `13/15`；13 次均返回 Provider 契约，超时率和重试率均为 0。没有复测 Tool Calling、高德、普通网页或重定向网页
- outcome 与候选：9/9 样本均完整记录 outcome，原 QA 工具 P1 已关闭。文本为 `candidates` 1、`model_invalid_output` 2，候选 `[1,0,0]`；结构修复为 `model_invalid_output` 3，候选 `[0,0,0]`；图片为 `candidates` 1、`model_invalid_output` 2，候选 `[1,0,0]`。记录成功率 100%，可用结构结果率为文本 33.3%、结构修复 0%、图片 33.3%，合计 2/9（22.2%）
- 调用与生产路径：文本样本 2、3 和图片样本 2、3 触发唯一修复；结构修复类每个样本的首次非法响应都来自本地固定 Fixture，每个样本只消耗一次真实修复请求。QA 在内存中用生产 `parse_extraction_response`、Pydantic 严格校验和 `canonicalize_extraction_result` 核对；非法真实响应由生产服务稳定恢复为 `MODEL_INVALID_OUTPUT`
- 延迟：文本模型单次 P50/观测 P95/max 为 `4.071/4.555/4.571s`，端到端为 `7.711/8.927/9.062s`；结构修复单次为 `4.232/4.251/4.253s`，端到端为 `4.233/4.252/4.254s`；图片单次为 `3.955/5.516/5.717s`，端到端为 `5.725/8.379/8.674s`。每类只有 3 个端到端样本，P95 只是观测插值，不具有统计验证意义
- Token、费用与清理：文本 `10,328/832/11,160`、结构修复 `6,092/461/6,553`、图片 `14,331/683/15,014` 输入/输出/总 Token，合计 `30,751/1,976/32,727`；单价未配置，费用未知。三个图片临时对象和整个仓库外临时私有根目录均已清理，未记录图片、Base64、文件名、路径或 `file_key`
- 分类与结论：真实结构兼容性 P1，根因待安全诊断；Prompt、Schema、模型输出、解析器和配置均未排除。离线回归、生产 parse/validate/fallback 和 QA outcome 记录均通过；本任务不追加调用，不修改生产代码，不关闭 M0-Gate，不合并、不推送；结果交回 M0-Gate 主控，等待结构兼容性、重定向网页和 Dockerfile 收尾决策

#### 2026-07-23｜M0-Gate 真实结构兼容性安全诊断｜阻塞

- 分支与基线：`codex/m0-gate-structure-diagnostic` 从包含证据提交
  `27c47bbdab255f45e91bc9dab4c50b2de9599278` 的
  `codex/m0-gate-structured-retest` 创建；开始工作区干净，没有合并 `main`，
  没有生产业务代码改动
- 离线门禁：一次性 QA 工具只位于 `/tmp`，复用生产文本/图片服务、Provider 和
  parser；Ruff、strict mypy、19 项安全自测通过。生产 Ruff、93 文件 strict mypy
  通过；四组指定回归明确排除 `real_provider`，结果 `172 passed`
- 授权与调用：用户分别授权文本最多 4 次、固定结构修复最多 3 次、图片最多 4 次，
  实际为 `4/4 + 3/3 + 4/4 = 11/11`；SDK 和外层重试均为 0，没有替换或新增样本，
  没有调用 Tool Calling、高德、普通网页或重定向网页
- outcome：2 个文本、3 个固定修复和 2 个图片样本全部稳定返回
  `model_invalid_output`，候选均为 0；11/11 真实请求返回 Provider 契约，
  `finish_reason=stop`、存在 content、无 tool_calls、无 ProviderError、无超时
- 安全 issue：所有真实响应都可 JSON 解码；文本 initial/repair 重复
  `candidates.0.place/value_error` 2 次和 `candidates.1.place/value_error` 1 次；
  固定非法 Fixture initial 为 `$/json_invalid` 3 次，真实 repair 为
  `candidates.0.place/value_error` 2 次和 `candidates.0.event/value_error` 1 次；
  图片 initial/repair 分别重复 `candidates.0.place/value_error` 和
  `$/value_error` 各 1 次
- Token、费用与清理：文本 `8,484/944/9,428`、固定修复
  `6,092/580/6,672`、图片 `11,531/420/11,951` 输入/输出/总 Token，合计
  `26,107/1,944/28,051`；单价未配置，费用未知。Helvetica 字体身份校验通过；
  两个图片临时对象和整个仓库外私有根目录完整清理
- 根因：失败集中在 Pydantic `model_validator` 的严格业务语义，不是 JSON 形态、
  transport、鉴权、限流、超时或 Provider 映射。相关缺失/不确定项、价格、
  Place/Event、outcome 和时间规则来自 PRD，不应放宽。生成 JSON Schema 不表达这些
  跨字段语义；repair 只得到 generic `value_error`；当前 Provider 请求未使用
  `response_format`。本机 SDK 2.46.0 提供 json_schema/json_object 类型，但远端
  endpoint/model 能力未验证，不能据此推断支持
- 缺陷分级：没有生产 P0；存在阻塞收藏核心链路的生产可用性 P1，归属为
  Prompt/Schema/repair 安全反馈/structured-output 配置的契约桥接，不归为领域 DTO
  或生产 parser 错误。完整文件、行号、影响、最小修复方案、离线与真实复测范围及
  独立修复 Prompt 见 `docs/technical/M0_VALIDATION_REPORT.md` 第 12 节
- 范围与下一步：本任务只更新两份文档并创建文档原子提交；不修改生产代码，不追加
  调用，不复测网页，不创建 Dockerfile，不开始 M1，不合并 `main`，不推送。下一
  修复窗口按第 12.6 节 Prompt 先完成离线修复，再另行授权只复测本轮 7 个失败样本

#### 2026-07-23｜M0-Gate 真实结构兼容性离线修复｜待真实复测

- 分支与门禁：`codex/m0-gate-structure-fix` 从指定诊断基线
  `bfdaefb0d69bb3562523c58773e5a59c8d31dc5c` 创建；开始工作区干净，`main` 与
  `origin/main` 均保持 `0ace869ae2708608d238b77b3ade3153b1307549`，修复前后端
  生产树与该基线一致，Alembic 唯一 head 保持 `20260722_0006`
- 生产提交：`7660fb0aa2e7607b67e89358930d7ddea4609f53`
  (`fix: bridge extraction structured output contract`)；生产修复和对应测试为一个
  原子提交，本文档结果另行提交
- 稳定语义：保留唯一 `ExtractionResult` 和全部 PRD 规则，使用 Pydantic
  `PydanticCustomError` 将价格、missing/uncertain、Place/Event、时间、outcome、
  reason、恢复建议与应用保留 model-invalid 等跨字段失败收敛为稳定无值 type；
  `_safe_validation_issues()` 仍只输出 `path/type`
- Prompt、Schema 与 repair：文字和图片复用 `extraction_output.py` 的单一语义
  片段和同一份 `ExtractionResult.model_json_schema()` 生成结果；没有平行 Schema。
  repair 仍最多一次，只按安全 type 映射固定纠正说明，不执行第二次业务判定，并移除
  source text、图片/Base64 和完整原始响应
- structured output：唯一 `ModelProvider.chat()` 增加可选 `StructuredOutput`；
  唯一 `OpenAICompatibleProvider` 离线证明缺省请求不变、`json_schema`/
  `json_object` 映射、Schema 深拷贝、非法 tools 组合网络前拒绝、Provider 错误不
  fallback、SDK 零重试。`MODEL_STRUCTURED_OUTPUT_MODE` 默认 `none`，只作为显式
  capability 配置，不使用模型名/供应商白名单或额外探测
- 离线验证：Ruff 通过；strict mypy 对 93 个源文件通过；指定聚焦组合
  `304 passed`，扩大聚焦组合 `429 passed`；非真实全集
  `1451 passed / 1 skipped / 1 deselected`；默认全集
  `1451 passed / 2 skipped`；仓库外插件封锁 DNS、socket connect/connect_ex 与
  create_connection 后非真实全集仍为 `1451 passed / 1 skipped / 1 deselected`
- 既有测试提示：默认与封网全集各观察到一次历史已记录的 aiosqlite worker/事件循环
  收尾 warning，所有功能断言通过且落点不同；本修复未修改数据库生命周期、过滤
  warning、增加 sleep 或 skip，该 P2 分类不变
- 真实调用与安全：本任务未读取 `.env`，未调用真实模型、高德、网页或其他外部服务；
  新增真实请求、Token、费用均为 0，未保存完整响应或临时图片。远端
  `json_schema/json_object` capability 未验证，默认不启用
- 状态与风险：结构兼容性 P1 已完成离线修复，但七个原失败样本未获当前任务真实复测
  授权，因此仍不能关闭；真实重定向链 P1、最小 Dockerfile P2、幂等锁注册表 P2 和
  aiosqlite 收尾 P2 仍在。没有已知 P0，不允许进入 M1 或关闭 M0-Gate
- 下一步：主控先复核生产提交、文档提交与净复杂度；随后另行分别授权只复测 2 个
  文本、3 个固定修复和 2 个图片失败样本，总请求上限 `4 + 3 + 4 = 11`，SDK 和
  外层零重试。未获授权前不得读取 `.env`、探测 capability 或发起真实请求

#### 2026-07-23｜M0-Gate repair 业务证据补充修复｜待真实复测

- 分支与门禁：`codex/m0-gate-structure-repair-evidence-fix` 从指定基线
  `8020f02920caf2eefa60b66b9b8b5c4b5181e099` 创建；开始时工作区干净，`main` 与
  `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`。未开始重定向
  网页、Dockerfile、锁注册表、aiosqlite、M1 或其他旁支
- 生产提交：`6d02236e045fdcd923db998c15276e4b9db98b20`
  (`fix: preserve evidence for extraction repair`)；只修改共享 repair 构建、现有
  文字/图片调用方与对应证据型测试，没有新增 Parser、DTO、Provider 或 repair 服务
- 原缺口：上一版 `build_repair_messages()` 只保留 system 并丢弃
  `invalid_response`，导致唯一 repair 只有 Schema、path/type 与固定 guidance，
  无法判断要修复的地点或活动；固定成功 Fake 队列不能证明结果与业务证据一致
- 文字证据：第二次请求深拷贝保留初始 system、原始 user 输入，并在安全长度的普通
  响应下增加上一轮 assistant 文本；validation feedback 继续只含 path/type 和固定
  guidance，不含 Pydantic input/value、异常文本或堆栈。空白、缺失、超长或 Tool
  Call 响应不会作为 assistant 复制，但原始文字仍足以支持唯一 repair
- 图片证据：第二次请求只保留 system 与上一轮安全、可恢复候选结构文本；不再次携带
  图片 user message、`data:image`、Base64、图片字节、文件名、`file://` 或私人/
  存储路径。指令明确只能修复上一轮已有候选和事实；上一轮没有候选身份或含不安全
  文件证据时不发出无证据 repair，稳定返回 `model_invalid_output`
- 测试证明：文字和图片自定义 Stub 都会检查第二次请求的指定原始地点/上一轮候选后
  才返回同一修复结果；图片无候选证据时，即使 Fake 队列准备了任意新地点，也只执行
  一次调用且不会接受该候选。另覆盖两次非法响应、最多两次调用、ProviderError、
  取消、超长输出、Tool Call、临时图片清理、messages/response_format/Schema 隔离
- 离线验证：仓库 `.venv` 的 Python 3.13.5 下 Ruff 通过；strict mypy 对 93 个源文件
  通过；core `120 passed`，Provider `39 passed`，ExtractionResult 契约
  `31 passed`，文字 `62 passed`，图片 `61 passed`，配置 `125 passed`。非真实全集
  `1460 passed / 1 skipped / 1 deselected`，默认全集
  `1460 passed / 2 skipped`；仓库外插件封锁 DNS、connect、connect_ex 和
  create_connection 后非真实全集仍为 `1460 passed / 1 skipped / 1 deselected`
- 已知测试提示：默认全集与封网全集各出现一次已记录的非稳定 aiosqlite worker/
  事件循环收尾 warning，落点不同且所有功能断言通过；本修复未修改数据库生命周期、
  warning 策略、sleep 或 skip
- 迁移、配置与外部调用：Alembic 仍只有 `20260722_0006` 为最新 revision；未新增
  迁移、依赖、真实配置值或 M1 功能。未读取 `.env`，未运行 `real_provider`/
  `real_map`，未调用模型、高德、网页、对象存储、消息或其他外部服务；真实请求数、
  Token 和费用均为 0
- 状态与下一步：repair 业务证据 P1 已完成离线修复，但七个原真实失败样本尚未复测，
  真实结构 P1 继续为“等待真实复测”，不得关闭；M0-Gate 仍阻塞且不得进入 M1。
  本分支不合并、不推送，完成后交回主控进行独立复核和后续授权决策

#### 2026-07-23｜M0-Gate 真实结构兼容性最终复测｜阻塞

- 分支与门禁：`codex/m0-gate-structure-real-retest` 精确基于
  `0705eee61b1a5209a886e8925c90c6f7e2f1e8f3`，开始工作区干净；`main` 与
  `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`，生产修复
  `7660fb0`、`6d02236` 均在提交链，Alembic 唯一 head 为 `20260722_0006`
- 环境漂移：首次系统 Python mypy 的四个 `redundant-cast` 经用户确认是验证环境
  漂移，不修改 `collections.py` 或删除 cast。显式项目环境 Python `3.13.5`、
  mypy `1.20.2` 下 `pip check`、Ruff、93 文件 strict mypy 与指定聚焦测试
  `438 passed` 全部通过
- 授权：用户分别授权文本最多 4 次、固定结构 repair 最多 3 次、图片最多 4 次，
  三类 SDK/外层重试均为 0；唯一 structured-output 模式为 `json_schema`，不设费用
  上限，远端不支持时计入已发请求并立即停止对应类别，禁止切换模式或追加探测
- 实际调用：三个类别的首个真实 `json_schema` 请求均在形成 `ModelResponse` 前返回
  安全 `PROVIDER_ERROR`，因此分别立即停止；文本 `1/4`、固定 repair `1/3`、图片
  `1/4`，合计 `3/11`。没有 fallback、重试、追加探测、替换样本或后续样本调用
- outcome 与证据：已尝试的三个样本均未形成生产 outcome 或候选，候选成功率为
  `0/3`；固定类本地非法 initial 正确记录 `$/json_invalid`，唯一真实 repair 被
  capability 拒绝。失败发生在生产 Parser、严格 DTO 与 canonicalization 之前，
  不能据此判定业务样本、Parser 或领域规则失败，也无法验证候选身份与 generic
  `value_error` 是否消失
- capability：百炼 OpenAI-compatible Chat Completions 官方结构化输出采用
  `response_format={"type":"json_object"}`；本轮唯一授权模式 `json_schema`
  与该协议不兼容。Provider 安全边界只公开 `PROVIDER_ERROR`，未记录远端正文、
  完整响应、请求、密钥或异常链。现有生产 Provider 已显式支持 `json_object`，
  因此本窗口不新增生产修复
- 延迟、Token 与费用：文本、固定 repair、图片各一个已尝试样本的端到端单点观测为
  `1.248s`、`0.353s`、`0.490s`；P50、观测 P95、最大值均等于各自单点且不具有统计
  意义。Provider 未返回 Token；费率未知，费用不可确认。超时率与重试率均为 0
- 超时校准：模型单次配置 30 秒小于文本 60 秒外层预算，但不小于图片 20 秒外层硬
  预算；本轮没有提高或修改时限，后续需独立校准，不能用 capability 快速失败证明
  图片正常余量
- 图片清理：首个图片失败样本的临时对象、元数据、reservation、临时文件和整个仓库外
  私有根目录均已清理；未公开图片、Base64、文件名、路径、哈希或 OCR 正文
- 离线回归：清除真实进程配置后，Ruff、93 文件 strict mypy 通过；非真实全集
  `1460 passed / 1 skipped / 1 deselected`；封锁 DNS、connect、connect_ex 和
  create_connection 后仍为 `1460 passed / 1 skipped / 1 deselected`。普通全集
  出现一次既有 aiosqlite 收尾 warning，封网全集无 warning，该 P2 不变
- 结论与下一步：真实结构兼容性 P1 保持“等待 `json_object` 模式真实复测”，
  M0-Gate 继续阻塞；本任务不修改生产代码、不合并、不推送。下一窗口须重新取得
  三类明确授权，只用官方 `json_object` 模式复测相同七个样本，不得把本轮三次
  capability 拒绝归因于样本、Parser、DTO 或 repair；真实重定向链、Dockerfile、
  锁注册表、aiosqlite 和 M1 均未处理

#### 2026-07-23｜M0-Gate 百炼 json_object 真实结构复测｜阻塞

- 分支与门禁：`codex/m0-gate-structure-json-object-retest` 精确基于
  `bcd61dfae2be80dca9aa0fc80796a405bae02eee`；开始工作区干净，`main` 与
  `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`，提交链和
  Alembic 唯一 head `20260722_0006` 均符合要求
- capability 与授权：官方确认 OpenAI-compatible 结构模式为 `json_object`；
  授权后只读确认配置完整、模型类型在官方支持范围。用户授权文本 `4`、固定 repair
  `3`、图片 `4`，SDK/外层零重试，单次模型 8 秒、图片外层 20 秒，禁止模式、模型、
  endpoint、样本或调用切换
- QA 门禁：原样本清单从既有记录唯一恢复，图片配方保持不变；仓库外工具增加三类和
  总计数发送前熔断，Ruff、strict mypy、19 项安全自测通过。工具、样本、结果和图片
  临时对象均未写入仓库并已清理
- 真实结果：实际文本 `3/4`、固定 repair `3/3`、图片 `2/4`，总计 `8/11`；文本
  `2/2` 通过，均为证据一致 `candidates`；固定 repair `1/3` 通过，另两个稳定为
  `absent_field_not_classified` 后的 `model_invalid_output`；图片 `2/2` 通过，
  清晰图片为证据一致 `candidates`，模糊图片安全返回
  `insufficient_information`，身份一致性不适用。总计 `5/7` 样本通过
- 安全与资源：8 个响应均为 stop、有 content、无 tool calls；ProviderError、超时、
  重试、fallback、额外调用和图片残留均为 0。Token 合计输入 `21,141`、输出
  `1,436`、总计 `22,577`；费率未知
- 延迟：模型单次文本 P50/观测 P95/最大 `6.318/6.699/6.741s`，固定 repair
  `4.048/4.520/4.572s`，图片 `2.785/3.033/3.060s`；小样本 P95 不具统计意义。
  文本观测 P95 占 8 秒约 83.7%，高于建议区间；图片本轮未触发 repair，20 秒内双
  调用完整链余量仍未取得真实证据
- 离线回归：Ruff、93 文件 strict mypy 通过；非真实全集
  `1460 passed / 1 skipped / 1 deselected`，默认全集 `1460 passed / 2 skipped`，
  封网非真实全集 `1460 passed / 1 skipped / 1 deselected`。三轮各有一次既有
  aiosqlite 收尾 warning，P2 不变
- 结论：结构兼容性 P1 不关闭，唯一剩余结构阻塞为固定 repair 的语义遵循仅
  `1/3` 通过。模糊图片的 `insufficient_information` 符合生产“不猜测”规则，也
  满足原始 Gate“形成结构化结果或正确恢复”的验收口径，不构成缺陷或产品冲突。
  文本观测 P95 占 8 秒约 83.7% 和图片双调用余量未获真实覆盖继续作为超时校准风险，
  不混入结构 P1。未合并、未推送、未进入 M1；真实重定向链、Dockerfile、锁注册表
  和 aiosqlite 均未处理

#### 2026-07-23｜M0-Gate 固定 repair 语义收敛｜待真实复测

- 分支与门禁：`codex/m0-gate-fixed-repair-semantics` 从指定基线
  `ae659bc4c799a629228ef90d8488f144b2c27bea` 创建；开始时工作区干净，`main` 与
  `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`，Alembic 唯一
  head 为 `20260722_0006`。没有读取 `.env`，没有调用真实 API
- 生产提交：`5bcdb9ca302f9298da7a425b7f5deb2805ae7b8b`
  (`fix: strengthen extraction repair semantic checklist`)；只修改共享 repair
  guidance 和对应文字抽取测试，没有修改图片服务、Provider、领域 DTO、Parser、
  canonicalization、调用上限、迁移、依赖或配置
- 根因与净变化：本地非法 JSON 稳定产生 `$/json_invalid`，但该 type 未进入专用
  guidance，唯一 repair 只收到通用“按 Schema 重建”要求；system 规则虽包含严格
  语义，却没有要求重建时逐候选完成字段闭合审计。生产净变化为共享模块增加
  `json_invalid` 固定 guidance，并把字段闭合片段同时复用于初次规则与 repair
- 规则唯一性：Place/Event 字段名从既有唯一 `CandidateField` 枚举生成；新增文本
  只指导模型输出，不执行校验。`ExtractionResult`、候选 DTO 及其 validator 仍是
  唯一业务规则执行点，没有第二套 Schema、Parser、DTO、Provider 或 repair 服务
- 安全与边界：guidance 固定且无样本值，明确 Place 8 类字段、Event 额外两个时间
  字段、missing/uncertain 互斥、价格成对、Place/Event 时间边界、候选 outcome、
  禁止自报 model-invalid 和禁止发明事实；安全 issue 仍只有 path/type。repair
  仍最多一次，遗漏字段仍稳定 `model_invalid_output`，图片不重传 Base64 的既有
  行为未改
- 离线结果：Python `3.13.5`、mypy `1.20.2`；`pip check`、Ruff、93 文件 strict
  mypy 通过。core `120 passed`、Provider `39 passed`、ExtractionResult 契约
  `31 passed`、文字 `66 passed`、图片 `61 passed`、配置 `125 passed`。非真实
  全集 `1464 passed / 1 skipped / 1 deselected`，默认全集
  `1464 passed / 2 skipped`
- 封网结果：首次仓库外插件把 `connect/connect_ex` 错写为模块属性，setup 阶段
  退出 1，项目测试未执行；修正为封锁 `socket.socket.connect/connect_ex` 以及
  `socket.getaddrinfo/create_connection` 后，非真实全集为
  `1464 passed / 1 skipped / 1 deselected`。临时插件目录已删除
- 既有提示：普通非真实全集与默认全集各出现一次已记录的 aiosqlite worker/事件
  循环收尾 warning，封网全集无 warning；本任务未处理或掩盖该独立 P2
- 真实结论：新增真实请求、Token、费用均为 0；第 16 节文本 `2/2`、图片 `2/2`
  的既有真实结论保持不变。固定 repair P1 状态为“离线修复完成，等待有限真实
  复测”，不能提前关闭；文本 8 秒余量和图片双调用 20 秒余量继续作为独立超时
  校准风险
- 下一步：另开真实复测窗口，只使用相同 3 个固定非法 Fixture，每个样本最多一次
  `json_object` repair，总上限 3 次请求，SDK `max_retries=0`、外层重试 0、模型
  单次 8 秒；不得结转旧额度，不复测文本、图片、Tool Calling、高德或网页。需等待
  用户新授权。本分支不合并、不推送、不进入下一 Gate 项或 M1

#### 2026-07-23｜M0-Gate 固定 repair 最终真实复测｜阻塞

- 分支与门禁：`codex/m0-gate-fixed-repair-real-retest` 精确基于
  `fa077e1ef62f8f60fcad606e5464b1e0afd07cc2`；开始工作区干净，`main` 与
  `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`，生产修复
  `5bcdb9ca302f9298da7a425b7f5deb2805ae7b8b` 在提交链，Alembic 唯一 head 为
  `20260722_0006`，没有其他生产代码变化
- 离线门禁：项目 `.venv` 为 Python `3.13.5`、mypy `1.20.2`；`pip check`、
  Ruff、93 文件 strict mypy 通过，指定聚焦测试 `442 passed`
- 授权与边界：授权后才只读检查配置完整性；只使用第 16、17 节相同 3 个固定非法
  Fixture，`json_object`、SDK/外层零重试、模型单次 8 秒、发送前总计数熔断。
  仓库外工具复用生产 Provider、repair messages、Parser、严格 DTO 与
  canonicalization，不保存完整请求、响应、样本、Prompt 或 Schema
- 真实结果：实际请求 `1/3`。匿名样本 1 的唯一 repair 返回 Provider 契约，
  finish_reason 为 stop、有 content、无 tool_calls，但 outcome 为
  `model_invalid_output`、候选数 0；initial 为 `$/json_invalid`，repair 安全
  issue 为 `candidates.0.place/absent_field_not_classified`。未形成候选，身份与
  证据一致性不成立；没有 generic `value_error`、ProviderError、超时、重试、
  fallback 或无证据事实。按失败即停规则，样本 2、3 未发送
- 延迟与资源：样本 1 模型/端到端延迟 `4.936/4.940s`；n=1 时 P50、观测 P95、
  最大值均等于单点，P95 不具统计意义。模型观测 P95 占 8 秒约 `61.7%`；超时率、
  重试率均为 0。Token 输入 `2,621`、输出 `166`、总计 `2,787`；费率未知，费用
  无法确认
- 回归：真实进程配置已清除且 `.env` 未修改。Ruff、93 文件 strict mypy 通过；
  非真实全集 `1464 passed / 1 skipped / 1 deselected`，默认全集
  `1464 passed / 2 skipped`，封锁 DNS、connect、connect_ex、create_connection
  后非真实全集仍为 `1464 passed / 1 skipped / 1 deselected`。三轮均仅有一次
  已记录的 aiosqlite 收尾 warning，该 P2 不变
- 结论：失败分类为代码 / Prompt 语义兼容性缺陷，不是 Provider、配置或环境故障。
  固定 repair 未达到 `3/3`，结构 P1 不关闭；文本 `2/2`、图片 `2/2` 既有结论
  保留。完整独立修复 Prompt 已写入 M0 验证报告第 18.6 节。M0-Gate 仍有该结构
  P1、真实重定向链、Dockerfile 与三个既有 P2；本分支不合并、不推送、不进入下一项

#### 2026-07-23｜M0-Gate 保守缺失归一化｜待有限真实复测

- 分支与门禁：`codex/m0-gate-conservative-missing-normalization` 精确从
  `f067d31c43f8f95c87d7d5f3f6024aca7f77d729` 创建；开始工作区干净，`main` 与
  `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`，`5bcdb9c`
  在提交链且其后只有两次文档提交。Alembic 唯一 head 为 `20260722_0006`
- 产品决定：用户明确批准在唯一模型响应解析边界，把“值为空、未明确 uncertain、
  也未登记 missing”的适用候选字段保守加入 `missing_fields`。这只是应用派生状态
  记账，不生成地址、区域、价格、标签、时间或其他事实；已有值、显式 uncertainty
  及原因和其他业务事实均不修改
- 生产提交：`6b318f58f91304f6d95a87db6840463e1b250a90`
  (`fix: normalize absent model fields conservatively`)；在唯一
  `parse_extraction_response()` 中深拷贝 JSON，把既有已知金额补 CNY 与缺失状态
  归一化收敛为同一阶段，随后仍经过唯一严格 DTO、全部 validator、自报 invalid
  拒绝与 canonicalization
- 字段与严格边界：稳定顺序来自唯一 `CandidateField`，适用范围由现有
  Place/Event DTO 字段生成，Place 不含 Event 时间、Event 额外含两个时间字段。
  非空、explicit uncertainty、已有 missing 均保留；冲突、重复、非法类型/结构、
  未知字段、非法 kind、price pair、Event 时间、outcome 继续由 DTO 拒绝。直接
  构造缺失分类不完整的领域候选仍失败
- Prompt 收敛：删除 `5bcdb9c` 的逐字段闭合 checklist、Place/Event 字段目录和
  专用长 `json_invalid` guidance；恢复简洁通用 JSON repair。文字、图片与共享
  Prompt 改为无证据事实留空、来源明确歧义才写 uncertainty，不再要求模型可靠维护
  全部 missing 账目；保留证据绑定、图片不重传、安全 path/type、价格与类型边界
- 覆盖与隔离：新增/更新测试覆盖 Place/Event 稳定顺序、Place 无 Event 时间、
  uncertainty 原因保持、已有 missing、有值事实、全部非法分类、未知字段/kind、
  price/time/outcome、自报 invalid、原对象不变、重复幂等、多候选顺序、并发隔离和
  三个固定 repair 响应。普通 Provider、Tool Calling、json_object/tools 互斥、
  最多一次 repair、图片行为/Cleanup/CNY 和 Schema/messages/response_format 隔离
  均回归通过
- 最终验证：Python `3.13.5`、mypy `1.20.2`；`pip check`、Ruff、93 文件 strict
  mypy 通过。core `120 passed`、Provider `39 passed`、ExtractionResult
  `31 passed`、文字 `83 passed`、图片 `61 passed`、配置 `125 passed`；非真实
  全集 `1481 passed / 1 skipped / 1 deselected`，默认全集
  `1481 passed / 2 skipped`，封锁 DNS、connect、connect_ex、create_connection
  后非真实全集仍为 `1481 passed / 1 skipped / 1 deselected`
- 范围与安全：没有新增迁移、依赖、Parser、DTO、Schema、Provider、repair 服务、
  fallback、第三次调用、数据库、图片或响应快照；未处理重定向网页、Dockerfile、
  锁注册表、aiosqlite 或 M1。未读取 `.env`，未运行真实 marker，真实模型、高德、
  网页、消息及其他外部请求均为 0
- Gate 状态：固定 repair P1 为“保守归一化离线修复完成，等待有限真实复测”。
  文本 `2/2`、图片 `2/2` 既有真实结论与模糊图片正确恢复不变；文本 8 秒余量和
  图片双调用 20 秒余量仍是独立超时校准风险
- 下一步：等待新的明确授权，只复测第 16–18 节相同 3 个固定 Fixture；initial
  全为本地固定非法 JSON，每样本最多一次 `json_object` repair，总上限 3 请求，
  SDK/外层零重试、单次 8 秒、发送前熔断、不结转旧额度；不复测文本、图片、Tool
  Calling、高德或网页，不扩大样本。本分支不合并、不推送

#### 2026-07-23｜M0-Gate 保守缺失归一化最终真实复测｜结构 P1 已关闭

- 分支与门禁：`codex/m0-gate-conservative-missing-real-retest` 精确从
  `60092a9045ab7cf33bd1389513e12aa95393fa84` 创建；开始工作区干净，`main` 与
  `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`，生产修复
  `6b318f58f91304f6d95a87db6840463e1b250a90` 在提交链且其后只有两份文档变化，
  Alembic 唯一 head 为 `20260722_0006`
- 离线门禁：项目 `.venv` 的 `pip check`、Ruff、93 文件 strict mypy 通过；指定
  core、Provider、ExtractionResult、文字、图片和配置聚焦组合为 `459 passed`
- 授权原文：“授权本窗口保守缺失归一化固定 repair 真实复测：使用相同 3 个固定
  Fixture，每个最多一次真实 repair，总上限 3 次模型请求；唯一模式 json_object；
  SDK 和外层均 0 重试；模型单次时限 8 秒；本轮不设费用上限。不得切换模式、模型、
  endpoint、样本或追加调用。”
- 配置与工具：授权后只读确认配置完整、8 秒、`json_object` 和既有官方支持范围；
  仓库外工具从唯一历史 manifest 恢复相同三项清单并核对身份哈希，三个 initial
  均为本地固定非法 JSON 且安全 issue 为 `$/json_invalid`。工具复用生产
  `OpenAICompatibleProvider`、`TextExtractionService`、repair messages、唯一
  Parser、保守归一化、严格 DTO 和 canonicalization；发送前总熔断为 3
- 真实结果：实际请求 `3/3`，三个样本各只执行一次真实 repair；Provider 均为正式
  contract、`finish_reason=stop`、有 content、无 tool_calls。三个 outcome 均为
  `candidates`，候选数均为 1，身份一致与来源事实一致均为 true；归一化后均通过
  严格 DTO 与 canonicalization，没有 `absent_field_not_classified`、generic
  `value_error`、ProviderError、超时、重试、fallback、额外调用或无证据事实
- 保守归一化：三个 repair 响应都经过唯一解析边界；空且无显式 uncertainty 的适用
  字段由应用保守登记为 missing，已有事实不变，显式 uncertainty 不被改写，Place/
  Event 适用字段边界继续由既有 DTO 决定。安全工具不保存完整响应或字段值
- 延迟与资源：三个样本模型/端到端分别为
  `5.359/5.360s`、`4.846/4.847s`、`3.694/3.695s`；模型 P50/观测
  P95/最大为 `4.846/5.308/5.359s`，端到端为
  `4.847/5.309/5.360s`。n=3 的 P95 只为观测插值，不具有统计验证意义。Token
  输入 `7,226`、输出 `533`、总计 `7,759`；费率未知，费用无法确认；超时率与
  重试率均为 `0%`
- 回归：真实命令级进程配置结束且 `.env` 未修改。Ruff、93 文件 strict mypy
  通过；非真实全集 `1481 passed / 1 skipped / 1 deselected`，默认全集
  `1481 passed / 2 skipped`，仓库外插件封锁 DNS、connect、connect_ex 和
  create_connection 后非真实全集仍为 `1481 passed / 1 skipped / 1 deselected`
- 结论与下一步：固定 repair 达到 `3/3`，真实结构兼容性 P1 关闭；第 16 节文字
  `2/2`、图片 `2/2` 的既有真实结论保留。下一项是重定向网页真实验收。最小
  Dockerfile、幂等锁注册表、aiosqlite 收尾 warning、文本 8 秒余量和图片双调用
  20 秒余量风险均保留；未处理或开始这些事项，也未进入 M1。本分支不合并、不推送

#### 2026-07-23｜M0-Gate 重定向网页真实复测｜重定向 P1 已关闭

- 分支与门禁：`codex/m0-gate-redirect-real-retest` 从
  `ebeac0ba157e7195dc2c676a0a183ea853570708` 创建；开始工作区干净，
  `main` 与 `origin/main` 均为
  `0ace869ae2708608d238b77b3ade3153b1307549`；Alembic 唯一 head 为
  `20260722_0006`，真实结构兼容性 P1 已在文档中关闭
- 授权与工具：本窗口只授权两个固定公开匿名 GET-only httpbingo 样本，A 为普通
  单跳、B 为相对两跳，HTTP 总上限 5。仓库外探针复用生产 Web 配置、HTTP client、
  Provider、SystemHostResolver、URL/DNS/SSRF 与显式重定向校验；connect/read/
  total 为 `5/10/20s`，全部零重试，禁用环境代理、认证、Cookie 和 keepalive，
  transport 在发送前计数并在第 6 次委托前硬拒绝
- 离线门禁：全新 Python 3.13.5 `git archive` 快照安装和 `pip check` 通过；
  Ruff、93 文件 mypy 通过；Web Provider `114 passed`、URL 安全 `59 passed`、
  Provider 契约 `22 passed`、统一输入 `19 passed`；非真实全集与封网全集均为
  `1481 passed / 1 skipped / 1 deselected`，所有命令退出 0、无 warning
- 真实结果：A 为 `3xx → 2xx`，实际 2 请求、`redirect_count=1`、逐跳耗时
  `828.457/692.671ms`、端到端 `1700.369ms`；B 为
  `3xx → 3xx → 2xx`，实际 3 请求、`redirect_count=2`、逐跳耗时
  `579.096/513.655/526.016ms`、端到端 `1663.756ms`。两者均返回公开 HTML
  `WebPageContent` 且标题或清理正文非空
- 指标与预算：实际 HTTP 恰好 `5/5`，成功率 `100%`、超时率 `0%`、重试率
  `0%`；hop P50/观测 P95/max 为 `579.096/801.300/828.457ms`，端到端为
  `1682.062/1698.538/1700.369ms`，最大占 20 秒 `8.502%`。P95 只是 n=5/n=2
  小样本观测插值，不具有统计意义；Token `N/A`，费用未知
- 安全与副作用：5 个请求各有一次生产 DNS/SSRF 校验，两个相对重定向均重新校验；
  Cookie 始终为空，无认证、代理或环境变量注入；未记录完整 query、Header、响应
  头、正文或异常原文；没有数据库、Source、收藏、AgentRun 或 ToolRun 写入。未读取
  `.env`，未调用模型、高德、图片、对象存储、Tool Calling、消息或其他外部服务
- 清理与回归：真实进程结束后删除探针和旧插件；Ruff、93 文件 mypy、非真实全集
  `1481 passed / 1 skipped / 1 deselected`、默认全集 `1481 passed / 2 skipped`
  及再次封网全集 `1481 passed / 1 skipped / 1 deselected` 全部退出 0、无
  warning；随后删除新插件、字节码、完整临时快照和虚拟环境并确认均不存在
- 结论与下一步：真实一跳与两跳链 `2/2` 通过，第 9.5 节重定向 P1 关闭；生产最多
  五跳仍只由离线测试证明，不宣称真实五跳覆盖。真实结构兼容性和真实重定向链均已
  关闭，没有未关闭的真实链路 P1。M0-Gate 尚未整体关闭，下一项为“最小
  Dockerfile 补齐与容器验收”；锁注册表、aiosqlite warning、文本 8 秒余量和图片
  双调用 20 秒余量继续保留。本任务未修改生产代码/测试，未合并、未推送、未进入 M1

#### 2026-07-23｜M0-Gate 最小 Dockerfile 与容器验收｜待最终收口

- 分支与提交：`codex/m0-gate-dockerfile` 从指定提交
  `632c9c2dd585b185a1511ddd4849565d5ab81cf8` 创建；`main` 与 `origin/main`
  均保持 `0ace869ae2708608d238b77b3ade3153b1307549`。首个原子提交为
  `0f9b48e74adaee240b2f55f32b8acdc92f40571b`
- 实现范围：新增根目录唯一 Dockerfile 与 `.dockerignore`，README 增加最小
  build、显式 Alembic 迁移、运行时变量注入、`/healthz` 和 SQLite/M1 边界。只
  安装 `backend/pyproject.toml` 正式依赖，复用 `app.main:app`，UID `10001`
  非 root 运行；没有自动迁移、第二套入口、Compose、PostgreSQL、Worker、SSE 或 M1
- 环境与构建：Docker Client/Server `29.6.1`、Docker Desktop arm64；官方
  `python:3.13-slim` 实际解析摘要为 `sha256:6771159c...e1a91`。工作树首次
  `--pull` 构建 56.07 秒，精确首提交 archive 重建 35.69 秒，最终镜像
  `69,961,884 bytes`
- 镜像内容：容器 Python `3.13.14`、UID `10001`、工作目录 `/app`；`pip check`
  和 app/nanobot_core/app.main import 通过。六个 revision 与 Alembic 配置可读，
  唯一 head `20260722_0006`；`.env`、Git、tests、缓存、数据库、日志和本机路径
  不存在，pytest/mypy/ruff 未安装，配置与 history 敏感扫描无命中
- 迁移与运行：临时 SQLite 显式 `upgrade head/current/check` 通过，current 为
  `20260722_0006 (head)` 且 check 无待生成操作。API 只绑定宿主
  `127.0.0.1` 随机端口，不使用 `--env-file`；容器 running、Docker HEALTHCHECK
  healthy，自动和显式 Request ID 的 `/healthz` 均为 HTTP 200 与
  `{"status":"ok"}`，显式 ID 回显，日志不含 query/Header/Cookie/Authorization/
  正文，外部 Provider 调用为 0
- 停止与清理：精确提交容器 0.52 秒内正常停止、退出码 0，停止后端口关闭；临时
  迁移/API 容器与容器内数据库已删除。任务镜像标签、archive、venv、QA 插件和
  `/tmp` 日志在最终交接前统一清理，不触碰用户原有容器、镜像或缓存
- 隔离基线：起始提交 archive 的全新 Python 3.13.5 venv 中安装与 `pip check`
  通过；Ruff、93 文件 mypy、非真实 `1481 passed/2 deselected`、默认
  `1481 passed/2 skipped`、封网非真实 `1481 passed/2 deselected` 均通过
- 修改后回归：Ruff、93 文件 mypy、非真实与默认全集同上；core `120 passed`、
  migrations `21 passed`、M0-4D `19 passed`、结构检索 `42 passed`、计划草案
  `43 passed`、外部补充 `27 passed`，再次封网非真实 `1481 passed/2
  deselected`。全部运行无 aiosqlite warning，历史 P2 不变
- 安全与边界：没有读取、打印或复制 `.env`，没有真实或付费 API 调用，没有修改
  生产 Python、测试、迁移、依赖范围或 `.env.example`；未合并、未推送
- 结论与下一步：最小 Dockerfile P2 已关闭，当前没有未关闭 P0/P1；M0-Gate 仅为
  “待最终收口”，不在本窗口宣布 M0 正式关闭。锁注册表 P2 必须在 M1 开始前解决；
  aiosqlite warning、文本 8 秒余量和图片双调用 20 秒余量继续保留。下一窗口只执行
  主控最终 Gate 复核、状态文档收口、ff-only 合并和推送

#### 2026-07-23｜M0-Gate 最终主控收口｜已完成

- Git 与提交链：主控从候选
  `41a640b60ec47db0ce1cfaee5c6bba62083ae38b` 和初始 `main`/`origin/main`
  `0ace869ae2708608d238b77b3ade3153b1307549` 开始；真实远端复核无变化。
  `main..候选` 恰好 18 个单父提交且无 merge commit；
  `codex/m0-regression` 已从
  `fb7929e1e0e3510198dd060451399fddeeb7c47a` 纯快进到候选，工作区干净
- 范围、复杂度与冗余：最终差异只涉及共享结构输出兼容与 repair 修复、对应测试、
  配置、Dockerfile/`.dockerignore`、README 与 Gate 文档。AgentRunner、
  ToolRegistry、ModelProvider、Parser/规范化/repair、Web Provider、地点匹配、
  检索和计划服务均保持唯一；文字和图片共用同一结构边界，没有样本白名单、测试
  专用生产分支、第二套入口或 M1 实现
- 最终隔离环境：macOS 26.5.1 arm64、仓库外候选 archive、全新 Python 3.13.5
  venv、pip 25.1.1；安装、`pip check`、Ruff 和 93 文件 strict mypy 全部退出 0
- 最终全集：`not real_provider and not real_map` 为
  `1481 passed / 1 skipped / 1 deselected`；正式非真实全集为
  `1481 passed / 2 deselected`；默认全集为 `1481 passed / 2 skipped`；仓库外
  插件硬封 DNS 与三类 socket 连接后正式非真实全集仍为
  `1481 passed / 2 deselected`，全部 failed/warning 为 0
- 聚焦测试：core `120 passed`、迁移 `21 passed`、M0-4D `19 passed`、结构检索
  `42 passed`、计划草案 `43 passed`、外部补充 `27 passed`
- 迁移与本地运行：临时 SQLite 的唯一 head `20260722_0006`，upgrade/current/
  check/downgrade base/re-upgrade 往返全部通过；现有 Uvicorn `/healthz` 返回
  HTTP 200 和 `{"status":"ok"}`，Request ID 正常，日志不含 query、Header、
  Cookie、Authorization 或正文，停止后端口释放
- Docker：Docker 29.6.1、Linux arm64；精确候选快照构建成功，容器 Python
  3.13.14、UID 10001、`pip check` 与 Alembic 通过，HEALTHCHECK healthy，
  `/healthz` 固定响应与日志脱敏通过，停止退出码 0；镜像不含 `.env`、Git、tests、
  docs、缓存、数据库或本机路径，本任务容器与镜像标签均已清理
- 安全与真实调用：本最终窗口没有读取 `.env`，没有运行真实 marker；新增模型、
  高德、网页、图片、对象存储及其他真实/付费 API 请求均为 0。历史逐次授权的文字
  `2/2`、图片 `2/2`、固定 repair `3/3`、Tool Calling `1/1`、高德 `5/5`、
  普通网页 `2/2` 和重定向 `2/2` 证据保留在
  `docs/technical/M0_VALIDATION_REPORT.md`
- 风险：锁注册表无界增长保持 P2，100,000 唯一键约 24.7 MB，必须作为 M1-0
  第一项前置修复；aiosqlite warning 本轮未复现但继续监测；文本 8 秒观测 P95
  占比 83.7%、图片双调用 20 秒未真实覆盖、网页真实最多五跳未覆盖均继续登记，
  不通过无限提高超时或放宽断言处理
- 结论与交接：当前无未关闭 P0/P1，M0-Gate 已完成，M0 正式关闭。当前允许阶段为
  M1-0 PostgreSQL 与任务基础，状态未开始；M1-0 必须先完成锁生命周期修复，再进入
  既定 PostgreSQL、Job、Worker、APScheduler、Docker Compose 与 SSE 范围。
  不得提前实现 M1-1 Session、M1-2 Next.js 或其他后续阶段

#### 2026-07-24｜M0 关闭后真实截图超时校准修复｜待主控验收

- 分支与门禁：`codex/m0-timeout-calibration` 从指定且 fetch 后未变化的
  `main` / `origin/main` / `HEAD`
  `55a9da825cffb501051c66e6065ca43b0893b11e` 创建；开始工作区干净，目标分支
  原先不存在，Alembic 唯一 head 为 `20260722_0006`。M0 保持已完成，M1-0
  仍未开始
- 真实烟雾事实：固定 01–06 只执行 01–03。01 内容识别正确，但模型耗时
  `11.561s`，超过旧 8 秒严格口径；02 在 `6.285s` 完成并通过；03 返回
  `PROVIDER_TIMEOUT`，触发停止条件；04–06 未执行，不能记为失败。旧 8 秒值已被
  真实样本证明余量不足
- 根因复现：完全离线的持续分段活动 transport 令单个分段均短于 SDK 阶段 timeout，
  但完整 SDK 调用超过配置值；修复前新增测试按预期 `1 failed`，调用在约 2.5 秒后
  正常完成，证明 SDK/httpx timeout 不等价于总墙钟截止
- 生产修复：唯一 `OpenAICompatibleProvider` 在实际
  `chat.completions.create()` await 边界使用同一配置值建立一次总墙钟截止；到点
  取消并等待活动请求结束后映射为唯一 `ProviderErrorCode.TIMEOUT`。错误映射退出
  SDK exception handler 后统一抛出，异常链、日志、repr 和公开字典不保留响应、
  Prompt、Base64、密钥、endpoint、Authorization 或 Request ID
- 配置校准：`MODEL_TIMEOUT_SECONDS` 明确表示一次完整 Provider SDK 调用的总墙钟
  截止，当前限制为有限 `(0, 15]`，`.env.example` 暂定为 `15`。15 秒只来自本轮
  有限真实观测，不构成统计 P95，也不授权无限提高
- 预算关系：URL/图片整链路继续只由既有 `TextCollectionWorkflow` 和
  `AgentRunService.execute_application()` 建立一次最多 20 秒共享总预算；
  `ImageRecognitionService` 没有新增计时器。上传、校验、存储、initial、唯一
  repair、解析、数据库写入和清理共用该预算，initial 消耗后 repair 只能使用剩余
  时间
- 取消、清理与零重试：总墙钟 timeout 会取消活动 SDK 流，测试确认请求只发一次、
  流和辅助任务终结、无后台请求且 Provider close 后 HTTP client 关闭；外部
  `CancelledError` 原对象传播。SDK `max_retries=0`、外层重试 0、ProviderError
  零重试不变。图片 repair 共享预算、整链路 timeout、数据库写入 timeout 与取消
  均清理 objects、metadata、temporary、reservation 和未提交业务写入
- 兼容与输入隔离：普通文本、Tool Calling、`json_object`、`json_schema`、多模态、
  Token/耗时映射继续通过；messages、tools、Schema 和图片输入不被修改。没有修改
  抽取 Prompt、候选规则、结构契约、数据库模型或迁移
- 正式验证：项目根 `.venv` 为 Python `3.13.5`、mypy `1.20.2`、SQLAlchemy
  `2.0.51`。editable 安装、`pip check`、Ruff、93 文件 strict mypy 均退出 0；
  Provider+图片 `102 passed`；统一输入+文字抽取/契约 `135 passed`；正式非真实
  全集 `1486 passed / 2 deselected`；仓库外插件硬封 DNS、connect、connect_ex、
  create_connection 后五个聚焦文件 `237 passed`。以上正式命令均为 0 failed、
  0 skipped、0 warning
- 环境说明：正式安装前系统解释器的 mypy `1.14.1` / SQLAlchemy `2.0.39` 对未修改
  的既有 Repository 报 4 个 `redundant-cast`；未改无关代码。切换到项目已验收依赖
  环境后规定 mypy 命令通过 93 个源文件
- 复杂度与范围：ModelProvider、OpenAICompatibleProvider、AgentRunner、
  ImageRecognitionService、统一输入工作流和 Parser/repair 均保持唯一；新增总墙钟
  截止只位于 Provider SDK 不可信 await 边界，20 秒预算仍只在既有统一工作流外层。
  没有 timeout helper、第二套错误映射、重复清理、图片样本规则、M1 代码或 SDK
  私有属性依赖
- 外部调用与下一步：本修复没有读取 `.env`，真实模型、高德、网页、对象存储、消息
  及其他外部 API 调用为 0。等待主控离线验收和集成；集成后必须重新取得用户明确
  授权，固定按原 01–06 顺序复测，每张 initial 最多 1 次，只有生产唯一 repair
  正常触发时最多再 1 次，总上限 12 次非流式 Chat Completions，单次总墙钟 15 秒、
  每张完整共享 20 秒、SDK/外层重试均为 0

#### 2026-07-24｜M0 关闭后 Event 日期粒度修正｜待主控验收

- 分支与基线：`codex/event-date-granularity` 从本地 `main`
  `d75d62087efdf15c7cdbafb4246a6747444d2f07` 创建；该基线包含
  `origin/main` 的 `55a9da825cffb501051c66e6065ca43b0893b11e`
- 实现提交：`12d57f137f534eda0d00347a660e25773818e302`
  （`fix: distinguish event dates from exact times`）；随后仅以独立文档提交记录本完整
  SHA
- 领域语义：唯一 EventCandidate、CollectionItem 和 CandidateField 增加
  `event_start_date/event_end_date`；日期结束日包含当天且允许单日相等，日期顺序由
  一份共享领域验证负责。既有 aware `event_start_at/event_end_at` 继续只表达准确
  场次且结束严格晚于开始；date-only 不转换成午夜、时区或每日开闭馆时间
- 正式数据链：共享文字/URL/图片结构抽取与 repair、严格 DTO、自动收藏与幂等快照、
  CollectionItem、唯一 Repository、API 查询/PATCH 和修改清空均保留日期事实；
  Place 拒绝 Event 日期元数据
- 状态与计划：date-only Event 保存为 `pending_details`，不会被结构化检索纳入计划；
  exact-time Event 的既有 `active` 行为保持。没有新增计划状态、日期转时刻逻辑或
  M1 能力
- 迁移：新增唯一 head `20260724_0007`，down revision 为 `20260722_0006`；
  SQLite 临时库完成 upgrade、check、downgrade、re-upgrade，最终为
  `20260724_0007 (head)`；已有行升级后日期列为 null，存在日期事实时拒绝有损降级
- 验证：editable 安装和 `pip check` 通过；Ruff 通过；strict mypy 94 文件通过；
  日期链聚焦回归 `417 passed`；正式离线全集
  `1503 passed / 2 deselected`；仓库外插件封锁 DNS 与 socket 后抽取、统一输入、
  收藏写入、Repository、API、检索和计划聚焦回归 `437 passed`。全部最终命令
  0 failed、0 warning
- 纯度与范围：真实模型、地图、网页、对象存储、消息及其他外部 API 调用为 0；
  没有截图/标题白名单、第二套 DTO/解析/repair/Repository/计划服务、AgentRunner、
  ToolRegistry、ModelProvider 或 M1 改动。样本 06 不作为内容正确性 Gate，样本 03
  没有生产特例
- 下一步：等待主控复核迁移安全、严格字段闭合、日期/时刻区分、date-only 计划排除
  和 exact-time 回归后集成。M0 保持完成，M1-0 仍未开始；其第一项强制前置仍是
  `IdempotencyLockRegistry` 有界生命周期修复

#### 2026-07-24｜Event 日期粒度幂等重放 P1 修复｜待主控复测

- 分支与基线：继续使用 `codex/event-date-granularity`，从待修复 HEAD
  `6911a7c7b8353cb34e7e659abac9ab6adbf02251` 开始；未改写、变基、压缩或 amend
  既有提交
- 缺陷复现：新增公开文字消息入口回归后，修复前 date-only Event 首次请求为 200，
  同 Session、相同输入和 idempotency key 的第二次重放为 422，稳定命中
  `event_date_absent_not_classified`；目标用例为 `1 failed`
- 修复：只在 `TextCollectionWorkflow._extraction_from_source()` 现有 EventCandidate
  重建映射中补回 `item.event_start_date` 与 `item.event_end_date`，没有新增服务、
  DTO、转换器、fallback、Prompt、repair、Repository、状态或 M1 能力
- 回归：date-only Event 两次均成功，第二次 `replayed=true`，两次 CollectionItem
  ID、日期和完整公开收藏结果一致，精确 datetime 仍为 null，状态仍为
  `pending_details`；该请求 Provider 只调用 1 次且数据库仍只有 1 条对应收藏
- 兼容与纯度：同一公开测试同时确认 exact-time Event 重放继续为 `active` 且准确
  datetime 不变，Place 重放的 Event 日期与时间字段均为 null；请求 payload 与首次
  持久化 CollectionItem 快照在重放后不变。三个首次请求合计 Provider 3 次，各自
  重放均无额外调用
- 验证：修复后目标用例 `1 passed`；规定聚焦集 `80 passed`；正式离线全集
  `1504 passed / 2 deselected`；仓库外插件封锁 DNS、connect、connect_ex 和
  create_connection 后统一输入 `23 passed`。`pip check`、Ruff、94 文件 strict
  mypy 全部通过；临时 SQLite 的 Alembic 唯一 head 仍为 `20260724_0007`，
  `alembic check` 无待生成操作
- 安全与下一步：所有命令显式使用测试环境；未读取 `.env`，真实模型、地图、网页、
  对象存储、消息及其他真实/付费 API 调用为 0。等待主控重点复测 date-only 重放、
  exact-time/Place 边界和零重复收藏后集成；M0 状态与 M1-0 前置不变

#### 2026-07-26｜模型与富输入超时策略收敛修复｜待主控验收

- 分支与门禁：继续使用 `codex/event-date-granularity`，指定基线与开始 HEAD 均为
  `1c921c54215cdaf56e6ca04e5aeee2b46c5fddc4`；开始工作区干净，Event 日期粒度与
  幂等重放修复提交链完整。Alembic 唯一 head 为 `20260724_0007`
- 配置与 Provider：`MODEL_TIMEOUT_SECONDS` 默认值和最大允许值统一为 30 秒；
  唯一 `OpenAICompatibleProvider` 继续在一次
  `chat.completions.create()` SDK await 外使用一次总墙钟截止，SDK
  `max_retries=0`，一次 chat 只发一次请求。15 秒后、30 秒前的受控逻辑耗时成功，
  到点继续映射唯一 `PROVIDER_TIMEOUT`
- 富输入预算：唯一 `TextCollectionWorkflow` 的既有
  `MAX_RICH_INPUT_WORKFLOW_SECONDS` 从 20 收敛为 60；URL 与图片仍只通过
  `AgentRunService.execute_application()` 建立一次外层预算。initial 和唯一 repair
  位于同一个 operation，initial 消耗后 repair 只使用剩余时间，不重置预算
- 性能与产品语义：20 秒只保留为 URL/图片解析非阻断性能观察目标，不再是统一工作流
  强制失败阈值；30/60 是稳定产品硬兜底，不按固定样本继续上调。Event 日期字段、
  状态、Parser、Prompt、结构抽取、repair 和计划规则均未修改
- 取消、清理与重试：Provider/工作流硬截止继续由 `asyncio.wait_for` 取消并等待活动
  协程；外部 `CancelledError` 原对象传播。图片 timeout、取消和数据库写入 timeout
  继续清理 objects、metadata、temporary、reservation 与未提交业务写入；SDK、
  Provider 和应用层自动重试均为 0
- 离线验证：无索引 editable 安装最终通过，`pip check`、Ruff、94 文件 strict
  mypy 均通过；超时/配置/Provider/图片/抽取/统一输入聚焦 `379 passed`，Event
  检索与计划回归 `86 passed`；正式非真实全集
  `1508 passed / 2 deselected`，默认全集 `1508 passed / 2 skipped`
- 封网与迁移：仓库外 pytest 插件封锁 DNS、connect、connect_ex 和
  create_connection 后聚焦 `251 passed`、非真实全集
  `1508 passed / 2 deselected`；迁移测试 `23 passed`。所有最终测试命令均为
  0 failed、0 warning
- 环境说明：首次 `PIP_NO_INDEX=1` 构建隔离安装因本机未缓存 setuptools/wheel
  构建依赖退出 1；随后只复用本机 Anaconda 已有的 setuptools wheel 与 wheel 包，
  使用 `--no-build-isolation` 完成无网络 editable 安装。没有从外部索引下载依赖
- 复杂度与安全：ModelProvider、OpenAICompatibleProvider、AgentRunner、
  ImageRecognitionService、TextCollectionWorkflow、Parser 与 repair 均保持唯一；
  没有新增 timeout helper、后台任务、样本 03 特例、自动重试、配置入口、迁移或
  M1 代码。Git 不跟踪 `.env`、数据库、缓存、临时脚本或虚拟环境；未读取 `.env`
- 外部调用与下一步：真实模型、地图、网页、对象存储、消息及其他外部 API 调用为
  0。固定真实样本 03 尚需主控离线集成通过后重新取得授权再按 30/60 策略复测；
  M0 保持完成，M1-0 仍未开始，首项前置仍是 `IdempotencyLockRegistry` 有界生命周期

#### 2026-07-26｜富输入截止时间单一归属修复｜待主控验收

- 分支与门禁：开发分支 `codex/rich-input-deadline-convergence` 从指定基线
  `fe93904ad7ede25f5ed43bcb43830f6feadc6fbf` 创建；开始时工作区干净且 HEAD
  精确等于该 SHA。没有读取或修改 `.env`，没有合并 main 或推送
- 超时所有权：URL/图片继续只复用 `AgentRunService.execute_application()` 的
  60 秒外层共享截止，覆盖输入准备、initial、唯一 repair、解析、提交和清理；
  initial 消耗后 repair 只能使用剩余时间。60 秒是正常富输入路径唯一可触达的硬
  截止，20 秒仍只是非阻断性能观察目标
- Provider 安全上限：`MODEL_TIMEOUT_SECONDS` 默认值和最大允许值由 30 秒统一替换为
  75 秒，只作为 Provider/传输层异常安全上限；正常富输入必须先由应用层 60 秒取消
  SDK 请求。SDK `max_retries=0`，外层重试为 0，一次 chat 仍只产生一次非流式 HTTP
  请求，没有 fallback、退避、模式切换或补调用
- 取消与清理：外层取消沿既有调用栈进入唯一 `OpenAICompatibleProvider`，Provider
  原样传播 `CancelledError`；其 `asyncio.wait_for` 等待 SDK 请求取消结束，再由既有
  图片和工作流清理移除 objects、metadata、temporary、reservation 及未提交数据库
  业务写入。离线 MockTransport 用例证明 0.6 秒应用层截止先于 0.75 秒 Provider
  安全上限触发、HTTP 恰好一次、请求收到取消、客户端关闭且业务与存储无残留
- 旧规则与复杂度：删除当前配置、断言、README、MVP 技术方案、阶段校准要求和验证
  报告中的 30 秒正式边界描述，替换为 60 秒单一正常截止与 75 秒异常安全上限；
  没有新增 Deadline/Timeout helper、第二套 Provider、workflow、图片服务、Parser、
  repair、清理机制或后台 Task，净生产复杂度未增加
- 验收 P2 修复：删除
  `test_provider_allows_response_after_application_deadline_before_safety_cap`。该测试重复
  覆盖已有契约，且 60/75ms 外部计时依赖其他测试预热 SDK，单独运行时会因首次懒
  初始化稳定失败；本修复没有通过增加 sleep、放宽容差或放大计时比例规避问题，也
  没有新增替代测试。配置 75 秒边界、Provider 自身截止取消/等待及 TIMEOUT 映射、
  截止前分段响应成功、正式图片工作流 60 秒先取消 75 秒 Provider、单次 HTTP 与
  清理无残留继续由现有独立测试覆盖
- 修复验证与复杂度：按指定清单各执行一次，聚焦组 `379 passed`；Ruff 通过，
  strict mypy 对 94 个源文件无问题；全量离线组
  `1508 passed / 2 deselected`。P2 修复只删除一项测试并更新本交接记录，生产代码、
  配置值和产品文档语义零修改，净测试复杂度下降；没有生产 sleep、特例、skip 或
  放宽断言
- 范围与下一步：Event 日期逻辑、Prompt、数据库模型、迁移和 M1 功能均未修改；真实
  模型、地图、网页、对象存储、消息及其他外部 API 请求为 0。固定样本 03 未执行、
  未标记通过；主控应先离线复核并 ff-only 集成，再单独取得最多两次非流式请求授权，
  保持零重试。若真实同步请求仍超过 60 秒，不再提高上限，后续转 M1 后台 Job

#### 2026-07-26｜Event 日期与富输入截止最终主控验收｜已完成

- 集成：主控确认修复提交 `55ae656bae212c5655694854591d41b1719e3b9f`
  直接包含本地 `main` 基线，工作区干净且提交链无 merge commit；以 `--ff-only`
  集成到本地 `main`，合并前后 tree 一致、无冲突和额外代码变化
- 离线验收：`pip check`、Ruff、94 文件 strict mypy 通过；修复聚焦组
  `379 passed`，正式非真实全集 `1508 passed / 2 deselected`；合并后配置、
  Provider 和统一输入最小检查 `194 passed`。Alembic 唯一 head 保持
  `20260724_0007`
- 复杂度：验收修复只删除一项依赖 SDK 首次懒初始化时序的重复测试，没有增加
  sleep、容差、特例或生产代理。ModelProvider、OpenAICompatibleProvider、
  AgentRunner、ImageRecognitionService、TextCollectionWorkflow、Parser 和 repair
  路径继续各自唯一
- 真实授权：用户明确授权固定样本 03 最多 2 次非流式请求、零重试；实际 initial
  1 次、repair 0 次，底层 HTTP 1 次，没有人工补调用、fallback、退避、模式切换、
  高德、网页或其他外部 API
- 真实结果：统一图片入口约 47.1 秒返回 HTTP 200；识别
  `event_start_date=2026-06-13`、`event_end_date=2026-07-31`，精确开始/结束时刻
  均为空，状态为 `pending_details`。结果正确区分展期日期与每日准确时刻
- 清理与安全：Provider、HTTP client 和应用生命周期正常关闭，后台任务为 0；隔离
  原图、metadata、临时文件、reservation、数据库和 QA 临时根均已清理。报告未记录
  完整请求/响应、Base64、密钥、模型名、endpoint、Authorization、Request ID、
  账号或私人路径
- 结论：当前无未关闭 P0/P1，60 秒应用截止与 75 秒 Provider 异常安全上限的本轮
  真实门禁通过。47.1 秒超过 20 秒性能观察目标且样本量不足，继续作为性能风险；
  若达到 60 秒则转 M1 后台 Job，不再放宽同步时限。当前允许开始 M1-0，首项仍是
  `IdempotencyLockRegistry` 有界生命周期修复

#### 2026-07-26｜M1-0 PostgreSQL 与任务基础｜待主控验收

- 分支与门禁：`codex/m1-0-postgresql-jobs` 从指定基线
  `6dbdbbaa49c8493b425870e2ea74682c6f2c0ca6` 创建；开始时 HEAD、`main` 和
  `origin/main` 均精确等于基线，工作区干净，M0 已完成，Alembic 唯一 head 为
  `20260724_0007`
- 提交：锁修复
  `6bd3d71f2b763e8e4543291aa2517275f084b847`；PostgreSQL
  `8ea7bc454546b35646c62f01ec359d5a16ae91d9`；Job/Worker
  `d86c9f02c0b95048cf5be0af11f0d0c2b912f960`；SSE/Compose
  `61db0b2ff4469d7e311a7fe4b6b117da1da81b9a`；文档提交及最终 HEAD 的完整 SHA
  以最终交接输出和 `git rev-parse HEAD` 为准
- 锁前置：永久锁字典替换为单注册表互斥下的参与者计数生命周期；同用户/键共享
  一把锁，最后持有者/等待者在正常、异常、取消和淘汰竞态后清除。没有 TTL、LRU、
  sleep、后台清扫或第二套幂等服务；10,000 个高基数请求结束后注册表计数为 0
- PostgreSQL 与迁移：正式配置支持 `postgresql+asyncpg` 且 production 拒绝
  SQLite；历史迁移同时兼容 SQLite/PostgreSQL。`0008` 新增 `scheduled_jobs`，
  `0009` 新增既有 AgentRun 子表 `run_events`；唯一 head 为 `20260726_0009`，
  全新升级、current/check、降级 base 和重新升级在 PostgreSQL 16 通过
- Job/Worker/Scheduler：唯一 `JobQueue` 和 `PostgresJobQueue` 使用
  `FOR UPDATE SKIP LOCKED`；支持 queued/running/succeeded/failed/cancelled、用户
  幂等键、5/30 秒有界重试、最多三次执行、取消和 60 秒租约恢复。
  `python -m app.worker` 是唯一 Worker 入口；APScheduler 只创建持久化 Job
- SSE：RunEvent 写入锁定既有 AgentRun 后分配 trace 内 sequence；支持七种公开事件，
  安全摘要不含思维链；`GET /api/v1/agent-runs/{trace_id}/events` 支持
  `Last-Event-ID`。20 个并发事件得到连续唯一的 1..20；重连只补发未确认 sequence；
  跨用户/trace 统一隔离
- 安全：原候选用 `app.domain.public_data` 同时校验内部 Job payload 和公开摘要；
  QA 后续确认这是启发式黑名单设计，已由 2026-07-27 P1 修复记录取代。未读取或打印
  `.env`，真实模型、高德、网页、消息、云和其他外部 Provider 调用均为 0
- 自动化：原候选曾记录 strict mypy 对 108 个源文件通过，但 QA 在精确候选
  `b8bbb8ff366614370e1a45b4eab4922c20617fc9` 实际复现 11 个错误；该原候选
  mypy 结论无效。修复后的真实结果见下一条记录
- Compose：PostgreSQL、API、Worker 均健康；API/Worker 为 uid 10001；`/healthz`
  200；容器迁移为 `20260726_0009 (head)`。扩容两个 Worker 后确定性任务只执行
  一次，最终 `succeeded/attempt=1`；重复创建返回同一 Job 且 replayed；SSE replay
  只返回 sequence 2、3。服务和本次测试卷已正常停止/清除
- 复杂度与唯一性：AgentRunner、ToolRegistry、Provider、Base、Database、
  Repository 家族、JobQueue、Worker 入口、幂等服务和 AgentRun 主记录各保留一套；
  Job/RunEvent 安全规则已收敛，没有生产特例、白名单、重复校验或框架内部代理
- 已知风险：租约恢复是至少一次语义，真实有副作用 handler 必须持有业务幂等键；
  APScheduler 注册需由未来权威业务数据在进程重启时确定性重建；SSE 使用 250 ms
  数据库轮询，尚未做压力测试；Compose 默认口令仅限本机；本轮只验证 PostgreSQL 16
- 下一步：主控按 `docs/technical/M1_0_HANDOFF.md` 复核并交给 QA 独立验收；通过前
  不合并、不推送、不开始 M1-1 或 M1-2

#### 2026-07-27｜M1-0 QA 阻断 P1 修复｜待主控验收

- 分支与门禁：继续使用 `codex/m1-0-postgresql-jobs`，从指定修复基线
  `b8bbb8ff366614370e1a45b4eab4922c20617fc9` 追加提交；开始时工作区干净，
  `main` 与 `origin/main` 均精确为
  `6dbdbbaa49c8493b425870e2ea74682c6f2c0ca6`。未 amend、rebase、squash、合并
  main 或推送
- 三个 P1 提交：取消清理
  `67716ea01f9350e3253bace5370e849e61d018b4`；DML 类型边界
  `85765af6dce984a60541f0b97cd239215a3175bf`；显式公开数据契约
  `2b2f7a3036a411d5a0bd35546f137fd95c1c3a2a`。最终文档提交和最终 HEAD 由开发
  窗口交接输出记录
- 取消清理：锁获取等待和 lease 退出都把参与者清理交给本次调用持有的单个 cleanup
  task，并用 shield 抵御退出阶段的重复取消；调用方在观察 task 结果、确认注册表
  计数更新后才重新抛出最早的原始 `CancelledError`。没有遗留未观察 task，没有
  TTL、LRU、sleep、扫描、后台清扫或第二套锁；数据库唯一约束仍是跨进程边界
- 锁回归：Event 精确协调清理开始与放行，不依赖计时碰运气；覆盖同 key、不同
  user/key、10,000 高基数、异常、等待获取取消、持有期间取消、退出清理阶段连续
  取消和淘汰竞态。聚焦 `9 passed`，每类最后参与者退出后
  `active_key_count == 0`
- mypy 与 SQLAlchemy：原候选 11 个错误全部来自 ORM `AsyncSession.execute()` 对
  DML 返回 `Result[Any]` 的静态类型。新增唯一
  `app.infrastructure.db.dml.execute_dml_rowcount()`，在一处确认
  `CursorResult` 并返回 `int rowcount`；Job 的 CAS/取消/两类租约恢复与 Collection
  的 CAS/删除/Undo 仍通过原 Session 和事务执行。没有 `Any` 返回、错误码关闭、
  mypy 放宽或逐调用类型代理；SQLite Collection/写入回归 `41 passed`，PostgreSQL
  同样通过
- 公开数据契约：删除 `app.domain.public_data`、字段关键词黑名单、Base64 正则猜测
  和对应重复测试。Job payload 现在是仅供 JobQueue/Worker 使用的有界内部 JSON；
  Job 公开结果为唯一 `JobResultSummary`。七类 RunEvent 各有显式冻结 summary
  模型，Repository 持久化与 SSE 共用同一类型化序列化函数，不接受任意 dict
- 安全行为：`apiKey`、`access_token`、`modelResponse`、Prompt、Authorization、
  Cookie、Header、私有文件 key/路径都没有公开 summary 字段；extra-forbid 在模型
  构造前拒绝。合法 64 位 lowercase `content_sha256` 在 Job 结果或
  `result.updated` 明确字段可保存、重放。内部 payload 即使含同名内部键也不会
  自动进入 Job 结果、RunEvent 或 SSE
- 静态与离线结果：项目 `.venv` 的 `pip check`、Ruff 和 strict mypy 全部退出 0，
  mypy 检查 108 个源文件；指定 P1 聚焦 `37 passed`，加既有 SQLite Run tracking
  为 `61 passed`。将 `PytestUnhandledThreadExceptionWarning` 升级为 error 的非真实
  全集为 `1546 passed / 8 skipped / 2 deselected`，未观察到 aiosqlite 收尾
  warning；Core `120 passed`，SQLite 迁移 `23 passed`，Alembic 唯一 head 为
  `20260726_0009`
- PostgreSQL 16：一次性本地容器完成全新 upgrade/current/check、downgrade base、
  re-upgrade/current/check；PostgreSQL migrations、双 Worker、Job 幂等/三次重试/
  取消/过期租约、并发 RunEvent sequence、用户/trace 隔离、SSE replay、内部
  payload/公开摘要隔离、合法 SHA-256 与锁取消聚焦合计 `17 passed`
- Compose：无真实 Provider 配置，重新构建后 PostgreSQL、API、两个 Worker 全部
  healthy；API/Worker UID 均为 10001，`/healthz` 为 200，迁移为
  `20260726_0009 (head)`。重复任务返回相同 ID 和 `replayed=true`，两个 Worker
  最终只完成一次（`succeeded/attempt=1`）；`Last-Event-ID: 1` 只重放 sequence
  2、3，合法 SHA-256 保留。日志未命中 Provider、Authorization、Cookie 或内部
  payload 哨兵；Compose 服务、网络与测试卷已正常停止并清理
- 复杂度、范围与风险：AgentRunner、ToolRegistry、Provider、Base、Database、
  Repository 家族、JobQueue、Worker、RunEvent、AgentRun 和幂等服务继续各一套；
  没有新增黑名单、通用安全代理、重复校验器、生产特例或后续业务 Job。租约仍为
  至少一次恢复，未来有副作用 handler 必须自带业务幂等；APScheduler 注册仍需未来
  从权威数据重建；SSE 250 ms 轮询尚未压力测试。状态继续“待主控验收”，不进入
  M1-1/M1-2

#### 2026-07-27｜M1-0 PostgreSQL 与任务基础｜主控验收通过

- 验收候选：`55458db5ae857c2dae6bdfe66622a9b835e425fc`；基线、`main` 与
  `origin/main` 在集成前均为 `6dbdbbaa49c8493b425870e2ea74682c6f2c0ca6`，
  提交链线性且无 merge commit
- 三个 QA P1 已关闭：取消发生在锁退出清理期间时仍等待唯一 cleanup task 完成并
  原样传播取消，仓库外竞态探针结束后 `active_key_count == 0`；SQLAlchemy DML
  rowcount 只经过一个类型边界，strict mypy 对 108 个源文件通过；内部 Job payload
  与显式 Job/RunEvent 公开摘要分离，旧关键词黑名单和 Base64 猜测已删除
- 独立离线结果：`pip check`、Ruff、mypy 均通过；聚焦回归 `60 passed`；普通及
  进程级封网非真实全集均为 `1546 passed / 8 skipped / 2 deselected`；Core
  `120 passed`；SQLite 迁移 `23 passed`；Alembic 唯一 head 为
  `20260726_0009`
- PostgreSQL 16：显式组 `8 passed / 1548 deselected`，覆盖迁移往返、双 Worker、
  Job 幂等/重试/取消/租约恢复、并发 RunEvent、用户隔离、类型化摘要和 SSE replay
- Compose：PostgreSQL、API、两个 Worker 均 healthy，API/Worker 均以 uid 10001
  运行；`/healthz` 200；迁移位于 head；重复任务同 ID 且只执行一次，
  `succeeded/attempt=1`；`Last-Event-ID: 1` 仅返回 sequence 2、3；日志无内部
  payload、凭据或真实 Provider 标记；本轮资源已全部清理
- 安全与复杂度：未读取 `.env`，真实模型、地图、网页、消息和付费 API 调用均为
  0；AgentRunner、ToolRegistry、Provider、Database、Repository、JobQueue、
  Worker、RunEvent、AgentRun 和幂等服务继续各一套，没有新增黑名单、生产特例、
  重复校验器或后续业务 Job；当前无未关闭 P0/P1
- M1-0 允许完成并集成。保留的非阻断风险为至少一次租约要求未来有副作用 handler
  自带业务幂等、APScheduler 注册需从权威数据重建，以及 SSE 250 ms 轮询尚未压力
  测试。当前唯一允许阶段改为 M1-1；M1-2 及后续阶段未开始

#### 2026-07-27｜M1-1 Web 会话与 Demo 身份｜待主控验收

- 分支与门禁：`codex/m1-1-web-session` 从指定基线
  `272c710259862566586b968f87a64fa1e73e42a8` 创建；开始时本地 `main`、
  `origin/main` 和 HEAD 均精确等于基线，工作区干净，Alembic 唯一 head 为
  `20260726_0009`
- 提交：持久 Web Session
  `97c89d0ea1d84ffcd89de1190455f5a926392ad2`；浏览器 Demo 沙盒
  `2ad2c501f0e288bb59c64954e52b226c2a1b312b`；安全与隔离测试
  `bdad9e29a628c2b8e39dd06ed84df71802ea6767`；并发恢复与 Cookie 生命周期修复
  `4aca9bf7990af21ba3e7787aa2ddda857daba870`；文档提交及最终 HEAD 以最终交接输出
  和 `git rev-parse HEAD` 为准
- 身份与安全：建立唯一 `BrowserSession`、`CurrentPrincipal`、
  `WebSessionService` 和 SQLAlchemy Repository；既有 `Session` 继续只表示
  Agent/消息会话。服务端生成 256-bit Session Token，CSRF 通过带版本化领域上下文
  的 HMAC-SHA-256 确定性派生，数据库只保存两者哈希；Cookie 固定 HttpOnly、
  SameSite=Lax、Path=/、无 Domain，production 强制 Secure；写请求统一使用
  `X-CSRF-Token`
- 生命周期：真实会话保留默认/上限 30 天能力但没有公开登录入口；Demo 默认 2 小时、
  上限 24 小时；绝对过期采用 `[created_at, expires_at)`，不滑动续期。当前设备可
  撤销；普通 Demo 恢复以只读方式保持同一沙盒、稳定 Session Token 和可重建 CSRF，
  多路跨进程恢复不会相互失效。恢复 Cookie 的 Max-Age/Expires 使用数据库剩余寿命
- Demo 隔离：删除运行时固定 Demo User；每个 Cookie Jar 在 Demo 数据库创建独立
  User、Web Session 和消息 Session。API 从已验证 Session 得到 `user_id` 与数据库，
  跨用户 Message、Collection、Source、AgentRun、RunEvent、Job 和 Undo 继续统一
  所有权过滤，跨用户与不存在资源保持相同 404
- 物理隔离：应用使用两个独立 `Database` 实例与两个私有存储根；production 启用
  Demo 时必须显式配置不同 PostgreSQL 目标和不同存储根。Compose 提供正式与 Demo
  PostgreSQL，并在 API 启动前分别迁移到新唯一 head `20260727_0010`
- ChannelIdentity：只定义供应商无关的 `channel + subject` 领域对象和
  `resolve_user_id` Repository 协议；因当前没有持久化消费者而不建表。微信字段、
  登录链接、绑定码、兑换和 OAuth 全部延后到 M2-2
- 自动化：editable 安装与 `pip check` 通过；Ruff 通过；strict mypy 对 115 个
  源文件通过；严格线程告警的非真实全集和仓库外 DNS/TCP 封锁全集均为
  `1559 passed / 10 skipped / 2 deselected`；身份/迁移封网聚焦 `34 passed`
- PostgreSQL 与 Compose：PostgreSQL 16 标记组 `10 passed / 1561 deselected`，
  覆盖迁移往返、8 路 API 稳定恢复、Session 并发、双库、JobQueue、RunEvent 和
  SSE。Compose 两库、API、Worker 全部 healthy，API/Worker uid 均为 10001，两库均在
  `20260727_0010`；Demo 启动后正式库 User/Web Session 为 0，Demo 库各为 1；
  日志不含凭据或 Provider 调用，本轮容器、网络、镜像和卷已清理
- 安全与复杂度：日志、异常、repr、OpenAPI 和公开响应不含 Session Token、Cookie、
  哈希或 `user_id`。AgentRunner、ToolRegistry、Provider、User、消息 Session、
  Database 类型、Repository 家族、AgentRun、RunEvent、JobQueue 和业务 API 均继续
  唯一；没有白名单、固定 Token、重复路由校验或认证中间件
- 调用与环境：真实模型、高德、网页、对象存储、消息、微信和付费 API 调用总数为
  0；未读取或提交 `.env`
- 风险与下一步：过期 Session 清理任务尚未实现；ChannelIdentity 持久化等待
  M2-2。事件门控的 SQLite/PostgreSQL 并发测试已证明所有恢复响应凭据均可用，当前
  无未关闭 P0/P1。主控按 `docs/technical/M1_1_HANDOFF.md` 独立验收；通过前当前
  允许阶段仍为 M1-1，不合并、不推送、不开始 M1-2

#### 2026-07-27｜M1-1 Web 会话与 Demo 身份｜主控验收通过

- 验收候选：`aaa05fb63dd0059af6b994157cd830a39101cded`；指定基线、本地
  `main` 与 `origin/main` 均为
  `272c710259862566586b968f87a64fa1e73e42a8`，提交链线性且无 merge commit
- 缺陷关闭：普通 Demo 恢复不再轮换数据库凭据，Session Token 稳定，CSRF 由该
  Token 通过单一领域分离 HMAC 路径确定性派生；恢复 Cookie 使用数据库剩余寿命，
  不滑动续期。独立仓库外探针连续 5 轮、每轮 16 个客户端并发恢复，全部 201，
  随后读取全部 200、CSRF 写边界全部正确，数据库始终只有一组 Demo 身份
- 静态与离线：`pip check`、Ruff 和 strict mypy（115 个源文件）通过；身份、迁移
  聚焦 `34 passed`；严格线程告警非真实全集
  `1559 passed / 10 skipped / 2 deselected`；默认全集
  `1559 passed / 12 skipped`；Core `120 passed`；DNS/TCP 封锁聚焦
  `34 passed`，封网非真实全集再次
  `1559 passed / 10 skipped / 2 deselected`
- PostgreSQL 16：标记组 `10 passed / 1561 deselected`，覆盖迁移往返、8 路 API
  稳定恢复、Web Session 并发、双库、JobQueue、RunEvent 和 SSE；Alembic 唯一
  head 为 `20260727_0010`
- Compose：使用独立项目、端口、镜像和临时卷重新构建；正式库、Demo 库、API 和
  Worker 全部 healthy，API/Worker UID 均为 10001，两库均位于
  `20260727_0010`。容器内 8 路并发恢复全部可用；Demo 写入后正式库
  User/Session/WebSession 均为 0，Demo 库各为 1；日志凭据扫描通过，测试资源已
  全部清理
- 安全与复杂度：数据库只保存 Token/CSRF 哈希，Cookie、CSRF、过期、撤销和身份
  路由保持单一边界；被替代的凭据更新路径已经删除，没有进程锁、sleep、重试、
  Token 白名单、第二套 Session/CSRF 或前端串行化补丁。未读取 `.env`，真实模型、
  地图、网页、消息和付费 API 调用均为 0
- 结论：当前无未关闭 P0/P1。保留的非阻断风险为过期 Session 清理任务尚未实现，
  ChannelIdentity 持久化继续等待 M2-2。M1-1 允许完成并集成，当前唯一允许阶段
  改为 M1-2；M1-3 及后续阶段未开始

#### 2026-07-27｜正式 UI/UX 方向基线 v0.2｜方向评审

- 范围：在 M1-2 正式实现前补充响应式 UI/UX 方向基线；本轮只新增独立静态评审稿
  与产品方向文档，不接入 API，不提前实现 M1-3 至 M1-8 的业务功能
- 产物：新增 `docs/product/拾光_UI_UX方向_v0.2.md`，记录设计命题、色彩与排版
  Token、移动/桌面框架、页面方向、共同状态语言、可访问性要求和 M1-2 采用边界；
  新增 `prototypes/ui-direction/`，用于在 390px、响应式和 1440px 模式下评审
- 方向：正式产品不保留旧 UX Lab 外壳或模拟手机边框；移动端采用顶部上下文、单列
  主内容与底部四项导航，桌面端采用左侧主导航、中央任务区和按需右侧上下文区；
  延续纸白、深绿和青柠配色，并以“拾光轨迹”作为计划和执行状态的识别元素
- 产品原则：收藏优先、来源和风险透明、操作可逆、重要行为需确认、异常可恢复；
  明确补充快捷任务入口、跨城市收藏状态、外部地点动作、提醒单独授权、完成反馈
  三态和分享脱敏预览
- 输入框处理：Agent 输入区进入主任务流，桌面端位于任务入口下方，移动端作为内容
  卡片自然滚动；不再把对话输入框固定在 M02 页面底部，底部固定区域只保留主导航，
  计划确认等明确终局动作才使用 Sticky CTA
- 验证：`node --check prototypes/ui-direction/app.js` 与 `git diff --check` 通过；
  浏览器实测 390×844 和 1440×1000 无横向溢出，移动/桌面导航按断点正确切换，
  390px 内置预览宽度、计划 Sticky CTA 和底部导航宽度正确；Agent、收藏、计划、
  状态与权限四个视图可切换，浏览器控制台无 warning/error
- 阶段状态：当前唯一允许阶段仍为 M1-2；本方向稿需经用户确认后作为 M1-2 的视觉
  与交互基线，M1-2 正式产品实现尚未开始
- v0.2 校准：根据用户评审重新读取 `prototypes/ux/` 原始设计；保留 v0.1 的
  响应式布局、任务入口与产品状态 UX，视觉恢复原版深湾绿主输入卡、纸面网格、
  宋体展示标题、线性 SVG 图标、克制青柠和移动端浮动导航，删除通用工作台式的
  大号入口卡与 Unicode 功能符号

#### 2026-07-27｜完整 UI/UX 原型 v2｜产品与交互评审

- 范围调整：根据用户评审，交付目标由“方向展示”升级为基于原 8 页原型的完整
  可点击 UI/UX 原型；`prototypes/ux/` 继续作为正式评审入口，方向稿只保留为
  视觉决策记录
- 响应式：新增“移动 H5 / 桌面 Web”画布切换；移动端保持 390×844、顶部上下文和
  底部浮动四项导航，桌面端使用 960×760 画布、左侧四项主导航和中央任务区；两端
  共用页面、状态名称和产品动作
- Agent 与收藏：M01 增加两个明确任务入口；M02 增加动态标题、三阶段识别进度、
  待补充与失败分离、撤销后恢复，输入框改为内容流内定位；M03 增加跨城市筛选、
  当前计划资格及排除原因；M04 增加任意分店、以上都不是、字段编辑、删除和返回
  原对话上下文
- 计划与执行：M05 使用“预算未设置”，增加匹配度解释、风险、备选、可选延伸、
  外部地点原因/替换/删除/收藏和 Sticky 确认；拒绝外部补充后进入“仅用收藏”
  轻量方案而非错误；M06 确认后不自动提醒，补齐提醒单独授权、版本历史、取消计划、
  分享预览/管理以及已完成、部分完成、未完成三种反馈后续
- 我的与分享：M07 记忆展示来源、创建时间、最近使用和影响计划，支持修改、停止
  推荐和删除，微信入口改用用户语言；M08 增加最后更新时间、失效时间，主操作改为
  “查看路线”，保留有效、取消、关闭和失效四态
- 文档：新增 `docs/product/拾光_UI_UX完整原型_v2.md` 问题覆盖矩阵，更新
  `prototypes/ux/README.md`
- 验证：`node --check prototypes/ux/app.js` 和 `git diff --check` 通过；浏览器
  验证 8 页默认态及全部 38 个状态均可渲染、无横向溢出；关键点击分支覆盖外部授权
  拒绝、任意分店、提醒授权、分享预览/管理、三态反馈和记忆详情；移动 390px
  评审页无页面横向溢出，桌面画布正确显示左侧导航；控制台无 warning/error
- 视觉校准：清除评审设备框、浏览器默认按钮、选中态、主按钮和深色内容面的近黑
  边框/填充；评审框改为浅灰绿边界，产品深色实心面统一使用深湾绿。浏览器重新
  扫描 8 页全部 38 个状态，产品画布内深色边框命中为 0，交互结构和 UX 状态不变
- M03 信息降噪：将原先同时平铺的城市、收藏状态、计划资格和场景标签收敛为一组
  主状态切换与一个按需展开的筛选面板；默认首屏只显示本次深圳计划的参与摘要、
  搜索和三个高频状态，跨城市与排除原因等既有 UX 信息仍可查看
- M05 层级校准：保留主方案摘要、匹配度和备选入口，但将摘要高度压缩至约 112px，
  备选入口压缩为单行；时间光轨增加日期、站点数和步行摘要，并强化纵向轨道。移动
  与桌面默认视图均可在首屏范围呈现 3 个行程节点，风险、来源和外部地点操作不变
- 紧凑度校准：M05 展开备选后删除重复标题，入口与备选卡间距收至 6px，卡片高度
  收至 56px；M01 主输入卡压缩至约 214px，减少标题、输入框和附件入口间的空白，
  同时保留附件操作 44px 点击区域。两页共 9 个状态及桌面布局均无横向溢出
- 页面节奏校准：M01 与 M03 增加页面级布局边界，将同组控件间距统一为 8px、
  板块间距统一为 16px、标题到内容统一为 8px；消除 M03 搜索区底部与下一标题
  顶部叠加出的 34px 空档。两页共 6 个状态和桌面布局无溢出，控制台无错误
- M01 内部对齐：主输入卡标题与输入框整体下移 4px，附件入口视觉间距继续压缩，
  但完整保留 44px 点击范围；三个快捷条件改为 32px 视觉高度和 10px 圆角矩形，
  外层点击范围仍为 44px。M01 三个状态及桌面布局无溢出
- M02 输入坞：根据最新评审将内容流内输入框改为独立底部输入坞；移动端距底部导航
  8px，桌面端距内容画布底部 18px、距左侧导航 32px，消息区分别预留 154px 与
  96px 底部安全空间。六个状态位置稳定，发送交互正常，控制台无错误
- 正式前端校准：统一方向稿与完整原型的字号约束，正式正文和核心控件不低于 14px、
  辅助信息不低于 12px；弱化文字 Token 在白底对比度提高到 5.12:1，危险文字 Token
  与方向稿一致。评审原型补齐视图/状态选中语义、具体图标按钮名称、表单名称和
  autocomplete，并把主要触控目标统一到至少 44px
- 评审结论：用户已确认本完整原型作为 M1-2 视觉与交互基线。正式产品只提取内层
  产品界面、设计 Token 和交互规则，不复制评审工作台、模拟设备边框、固定 Mock
  数据或原型脚本；正式路由必须使用 Next.js Link
- 阶段状态：当前唯一允许阶段仍为 M1-2，正式 Next.js 产品实现尚未开始

#### 2026-07-27｜M1-2 正式前端基础｜待主控验收

- 分支与基线：`codex/m1-2-frontend-foundation` 从指定
  `97addee78dd8791ec0671213f7f07892a8c8d217` 创建；开始时工作区干净，本地
  `main` 精确等于指定基线并包含 `origin/main`
  `1b471c704b3e63f82866dbabaa25040d43a05048`，两者差异只有已确认 UI/UX 基线；
  M1-2 是唯一允许阶段，`frontend/` 尚不存在，M1-3 及后续未开始
- 工程与路由：在 `frontend/` 建立 Next.js 16.2.12 App Router、React 19 与
  TypeScript strict 工程；只使用 npm 和一个 `package-lock.json`。根路径重定向到
  `/agent`，`/agent`、`/collections`、`/plans`、`/me` 四个空业务路由支持直达、
  刷新和浏览器前进后退；导航全部使用 Next.js `Link` 并准确设置
  `aria-current="page"`
- 设计与响应式：`styles/tokens.css` 是颜色、字体、字号、间距、圆角、阴影、层级、
  动画、布局和 44px 触控尺寸的唯一 Token 来源；标题使用宋体系统栈，正文使用
  无衬线系统栈。移动端为全屏 H5、浮动四项底部导航与安全区；768–1199px 使用
  左侧导航和收敛主内容；1200px 起按需显示右侧上下文区。正式界面只提取原型内层
  视觉规则，没有评审工作台、设备边框、页面目录、原型脚本或 Mock 业务数据
- 公共入口：`lib/api-client.ts` 是唯一 Fetch/API Client，集中同源 Base URL、
  `credentials: include`、超时、外部取消、稳定 HTTP/网络/解析错误和可选
  `X-CSRF-Token`；不记录 Cookie、CSRF、请求正文、异常原文或敏感响应。
  `lib/sse-client.ts` 是唯一实时连接实现，使用 Fetch 流支持递增 sequence、
  `Last-Event-ID` 重放、重复序列过滤、有限重连、断开/错误状态、终态关闭与取消
- 状态与可访问性：提供 Loading、Empty、Error、Offline/Disconnected 和 Retry
  Action，App Router 页面级 `error.tsx`、`loading.tsx`、`not-found.tsx`；提供
  Skip Link、可见 `focus-visible`、主 landmarks、单一 H1 层级、SVG 图标语义、
  `aria-live`/`aria-busy`、`prefers-reduced-motion` 和强制 label/name/autocomplete
  的基础输入组件
- 安装与静态检查：Node 25.8.0、npm 11.11.0；首次安装因用户全局 npm 缓存历史
  root 所有权失败，未修改全局权限，改用仓库外临时缓存成功。最终 `npm ci
  --ignore-scripts` 通过；`npm run lint` 与 `npm run typecheck` 均退出 0；
  `npm audit --omit=dev --audit-level=high` 为 `found 0 vulnerabilities`
- 自动化与构建：Vitest + Testing Library 是唯一组件测试栈，`npm test` 为
  `22 passed`，覆盖导航/aria-current、统一状态、Retry、表单基础、API 错误/超时/
  取消/CSRF/凭据/脱敏，以及 SSE sequence/replay/重连/断开/取消。`npm run build`
  成功，7 个静态页面生成；Playwright 是唯一浏览器测试工具，`13 passed`
- 响应式与视觉：Playwright 覆盖 320、390、768、1024、1440px，五档均无横向
  溢出，当前导航准确，所有可见主导航目标至少 44×44px，四路由直达/刷新、键盘
  Skip Link、浏览器前进后退和减少动画通过，页面控制台错误为 0；另对 390×844
  和 1440×1000 截图人工复核，未发现遮挡、设备外壳或布局漂移
- 对比度与安全：普通 Ink、Muted、Bay 文字在 Paper 上对比度分别为
  15.60:1、6.04:1、6.20:1，深湾绿按钮白字为 10.00:1；生产浏览器静态资源未命中
  密钥或本机路径。Git 未包含 `.env`、数据库、缓存、依赖、截图、测试报告或构建
  产物，学习参考目录、后端代码与迁移均未修改
- 复杂度与范围：API Client、SSE Client、Token、导航、状态体系和测试工具各只有
  一套；没有 M1-3 输入/URL/截图、M1-4 收藏与消歧、M1-5 计划、真实“我的”、登录、
  微信、后端接口、数据库、第三方 API、部署或消息发送。未读取 `.env`，真实模型、
  高德、网页、对象存储和付费调用为 0
- 已知风险：当前只在 macOS、Node 25.8.0 和 Chromium 145 验证，未覆盖 Node 20/22、
  Windows/Linux、Safari/Firefox 或真实后端联调；Next.js 服务器内部生成元数据会
  记录构建工作目录，但未进入浏览器静态资源且 `.next` 不提交。完整 npm audit 的
  剩余告警仅来自开发期 ESLint 依赖链；生产依赖 audit 为 0
- 下一步：主控使用本记录命令独立复测并检查阶段范围、唯一公共入口和净复杂度；
  通过前不合并、不推送、不开始 M1-3

#### 2026-07-27｜M1-2 主控 QA 修复｜待主控验收

- 分支与提交：在 `codex/m1-2-frontend-foundation` 的候选提交
  `493a92099c294d3b0e922f1b44d963692c9509e6` 上修复；本记录与修复代码位于同一个
  独立 QA 修复提交，完整 SHA 见阶段最终交接
- API Client：唯一 `lib/api-client.ts` 继续使用同一个 `AbortController` 和总截止；
  cleanup 延后至响应状态和正文消费全部结束。响应头返回后正文悬挂会稳定映射
  `timeout`，正文阶段外部取消映射 `aborted`，损坏 JSON 保持
  `invalid_response`；自动化确认超时/取消后定时器归零且外部监听器移除
- SSE Client：唯一 `lib/sse-client.ts` 在既有有限重连边界内把未知 Fetch/Reader
  传输异常收敛为 `SseClientError("network_error", null)`；最终错误不携带原始消息、
  URL、endpoint 或传输细节，`http_error`、`invalid_event`、`disconnected`、取消、
  Last-Event-ID、序列去重和终态行为不变
- 触控与浏览器验证：品牌图形及文字视觉尺寸不变，仅把品牌链接有效高度提升至
  44px；Playwright 改为检查 App Shell 内全部可见产品链接和按钮，不包含 App Shell
  外的 Next.js 开发工具。320、390、768、1024、1440px 均无横向溢出，13 个 E2E
  全部通过，控制台错误为 0，键盘焦点、`aria-current`、前进后退和 reduced motion
  保持通过
- 完整验证：使用仓库外临时 npm 缓存执行 `npm ci --ignore-scripts` 成功；
  `npm run lint`、`npm run typecheck`、`npm run build` 均退出 0，7 个静态页面生成；
  Vitest 3 个文件共 `27 passed`，Playwright `13 passed`；
  `npm audit --omit=dev --audit-level=high` 为 `found 0 vulnerabilities`
- 范围与冗余：API Client、SSE Client、Token、导航和状态体系仍各只有一套；测试
  全部使用 Mock/Fake 或本地 Next 服务，没有真实 API、模型、地图、网页或付费调用。
  后端文件与迁移无变化；Git 不包含 `.env`、`node_modules`、`.next`、截图、测试
  报告或构建产物；未实现 M1-3 或后续业务
- 已知风险：本次仍只在 macOS、Node 25.8.0、npm 11.11.0 与 Chromium 145 验证，
  未新增 Node 20/22、Windows/Linux、Safari/Firefox 或真实后端联调覆盖；开发依赖
  完整 audit 仍有既有 ESLint 依赖链告警，但要求的生产依赖 audit 为 0
- 阶段状态：M1-2 保持“待主控验收”，当前唯一允许阶段仍为 M1-2；M1-3 未开始

#### 2026-07-27｜M1-2 正式前端基础｜主控验收通过

- 集成：主控确认修复提交
  `8d17d74f264dcfc21cd6280452cd42d73c4dcc93` 直接继承初版提交
  `493a92099c294d3b0e922f1b44d963692c9509e6` 和 UI/UX 基线
  `97addee78dd8791ec0671213f7f07892a8c8d217`；工作区干净、提交链线性，已将
  `codex/m1-2-frontend-foundation` 纯快进集成到 `main`
- P1/P2 关闭：独立仓库外用例确认 API 总截止覆盖响应正文消费，正文悬挂映射
  `timeout`；SSE Fetch/Reader 原始异常收敛为不含传输细节的
  `SseClientError("network_error")`。品牌链接有效高度达到 44px，根 README 与
  前端 README 的阶段状态一致
- 独立快照：Node 25.8.0、npm 11.11.0；`npm ci --ignore-scripts`、lint、
  typecheck、build 全部退出 0；Vitest `27 passed`，主控附加边界测试
  `2 passed`，Playwright `13 passed`；生产依赖 audit 为 0
- 浏览器：320、390、768、1024、1440px 自动化通过；主控另在 390×844 和
  1440×900 实际渲染检查四个正式路由，未发现横向溢出、重复 ID、小于 44px 的
  App Shell 交互目标、控制台 warning/error 或视觉阻断
- 范围、安全与复杂度：继续只有一套 API Client、SSE Client、设计 Token、导航和
  状态体系；未修改后端与迁移，未实现 M1-3 或后续业务；未读取 `.env`，未调用
  模型、地图、网页、对象存储或其他真实/付费 API，未提交依赖、构建和测试产物
- 非阻断风险：完整开发依赖 audit 仍有 9 个 high，均位于既有 ESLint/minimatch
  开发依赖链，生产依赖 audit 为 0；尚未覆盖 Node 20/22、Windows/Linux、
  Safari/Firefox 或真实后端联调
- 结论：当前无未关闭 P0/P1，M1-2 完成；当前唯一允许阶段改为 M1-3 Agent 与内容
  导入页面，M1-3 尚未开始，M1-4 及后续阶段不得提前开发

#### 2026-07-27｜M1-3 Agent 与内容导入页面｜待主控验收

- 分支与基线：`codex/m1-3-agent-import`，精确继承
  `d1832e9ae8355fe1e58faae0e101b9f8e0a4d2c8`
- 后端：消息提交收敛为 `202 Accepted`，复用唯一 JobQueue、Worker、AgentRun、
  RunEvent 与 TextCollectionWorkflow；新增权威结果和当前对话查询，并在既有
  CollectionWriteService 增加公开恢复动作
- 前端：正式 M01/M02 产品内层支持 Demo Session 创建/恢复、内存 CSRF、文字、
  HTTP(S) URL、JPEG/PNG/WebP、SSE 产品阶段、有限重连、终态权威结果、修改、
  撤销、恢复、继续添加和默认折叠的安全工具步骤
- 状态机：`idle → submitting → queued/processing → saved |
  pending_selection | pending_details | failed | undone`；SSE 不推测收藏内容，
  成功只由终态结果查询触发
- 迁移：新增 `20260727_0011`，仅为 `collection_items` 保存删除前精确状态；
  现有表无法在 `active`、`pending_selection`、`pending_details` 等状态间完成
  无损恢复；Alembic 保持单一 head
- 验证：后端 pip、Ruff、mypy、core 120 项、迁移 23 项及完整离线回归通过；
  前端生产依赖 audit 0、lint、typecheck、29 项 Vitest、生产构建通过；
  Playwright 14 项通过，其中一项连接真实 FastAPI 与离线 Fake Provider，覆盖
  首次进入、识别、权威收藏、修改、撤销、恢复和继续添加
- 安全与幂等：Job payload 只含安全 ID 和输入类型，图片/Base64、正文、URL、
  Cookie、CSRF、存储 key 与供应商响应不进入任务载荷或公开工具 DTO；同一用户、
  Session 和幂等键复用 Message、Job、Source、文件及收藏；原始 HTML 按文本渲染
- 范围：未实现 M1-4 收藏库/完整详情/候选消歧、M1-5 计划、真实登录、微信、
  分享、提醒或“我的”业务；未调用真实或付费 API，未合并、未推送
- 已知风险：截图一旦完整写入私有存储即进入既有 30 天保留策略；后台识别失败
  不产生临时文件或重复文件，但已登记原图不会立即物理删除。尚未覆盖 Node 20/22、
  Windows/Linux、Safari/Firefox 或生产 PostgreSQL 浏览器联调
- 下一步：主控独立复核接口、刷新/断线/重复提交、安全 DTO、恢复迁移、响应式和
  真实 FastAPI 离线浏览器闭环；验收前不开始 M1-4

#### 2026-07-27｜M1-3 主控 QA 缺陷修复｜待主控验收

- 分支与边界：在 `codex/m1-3-agent-import` 候选提交
  `d1daa7354d3ae63dd71972cf6a6631c968637c1b` 上修复；继续只处理 M1-3，
  未合并、未推送、未读取 `.env`，未实现 M1-4 或调用真实模型、地图、网页与付费
  API
- Worker 默认启动：无模型配置时不再构造 Provider，API、主/演示 PostgreSQL 与
  Worker 均保持 healthy；`content.import` 使用既有工作流收敛为
  `failed / MODEL_PROVIDER_NOT_CONFIGURED`，不会让 Worker 退出或留下永久 queued
  Run；完整配置仍只构造既有 `OpenAICompatibleProvider`
- 租约：唯一 `JobQueue` 增加通用 `renew_lease`，唯一 `JobWorker` 在 Handler
  生命周期内按 20 秒心跳续租；完成、异常、取消与失去所有权都会停止心跳，真实
  失联仍由原 `recover_stale` 恢复。PostgreSQL 回归及 Compose 实测均证明处理跨过
  原租约边界时第二个 Worker 不会执行 Handler
- 提交一致性：Message、queued AgentRun、Source/私有文件准备完成后若 Queue 创建
  失败，会先查询 trace 处理“响应丢失但 Job 已创建”，确认无 Job 才通过既有
  Repository 补偿 Message、Run、RunEvent、Source 与文件；同 key 重试继续复用
  原任务或确定性重建，不重复收藏
- 图片取消：既有图片签名、解码与推理图准备移出事件循环执行，保持同一校验和存储
  边界，同时确保外层工作流截止可以及时取消 Provider 请求和进入原清理路径
- 前端：同一输入在不确定网络失败后的重试复用 idempotency key，只有正文变化、
  选择新文件或“继续添加”才换 key；统一 operation generation 管理 Session 恢复、
  新提交、权威结果与唯一 SSE Client，迟到恢复/响应不能覆盖新 Run，新 Run 前
  取消旧 SSE
- 多结果与可访问性：不再使用 `collections[0]`，一次导入的所有收藏均显示各自
  状态，并可按具体收藏修改、撤销与恢复；主输入和快速编辑补齐稳定
  `name`/`autocomplete`，“继续添加”和“补充文字”回焦主输入，失败提示只保留
  一处 live region
- Compose：从干净快照、不使用 `--env-file` 构建；PostgreSQL、Demo PostgreSQL、
  API、Worker 全部 healthy，API/Worker 重启计数为 0。分进程离线 Provider
  `content.import` 得到 succeeded，`Last-Event-ID` 仅重放后续 sequence；短租约
  双 Worker 验证执行计数为 1。默认无模型导入得到安全失败终态
- 验证：后端 `pip check`、Ruff、mypy、完整离线回归、core、迁移和 11 项真实
  PostgreSQL 标记测试通过；前端生产依赖 audit 为 0，lint、typecheck、34 项
  Vitest、build 通过；Playwright `14 passed`，真实 FastAPI + 离线 Fake 闭环保持
  通过
- 迁移与冗余：本次不新增迁移，Alembic 仍为单一
  `20260727_0011` head；没有新增第二套 Provider、JobQueue、Worker、AgentRunner、
  ToolRegistry、workflow、SSE Client、Repository、幂等或 Undo/Restore 系统
- 阶段状态：M1-3 继续为“待主控验收”；主控复测通过前不开始 M1-4

#### 2026-07-27｜M1-3 多收藏并发状态覆盖 P1 修复｜待主控验收

- 修复基线：`da60a6db0cdf450f1dc4630166e44f426d24eed1`；只修改 M1-3
  Agent 前端、聚焦测试和交接记录，后端接口、数据库与迁移均未变化
- 状态收敛：删除基于闭包旧 `result` 构造完整快照并覆盖状态的路径；收藏响应现在
  只通过 `setResult(current => ...)` 合并到 React 提供的最新结果
- 响应归属：每次修改、撤销、恢复记录现有 operation generation、trace id 和
  collection id；成功响应只有三者仍属于当前结果时才替换对应项，响应 item id
  不匹配时不写入
- 生命周期：继续添加和新 Run 沿用既有 generation 失效旧请求；旧操作迟到成功
  不会恢复已清空结果，迟到失败不会覆盖新 Run 状态或反馈
- 并发：不同收藏的函数式 updater 可按任意响应顺序组合并保留两项最终状态；同一
  收藏继续携带既有 `expected_version`，没有新增前端版本规则、全局禁用或顺序等待
- 复杂度：结果派生展示使用普通纯计算；`setResult` updater 内没有其他 setState
  或副作用，没有新增结果状态、API Client、Mutation Manager 或收藏写服务
- 验证：前端 lint、typecheck、build、生产依赖 audit 通过，Vitest
  `38 passed`，其中新增 4 项反序完成和跨 Run 迟到响应回归；M1-3 后端聚焦契约
  `7 passed`
- 阶段状态：M1-3 继续为“待主控验收”，不开始 M1-4

#### 2026-07-27｜M1-3 Agent 与内容导入页面｜主控验收通过

- 集成：确认最终修复提交
  `f761c9dcdca11ec9b296c7f1638ad9bfe04a8275` 线性继承
  `da60a6db0cdf450f1dc4630166e44f426d24eed1` 和阶段基线
  `d1832e9ae8355fe1e58faae0e101b9f8e0a4d2c8`；已将
  `codex/m1-3-agent-import` 纯快进集成到 `main`
- P1 关闭：多收藏更新只在最新 result 上函数式替换目标项，并按 operation
  generation、trace id 和 collection id 拒绝跨 Run 或错项迟到响应；主控复测两种
  A 修改/B 撤销反序、继续添加后的迟到成功和新 Run 后的迟到失败均通过
- 独立快照：前端 lint、typecheck、build、生产依赖 audit 通过，Vitest
  `38 passed`；M1-3 后端契约 `7 passed`，Alembic 唯一 head 为
  `20260727_0011`
- 浏览器：Playwright `14 passed`，覆盖 320–1440px、键盘焦点、reduced motion
  及真实 FastAPI + 离线 Fake Provider 闭环；主控实际浏览器复核提交、权威结果、
  撤销、恢复和控制台，未发现 warning/error
- 合并后检查：M1-3 契约与迁移 `30 passed`，前端 Vitest `38 passed`，lint
  通过；纯快进前后代码树一致
- 范围、安全与复杂度：当前无未关闭 P0/P1；未新增第二套结果状态、API/SSE
  Client、Provider、JobQueue、Worker、收藏写服务或版本规则；未读取 `.env`，未
  调用真实模型、地图、网页或付费 API，未实现 M1-4
- 结论：M1-3 已完成；当前唯一允许阶段改为 M1-4 收藏库与地点消歧，M1-5 及后续
  阶段不得提前开发

#### 2026-07-27｜M1-4 收藏库与地点消歧｜待主控验收

- 后端：在 `SqlAlchemyCollectionRepository` 增加唯一列表查询入口，统一用户
  隔离、搜索、城市分组、Place/Event、状态、标签、稳定排序、计数和分页；详情和
  来源继续读同一持久化数据
- 地点消歧：公开持久化候选快照的安全摘要，选择具体候选或“以上都不是”均复用
  `PlaceTargetSelectionService`；前者确认 PlaceTarget，后者保留原收藏并转为
  `pending_details`，没有首项猜测
- 规划边界：API 明确返回正式城市分组、规划资格和排除原因；城市待确认、
  `pending_selection`、`pending_details`、非深圳及非 active 收藏不会进入当前
  深圳计划
- 前端：正式 `/collections` 覆盖加载、空、错误重试、显式搜索、筛选、分页、
  详情编辑、候选选择、删除恢复和版本冲突；查询与详情保存在 URL，迟到列表/详情
  响应按 generation 丢弃
- 可访问性与安全：候选显示分店、行政区、商圈、地址和地标线索；详情进入焦点并
  支持 Escape；320–1440px、44px 目标、reduced motion 和恶意 HTML 文本渲染均
  有自动化覆盖
- 数据库：现有版本、删除恢复、候选快照、PlaceTarget、正式 POI 城市及来源关系
  足够表达 M1-4，未新增迁移；Alembic 保持单一 `20260727_0011` head
- 复用与复杂度：未新增第二套 Repository、收藏写服务、候选评分/选择、
  Undo/Restore、API Client、Session/CSRF、Place/Event DTO 或前端全局状态
- 验证：pip check、Ruff、mypy 通过；M1-4 契约 `5 passed`、M1-3 回归
  `7 passed`、迁移往返 `23 passed`、完整离线后端
  `1576 passed, 11 skipped, 2 deselected`；前端 lint、typecheck、build、audit
  通过，Vitest `47 passed`，Playwright `22 passed`
- 范围：未读取 `.env`，未调用真实模型、地图、网页或付费 API；未实现、合并或
  推送 M1-5 及后续业务

#### 2026-07-27｜M1-4 P1 QA 修复｜修复完成，待主控复验

- 前端操作归属：PATCH、DELETE、restore 和候选选择统一绑定当前详情 generation
  与收藏 ID；关闭、切换和 URL 历史导航会使旧操作失效，迟到成功、失败及 finally
  不再覆盖后开的详情、feedback、saving 或候选状态
- 合并 URL：候选选择返回不同收藏 ID 时，仅替换 URL 的 `item` 并保留搜索、筛选
  和页码，随后读取正式收藏；同 ID 的“以上都不是”不产生额外导航
- 来源迁移：HTTP 路由不再选择 `sources[0]`；唯一
  `PlaceTargetSelectionService` 在原事务内把待选收藏的全部来源幂等关联到既有
  exact/any-branch 收藏，保持既有来源、唯一约束、expected_version 和幂等语义
- 回归：新增保存迟到成功/失败，删除、恢复和候选选择迟到，合并 URL/详情/刷新，
  同 ID 无导航，多来源 exact/any-branch 合并、重放/载荷冲突及跨用户隔离覆盖
- 验证：指定后端组合 `78 passed`；完整离线后端
  `1577 passed, 11 skipped, 2 deselected`；前端 Vitest `53 passed`、
  Playwright `22 passed`；pip check、Ruff、mypy、lint、typecheck、build 和
  `npm audit --omit=dev --audit-level=high` 均通过
- 数据库与复杂度：未新增迁移，Alembic 仍为单一 `20260727_0011` head；未新增
  Mutation Manager、全局状态框架、合并服务、Repository、来源模型、幂等记录或
  第二条来源迁移路径
- 范围：未读取 `.env`，未调用真实模型、地图、网页或付费 API；未实现、合并或
  推送 M1-5 及后续业务

#### 2026-07-28｜M1-4 收藏详情保存 P1｜修复完成，待主控复验

- 根因：FastAPI 将合法 JSON array 解码为 Python `list`，嵌套 strict
  `CollectionItemPatch.tags: tuple[str, ...]` 因而在真实 PATCH 入口返回 422；
  原前端测试只 mock 成功响应，没有穿过真实 API DTO
- 唯一修复边界：仅在公开 `CollectionPatchRequest.changes` 将 JSON array 递归
  规范化为领域 tuple，不转换标量；随后继续由唯一 `CollectionItemPatch` 验证全部
  字段、成员、组合和未知键，没有新增 DTO、编辑服务或标签校验器
- 行为：标签数组可保存和清空；标题、城市线索、行政区、地址与标签在一次 PATCH
  原子保存，响应、详情和列表一致且版本只增加一次；非法结构仍为 422，旧版本为
  409，跨用户为 404
- 前端：保留正常 `tags: string[]` JSON body；组件回归检查实际请求体、已有标签
  修改标题、标签修改/清空及 422 不显示成功；详情操作归属和原三个 P1 回归保留
- 真实验证：M1-4 ASGI 契约 `6 passed`；地点选择与迁移 `66 passed`；完整离线
  后端 `1578 passed, 11 skipped, 2 deselected`。仓库外 pytest 插件封锁 DNS 与
  三类 socket 连接后相关后端 `72 passed`
- 浏览器：Playwright `23 passed`；新增真实 FastAPI + FakeProvider 链路创建带
  “观星、周末”标签的收藏，从 `/collections` 修改名称并保存，关闭重开后名称和
  标签保持一致。Vitest `54 passed`，lint、typecheck、build 均通过
- 数据库与范围：无迁移，Alembic 仍为单一 `20260727_0011` head；未读取 `.env`，
  未调用真实模型、地图、网页或其他真实 API，未合并、未推送、未实现 M1-5

#### 2026-07-28｜M1-4 收藏库与地点消歧｜已完成（主控验收）

- 集成：最终提交 `512650a60914cc613cfeb3be1e5c27b243b17e63` 线性继承
  P1 修复 `91d54d6c49d63865daa2ab840546ae7c1b4a0845` 和阶段基线
  `e244bf663c73f12057d24fbaf65e0cb5e2f50523`；主控以 `--ff-only` 纯快进
  集成到 `main`，没有冲突、merge commit 或额外代码变化
- P1 关闭：详情写操作归属、候选合并 URL、exact/any-branch 全来源迁移和公开
  JSON array → 领域 tuple 边界均通过独立复验；标签可保存、修改和清空，非法
  结构仍为 422，旧版本为 409，跨用户为 404
- 隔离验证：全新 Python 3.14 快照中 pip check、Ruff、mypy 通过；M1-4 真实
  ASGI 契约 `6 passed`，服务/旧契约/迁移组合 `83 passed`；完整离线及封网全集
  均为 `1578 passed, 11 skipped, 2 deselected`；Alembic 唯一 head 为
  `20260727_0011`
- 前端验证：Node 25.8、npm 11.11；生产依赖 audit 0，lint、typecheck、build
  通过，Vitest `54 passed`，Playwright `23 passed`
- 浏览器：真实 Next.js + FastAPI + Worker + 临时 SQLite + FakeProvider 创建
  “深圳天文台”收藏；带“观星、周末”标签修改名称成功，关闭重开后持久化一致，
  清空标签后版本正确递增且列表/详情一致
- 合并后检查：Ruff、mypy、M1-4/地点选择/迁移聚焦 `72 passed`，前端 lint、
  typecheck 和 Vitest `54 passed` 全部通过
- 安全与复杂度：当前无未关闭 P0/P1；没有第二套 CollectionItemPatch、
  Repository、编辑服务、候选服务、来源迁移或前端状态框架；未读取 `.env`，
  未调用真实模型、地图、网页或付费 API，未实现 M1-5
- 已知非阻断项：aiosqlite 线程收尾 warning 仍偶发，目标测试以
  `PytestUnhandledThreadExceptionWarning` 作为 error 单独复跑通过；详情未保存
  提示、弹层 overscroll 和非认证表单 autocomplete 作为统一 UI 收口债务登记
- 下一步：M1-5 前置条件满足；从本次文档提交后的最新 `main` 创建
  `codex/m1-5-plan-experience`，只实现计划生成、调整和明确确认

#### 2026-07-28｜M1-5 计划生成、调整和确认｜待主控验收

- 基线与分支：从指定 `26a8ac15b367dc9cc012238314d3304a54de98b7`
  创建 `codex/m1-5-plan-experience`；开始时 `main`、`origin/main` 和工作区门禁
  全部通过，M1-4 已完成且 M1-5 为唯一允许阶段
- 后端：新增正式计划版本、计划项和 Approval 持久化；提供生成、列表、详情、调整、
  明确确认及外部地点授权 API；自然语言调整只应用明确识别的字段并保留其余
  `PlanConstraints`
- 异步链路：复用唯一 JobQueue、JobWorker、AgentRun、RunEvent 和 SSE；每个计划
  版本绑定独立 trace，迟到结果只能更新仍处于 generating 的绑定版本，计划任务不
  自动重试
- 规划复用：继续组合 `StructuredCollectionRetrievalService`、
  `ExternalPlaceSupplementService` 和 `PlanDraftService`；地图事实解析器只提供
  原领域服务所需的动态事实，没有新增第二套规划器、排序、预算或硬约束规则
- 版本与确认：调整创建不可变子版本，数据库约束版本链、每条链最多一个 confirmed、
  确认幂等和跨用户外键；未确认版本无法通过未来执行边界，确认外部地点不创建收藏
- 前端：正式 `/plans` 覆盖条件输入/确认、SSE 进度恢复、主备方案、时间光轨、
  费用/路线/来源/风险、外部补充授权、自然语言调整、版本切换和明确确认；刷新和
  重新进入读取权威后端状态，operation generation 拒绝旧响应
- 数据库：新增单一向前迁移 `20260728_0012`，直接继承 `20260727_0011`；
  upgrade、current、check、downgrade/upgrade 往返通过，Alembic 唯一 head 为
  `20260728_0012`
- 验证更正：失败候选的 strict mypy 实际未通过，
  `repositories/plans.py` 直接读取 `Result.rowcount` 产生 3 个类型错误；原“mypy
  通过”记录无效，由下方主控缺陷修复记录的实测结果取代。该候选其余记录为：完整离线后端
  `1585 passed, 11 skipped, 2 deselected`，迁移 `23 passed`；仓库外临时插件
  封锁 DNS 和 socket 后规划聚焦 `177 passed`
- 前端验证：`npm ci`、lint、typecheck、build 通过，Vitest `58 passed`，
  Playwright `25 passed`；生产依赖 audit 为 0
- 安全与范围：未读取 `.env`，未调用真实模型、地图、网页或付费 API；未实现
  M1-6、M1-7、分享、提醒、微信、云部署、多城市或自动收藏外部地点
- 复杂度：没有第二套 Provider、AgentRunner、ToolRegistry、Plan DTO、Approval、
  Job/Worker、SSE Client、API Client 或前端全局状态；当前无已知未关闭 P0/P1
- 交接：详见 `docs/technical/M1_5_HANDOFF.md`；阶段状态保持“待主控验收”，
  不自行标记完成，不开始 M1-6

#### 2026-07-28｜M1-5 主控验收缺陷修复｜待主控验收

- 修复范围：线性继承失败候选
  `2e554e7c1114e3ccb6c2c5e3ac0607d126ea509e`，仅处理 M1-5；未 amend、未合并
  `main`、未推送、未开始 M1-6
- 类型边界：计划 Repository 的 3 处 UPDATE 统一复用已有
  `execute_dml_rowcount`；没有 `type: ignore`、`Any` 扩散或第二个 rowcount helper。
  strict mypy 实测 `125 source files` 无错误
- 提交一致性：生成/调整先复用现有 AgentRun，再通过唯一 JobQueue 入队；Job 创建
  抛错或 `CancelledError` 且按 trace 查不到 Job 时，以独立事务删除仍为
  `generating` 的绑定 Plan 和 queued AgentRun。补偿覆盖一次自身瞬时失败后重试，
  同键可重新提交并幂等重放，不同键创建独立 root；最终不存在无 Job 的 generating
  Plan、无 Job 的 AgentRun 或被占用的不可恢复幂等键
- 调整解析：删除生产正则、中文短语表和同步解析路径，新增唯一严格
  `PlanAdjustmentParser`，只通过既有 `ModelProvider` 的 JSON Schema 输出最小
  `PlanConstraints` patch，并在既有异步计划 Job 内执行；完整约束只由
  `PlanConstraints` 验证一次。产品示例正确替换咖啡包含目标、加入散步、明确排除
  咖啡，未提及的时间、预算、范围、节奏、交通与 `collection_only` 保持不变
- 地图事实：继续复用 `StructuredCollectionRetrievalService`、
  `PlaceMatchingService`、`ExternalPlaceSupplementService`、`PlanDraftService`
  和唯一 MapProvider。确定性资格筛选先于任何天气/路线调用；支持 active exact
  Place、带准确日期时间与 exact 正式位置的 Event，以及在当次范围解析并固定具体
  POI 的 any_branch。最多选择 6 个事实候选，单次计划最多 48 次路线调用；其他城市、
  archived、pending、时间/范围/包含/排除不符的收藏为 0 次路线调用
- 数据库：新增单一向前迁移 `20260728_0013`，直接继承 `20260728_0012`，允许
  Event 持有 exact 正式 PlaceTarget，同时避免 Event 与收藏 Place 的 POI 去重冲突；
  迁移专测 `23 passed`，upgrade/current/check 和 downgrade/upgrade 往返通过，
  Alembic 唯一 head 为 `20260728_0013`
- 配置与恢复：缺少 MapProvider 时在持久化前返回安全 503，不创建 Plan、Run 或
  Job；调整还要求既有 ModelProvider。已有 draft/confirmed 计划可“新建计划”并
  创建独立 root；最新失败版本仍显示完整版本索引，可回到上一份草案
- 真实离线浏览器：新增 1 条不 mock `/api/v1/plans`、Job、SSE 或结果接口的
  Playwright 流程，真实穿过 Next.js、FastAPI、JobQueue、Worker、临时 SQLite 和
  StubMapProvider，覆盖创建、Worker 完成、SSE/权威恢复、自然语言调整、版本切换、
  明确确认、新建第二个 root，以及失败版本返回上一版
- 验证：pip check、Ruff 通过；strict mypy `125 source files`；完整后端
  `1592 passed, 13 skipped`；迁移 `23 passed`。仓库外 pytest 插件封锁 DNS、
  `connect`、`create_connection` 后，计划聚焦 `36 passed, 21 deselected`，非真实
  全集 `1592 passed, 11 skipped, 2 deselected`
- 前端：lint、typecheck、build 通过，Vitest `58 passed`，Playwright
  `26 passed`；移动端真实计划闭环包含新 root 和失败版本恢复
- 复杂度与安全：删除原自然语言短语规则路径，没有第二套规划器、筛选/排序/Event/
  分店规则、Approval、Job/Worker/SSE 状态机、Provider、Client 或全局状态。离线
  QA 显式 `_env_file=None`；未读取本机 `.env` 内容，真实模型、地图、网页及其他
  外部/付费 API 调用均为 0；当前无已知未关闭 P0/P1
- 阶段状态：继续为“待主控验收”，不自行标记完成

#### 2026-07-28｜M1-5 剩余主控验收缺陷修复｜待主控验收

- 线性基线：继承 `7d6d66f8972d1eedeaa0f8178fd32b9e0be2e07e`，仅追加一个
  M1-5 修复提交；未合并、未推送、未开始 M1-6
- any_branch：一次计划对每个 any_branch 只调用一次既有
  `PlaceMatchingService`；具体 POI 按收藏 ID 冻结进现有规划事实契约，结构化检索
  不再搜索，事实层与最终草案使用同一 POI 和查询时间
- 结构化调整：Worker、Demo Worker 与真实离线 E2E 均把
  `Settings.extraction_structured_output_mode()` 传入唯一 `PlanAdjustmentParser`；
  默认请求 `json_object`，schema 位于 Prompt，Pydantic 严格校验保留，无自动
  fallback、探测或重试。模型不能输入 origin 精确坐标，也不能输出 Coordinate 或
  ActivityArea 写入计划硬事实
- Event：仍保存为一个 Event；文本/截图保存后复用唯一 Matcher、候选快照和地点
  选择服务，用户明确选择一个 exact POI 后才可进入计划；未选择、日期不完整和仅
  日期 Event 保守排除，any_branch 继续禁止。新增迁移 `20260728_0014`
- 排序与恢复：删除事实层 UUID 排序，复用仓储稳定顺序、资格与规划排序；显式
  include 不被随机截断。候选/路线调用上限仍为 `6 / 48`。历史版本显示“历史版本”
- 离线验证：pip check、Ruff、strict mypy `126 source files` 通过；后端非真实全集
  `1596 passed, 13 skipped`；迁移专测 `23 passed`，唯一 head
  `20260728_0014`；前端 lint、typecheck、build 通过，Vitest `59 passed`，
  Playwright `26 passed`
- 复杂度与安全：删除检索层第二次 any_branch 搜索，没有第二套 Provider、Matcher、
  Parser、Planner、地点选择服务、排序或状态机；未读取 `.env`，真实模型、地图、
  网页及付费 API 调用为 0。阶段继续为“待主控验收”

#### 2026-07-28｜M1-5 最后一轮验收缺陷修复｜待主控验收

- 线性基线：继承 `2646f1d70248bff3b59cd9585b78c5f7ce165fa6`，只追加一个
  M1-5 修复提交；未 amend、未合并 `main`、未推送、未开始 M1-6
- any_branch：请求级 `PlanningFactSnapshot` 同时冻结唯一搜索得到的具体 POI 或
  精确失败原因；Provider 超时/不可用、正常无结果、结果证据不足分别为
  `BRANCH_PROVIDER_FAILED`、`BRANCH_NOT_FOUND`、
  `BRANCH_EVIDENCE_INSUFFICIENT`。组合测试穿过 `MapPlanFactResolver` 与
  `StructuredCollectionRetrievalService`，每个 any_branch 搜索严格 1 次，检索层
  不再持有或调用 Matcher
- Event：继续是单一 Event，复用既有城市提示解析、`PlaceMatchingService`、候选
  快照和 `PlaceTargetSelectionService`。只有城市边界确认深圳才查询深圳；广州和
  城市待确认 Event 的地图调用为 0。“以上都不是”清除候选快照并回到
  `pending_details`，原 Event、准确时间与来源保留，幂等重放及并发版本冲突通过
- 调整：从唯一 `PlanAdjustmentPatch` 删除 `location_intent`，继续禁止模型读写
  origin、Coordinate 和 ActivityArea。唯一 Parser 使用 Settings 的 `json_object`
  配置并在持久化前生成严格最小 patch；精确地点/活动范围调整返回
  `PLAN_ADJUSTMENT_UNSUPPORTED` 和“新建计划”恢复路径，不创建 Plan、AgentRun、
  幂等键或 Job。预算、节奏、时间、交通、包含/排除和 `collection_only` 保持原
  调整能力
- 前端：计划表单 input/select/checkbox 增加稳定 `name`；真实离线 Playwright
  证明地点调整被拒绝时停留在 V1 且不产生 V2。历史版本不显示“当前版本”的边界
  保持
- 验证：`pip check`、Ruff、strict mypy `126 source files` 通过；完整后端离线
  `1603 passed, 13 skipped`；仓库外插件硬封 DNS/socket 后非真实全集
  `1603 passed, 11 skipped, 2 deselected`；迁移专测 `23 passed`，唯一 head
  `20260728_0014`，upgrade/current/check/downgrade/upgrade 往返通过；前端 lint、
  typecheck、build 通过，Vitest `60 passed`，Playwright `26 passed`
- 复杂度与剩余风险：没有新增第二套 Provider、Matcher、Parser、Planner、排序器、
  地点选择服务或状态机；删除 Worker 内重复调整解析。候选/路线硬上限保持
  `6 / 48`。不再宣称仓储顺序的前 6 个合格候选等于规划排序；剩余 P2 为高基数
  收藏中更晚但软偏好更高的候选可能未进入最终排序，本轮按要求不新增第二套预排序
- 安全与状态：未读取本机 `.env`，真实模型、地图、网页、DNS、socket 和其他外部/
  付费 API 调用均为 0；无未关闭 P0/P1。阶段继续为“待主控验收”

#### 2026-07-28｜M1-5 最终异步调整链修复｜待主控验收

- 线性基线：继承 `771cc5c403fd3b5f00eeb8bf927f134d3dbc5a98`，仅追加本次
  M1-5 修复；未 amend、未合并 `main`、未推送、未开始 M1-6
- 异步边界：删除调整 API 对 ModelProvider / `PlanAdjustmentParser` 的注入和同步
  调用。API 只做本地格式、权限、当前版本和幂等检查，持久化或重放既有 AgentRun、
  ScheduledJob 与 trace 后立即返回语义准确的 202；响应使用 `base_plan_id`，
  不把尚不存在的 V2 冒充为已接受结果
- Worker：唯一 `PlanGenerationJobHandler` 根据既有计划 Job payload 在 Worker 内
  调用唯一 Parser，使用 `ApplicationRunObserver.record_model_response` 保存模型、
  Token、耗时、完成原因和费用估算。合法 patch 后重新锁定当前 base，才创建 V2、
  保留其他约束并调用既有规划器
- 安全恢复：地点/活动范围调整以 `PLAN_ADJUSTMENT_UNSUPPORTED` 终结且不创建 V2；
  已发生模型调用的 AgentRun 和 Job 作为正确审计记录保留。超时、鉴权、限流、
  格式错误和 CancelledError 均在 Worker/Run 生命周期内终结，不留下 queued 或
  running 后台任务
- 幂等与并发：用户作用域幂等键产生稳定 trace，ScheduledJob 唯一约束继续作为最终
  边界。同请求串行及并发重放只产生一个调整 Job、一个 AgentRun、一次模型调用和
  一个 V2；同键不同 instruction 返回 409；旧 base 不会覆盖新版本
- 前端：SSE 终态后先读取 base 的权威版本索引，再切换到实际产生的 V2；unsupported
  或其他 Worker 失败继续展示原版本及明确恢复提示
- 验证：`pip check`、Ruff、strict mypy（126 个源文件）通过；指定聚焦与回归
  `107 passed`；后端非真实全集
  `1609 passed / 11 skipped / 2 deselected`；迁移专测 `23 passed`，唯一 head
  `20260728_0014`。前端 lint、typecheck、build 通过，Vitest `60 passed`，
  Playwright `26 passed`
- 唯一性与安全：未新增 Provider、Parser、Planner、JobQueue、Worker、AgentRun、
  Matcher、锁或状态机；API 层同步 Parser 和模型异常映射已删除。未读取 `.env`，
  Fake/Stub 之外真实模型、地图、网页及付费 API 调用为 0。阶段继续为“待主控验收”

#### 2026-07-28｜M1-5 主控最终验收与集成｜已完成

- 集成：阶段分支 `codex/m1-5-plan-experience` 的最终开发提交
  `6572e15a20158fa834a650f653d48d506ffc09ed` 已从
  `26a8ac15b367dc9cc012238314d3304a54de98b7` 纯快进集成到 `main`；无冲突、无
  merge commit、无额外生产代码变化
- 独立验收：pip check、Ruff、strict mypy（126 个源文件）通过；M1-5 调整链和回归
  聚焦 `107 passed`；完整后端离线及仓库外 DNS/socket 封网复跑均为
  `1609 passed, 11 skipped, 2 deselected`；迁移专测 `23 passed`，唯一 Alembic
  head 为 `20260728_0014`，upgrade/check/downgrade/upgrade 往返通过
- 前端与运行态：lint、typecheck、build 通过，Vitest `60 passed`，Playwright
  `26 passed`；主控另用本地 Next.js + FastAPI + Worker + 临时 SQLite 实际操作
  `/plans`，验证 V1 生成、异步调整和 V2 权威恢复
- 修复结论：调整 API 不同步调用模型；唯一 Parser 位于 Worker，AgentRun、Job、
  模型计量和 V2 生命周期一致；幂等重放、旧任务隔离、unsupported 恢复和确认边界
  均通过。没有第二套 Provider、Parser、Planner、Runner、Registry、Job/SSE 或前端
  状态框架，也没有 M1-6 实现
- 安全与风险：未读取 `.env`，真实模型、地图、网页及其他外部/付费 API 调用为 0；
  当前无未关闭 P0/P1。保留 P2：高基数收藏在事实读取阶段按稳定仓储顺序截取前 6
  个合格候选，可能使较晚但软偏好更高的候选未进入最终排序；后续只能收敛进唯一
  规划排序边界，不新增第二套预排序
- 阶段结论：M1-5 已完成；当前允许开始 M1-6，M1-7 及后续阶段不得提前开始

#### 2026-07-28｜M1-6 执行入口与手动反馈｜待主控验收

- 线性基线与提交：开始时确认 `main`、`origin/main` 均为
  `7d66aa8310436fd9ef37561f533e455e0c664c61`，工作区干净、Alembic head 为
  `20260728_0014`、M1-5 已完成；从 main 创建
  `codex/m1-6-execution-feedback`。完整开发提交为
  `c10b68a123eafb1c0c114857d95aabec77c393ea`
- 执行门禁与入口：复用唯一 `require_confirmed_for_execution`；未确认计划统一拒绝
  日历、导航和反馈。新增 `.ics` 下载及最小执行只读视图，导航只调用既有
  `MapProvider.build_navigation_uri`，未知 POI 不伪造，生成过程不发 HTTP
- 日历：完整主计划使用 `Asia/Shanghai`、稳定 Plan UID、准确起止和 POI 地址，
  支持 UTF-8 中文、特殊字符转义、CRLF 与 75 字节折行；独立测试解析器可读取，
  输出不含密钥、Cookie 或本机路径
- 反馈与收藏：支持完成、部分完成、未完成；部分完成逐项选择，外部地点不自动收藏。
  当前状态、不可变审计、收藏访问基线和来源共同支持更正重算；用户原有 visited 或
  其他有效到访来源不会被错误撤销
- 幂等与安全：用户作用域键、请求指纹、revision 唯一约束、行锁和单事务提交覆盖
  串行重放、同键冲突、用户隔离、跨计划 PlanItem、越权选择和中途异常回滚；初始
  交接时 PostgreSQL 同 key 并发曾错误返回版本冲突，已由下方 QA 联合修复关闭并
  补充真实 PostgreSQL 并发证明
- 偏好边界：只产生待确认建议，不写长期记忆，不同步调用模型，不增加关键词规则；
  未实现 M1-7、主动询问、提醒、消息、分享、导出或自动收藏
- 数据库：单一迁移 `20260728_0015` 线性继承 `0014`，扩展确认后终态与 PlanItem
  执行状态，新增四张反馈/到访来源表并使用复合所有权外键；唯一 head 为
  `20260728_0015`
- 前端：M06 复用 App Shell、API Client 和既有局部状态边界，覆盖日历、导航、
  三种反馈、逐项选择、刷新恢复、更正和待确认偏好建议。真实离线 E2E 穿过
  Next.js、FastAPI、临时数据库、既有 Worker/计划服务完成确认 → 下载 → 导航 →
  部分完成 → 刷新 → 更正
- 验证：初始交接结果已由下方 QA 联合修复复测取代；以最新结果
  `7` 项聚焦、`24` 项 SQLite 迁移、`1617 passed, 14 skipped, 2 deselected`
  非真实全集、`4` 项本地 PostgreSQL、`65` 项 Vitest 和 `26` 项 Playwright 为准
- 复杂度、安全与风险：日历、导航、反馈、偏好建议各一个正式服务入口；没有第二套
  Plan、Repository、Provider、Job、Worker、AgentRun、状态机、API Client 或前端
  全局状态。未读取 `.env`，真实模型、地图、网页及其他外部/付费 API 调用为 0；
  当前无未关闭 P0/P1。保留既有高基数候选截断 P2；真实 PostgreSQL 并发已完成
  本地 PostgreSQL 16 复测，各移动日历客户端导入和高德真实设备拉起仍是非阻塞
  待验风险
- 交接：详见 `docs/technical/M1_6_HANDOFF.md`；阶段保持“待主控验收”，不合并、
  不推送、不开始 M1-7

#### 2026-07-28｜M1-6 主控 QA 联合修复｜待主控验收

- 修复基线：在 `codex/m1-6-execution-feedback` 的初始交接 HEAD
  `d57996defa4f2c343ddcb21d799a09c6060afc7b` 上追加一个可回滚修复提交；未 amend、
  rebase、合并或推送，M1-7 未开始
- PostgreSQL 并发幂等：继续使用数据库唯一约束与 Plan 行锁作为最终边界；取得
  Plan 行锁后、比较 expected revision 前重新读取幂等审计。同 key 同 fingerprint
  并发实测两个请求均成功且 replayed 一真一假，审计、revision、收藏来源及
  PlanItem 更新各一次；同 key 不同载荷返回幂等冲突，不同 key 同 revision 仍只有
  一个成功，事务失败后原 key 可安全重试
- 审计关系：直接修正尚未集成 main 的 `20260728_0015`，不新增 `0016`。当前反馈
  指针及 `corrects_feedback_id` 均以复合外键绑定同一 plan 和 user 的审计；ORM 与
  迁移一致，合法更正链通过，SQLite 与 PostgreSQL 均拒绝孤儿、跨用户和跨计划指针
- 前端竞态：execution 加载与反馈提交复用既有 operation generation、
  AbortController 和局部状态；版本切换、新建计划、卸载后的旧响应及 `finally`
  不再修改当前 Plan、execution、选择、提示或 busy。网络结果不确定时同载荷重试
  保持幂等键，成功或载荷改变后才换键
- 日历 P2：删除没有可信公开 Base URL 的 `shiguang.local` URL；测试改用成熟独立
  `icalendar` 解析器验证稳定 UID、Asia/Shanghai、CRLF、UTF-8 折行、中文、地址和
  特殊字符，没有复制生产解析逻辑
- 验证：pip check、Ruff、strict mypy（129 个源文件）通过；M1-6 聚焦
  `7 passed`，SQLite 迁移 `24 passed`，非真实全集
  `1617 passed, 14 skipped, 2 deselected`。一次性本地 PostgreSQL 16 运行反馈
  并发/约束 3 项及迁移往返 1 项，合计 `4 passed`。仓库外插件封锁 DNS 和全部
  socket 连接入口后，聚焦与非真实全集以相同数量再次通过
- 前端验证：lint、typecheck、build 通过，Vitest `65 passed`，Playwright
  `26 passed`；真实离线 M06 继续穿过 Next.js、FastAPI、临时数据库和既有服务完成
  确认 → 日历 → 导航 → 部分完成 → 刷新恢复 → 更正
- 范围与安全：四个正式服务、Plan Repository、MapProvider、API Client 和前端
  operation generation 均保持唯一；未新增进程锁、重试循环、sleep、第二套状态或
  SQLite 特判。未读取 `.env`，真实模型、地图、网页及其他外部/付费 API 调用为
  0；当前无未关闭 P0/P1。保留既有 M1-5 高基数候选截断 P2，以及移动日历客户端
  和高德真实设备验证两项非阻塞风险

#### 2026-07-28｜M1-6 主控最终验收与集成｜已完成

- 集成：阶段实现、交接和修复提交组成从
  `7d66aa8310436fd9ef37561f533e455e0c664c61` 到
  `a20c083a4bfd2c7ac9626db2584b7ae260a75ef9` 的线性提交链；主控以
  `--ff-only` 纯快进集成到 `main`，无冲突、merge commit 或额外生产代码变化
- 原缺陷复验：PostgreSQL 中同 key 同载荷并发返回两个成功结果且只产生一次审计、
  revision、收藏来源和 PlanItem 变更；同 key 不同载荷、不同 key 同 revision、
  失败回滚重试均符合边界。当前反馈与更正指针在 SQLite/PostgreSQL 均只能指向同一
  plan 和 user 的审计；版本切换、新建计划和卸载后的迟到 execution/feedback
  响应及 `finally` 不再覆盖当前界面
- 后端结果：`pip check`、Ruff、strict mypy（129 个源文件）通过；M1-6 契约与
  SQLite 迁移聚焦 `31 passed`；完整非真实及仓库外 DNS/socket 硬封网复跑均为
  `1617 passed, 14 skipped, 2 deselected`；一次性 PostgreSQL 16 的并发、回滚、
  指针约束及迁移往返 `4 passed`；Alembic 唯一 head 为 `20260728_0015`
- 前端结果：lint、typecheck、build 通过，Vitest `65 passed`，Playwright
  `26 passed`；真实离线 M06 走通 V2 确认、日历下载、导航、部分完成、刷新恢复、
  更正及新计划恢复
- 范围、复杂度与安全：继续只有一个 AgentRunner、ToolRegistry、ModelProvider、
  Plan 行锁串行化边界、反馈服务和前端 operation generation；没有第二套锁、
  Provider、Repository、状态机、解析器或测试专用生产分支。未读取 `.env`，真实
  模型、地图、网页及其他外部/付费 API 调用为 0
- 结论与风险：原三个 P1 与日历两个 P2 已关闭，当前无未关闭 P0/P1。保留既有
  M1-5 高基数候选截断 P2、移动端日历导入兼容性和高德 URI 真实设备拉起验证风险；
  它们不阻塞 M1-7。M1-6 已完成，当前允许开始 M1-7，M1-8 及后续阶段不得提前开始

#### 2026-07-28｜M1-7 我的、记忆和数据控制｜待主控验收

- 分支与基线：`codex/m1-7-memory-data-control` 从
  `c4d23b716af1426054705912ed0d7067e95e11e4` 创建；开始时 main、origin/main、
  HEAD 精确一致，工作区干净，Alembic head 为 `20260728_0015`，M1-7 是唯一
  允许阶段
- 提交：实现 `78543b611d564a83dab0e4d601619706e366369e`；跨用户建议隔离补测
  `1cf4a1b06b9a746a7baff6b77a460bacb430ee4d`；最终文档提交 SHA 见交付回复
- Memory 闭环：建立唯一结构化 Memory 聚合、仓储和应用服务；只允许已确认记录。
  M1-6 建议可确认或拒绝，拒绝后同证据不再出现；显式创建、修改、停用、删除具有
  用户作用域幂等、指纹冲突、乐观版本和事务回滚
- 规划与生命周期：只将已确认、未过期、未停用、未删除的 Memory 送入既有唯一
  `StructuredCollectionRetrievalService` 和 `PlanDraftService`；临时条件仍只属于
  PlanConstraints。实际影响主方案后才写使用依据、计划和最后使用时间
- 迁移与 API：新增线性 `20260728_0016` 及 memories、建议决定、操作、计划使用
  四表，所有反馈/计划/Memory 关系使用 user_id 复合所有权；新增 Memory 列表、
  详情、写入、建议决定及当前用户私有 JSON 导出 API
- M07：`/me` 支持建议确认/拒绝、Memory 列表和来源/影响详情、修改、停用/启用、
  两步删除和导出；主动提醒明确为“尚未实现 · 已关闭”。generation 所有权隔离
  刷新、切换、迟到详情和迟到写响应，移动端和键盘可用
- 验证：pip check、Ruff、strict mypy 通过；非真实全集及仓库外 DNS/socket 封网
  复跑均为 `1625 passed, 15 skipped, 2 deselected`；SQLite 迁移 `24 passed`，
  Alembic 唯一 head `20260728_0016`；一次性 PostgreSQL 16 Memory 并发/所有权和
  迁移往返 `2 passed`；前端 lint/typecheck/build 通过，Vitest `69 passed`，
  Playwright `27 passed`
- 安全与范围：未读取 `.env`，真实模型、地图、网页和付费 API 调用为 0；导出
  allowlist 不含 Cookie、Token、密钥、幂等键或内部审计，返回 private no-store。
  没有第二套 Memory Store、偏好服务、计划检索、Provider、API Client 或前端状态
  框架；没有 M1-8 分享、微信、提醒任务、部署或账号注销
- 风险与下一步：当前无未关闭 P0/P1；保留既有高基数候选截断 P2。详见
  `docs/technical/M1_7_HANDOFF.md`。保持待主控验收，不合并、不推送、不开始 M1-8

#### 2026-07-29｜M1-7 主控验收缺陷修复｜待主控验收

- 修复基线与提交：在 `2342cfef31cb0962cb4f212f6bfea68a01d4883e` 上追加代码
  与测试修复 `aa21144f83d536426578ba333ab449121a881289`；本记录所在文档提交完整 SHA
  见最终交付。未 amend、rebase、合并 main 或推送
- 请求优先与推断关闭：长期 pace Memory 不再覆盖当前唯一 `PlanConstraints.pace`；
  事实解析、草案和持久化继续使用当前请求约束。删除基于部分完成、未完成或自由文本
  原因推断 relaxed 的服务；新反馈不产生长期建议，0015 旧式
  `content/confirmation_status` JSON 仍作为中性候选读取，确认必须明确提交类型、
  内容和值，拒绝不创建 Memory
- 幂等与 PostgreSQL：update/delete 在包含逻辑删除行的 Memory 行锁后、版本或
  NotFound 前再次读取 `memory_operations`。一次性 PostgreSQL 16 预先持有行锁，
  证明两个请求均越过初次重放检查后等待；同键同载荷一真一假、同键异载荷冲突、
  异键同版本单成功、删除后重放，以及 operation 和业务版本各写一次均通过
- 排序与使用依据：唯一 `StructuredCollectionRetrievalService` 将任意数量匹配
  Memory 归一为 `-1/0/1`，负向稳定优先，同档只保留一个确定性依据；候选全同档时
  不记录未影响排序的使用依据。1000 条匹配 Memory 回归无 ValidationError、超时或
  第二排序器
- 常用区域：创建只接受深圳正式行政区结构化值和对应规范内容，不接受地址、坐标、
  POI 或门牌号；推断确认不能创建位置 Memory。因现有契约不能证明任意修改仍为
  粗粒度，API 和 M07 均禁止 usual_area 内容/值修改，只保留停用、启用和删除
- 前端恢复：组件内 ref 以写入载荷持有幂等键，不确定结果复用，成功或载荷改变后
  才换键；409 同时刷新列表和当前详情。延迟 Promise、网络结果不确定、409 恢复及
  迟到响应/finally 均不能覆盖新选择、详情、版本或 busy
- 迁移与测试：未新增 0017，未修改 0015 及更早迁移；新增 0015 真实旧 JSON 升级
  读取回归。pip check、Ruff、strict mypy（135 个源文件）通过；指定聚焦
  `130 passed`；普通与仓库外 DNS/socket 封网非真实全集均为
  `1628 passed, 15 skipped, 2 deselected`；PostgreSQL 迁移和强制行锁测试
  `2 passed`；SQLite 迁移 `25 passed`；Alembic 唯一 head 为 `20260728_0016`
- 前端与复杂度：lint、typecheck、build 通过，Vitest `73 passed`，Playwright
  `27 passed`。没有新增 Memory Store、Repository、偏好服务、排序器、进程锁、
  重试循环、Provider 或状态框架；删除了无产品依据的推断路径，没有生产白名单或
  样本特例
- 安全、风险和下一步：未读取 `.env`，真实模型、地图、网页和付费 API 调用为 0；
  一次性 PostgreSQL 容器已移除，仓库未包含数据库、导出、缓存或真实用户数据。
  六类主控缺陷均已关闭，当前无已知未关闭 P0/P1；保留既有 M1-5 高基数候选截断
  P2。阶段保持“待主控验收”，不合并、不推送、不开始 M1-8

#### 2026-07-29｜M1-7 第二轮主控验收缺陷修复｜待主控验收

- 修复基线：在 `codex/m1-7-memory-data-control` 当前
  `f3cf6b165f00afb752fedf08660c440d5d2699e6` 上追加独立修复；完整提交 SHA 由本次
  最终交付返回。未 amend、rebase、合并 main 或推送
- 反馈建议：现有反馈请求新增可选 `preference_candidate`，必须同时包含类型、内容、
  结构化值和证据摘要；原完成状态、部分/未完成和任意 reason 继续不产生建议。候选
  只进入既有反馈审计并保持 pending，M07 明确确认后才创建 Memory；拒绝决定按完整
  结构化证据阻止后续反馈再次展示。0015 历史 `content/confirmation_status` JSON
  仍按中性候选读取
- 节奏优先级：唯一 `PlanConstraints` 新增 `pace_source`，公开请求省略 pace 时标记
  `system_default`，明确提交（包括 balanced）标记 `user_request`。唯一规划执行器只
  在系统默认场景应用有效 pace Memory，并把同一最终约束用于事实、检索、草案、
  持久化和公开响应；只有 Memory 真正改变输入时产生使用依据
- 常用区域：删除深圳行政区名单，复用唯一 `ActivityArea`，常用区域值由一个明确
  分类的 district 或粗区域 label 服务器端规范化生成；创建和修改使用同一边界，
  支持南山区、大学城附近和大鹏新区。请求契约不接受 origin、坐标、地址或 POI
  字段，推断建议仍禁止创建位置 Memory；没有城市白名单或位置关键词解析
- 保留回归：update/delete 取行锁后重查 operation、PostgreSQL 同键并发、一千条
  Memory 有界聚合、前端不确定结果幂等键、409 列表/详情恢复和迟到响应隔离均未
  改写。代码扫描确认不存在 `_SHENZHEN_ADMIN_DISTRICTS`、新增偏好推断服务、
  第二 MemoryService/Repository、排序器、Runner 或前端状态框架
- 验证：pip check、Ruff、strict mypy（135 个源文件）通过；M1-7/检索/草案/迁移
  聚焦 `133 passed`；普通及仓库外 DNS/socket 硬封网非真实全集均为
  `1631 passed, 15 skipped, 2 deselected`；SQLite 迁移与 Alembic 唯一
  `20260728_0016` head 通过；一次性
  PostgreSQL 16 行锁并发及迁移往返 `2 passed`。前端 lint、typecheck、build 通过，
  Vitest `73 passed`，Playwright `27 passed`
- 安全、复杂度与状态：未读取 `.env`，未调用真实模型、地图、网页或付费 API；
  PostgreSQL 容器已移除，没有数据库、导出或真实用户数据进入仓库。三个 P1 的实现
  与回归已完成，但阶段仍保持“待主控验收”，不提前声明验收通过，不合并、不推送、
  不开始 M1-8

#### 2026-07-29｜M1-7 第三轮主控验收缺陷修复｜待主控验收

- 修复基线：在 `codex/m1-7-memory-data-control` 当前
  `1baa982dbec8d8dc2a8d7c68dbd34b4506de32a8` 上追加独立修复；完整提交 SHA 由本次
  最终交付返回。未 amend、rebase、合并 main 或推送
- 领域导入：移除 `app.domain.memories` 对 plans 包的顶层初始化依赖；usual_area
  验证时才延迟引用唯一 `ActivityArea`。新增真实子进程回归，未依赖 pytest
  `conftest` 或预导入 `app.main`
- pace 重算：唯一 `PlanConstraints` 和唯一规划执行器不变。`user_request` 永远
  保留；其余来源每次先恢复 `balanced/system_default`，再应用当前有效且确定性最新
  的 pace Memory。删除、停用、过期和被替换的旧默认立即退出，只有实际改变系统默认
  的 Memory 才记录使用依据
- 建议终态：既有反馈审计和 Memory Repository 使用当前用户、来源 plan 与 NFKC/
  空白/casefold 规范化证据摘要作为稳定身份。confirmed/rejected 均为终态；同计划
  更正 content/value/type 不会重复询问或创建 Memory，不同计划相同文字保持独立；
  0015 历史中性 JSON 继续读取
- pace 契约与界面：`PreferenceSuggestion` 和公开反馈请求统一复用 `PlanPace`
  枚举；非法值在保存反馈前返回 422。M06/M07 pace 值均为 relaxed、balanced、packed
  三项原生选择控件，正负偏好仍为文本；未新增前端状态框架
- 验证：全新进程导入通过；M1-6/M1-7/检索/草案/迁移聚焦 `150 passed`；pip check、
  Ruff、strict mypy（135 个源文件）通过；普通非真实全集及仓库外 DNS/socket 封网
  全集均为 `1641 passed, 15 skipped, 2 deselected`；SQLite 迁移 `25 passed`，
  Alembic 唯一 head `20260728_0016`；一次性 PostgreSQL 16 强制行锁并发与迁移往返
  `2 passed`，容器已移除
- 前端与范围：lint、typecheck、Vitest `73 passed`、build 和 Playwright
  `27 passed`。既有行锁、并发重放、结构化区域、千条 Memory 有界排序、幂等键和
  409 恢复未重做且回归通过。未读取 `.env`，未调用真实模型、地图、网页或付费 API；
  没有地名白名单、关键词推断、第二套服务/仓储/排序器/Runner/状态框架或 M1-8 功能
- 状态与风险：四项修复及自动化验证已完成，但仍保持“待主控验收”，不提前声明验收
  通过。保留既有 M1-5 高基数候选截断 P2；本分支不合并、不推送、不开始 M1-8

#### 2026-07-29｜M1-7 主控最终验收与集成｜已完成

- 集成：最终开发提交 `90b1ec1600b76c154679ee1c070eff7847303c8e` 已从
  `codex/m1-7-memory-data-control` 以 `--ff-only` 集成到 `main`；无冲突、merge
  commit 或额外生产代码变化
- 缺陷复验：全新解释器可独立导入 Memory 领域；非用户 pace 在每次生成前恢复系统
  默认并只应用当前有效记忆；确认/拒绝按用户、来源计划和规范化证据形成终态；非法
  pace 候选在公开边界拒绝；城市无关粗区域继续复用唯一 `ActivityArea`
- 后端：pip check、Ruff、strict mypy（135 个源文件）通过；主控聚焦
  `207 passed`；普通及 DNS/socket 硬封网非真实全集均为
  `1641 passed, 15 skipped, 2 deselected`；PostgreSQL 16 强制行锁与迁移往返
  `2 passed`；Alembic 唯一 head 为 `20260728_0016`
- 前端：lint、typecheck、Vitest `73 passed`、生产 build 和 Playwright
  `27 passed` 全部通过
- 范围与安全：仍只有一套 Memory Service/Repository、AgentRunner、ToolRegistry、
  计划检索和前端状态边界；没有地名白名单、关键词推断、测试专用生产分支或 M1-8
  代码。未读取 `.env`，真实模型、地图、网页及付费 API 调用为 0
- 结论：当前无未关闭 P0/P1；保留既有 M1-5 高基数候选截断 P2。M1-7 正式完成，
  当前唯一允许开始阶段为 M1-8 只读分享能力

#### 2026-07-29｜M1-8 行程只读分享开发｜待主控验收

- 基线与范围：从 `e8d8f918469428e97be528a1770377d889fcbcc6` 创建
  `codex/m1-8-readonly-sharing`；只实现行程只读分享，没有微信 SDK、短链接、
  协作编辑、提醒、通知、部署、真实 Provider 或后续阶段
- 正式边界：新增唯一 `PlanShareService`、唯一 `SharedPlanSnapshot` 脱敏构造入口
  和一套 owner/public 状态；复用既有 Plan/Version、Session、CSRF、Repository、
  MapProvider 与确认读取逻辑，没有第二套 Plan、Version、Session、权限或分享服务
- Token 与数据：`secrets.token_urlsafe(32)` 生成 256-bit bearer，表内只保存
  SHA-256；`20260729_0017` 增加行程/所有者复合外键、token 唯一约束及
  `revoked_at IS NULL` 部分唯一索引。重建先撤销旧记录；PostgreSQL 对根 Plan
  `FOR UPDATE` 串行化，SQLite 保留约束兼容回归
- 公开内容：匿名 GET 只读取最新确认版本；草稿和未选候选不影响公开结果，新确认
  版本立即替换快照。起点只公开结构化行政区，地点只使用确认 POI 的公开地址和本地
  公开路线 URI；收藏正文/URL/备注、记忆、对话、授权、用户身份和内部 ID 均无公开
  DTO 字段
- 撤销与过期：创建重复请求不重新暴露明文；重建使旧 token 立即失效，撤销即时
  生效；到达行程结束后七天边界统一无内容。撤销、过期和不存在不区分，取消只返回
  “行程已取消”
- Web/H5：确认版页面提供创建、一次性复制、预览、重建和撤销；`/share#token`
  使用独立匿名壳层，不出现产品导航或编辑入口，覆盖加载、正常、取消和统一无内容
  状态。320px 与 1280px 截图目视检查通过，无横向溢出
- 安全：owner 写操作复用登录与 CSRF；公开客户端 `credentials: omit`，API 与页面
  均设置 `no-store`、`no-referrer`、`nosniff` 和 noindex。公共路由只注册 GET，
  bearer 不能兑换 Session；分享 URL 使用不发送到服务器的 fragment，固定 API path
  与访问日志不含 token，两个数据库均完成查询后才选择结果
- 验证：pip check、Ruff、strict mypy（139 个源文件）通过；普通离线全集
  `1649 passed, 18 skipped`；M1-8 与 SQLite 迁移聚焦 `33 passed`，仓库外
  DNS/socket 封网插件复跑受影响 M1-6/M1-7/M1-8 与迁移为 `55 passed`；Alembic upgrade/check/
  downgrade-upgrade 往返通过且唯一 head 为 `20260729_0017`
- Fixture 稳定性：全量复跑跨过 M1-6 固定行程结束时刻后，修正共享 `_seed_plan`
  对墙上时钟的依赖，将历史种子固定在其有效审批窗口；生产规则和原断言未改动
- 前端验证：lint、typecheck、生产 build 通过，Vitest `80 passed`，Playwright
  `29 passed`；新增匿名 320px、取消/无内容与无编辑入口回归
- PostgreSQL 说明：已提交真实 PostgreSQL 八请求同计划行锁、不同计划并发和部分
  唯一索引终态测试。本机没有 Docker、postgres/pg_ctl/psql 或已授权
  `TEST_POSTGRESQL_URL`，按既有 fixture 跳过 1 项；主控必须在隔离 PostgreSQL
  环境复跑后再验收
- 复杂度与安全复核：无测试样本白名单、进程锁、第二 Repository/Runner/Registry、
  真实外部调用或 `.env` 读取；未合并、未推送，等待主控与 QA

#### 2026-07-29｜M1-8 主控验收缺陷修复｜待主控复验

- 修复基线与范围：在失败候选
  `c6f4023d7d8da4364fc57a76685a11fe9c7e8a8a` 上只追加修复；没有 amend、
  rebase、合并、推送或进入 M1-Gate。原 3 个 P1 和 1 个 P2 均已关闭
- P1 重建幂等与并发：`plan_share_links` 最小扩展既有 `20260729_0017`，保存
  所有者作用域幂等键摘要、请求指纹和操作类型，并增加用户/幂等键唯一约束、指纹和操作检查；
  复用既有 `IdempotencyKey`、`plan_request_fingerprint` 和根 Plan
  PostgreSQL 行锁。同键串行或并发只执行一次，重放只返回无明文安全状态；同键跨
  plan/操作返回 409，不同键明确重建会依次使旧 token 失效
- P1 过期优先级：公开读取先以分享记录同步维护的 `expires_at` 判断撤销、无效和
  到期，再判断计划取消；到期前一微秒的取消计划返回 cancelled，到达边界及之后统一
  unavailable。确认后的过期同步改为重新读取最新确认版本，旧确认幂等重放不能回写
  旧过期时间
- P2 标准地图入口：标准 `create_app` 在存在高德配置时构造唯一
  `AmapMapProvider`，公开分享和所有者预览复用既有 `build_navigation_uri`；
  无配置安全降级，URI 构造 HTTP 调用为 0，应用 lifespan 关闭自建 Provider
- P1 创建前预览：新增所有者只读 GET 预览，直接复用唯一
  `PlanShareService._build_snapshot` 与 `SharedPlanSnapshot`；前端先展示实际公开
  日期、地点、公开地址、交通/距离/缓冲、费用、风险、查询时间、路线入口、确认版本
  和失效时间，明确确认后才携带幂等键创建。SQL 语句监听确认预览期间
  `INSERT/UPDATE/DELETE` 为 0
- 安全与冗余：原 token 仍只在首次成功响应出现且数据库只保存 SHA-256；同键重放
  不生成第二个 token。Authorization、token、幂等键、私人字段和内部 ID 不进入
  日志、异常或公开 DTO；仍只有一个分享服务、一个快照构造入口、一个 MapProvider
  适配器和一套状态规则，没有进程锁、重试循环或第二套 DTO
- 自动化证据：pip check、Ruff、strict mypy（139 个源文件）通过；M1-8 聚焦
  `11 passed`，迁移合并聚焦 `36 passed`，普通非真实全集
  `1652 passed, 16 skipped, 2 deselected`。仓库外插件同时封锁 DNS、
  `connect`、`connect_ex` 和 `create_connection` 后受影响测试 `42 passed`
- PostgreSQL 16：一次性 Docker 容器内运行八个独立客户端同键创建/重建、不同键
  明确重建、不同计划并发及迁移往返，`2 passed`；测试完成后容器已删除
- 前端证据：lint、typecheck、生产 build 通过；Vitest `81 passed`，Playwright
  `29 passed`。新增创建前预览、确认创建/复制/重建/撤销及不确定结果同键重试覆盖
- 下一步：保持 M1-8“待主控复验”；等待主控复跑 PostgreSQL 并发、迁移、安全和
  Web/H5 交互，不合并、不推送、不调用真实 API、不开始 M1-Gate

#### 2026-07-29｜M1-8 取消计划所有者分享管理修复｜待主控复验

- 修复基线与范围：在
  `8b8bfdb9356bf49cac46296d87070bd677120963` 上只修复“计划取消后所有者无法
  查看和撤销分享”的 P1；没有修改前端、迁移、公开 DTO 或此前四项修复，也没有进入
  M1-Gate
- 根因与职责收敛：`status()` 和 `revoke()` 不再复用要求最新确认版本的
  `_require_shareable_plan()`。唯一 `PlanShareService` 新增一个内部
  `_require_owned_root()`，统一校验所有权并解析根 Plan；status 只读使用，revoke
  使用同一边界并对根 Plan `FOR UPDATE`。create、regenerate 和 preview 继续要求
  最新确认版本
- 行为关闭：取消并清除 `confirmed_at`/`draft_json` 后，所有者 GET 仍按分享记录
  返回 active 或 expired，DELETE 返回 inactive；撤销前匿名访问为 cancelled，
  撤销后为 unavailable。重复 DELETE 幂等，非所有者查询和撤销保持 404，已过期分享
  仍可由所有者关闭
- 状态优先级保持：到期前取消仍为 public cancelled；到达过期边界及之后仍为
  public unavailable；任意有效期内主动撤销后均为 public unavailable
- 自动化证据：Ruff、strict mypy（139 个源文件）通过；M1-8 契约
  `13 passed`，SQLite 迁移 `25 passed`，普通非真实全集
  `1654 passed, 16 skipped, 2 deselected`；一次性 PostgreSQL 16 分享并发测试
  `1 passed`，容器已删除
- 下一步：继续保持 M1-8“待主控复验”，等待主控验证本 P1；不合并、不推送、不调用
  真实 API、不开始 M1-Gate

#### 2026-07-29｜M1-8 主控最终验收与集成｜已完成

- 验收提交：`6afc2e8233f2129bf2a8103478e02d83ce0be264`；从
  `e8d8f918469428e97be528a1770377d889fcbcc6` 到候选保持单一线性提交链，
  已以 `--ff-only` 集成到 `main`，合并前后代码树一致
- 缺陷关闭：同键并发重建只签发一次明文、过期优先于取消、标准配置创建唯一
  AmapMapProvider、创建前脱敏预览，以及取消/过期后所有者仍可幂等撤销均已独立复核
- 后端证据：pip check、Ruff、strict mypy（139 个源文件）通过；M1-8 与迁移聚焦
  `38 passed`，仓库外取消后撤销探针 `1 passed`，封网聚焦 `35 passed`，非真实全集
  `1654 passed, 16 skipped, 2 deselected`
- 数据库与前端：全新 SQLite 完成 upgrade/check/downgrade/upgrade 往返且唯一 head
  为 `20260729_0017`；一次性 PostgreSQL 16 并发测试 `1 passed`；前端 lint、
  typecheck、build 通过，Vitest `81 passed`，Playwright `29 passed`
- 安全与复杂度：真实模型、地图和网页调用为 0；分享 Token 只存哈希，公开 DTO、
  日志和 Git 无密钥或私人内容；AgentRunner、ToolRegistry、ModelProvider、
  PlanShareService、快照构造和地图 Provider 均保持唯一，无样本特例或测试专用生产分支
- 结论：当前无未关闭 P0/P1，M1-8 已完成；当前唯一允许阶段为 M1-Gate

#### 2026-07-29｜M1-Gate 离线核心闭环验收｜进行中

- 基线与范围：从 `350beedec38013588a9aeba1812bf110f8ba6d8a` 的 `main`
  创建 `codex/m1-gate`；只做 M1-0 至 M1-8 整体 Gate 和测试稳定性收敛，没有新增
  产品功能、迁移、生产服务、微信、提醒、部署或 M2
- 历史文档差异：按用户更正，M1-2 从历史上没有独立 HANDOFF；已读取 DEV_STATUS
  完整记录、阶段定义、README、确认版 UI/UX 原型、实际前端、测试和 Git 历史，
  不补建重复文档，不作为阻塞
- Gate 修复：图片外层截止测试使用确定性准备隔离 Provider 取消传播，关闭全集负载
  下的 0.6 秒准备竞态；PostgreSQL 反馈种子使用固定计划约束 `created_at`，关闭固定
  行程随墙上时钟过期的问题。两项均只修改测试，60/75 秒产品边界、审批规则和
  PostgreSQL 约束不变
- 后端证据：全新 Python 3.14 环境 pip check、Ruff、strict mypy（139 个源文件）
  通过；非真实及硬封 DNS/socket 全集均为 `1654 passed, 16 skipped, 2 deselected`；
  Core `120 passed`，Integration `161 passed, 18 skipped`，封网核心闭环
  `233 passed`
- 数据库与容器：SQLite 完整迁移往返和 check 通过，唯一 head
  `20260729_0017`；一次性 PostgreSQL 16 全部 marker `16 passed`；仓库外无密钥
  Compose 配置完成构建、双 PostgreSQL、API、Worker、健康检查和 Demo API，验证后
  容器与卷已删除
- 前端与闭环：npm ci、lint、typecheck、生产 build 通过，Vitest `81 passed`、
  Playwright `29 passed`；精选闭环 `21 passed`，自动化成功率 100%；20 组计划
  fixture `20 passed` 且硬约束违反数为 0
- 离线性能：PostgreSQL 5,000 条收藏、100 次查询 P95 `18.652 ms`；文字、URL、
  图片各 20 次 Fake/Stub Job/SSE/最终结果均 0 超时，详细提交、首事件、P50、P95
  和最大值见 `docs/technical/M1_VALIDATION_REPORT.md`
- 状态与风险：当前无未关闭 P0/P1；真实模型、地图、网页、截图及付费 API 调用为
  0，真实 12/20 秒性能目标等待用户明确授权，不能用离线观测替代。M1-Gate 保持
  进行中并待主控最终验收，不关闭 M1、不合并、不推送、不开始 M2

#### 2026-07-29｜M1-Gate 真实 API 有限预检｜进行中

- 授权边界：文字、URL、图片、地图各 5 组；模型最多 30、网页最多 30、地图最多
  15 次请求；零自动重试，不设金额上限。未输出密钥、模型名、端点、完整请求或响应
- 调用计数：模型最多 16 次、网页 5 次、地图最多 10 次，其他真实 API 为 0，均未
  超过授权。15 个输入 Job 全部进入安全终态，无超时、重试或重复业务写入
- 输入结果：文字 5/5、图片 5/5 成功；URL 4/5 成功，1 个外部 4xx 被映射为
  `WEB_HTTP_STATUS`。各类只有 5 个样本，不能宣称 P95 已验证；观测最大最终耗时
  分别为文字 4.654 秒、URL 3.029 秒、图片 6.802 秒，均未超过 12/20 秒目标
- 地图阻塞：5 组逻辑样本仅 2 组成功，3 组返回脱敏 `MapProviderError`；当前没有
  足够信息区分供应商/额度环境与代码缺陷，登记为 P1 外部集成可靠性 Gate 阻塞。
  到此停止真实调用，不以重试掩盖问题
- 下一步：按 `docs/technical/M1_VALIDATION_REPORT.md` 的定点 Prompt，在新的明确
  调用授权下仅复现 3 个失败样本并记录稳定安全错误码；阻塞关闭前不关闭 M1、不
  合并、不推送、不开始 M2

#### 2026-07-29｜M1-Gate 高德失败样本定点诊断｜进行中

- 授权与执行：仅复现报告中的 3 个失败公共样本，每组一次、最多 6 次只读地图
  HTTP、`AMAP_MAX_RETRIES=0`；仓库外脚本实际执行 4 次，没有调用模型、网页、
  图片或其他真实 API，没有修改生产代码
- 脱敏结果：样本 1 的 search 与 route 均为 2xx 成功，耗时 333.260 ms 和
  96.303 ms；样本 2、3 的 search 均为 2xx、无 Retry-After，并分别在
  214.087 ms、221.938 ms 返回不可重试的 `MAP_PROVIDER_INVALID_RESPONSE`
- 归因：没有鉴权、限流、超时或网络不可用；样本 1 原失败未复现，不能归为代码
  缺陷。样本 2、3 稳定失败于成功 HTTP 响应后的契约解析边界，但当前授权禁止记录
  响应结构，无法区分供应商畸形候选与 Provider 规则过严
- Gate 结论：尚未明确证明生产代码缺陷，因此没有生产修复 Prompt、没有代码修改；
  P1 缩小为两个样本的响应契约兼容性待归因。若继续，需重新授权只输出字段类别而
  不输出字段值的安全结构分类；M1-Gate 保持进行中，不合并、不推送、不关闭 M1

#### 2026-07-29｜M1-Gate 高德响应安全结构分类｜进行中

- 授权与执行：仅对稳定失败的样本 2、3 各执行一次 search，总计 2/2 次只读地图
  HTTP，`AMAP_MAX_RETRIES=0`；未调用模型、网页、图片、路线或其他真实 API，
  仓库外脚本只在内存分析响应并在进程结束时丢弃
- 脱敏分类：两个 envelope 均有效，`pois` 均为 20 候选列表；首个失败候选序号
  分别为 5 和 9，失败类别均为 `typecode`、形态均为 `nonempty_string`，且失败
  候选之外均至少存在一个可成功映射候选；错误码仍为
  `MAP_PROVIDER_INVALID_RESPONSE`，耗时 296.662 ms、248.263 ms
- 归因：已明确证明 `AmapMapProvider.search_poi` 的候选隔离缺陷；单个畸形必需
  分类字段不应伪造，但也不应令同批合法候选全部丢失。非空响应全部候选均不可映射
  时仍应安全失败
- 处理：未修改生产代码；最小修复 Prompt 已写入
  `docs/technical/M1_VALIDATION_REPORT.md`，要求只在唯一搜索映射边界逐候选隔离，
  禁止样本白名单、第二套 parser、宽泛吞错或响应日志。P1 关闭前不关闭 M1、不
  合并、不推送、不开始 M2

#### 2026-07-29｜M1-Gate 高德候选隔离 P1 修复｜待主控复验

- 基线与范围：从 `ae55dcc3877ede7a6ae8acf98fb2820fb73c9a3e` 创建
  `codex/m1-gate-amap-candidate-isolation`；只修改唯一
  `AmapMapProvider.search_poi` 候选映射边界、对应离线测试和 Gate 记录，没有
  修改迁移、其他 Provider/API/DTO、路线、天气、`get_poi`、重试或 M2 功能
- 生产修复：逐候选调用既有 `_map_poi()`；候选本地的
  `_InvalidAmapResponse`、`ValidationError`、`TypeError`、`ValueError` 只丢弃
  当前候选，合法候选保持原顺序。没有伪造 typecode、坐标、地址、城市或其他字段，
  没有地点/字段白名单、第二套 parser、宽泛异常捕获或响应日志
- 安全语义：原始空列表仍正常返回空结果；非空列表零个候选映射成功仍返回
  `MAP_PROVIDER_INVALID_RESPONSE`；多个有效候选 identity 重复仍整体安全失败；
  混城、非法坐标和必填字段畸形按候选隔离，不削弱内部 POI 契约
- 离线验证：pip check、Ruff 和 strict mypy（139 个源文件）通过；Amap 单元
  `130 passed`；地点目标与外部补充等价契约入口 `70 passed`；仓库外插件封锁
  DNS、connect、connect_ex、create_connection 后聚焦回归 `200 passed`
- 测试路径差异：任务指定的
  `tests/contract/test_m0_3d_place_targets.py` 在指定基线不存在，原命令因此未收集
  测试；使用仓库现有权威等价入口
  `tests/application/test_place_target_service.py` 与
  `tests/application/test_external_place_supplement.py` 完成上述 `70 passed`
- 全集结果：普通和封网非真实全集均为
  `1 failed, 1659 passed, 16 skipped, 2 deselected`。唯一失败位于既有
  `tests/contract/test_m1_5_plans.py:517`：测试在固定 2026-07-29 行程上使用
  `datetime.now(UTC)` 完成生成，当前墙上时钟晚于固定行程有效边界，确认时触发
  `ck_approvals_expiry_order`。该文件未被本分支修改，属于与候选隔离无关的测试
  稳定性问题；本任务按允许范围不修改
- 外部调用与状态：未读取 `.env`，真实高德、模型、网页、图片及其他外部 API
  调用均为 0；没有进行真实复测，没有合并或推送。候选隔离生产修复完成，等待
  主控复验；不得据此关闭 M1-Gate 或开始 M2

#### 2026-07-29｜M1-Gate 最终主控收口｜已完成

- 集成链：`codex/m1-gate-amap-candidate-isolation` 的候选隔离提交
  `a95eeb8bc717ad79733d45b83126552345838039` 与时间夹具提交
  `e6b835f2bfb7c66be2386eca3d9311ffe73adcf2` 已纯快进集成回
  `codex/m1-gate`，没有冲突、merge commit 或额外代码变化
- 离线复验：pip check、Ruff、strict mypy（139 个源文件）通过；Amap 单元
  `130 passed`、地点应用层 `70 passed`、封网聚焦 `200 passed`、M1-5 合同
  `13 passed`；普通及封网非真实全集均为
  `1660 passed, 16 skipped, 2 deselected`
- 合并后检查：高德、地点与 M1-5 聚焦 `213 passed`；Alembic 唯一 head
  `20260729_0017`；工作区干净
- 真实复测：用户明确授权两个原失败样本各一次及一轮标准
  search/detail/route/weather，最多 7 次只读 HTTP、零重试。两个样本分别返回
  19 个城市范围正确的合法候选，耗时 288.979 ms、243.489 ms；标准真实测试
  `1 passed`，耗时 1.15 秒。实际使用 7/7 次，没有调用模型、网页、图片、对象
  存储或其他真实 API，没有输出密钥、端点、完整请求或响应
- 最终结论：高德候选隔离 P1 和独立时间夹具问题均关闭；当前没有未关闭 P0/P1。
  保留 M1-5 高基数候选截断、前端开发依赖审计、跨浏览器/跨平台覆盖及真实性能
  小样本限制等 P2/风险。M1-Gate 已完成，M1 正式关闭，当前允许开始 M2-0
