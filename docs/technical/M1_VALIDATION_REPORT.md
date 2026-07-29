# M1-Gate 核心闭环验收报告

## 1. 结论

M1-Gate 的离线、封网、PostgreSQL 16、Compose、前端、闭环场景和离线性能观测已
完成。用户随后授权了有限真实 API 预检；文字、网页、图片及既有模型 Tool Calling
预检达到安全终态且未超出性能目标，但地图 5 组逻辑样本只有 2 组成功，另外 3 组
返回脱敏 `MapProviderError`。定点零重试诊断后，其中 1 组已完整成功，另外 2 组
稳定返回 `MAP_PROVIDER_INVALID_RESPONSE`。安全结构分类进一步确认：两个有效
20 候选响应各含一个 `typecode / nonempty_string` 畸形候选，同时存在可成功映射
候选；修复前实现会令整批失败。现已在唯一 `AmapMapProvider.search_poi` 映射边界
完成逐候选隔离，并通过离线、契约和封网聚焦回归。

当前状态为 **生产修复完成，等待主控复验**。M1-Gate 仍在进行中；本报告不宣布
M1 关闭，不允许开始 M2，也不自行进行真实复测。真实预检全程零自动重试，没有
输出密钥、模型名、端点、完整请求或响应；本次修复阶段真实 API 调用为 0。

## 2. 基线与开始门禁

- 指定基线、`main`、`origin/main` 和分支起点均为
  `350beedec38013588a9aeba1812bf110f8ba6d8a`。
- 工作分支：`codex/m1-gate`；开始时工作区干净。
- Alembic 唯一 head：`20260729_0017`。
- M1-8 已完成，M2 未开始。
- `docs/technical/M1_2_HANDOFF.md` 历史上未单独创建。按用户更正，该差异不构成
  阻塞；M1-2 权威证据来自 `DEV_STATUS` 完整记录、阶段定义、README、确认版
  UI/UX 原型、实际前端、测试和线性 Git 历史。本次没有补建重复交接文档。
- 未读取仓库或本机 `.env`。

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

本次没有修改生产代码，只关闭两个时间/调度相关测试缺陷：

1. 图片外层截止测试原先假定图片线程准备必定在 0.6 秒内完成；全集负载下可能在
   Provider 请求开始前合法超时，导致取消 handler 断言偶发失败。测试现以确定性
   图片准备隔离取消传播边界，产品 60 秒共享截止和 Provider 75 秒异常上限不变。
   修复后聚焦连续 20 次通过，M0-4D 文件 `30 passed`，非真实全集稳定通过。
2. PostgreSQL 反馈测试以墙上时钟创建固定 2026-07-29 行程，执行时间越过行程末尾后
   会违反审批 `created_at < expires_at` 约束。种子现使用固定
   `PlanConstraints.created_at`，不改变生产审批规则或数据库约束。聚焦
   `3 passed`，全部 PostgreSQL marker `16 passed`。

## 5. 后端与迁移证据

全新 Python 3.14 虚拟环境、仓库外临时 SQLite：

- `pip check`：通过；
- Ruff：通过；
- strict mypy：139 个源文件通过；
- 非真实全集：`1654 passed, 16 skipped, 2 deselected`；
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
- 首轮地图请求最多 10 次；随后单独授权的定点诊断使用 4 次，M1-Gate 累计最多
  14 次；安全结构分类另获 2 次 search 授权并全部使用，M1-Gate 累计最多 16 次；
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

### P1：单个畸形地图候选导致整批合法候选失败（生产修复完成，等待主控复验）

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
- 影响与状态：生产缺陷已定点修复，但未经新的真实调用授权复测，且 M1-Gate 仍需
  主控复验，因此不关闭 M1。

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

候选隔离生产修复已完成，等待主控复验；主控处理独立测试稳定性问题并完成最终
复验前，M1-Gate 不得标记“已完成”，不得合并、推送或开始 M2。
