# M1-Gate 核心闭环验收报告

## 2026-07-30 稳定化纠正

真实运行复验在下方 2026-07-29 历史验收之后确认了截图导入 500、收藏补充 422、
地点确认不可达、Place/Event 与年份证据不稳、截图和文字互斥、Retry 未提交以及
Agent 计划入口不可达。M1-Gate 因此重新打开；下方“M1 正式关闭、允许开始 M2-0”
只作为历史记录保留，不再代表当前状态。

稳定化候选已在基线 `ee701939fe2d61405b769324da3b8df575bfc2bb`、分支
`codex/m1-stabilization-core-loop` 完成，当前状态只能是：

- M1-Gate 稳定化修复：待主控验收；
- M2-0：未开始，阻塞于主控复验；
- M1 未重新关闭。

### 2026-07-30 M1-Gate 修复 3 Event 表单校验阻断返修

M1-Gate 修复 3 表单校验返修完成，等待主控复验；计划闭环与 M2-0 未开始。

主控确认候选 `f85a177fcd76227c9fa9caa06f1df95a186c98fa` 的“具体场次日期”
保留 `min/max` 后，浏览器原生约束会在越界时拦截表单提交，导致既有
`confirmEventTime` 中文范围校验不可达。本次只在 Event 时间表单设置
`noValidate`：日期控件仍为 `date`、时间控件仍为 `time`，场次日期仍保留
`min/max` 选择提示，但所有提交统一进入原业务校验边界。

Chromium 回归通过真实点击“确认并保存”证明：输入超出有效范围的场次日期后显示
“具体场次不在活动有效日期范围内”中文反馈，PATCH 请求数为 0。既有组件回归继续
覆盖有效范围排除原准确场次、原始 UTC 瞬间保真、编辑 `HH:mm` 保留原日期、跨夜
场次、单日及多日 date-only 流程、清空时间，以及 409、422、超时、取消和网络错误
保留草稿。

验证结果：

- 前端 lint、typecheck、build：通过；
- Vitest：`113 passed`；
- `npx playwright test tests/e2e/collections.spec.ts`：`14 passed`；
- 后端 `pip check`、Ruff、strict mypy（140 个源文件）：通过；
- 指定收藏契约、写入单元与结构化检索回归：`72 passed`；
- 迁移回归：`25 passed`；Alembic 唯一 head：`20260729_0017`。

复杂度检查确认生产代码只增加表单级 `noValidate`，没有 `onInvalid`、第二套校验
helper 或重复日期规则。本轮无后端、DTO、数据库、迁移、Prompt、地点匹配、计划
功能或 M2 变更；未读取 `.env`，真实 API 调用为 0；未合并、未推送。

### 2026-07-30 M1-Gate 修复 3 Event 时间语义 P1 返修

M1-Gate 修复 3 返修完成，等待主控复验；计划闭环与 M2-0 未开始。

主控在候选 `f89a9531d57c7fbe66cd1f74573dc2c3658c89da` 发现：多日有效范围
`2026-08-02` 至 `2026-08-04` 内，原准确场次
`2026-08-02T07:30:00Z` 至 `2026-08-02T12:00:00Z` 未编辑直接确认时，结束
时刻会被重建到 8 月 4 日。根因是前端错误地把有效范围两个端点当成准确场次日期。

返修后的边界为：

1. 有效开始/结束日期继续使用 `date`，具体开始/结束时间继续使用 `time`；没有恢复
   `datetime-local`。
2. 已有准确场次时，开始和结束分别从原 ISO 瞬间保留各自上海自然日。未编辑时直接
   提交原始值，两个瞬间完全不变；只编辑 `HH:mm` 时以原日期生成带 `+08:00` 的
   ISO。已有跨日场次也分别保留两端日期。
3. 有效范围编辑不驱动准确场次平移。若修改后任一既有场次日期落在范围外，页面
   明确要求调整场次并且不发送 PATCH。
4. 没有准确场次时，单日范围以该自然日组合时间；多日范围仅增加一个有标签的
   “具体场次日期”控件，开始和结束共同使用用户确认的日期。未提供日期或日期越界
   均不猜测、不提交跨有效范围的伪场次。
5. 清空具体时间继续提交 `null`；只保存日期仍保持准确时间为 `null` 和待补充。
   日期倒置、缺少必要日期、结束不晚于开始均在 PATCH 前拒绝。
6. 409、422、超时、取消和网络错误保留有效日期、场次日期及时间草稿。最终状态、
   `planning_eligible` 和 `location_unconfirmed` 继续只读取服务端响应。

防回归测试明确断言上述 8 月 2 日一日场次直接确认后两个原始 UTC 瞬间不变，并覆盖
编辑时分保留原日、有效范围编辑不平移、跨日场次保真、单日组合、多日禁止猜测与
显式场次日期、越界拒绝、清空提交 `null`、请求失败保留全部草稿及地点服务端阻塞。

验证结果：

- 前端 lint、typecheck、build：通过；
- Vitest：`113 passed`；
- `npx playwright test tests/e2e/collections.spec.ts`：`13 passed`，Event
  表单在 320、390、768、1024、1440px 无横向溢出，标签和字段聚焦通过；
- 后端 Ruff、strict mypy（140 个源文件）：通过；
- 指定三组后端最小契约回归：`52 passed`；
- Alembic 唯一 head：`20260729_0017`。

复杂度检查确认只沿用收藏详情内既有 `isoToShanghaiParts` 和
`shanghaiDateAndTimeToIso`，并复用唯一收藏 PATCH；没有新增 Event Client、DTO、
服务、状态机、Repository 或时间模块。本轮无后端、迁移、Prompt、地点匹配、计划
闭环、Agent 输入或 M2 变更。未读取 `.env`，真实 API 调用为 0；未合并、未推送。

### 2026-07-30 修复 2 主控复验与集成

主控对最终提交 `c10d1237a27632dc74ab9b1cfe0ea0bd6d2dde11` 完成独立复验，并
将阶段分支以 `--ff-only` 集成到 `main`。地点身份变化后保留旧正式 POI、以及已支持
的广州线索无法进入唯一地图匹配链路两个 P1 均已关闭；广州正式 POI 仍由服务端统一
规划资格规则以 `other_city` 排除在深圳计划之外。

复验证据包括：Ruff、strict mypy（140 个源文件）、聚焦集 `201 passed`、非真实
全集 `1707 passed, 16 skipped, 2 deselected`、仓库外独立缺陷回归 `2 passed`、
封网聚焦 `201 passed`、迁移 `25 passed` 和唯一 Alembic head
`20260729_0017`。前端 lint、typecheck、build 通过，Vitest `98 passed`，收藏
Chromium E2E `8 passed`；纯快进后最小后端聚焦仍为 `201 passed`。

全集一次出现既有 `aiosqlite` 线程收尾 warning；对应目标将该 warning 升级为错误
后独立复跑 `1 passed`，未连续复现，继续按既有 P2 监测。复验未读取 `.env`，真实
模型、地图、网页和付费 API 调用为 0；未发现重复核心、样本特例、隐藏 fallback、
额外重试或下一阶段实现。修复 2 当前无未关闭 P0/P1；M1-Gate 仍因 Event 时间交互
和计划闭环后续分项保持打开，当前允许开始修复 3。

### 2026-07-30 M1-Gate 修复 2 生产返修

M1-Gate 修复 2 生产返修完成，等待主控复验；M1-Gate 仍打开，M2-0 未开始且阻塞。

主控 QA 的两个 P1 共用同一根因边界：收藏 PATCH 只按地点字段是否出现决定是否继续
匹配，却不允许已有正式目标随地点身份变化失效；继续确认方法又把非深圳城市提前返回，
并把全部正式请求固定成深圳范围。

本次只收敛既有唯一正式链路：

1. `CollectionWriteService` 在 CAS 写入前比较六个既有地点身份字段。实质变化会原子
   保存编辑、清除旧 `exact/any_branch place_target` 和候选快照，并转回
   `pending_details`，提交后再调用唯一
   `PlaceMatchingService → PlaceTargetSelectionService`。无结果、Provider 异常或
   `CancelledError` 均保留编辑和失效结果，旧正式 POI 不会恢复。
2. 等价判断对城市复用唯一 `resolve_city_hint`，对其他文本只做 NFKC、大小写和空白
   规范化。“深圳”“深圳市”“shenzhen”及其他相同规范化值保持原正式目标，地图
   请求为 0、版本不增加、状态不抖动。
3. 删除非深圳早退和硬编码深圳请求。广州通过既有解析入口进入 `guangzhou`
   `CityScope`；无城市线索仅以深圳作为默认搜索上下文；不支持城市不调用地图且不
   回退深圳。匹配确认的广州 POI 保留 provider、poi_id、正式 city_code 和 GCJ-02，
   但服务端规划资格继续以 `other_city` 排除深圳计划。
4. Place/Event 共用上述路径，Event 的日期、准确时间、确认语义和前端控件未修改。
   既有集中规划阻塞规则、expected_version、选择幂等、并发 CAS 与跨用户所有权边界
   未复制或放宽。

离线证据：`pip check`、Ruff、strict mypy（140 个源文件）通过；地点匹配、收藏
写入、Place/Event、规划资格与 API 错误映射聚焦集 `289 passed`；非真实
Provider/Map 全集 `1707 passed, 16 skipped, 2 deselected`；仓库外 pytest 插件
封锁 `getaddrinfo`、`connect`、`connect_ex`、`create_connection` 后聚焦集
`204 passed`；迁移 `25 passed`，Alembic 唯一 head 为 `20260729_0017`。前端未
改动且不受影响。

本轮没有新增迁移、MapProvider、地点服务、Repository、候选 DTO、城市解析器、
状态机、样本白名单、阈值调整、自动重试或隐藏 fallback。真实模型、高德、网页和
付费 API 调用为 0，`.env` 未读取。Event 时间交互和计划闭环仍留给后续独立修复。

### 2026-07-30 地点确认完整闭环生产修复

地点确认生产修复完成，等待主控验收；M1-Gate 仍打开，M2-0 未开始且阻塞。

缺陷根因和收敛结果：

1. 收藏 PATCH 仅允许 `Place + pending_details` 进入匹配，Event 和
   `pending_selection` 无法在补充地点线索后继续；现由唯一
   `CollectionWriteService` 对六类既有地点线索统一触发继续确认。
2. 文字导入为 Event 维护了独立的城市判断、`PlaceCandidate` 组装、匹配和候选
   写入旁路；该路径已删除，初次导入和后续 PATCH 均复用收藏写服务、
   `PlaceMatchingService` 和 `PlaceTargetSelectionService`。
3. 地图错误在补充 PATCH 后被吞掉，前端会看到保存成功却没有候选；现改为固定、
   可恢复且不含供应商载荷的 HTTP 错误。前端保留草稿，可刷新服务端 version 后
   重试；候选读取单独失败时可原地重载。
4. API 将地点和 Event 时间合并成 `pending_confirmation`，前端又复制 metadata
   推断规划资格；现集中定义地点、城市、其他城市、Event 时间及非活动五类事实
   阻塞，并由 API 与结构化检索共用。前端只展示服务端
   `planning_eligible/planning_exclusion_reason`。
5. 候选记录路径曾在没有正式目标时也清除城市 missing metadata，令无城市线索+
   地图无结果的 Event 违反领域契约；现只有正式目标建立后才清除正式城市相关项。

闭环证据覆盖 Place/Event 补充后自动匹配、无结果待补充、多分店候选、最多三个
候选、不采用供应商第一名、选择具体 POI、“以上都不是”、正式 Amap POI/城市代码/
GCJ-02 坐标写入、Event 地点完成但时间仍阻塞、可选价格/标签/商圈不阻塞、PATCH
旧版本冲突、选择幂等重放、跨用户隔离、地图错误与取消不留错误正式 POI，以及
关闭重开恢复权威候选状态。生产代码未加入“虾一跳”“深圳天文台”或其他店名、标题、
地址、行政区和城市样本特例。

架构与安全复核确认只有一个 `CollectionWriteService`、`PlaceMatchingService`、
`PlaceTargetSelectionService`、`MapProvider`、收藏 Repository、城市解析器和
候选 API 契约。没有新增迁移、自动重试、隐藏 fallback、候选白名单、阈值放宽或
第二套地点状态机。公开错误不记录 API Key、Authorization、Cookie、私人原文、
精确位置日志或完整供应商响应。

离线结果：

- `pip check`、Ruff、strict mypy（140 个源文件）：通过；
- 用户指定地点/收藏/内容导入/检索聚焦集：`264 passed`；
- 非真实 Provider/Map 全集：`1702 passed, 16 skipped, 2 deselected`；
- 仓库外插件封锁 `getaddrinfo`、`connect`、`connect_ex`、
  `create_connection` 后聚焦集：`205 passed`；
- 前端 lint、typecheck、build：通过；Vitest `98 passed`；
- 指定 Agent/收藏 Chromium E2E：`10 passed`；
- 迁移测试：`25 passed`；Alembic 唯一 head：`20260729_0017`。

真实模型、高德、网页和付费 API 调用为 0；`.env` 未读取。未修改 Event 时间
字段/控件、计划生成/调整/确认、Compose 或 M2。剩余 Event 时间交互和计划闭环
问题继续作为后续独立修复，不能据此关闭 M1-Gate 或开始 M2-0。

本次收敛复用唯一正式入口：API 与 Worker 共用运行时 Storage 构造；统一输入提交
负责截图、Message、AgentRun、Source、Job 的补偿；收藏补充继续使用唯一
`CollectionWriteService → PlaceMatchingService → PlaceTargetSelectionService`；
语义证据只在现有结构输出/规范化边界处理；计划按钮只导航到既有计划页。删除了
API `storage=None` 与 Worker 单独构造的运行分叉，以及截图准备失败后保留无 Job
运行记录的旧路径。未新增迁移、Provider、Runner、Registry、Storage、Parser、
匹配器、收藏 Repository、计划服务、样本白名单或自动外部重试。

### 2026-07-30 语义理解与可信确认边界收敛

本轮生产修复完成，等待主控复验；M1-Gate 未关闭。此前 Event 时间验真同时相信
模型自报证据并在应用侧维护标题切片、日期/时刻正则和格式解析表，实质上形成了第二
套脆弱的自然语言理解路径。现已删除 `source_evidence` 的 Schema、Prompt、解析
分支和全部手写时间证据函数；该临时字段不在领域 DTO、数据库、日志或公开响应中。

正式边界收敛为：

1. 模型在唯一 `ExtractionResult` 中提出 Place/Event 及原有四个 Event 时间字段；
2. 文字、URL、截图及 initial/repair 全部经过同一个 canonicalization；
3. 每个非空 Event 时间值原样保留并逐字段标记 uncertainty，不由应用猜测原文语义；
4. 用户通过既有收藏 PATCH 保存具体字段即完成该字段确认；未触及字段仍待确认，
   客户端不能只改 metadata 绕过；
5. 只有准确地点、完整准确场次以及所有已提出时间字段均已确认时，既有状态机才允许
   `pending_details → active`，并由地点选择、API、结构检索和地图计划事实共同复用
   `event_schedule_is_confirmed`。

因此模型错误提出的年份或时刻仍可见、可编辑，但在确认前不能成为计划事实；日期范围
和准确场次保持各自原字段，Event 类型不会因证据失败被改成 Place。没有新增 Parser、
Candidate、Provider、Runner、Repository、确认服务、迁移或并行抽取流程。

生产语义硬编码审计同时删除 `_GENERIC_INPUTS` 名称词表，“咖啡店、餐厅、展览、
活动”等泛化输入交由模型判断。空输入、长度限制和 PRD 明确不支持类型的高置信组合
预检仍作为公开边界硬约束保留；合法标题仅包含菜谱、商品或路线词时已有反例测试保证
不会被拒绝。高置信组合表达式是本轮保留、供主控复验的有限维护风险。

最终离线结果：`pip check`、Ruff、strict mypy（140 个源文件）均退出码 0；后端
全量 `1691 passed, 18 skipped`；仓库外插件封锁 DNS/socket 后的语义、图片、统一
输入、内容导入、收藏 PATCH、计划和 Memory 聚焦集 `340 passed`；Alembic 唯一
head 为 `20260729_0017`。前端生产代码未变，`lint/typecheck/test/build` 均退出码
0，Vitest `87 passed`，本轮按门禁未额外运行 Playwright。真实模型、地图、网页和
付费 API 调用均为 0。

### 2026-07-30 Event 时间确认 Web/H5 闭环

候选 `b5e34ff34c93d39f164e6a033d148b68f2ba6cbe` 已建立“模型建议、用户确认、
确认后才进入计划”的后端边界，但此前 Web/H5 没有提交这四个字段的正式入口。本轮
生产修复在既有收藏详情组件内补齐唯一确认表单，没有新增确认 API、API Client、
Event DTO、Repository 或业务状态机。

- 表单仅对 Event 展示，预填 `event_start_date/event_end_date/event_start_at/
  event_end_at`，同时列出当前时间 missing 与 uncertainty；
- 用户即使不修改建议，点击确认也通过既有收藏 PATCH 显式提交所有当前非空字段；
  清空原有建议则显式提交 null，不能通过直接提交 metadata 绕过确认；
- 日期使用原生 date，准确时刻使用 datetime-local。服务端 ISO 瞬间确定性转换为
  上海本地控件值，提交固定携带 `+08:00`，不依赖浏览器时区；
- 倒置日期和结束不晚于开始的时段在请求前拒绝；409、422、超时和取消保留输入；
  成功后只采用服务端返回的 item、version、status 与 planning eligibility；
- 只确认日期、缺少完整准确时段、仍有时间 uncertainty 或准确 POI 未确认时均继续
  不可规划；Agent 卡片只深链到 `/collections?item=<id>`，不复制时间表单。

后端新增回归覆盖 metadata 绕过、单字段部分确认、完整字段确认、重复确认和 version
冲突；此前准确 POI、完整时段及计划准入测试继续作为同一正式链路证据。验证结果：
`pip check`、Ruff、strict mypy 均退出码 0；指定聚焦集 `127 passed`；非真实
Provider/Map marker 全集 `1692 passed, 16 skipped, 2 deselected`；Alembic 唯一
head `20260729_0017`。前端 lint、typecheck、build 均通过，Vitest
`97 passed`。未新增迁移；真实模型、地图、网页和付费 API 调用为 0。

本轮状态只到“生产修复完成，等待主控复验”；M1-Gate 未关闭，M2-0 继续阻塞。

候选 `e3eeb90b1e25aac6d22ad03c7842b3786d5c1f86` 的主控前复验又发现并修复：

1. **P1：Event 关键词规则和跨候选时间污染。** 原因是文字抽取后置边界用有限活动
   关键词决定是否把 Event 改成 Place，并用整段输入共享的年份、时刻布尔值处理
   所有候选。修复已删除活动关键词白名单和 Event → Place 改型；Place/Event 继续
   由唯一模型语义契约决定，日期和时刻只在当前候选标题绑定的原文证据范围内核验。
   无法证明的时间事实被清除并进入 missing/uncertainty，但候选类型保持不变。
   音乐节、马拉松、工作坊和发布会均不依赖生产关键词；多 Event 的年份和时刻互不
   授权；周末访问偏好由模型契约保持 Place。
2. **P1：不确定网络失败失去幂等身份。** 原因是 Agent 前端每次点击提交或 Retry
   都生成随机键。修复后，未修改的文字/截图组合输入保存稳定 submission key；
   网络断开、超时和取消后的主动 Retry 复用同一键，权威终态识别失败后的主动
   Retry 才使用新键。文字或截图选择、删除、替换、编辑及“继续添加”会失效旧键。
   没有自动重试或第二套幂等服务；服务端响应丢失重放保持相同 message/trace，
   Message、AgentRun、Job、Source 各一条且模型最多调用一次。
3. **P2：图片输入错误错误地统一返回 500。** 类型不允许、签名不符、空文件和文件
   过大现分别返回 415/422/400/413；写入失败、损坏对象和内部故障保持 5xx。公开
   响应只含固定 error code、消息和恢复动作，不暴露文件名、路径、内容、异常链或
   存储实现。

候选 `8c7cd71924012b46f8f0573bc24c5f00b2774ef7` 随后的 Event 时间证据复验确认：
标题位置切片和手写年月日/钟点格式仍会误清中文上午/下午时刻，并在日期位于标题前
的多 Event 输入中跨候选吸收证据。生产修复已完成，等待主控复验，本报告不提前宣布
该 P1 关闭。

修复删除 `_candidate_evidence_scope`、`_date_is_evidenced`、
`_time_is_evidenced`、`_datetime_is_evidenced` 和对应日期/时区格式规则。文字模型
仍在唯一结构输出中返回原有候选，同时附带临时 `source_evidence`；证据逐条绑定
候选序号、Event 时间字段、原始结构值与原文逐字片段。统一解析边界先执行原有严格
领域结构校验，再核对临时字段值、原文片段及跨候选片段占用，最后在构造
`ExtractionResult/EventCandidate` 前删除证据。证据不持久化、不进入公开 DTO；
缺少或冲突时保守清空时间事实并保留 Event 类型。没有第二套 Candidate、Parser、
Provider、Runner、迁移、标题特例或日期/时间格式列表。

候选 `d60975814a1d4d0ae35d246bb6e6d44e1babb58d` 的进一步信任边界复验确认：
`candidate_index`、字段 `value` 和 `quote` 均由同一次模型响应自报，原实现只验证
片段存在、值等于候选字段以及片段不被两个候选同时占用，因此无时间片段、与值不符
的日期片段或另一候选的真实时间片段仍可能被错误信任。

生产修复已完成，等待主控复验。模型现在最多定位原文片段；唯一结构输出解析边界使用
一个集中的确定性时间证据验证器，解析片段内的明确日期和钟点，按
`Asia/Shanghai` 与规范化 Event 字段逐项核对，并把证据限制在当前候选唯一、精确
标题所在的原文分句。重复标题、改写标题、值/片段不一致、无时间片段及跨候选交换或
借用均无法通过，时间字段会保守清空并登记 uncertainty，Event 类型不变。initial
和唯一 repair 都经由同一 `parse_extraction_response` 边界；临时证据仍在领域 DTO
前删除，不持久化、不记录日志、不进入公开结果。没有扩充 Prompt、活动关键词、
标题白名单或样本特例，也没有新增 Candidate、Provider、Runner 或并行抽取流程。

离线验证结果：

- 候选的 pip editable 安装已通过；本轮 `pip check`、Ruff、strict mypy
  （140 个源文件）：退出码均 0；
- 最新指定 Event/API/统一输入/检索/计划聚焦集：`257 passed`，退出码 0；
- 后端非真实全量：`1697 passed, 18 skipped`，退出码 0；
- 仓库外 pytest 插件封锁 `getaddrinfo/connect/connect_ex/create_connection` 后，
  本轮语义、统一输入和内容导入聚焦集：`136 passed`，退出码 0；
  首次把插件文件路径直接传给 `-p` 时 pytest 插件加载参数格式错误，退出码 1、
  未收集或执行测试；改用仓库外目录 `PYTHONPATH` 和模块名后即得到上述通过结果；
- Alembic：唯一 head `20260729_0017`；仓库外临时 SQLite
  `upgrade head/current/check` 均退出码 0；迁移集成 `25 passed`；
- 默认本地数据库只读 `alembic check` 退出码 1，原因是该本地库未升级。为避免修改
  真实用户数据，本任务没有升级它；该结果不是迁移差异，临时干净库显示
  `No new upgrade operations detected`；
- 候选的 `npm ci` 已通过并报告既有开发依赖 9 个 high vulnerability；本轮
  `lint/typecheck/test/build` 均退出码 0，最新单测 `87 passed`；
- Playwright E2E `29 passed`，退出码 0；覆盖 320、390、768、1024、1440，
  输出 4 条 `NO_COLOR`/`FORCE_COLOR` 环境 warning；
- 新增完全离线闭环：
  文字 → 待补充收藏 → 补充地址 → 两个地点候选 → 用户选择 → active →
  计划草案 → 自然语言调整 → 明确确认。

真实模型、高德、网页、对象存储或付费 API 调用均为 0；`.env` 未读取；未合并、
未推送、未开始 M2。Event 时间证据 P1 的生产修复完成，等待主控复验，不在本窗口
宣布关闭；既有 P2 为 npm 开发依赖 audit 和跨浏览器覆盖限制，保留给主控评估。

## 1. 2026-07-29 历史结论

M1-Gate 的离线、封网、PostgreSQL 16、Compose、前端、闭环场景和离线性能观测已
完成。用户随后授权了有限真实 API 预检；文字、网页、图片及既有模型 Tool Calling
预检达到安全终态且未超出性能目标，但地图 5 组逻辑样本只有 2 组成功，另外 3 组
返回脱敏 `MapProviderError`。定点零重试诊断后，其中 1 组已完整成功，另外 2 组
稳定返回 `MAP_PROVIDER_INVALID_RESPONSE`。安全结构分类进一步确认：两个有效
20 候选响应各含一个 `typecode / nonempty_string` 畸形候选，同时存在可成功映射
候选；修复前实现会令整批失败。现已在唯一 `AmapMapProvider.search_poi` 映射边界
完成逐候选隔离，并通过离线、契约和封网聚焦回归。主控随后修复了独立的固定日期
测试夹具，并在新的明确授权下完成真实复测：两个原失败样本均返回 19 个城市范围
正确的合法候选，一轮标准 search/detail/route/weather 验收也通过。

当前状态为 **M1-Gate 已完成，M1 正式关闭**。最终普通及封网非真实全集均为
`1660 passed, 16 skipped, 2 deselected`，当前没有未关闭 P0/P1，允许开始
M2-0。全部真实预检和复测均为零自动重试，没有输出密钥、模型名、端点、完整请求
或响应；最终复测严格使用 7/7 次授权的只读地图 HTTP，没有调用其他真实 API。

## 2. 基线与开始门禁

- 指定基线、`main`、`origin/main` 和分支起点均为
  `350beedec38013588a9aeba1812bf110f8ba6d8a`。
- 工作分支：`codex/m1-gate`；开始时工作区干净。
- Alembic 唯一 head：`20260729_0017`。
- M1-8 已完成，M2 未开始。
- `docs/technical/M1_2_HANDOFF.md` 历史上未单独创建。按用户更正，该差异不构成
  阻塞；M1-2 权威证据来自 `DEV_STATUS` 完整记录、阶段定义、README、确认版
  UI/UX 原型、实际前端、测试和线性 Git 历史。本次没有补建重复交接文档。
- 离线验收没有读取仓库或本机 `.env`；只有获得明确授权后的真实地图进程通过既有
  Settings 配置入口加载本机凭证，凭证、端点和完整请求/响应均未输出或写入报告。

## 3. 范围、架构与安全复核

闭环覆盖输入、收藏、编辑/地点消歧、收藏检索、计划生成、自然语言调整、确认、
路线/日历、手动反馈、记忆/数据控制以及脱敏只读分享。

静态实现和自动化证据确认：

- `AgentRunner`、`ToolRegistry`、`ModelProvider` 抽象与正式
  `OpenAICompatibleProvider` 各只有一套；
- Collection 查询/写入、计划草案/体验/反馈、Memory、分享以及对应正式 Repository
  均保持唯一实现；
- 文字、URL、图片继续复用统一 Message、Source、运行跟踪和收藏写入边界；
- Demo 与真实用户使用独立数据库、存储根和 Web Session；
- PostgreSQL Job 领取/租约恢复、SSE sequence/replay、并发幂等、取消与所有权约束
  通过；重放未产生重复收藏、计划版本、文件、反馈、记忆或分享；
- 未发现测试白名单、地名样本特例、第二套 Runner/Registry/Repository、生产测试
  分支或重复业务规则；
- 未实现微信、提醒发送、云部署、账号绑定或其他 M2 功能；
- 日志、异常、公开 DTO、Git 与前端产物未发现密钥、Cookie、CSRF、Bearer、私人
  原文、完整外部响应或本机路径泄漏。

## 4. Gate 中关闭的测试缺陷

Gate 初始阶段只关闭两个时间/调度相关测试缺陷；候选隔离修复后，主控又关闭一个
独立固定日期测试夹具：

1. 图片外层截止测试原先假定图片线程准备必定在 0.6 秒内完成；全集负载下可能在
   Provider 请求开始前合法超时，导致取消 handler 断言偶发失败。测试现以确定性
   图片准备隔离取消传播边界，产品 60 秒共享截止和 Provider 75 秒异常上限不变。
   修复后聚焦连续 20 次通过，M0-4D 文件 `30 passed`，非真实全集稳定通过。
2. PostgreSQL 反馈测试以墙上时钟创建固定 2026-07-29 行程，执行时间越过行程末尾后
   会违反审批 `created_at < expires_at` 约束。种子现使用固定
   `PlanConstraints.created_at`，不改变生产审批规则或数据库约束。聚焦
   `3 passed`，全部 PostgreSQL marker `16 passed`。
3. M1-5 确认测试使用固定 2026-07-29 行程，却以当前时间创建审批。该用例现只在
   本地生成相对于测试当前时间的未来行程和匹配草稿，不冻结全局时钟、不修改生产
   审批约束。目标用例 `1 passed`，完整 M1-5 合同集 `13 passed`。

## 5. 后端与迁移证据

全新 Python 3.14 虚拟环境、仓库外临时 SQLite：

- `pip check`：通过；
- Ruff：通过；
- strict mypy：139 个源文件通过；
- 最终非真实全集：`1660 passed, 16 skipped, 2 deselected`；
- Core：`120 passed`；
- Integration：`161 passed, 18 skipped`；
- 仓库外插件同时封锁 `socket.getaddrinfo`、`socket.connect`、
  `socket.connect_ex`、`socket.create_connection` 后，非真实全集仍为
  `1654 passed, 16 skipped, 2 deselected`；
- 封网核心闭环聚焦：`233 passed`。

SQLite 迁移完成：

`heads → upgrade head → current → check → downgrade base → upgrade head → current`

最终仍为唯一 `20260729_0017 (head)`，`alembic check` 无待生成操作。

一次性 PostgreSQL 16 全部 marker：`16 passed, 1656 deselected`。覆盖：

- 两 Worker 领取、幂等、三次有界尝试、租约/心跳和服务恢复；
- RunEvent sequence、并发发布与 SSE replay；
- Web Session 并发创建/撤销、Demo 恢复和双库隔离；
- 反馈并发幂等、更正、所有权复合外键；
- Memory 更新/删除/重放和所有权；
- 分享同计划串行、不同计划并发、哈希 token 和唯一终态；
- PostgreSQL 迁移往返。

## 6. 前端与 Compose

Node 25.8.0、npm 11.11.0：

- `npm ci`：通过；
- lint：通过；
- typecheck：通过；
- Vitest：`81 passed`；
- 生产 build：通过，7 个正式路由生成；
- Playwright：`29 passed`，包含真实离线 FastAPI 输入/收藏闭环、计划生成/调整/
  确认/重启恢复、Memory 控制和匿名分享。

仓库外无密钥 `compose.env` 与独立 project name 完成：

- Compose 配置校验和镜像构建；
- API、Worker、真实 PostgreSQL、Demo PostgreSQL 全部 healthy；
- `/healthz` 返回 `ok`；
- Demo Session API 返回 201；
- 两个数据库分别迁移且 Demo User 只写入 Demo 数据库；
- API/Worker 日志未发现 traceback、error 或 credential 泄漏；
- 验证后容器、网络和一次性数据卷均已删除。

首次 BuildKit 拉取 Python 基础镜像元数据发生一次环境网络 deadline；显式拉取基础
镜像后单次重试成功，未修改代码或 Compose。

## 7. 闭环场景和硬约束

精选完整闭环自动化得到 `21 passed`，成功率 `100%`，覆盖：

- 文字、URL、清晰图片和低信息图片；
- 地点候选消歧、跨城市与城市待确认收藏；
- 收藏编辑、删除、恢复和并发版本冲突；
- 收藏充足、结构化缺口、拒绝外部补充；
- 计划生成、自然语言调整、并发重放和明确确认；
- 路线、iCalendar、三态反馈及反馈更正；
- Memory 确认、拒绝、禁用、删除和私有导出；
- 分享预览、创建、重建、撤销、取消、过期和匿名无内容；
- 超时、取消、重复请求、并发和 Worker 租约恢复。

另有 20 组具名确定性计划 fixture：`20 passed`，生成后硬约束违反总数为 0。

## 8. 离线性能观测

所有 P95 均使用 nearest-rank，且每组至少 20 个观测。这里的 SSE 指首个持久化、
可重放 RunEvent 出现时间；不是浏览器网络传输的真实公网首字节。

### PostgreSQL 收藏查询

一次性 PostgreSQL 16、单用户 5,000 条收藏、10 次预热、100 次正式观测：

| 指标 | P50 | P95 | 最大值 | 超时率 |
|---|---:|---:|---:|---:|
| 收藏文本查询完整 Application 调用 | 16.353 ms | 18.652 ms | 20.394 ms | 0% |

低于 500 ms 目标。

### Fake/Stub 异步输入链

每类 20 次，SQLite、Fake Model、Stub Web、本地私有存储、真实 Job/Worker 和持久化
RunEvent：

| 输入 | 阶段 | P50 | P95 | 最大值 | 超时率 |
|---|---|---:|---:|---:|---:|
| 文字 | 202 提交 | 6.754 ms | 14.741 ms | 69.661 ms | 0% |
| 文字 | 首个持久化 SSE 事件 | 16.288 ms | 30.998 ms | 83.401 ms | 0% |
| 文字 | 最终权威结果 | 32.940 ms | 55.265 ms | 102.302 ms | 0% |
| URL | 202 提交 | 6.565 ms | 7.150 ms | 7.672 ms | 0% |
| URL | 首个持久化 SSE 事件 | 16.240 ms | 20.333 ms | 20.434 ms | 0% |
| URL | 最终权威结果 | 34.817 ms | 37.845 ms | 38.878 ms | 0% |
| 图片 | 202 提交 | 8.687 ms | 9.229 ms | 9.420 ms | 0% |
| 图片 | 首个持久化 SSE 事件 | 19.605 ms | 22.030 ms | 22.282 ms | 0% |
| 图片 | 最终权威结果 | 38.713 ms | 41.726 ms | 45.792 ms | 0% |

这些结果证明离线编排没有性能阻断，但不能验证真实文本 12 秒或真实网页/图片 20 秒
目标。普通 Agent 60 秒硬截止和 Provider 75 秒异常安全上限均未调整。

## 9. 真实 API 有限预检

用户授权每类 5 组预检，最多 30 次模型、30 次网页、15 次地图请求，全部零自动
重试且不设金额上限。实际未超过授权：

- 模型请求最多 16 次：统一输入链 14 次，既有只读 Tool Calling 验收最多 2 次；
- 网页请求 5 次；
- 首轮地图请求最多 10 次；随后单独授权的定点诊断使用 4 次，安全结构分类使用
  2 次；修复后最终真实复测再获 7 次授权并全部使用，M1-Gate 地图累计最多 23 次；
- 其他真实 API 请求 0 次。

统一输入链共 15 个 Job，均进入安全终态，没有超时、重试或重复业务写入。文字
5/5、图片 5/5 成功；URL 4/5 成功，另 1 个外部 4xx 被稳定映射为
`WEB_HTTP_STATUS` 可恢复结果。下表的 P95 是 5 个样本的 nearest-rank
**观测值**，样本不足，不能宣称真实 P95 已验证：

| 输入 | 阶段 | P50 | 观测 P95 | 最大值 | 超时率 |
|---|---|---:|---:|---:|---:|
| 文字 | 202 提交 | 9.340 ms | 15.280 ms | 15.280 ms | 0% |
| 文字 | 首个持久化 SSE 事件 | 9.978 ms | 10.984 ms | 10.984 ms | 0% |
| 文字 | 最终权威结果 | 3.783 s | 4.654 s | 4.654 s | 0% |
| URL | 202 提交 | 10.590 ms | 14.800 ms | 14.800 ms | 0% |
| URL | 首个持久化 SSE 事件 | 9.012 ms | 11.989 ms | 11.989 ms | 0% |
| URL | 最终权威结果 | 1.757 s | 3.029 s | 3.029 s | 0% |
| 图片 | 202 提交 | 11.760 ms | 12.280 ms | 12.280 ms | 0% |
| 图片 | 首个持久化 SSE 事件 | 9.012 ms | 9.978 ms | 9.978 ms | 0% |
| 图片 | 最终权威结果 | 5.099 s | 6.802 s | 6.802 s | 0% |

这 5 组观测的最大值低于文字 12 秒、网页/图片 20 秒性能目标，但不能替代至少
20 组样本的正式 P95。既有真实模型 Tool Calling 验收 `1 passed`，耗时
4.88 秒。

地图预检由 1 组既有五项只读验收、1 组搜索/路线链和 3 组独立搜索组成。既有验收
通过（整体 1.27 秒），独立搜索中 1 组成功（208.453 ms）；其余搜索/路线链 1 组
及独立搜索 2 组返回脱敏 `MapProviderError`。最后两组分别在 210.344 ms 和
312.075 ms 终止。5 组只有 2 组成功，样本不足且成功率不合格，不计算或宣称地图
P95。预检到此停止。

用户随后只对上述 3 个失败公共样本授权一次定点诊断：每组执行一次、最多 6 次只读
地图 HTTP、`AMAP_MAX_RETRIES=0`，不调用其他真实 API。仓库外脚本实际使用 4 次
请求，结果如下：

| 样本 | 阶段 | 稳定错误码 | HTTP 类别 | retryable | Retry-After | 耗时 |
|---|---|---|---|---:|---:|---:|
| 1 | search | 无 | 2xx | 不适用 | 无 | 333.260 ms |
| 1 | route | 无 | 2xx | 不适用 | 无 | 96.303 ms |
| 2 | search | `MAP_PROVIDER_INVALID_RESPONSE` | 2xx | false | 无 | 214.087 ms |
| 3 | search | `MAP_PROVIDER_INVALID_RESPONSE` | 2xx | false | 无 | 221.938 ms |

没有出现鉴权、限流、超时、网络不可用或 Retry-After。样本 1 的原失败没有复现，不能
归为生产代码缺陷；样本 2、3 的失败稳定发生在成功 HTTP 响应之后的搜索响应契约
解析边界。由于本轮授权禁止记录响应正文或结构，而现有安全错误只暴露统一错误码，
当前证据无法进一步区分“供应商返回单条畸形 POI”与“Provider 对合法字段形态过严”。
因此该轮没有修改生产代码。

用户再次仅授权样本 2、3 各一次 search、总上限 2 次、零重试的安全结构分类。响应
只在内存分析，脚本和分类结果位于仓库外；没有保存或输出响应、字段值、地点、坐标、
地址、身份、凭证、请求或 Header。两次授权均已使用，未调用其他真实 API：

| 样本 | envelope | pois | 候选数 | 首个失败序号 | 类别 | 形态 | 其余存在可映射候选 | 错误码 | 耗时 |
|---|---:|---:|---:|---:|---|---|---:|---|---:|
| 2 | 有效 | 列表 | 20 | 5 | `typecode` | `nonempty_string` | 是 | `MAP_PROVIDER_INVALID_RESPONSE` | 296.662 ms |
| 3 | 有效 | 列表 | 20 | 9 | `typecode` | `nonempty_string` | 是 | `MAP_PROVIDER_INVALID_RESPONSE` | 248.263 ms |

这证明不是 envelope、列表或全部候选无法满足内部契约，而是单个畸形候选导致同批
其他合法候选全部丢失。不得伪造或猜测畸形 `typecode`；通用修复方向是把候选本地
映射失败隔离到该候选，保留可映射候选。若非空响应全部候选均无法映射，仍返回安全
`MAP_PROVIDER_INVALID_RESPONSE`。

## 10. 修复项、复验状态与剩余 P2

### P1：单个畸形地图候选导致整批合法候选失败（已关闭）

- 定位：`backend/app/providers/amap.py` 的 `search_poi` 搜索映射、
  `backend/tests/integration/test_amap_real.py:42` 的显式真实验收入口。
- 复现：两个固定公共样本均得到有效 20 候选列表；序号 5/9 的首个失败候选为
  `typecode / nonempty_string`，其他候选至少有一个可成功映射，最终仍整体返回
  `MAP_PROVIDER_INVALID_RESPONSE`。
- 实际：单个候选的畸形必需分类字段使同批所有合法候选不可用。
- 预期：不伪造畸形字段；隔离候选本地映射失败并保留合法候选。只有非空响应全部
  候选无法映射、envelope/list 损坏或有效候选存在跨候选冲突时才整体安全失败。
- 修复：在唯一搜索映射边界逐候选调用既有 `_map_poi()`；候选本地的
  `_InvalidAmapResponse`、Pydantic `ValidationError`、`TypeError` 或
  `ValueError` 只丢弃当前候选，合法候选按供应商原顺序返回。没有伪造或猜测任何
  字段，没有增加白名单、第二套 parser、Provider、DTO、候选规则或响应日志。
- 保持的安全边界：原始 `pois=[]` 仍正常返回空结果；原始列表非空但零个候选成功
  映射时仍返回 `MAP_PROVIDER_INVALID_RESPONSE`；重复有效 identity 仍整体失败；
  envelope、HTTP 错误、城市校验、`get_poi`、路线、天气、DTO、重试及公开错误
  映射保持不变。
- 主控离线复验：pip check、Ruff、strict mypy、Amap `130 passed`、地点应用层
  `70 passed`、封网聚焦 `200 passed`；修复时间夹具后，普通及封网非真实全集均为
  `1660 passed, 16 skipped, 2 deselected`。纯快进集成后的聚焦检查
  `213 passed`，Alembic 唯一 head 仍为 `20260729_0017`。
- 真实关闭证据：新的明确授权只允许两个原失败样本各一次，以及一轮标准
  search/detail/route/weather 验收，最多 7 次只读 HTTP、零重试。两个原失败样本
  分别在 288.979 ms 和 243.489 ms 返回 19 个合法候选，城市范围全部正确；
  标准真实测试 `1 passed`，耗时 1.15 秒。实际使用 7/7 次授权请求，未调用模型、
  网页、图片、对象存储或其他真实 API。
- 影响与状态：生产 P1 已由离线、封网和真实供应商复测关闭，没有为样本增加白名单、
  字段伪造、额外重试、第二套 Provider/parser 或响应日志。

已执行的最小生产修复 Prompt：

> 只修复 M0-3B `AmapMapProvider.search_poi` 的候选隔离 P1，不新增产品功能、不
> 调用真实 API。当前 `backend/app/providers/amap.py:211-220` 使用单个 tuple
> comprehension，任一候选的 `_map_poi` 失败会使整个有效搜索响应返回
> `MAP_PROVIDER_INVALID_RESPONSE`。在这一个正式搜索映射边界中逐候选调用现有
> `_map_poi`：候选本地的 `_InvalidAmapResponse`、Pydantic `ValidationError`、
> `TypeError` 或 `ValueError` 只丢弃该候选，不伪造 `typecode`、坐标、地址或其他
> 必需字段；保留所有成功映射候选。原始 `pois=[]` 继续返回空结果；原始列表非空但
> 零个候选可映射时继续返回 `MAP_PROVIDER_INVALID_RESPONSE`；有效候选之间的重复
> identity 继续整体失败。`get_poi`、envelope、城市范围、DTO、重试和安全错误边界
> 不变。不得增加地点/字段值白名单、第二套 parser、宽泛 `except Exception` 或
> 响应日志。补充离线测试覆盖畸形候选位于首/中/尾、多个畸形候选、合法候选保序、
> 全部畸形、原始空列表、重复有效 identity、混城/非法坐标/必填字段畸形、安全异常
> 与输入不变；运行 Ruff、strict mypy、完整 `test_amap_provider.py`、地图契约、
> 非真实全集和 M1 核心闭环。修复后真实复测仍须重新取得授权。

离线复验证据：

- `python -m pip check`、`python -m ruff check .` 通过；strict mypy
  `139` 个源文件通过。
- `tests/unit/test_amap_provider.py`：`130 passed`。
- 指定基线不存在任务文本中的
  `tests/contract/test_m0_3d_place_targets.py`，因此原命令未收集测试；仓库现有
  权威等价入口 `tests/application/test_place_target_service.py` 与
  `tests/application/test_external_place_supplement.py`：`70 passed`。
- 仓库外 pytest 插件封锁 DNS、`connect`、`connect_ex` 和
  `create_connection` 后，Amap 与上述应用层聚焦回归：`200 passed`。
- 普通及封网非真实全集结果一致：
  `1 failed, 1659 passed, 16 skipped, 2 deselected`。唯一失败为既有
  `tests/contract/test_m1_5_plans.py:517`：固定 2026-07-29 行程配合
  `datetime.now(UTC)`，在当前墙上时钟超过固定行程有效边界后，确认写入触发
  `ck_approvals_expiry_order`。该文件未被本修复修改，属于独立测试稳定性问题，
  本分支不越过允许范围修复。
- 本次修复未读取 `.env`，真实地图、模型、网页、图片或其他外部 API 调用为 0；
  未修改迁移，未自行进行真实复测。

- 既有 M1-5 高基数候选截断为非阻断 P2。
- npm 完整开发依赖 audit 仍有 9 个 high，位于既有 ESLint/minimatch 开发依赖链；
  生产构建通过，既有阶段证据中的生产依赖 audit 为 0。
- 浏览器自动化仍以本机 Chromium 为主，未覆盖 Safari/Firefox/Windows。
- M1-2 没有独立 HANDOFF 文件是历史文档组织差异，不是缺陷。

候选隔离 P1、独立时间夹具和最终复验均已关闭。当前没有未关闭 P0/P1；保留上述
P2 与小样本限制。M1-Gate 已完成，M1 正式关闭，当前允许开始 M2-0。
