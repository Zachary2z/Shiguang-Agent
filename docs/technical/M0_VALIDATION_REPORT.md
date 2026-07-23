# M0 技术验证总验收报告

| 项目 | 当前值 |
|---|---|
| 报告状态 | 阻塞：结构兼容性离线修复已完成，等待七个失败样本的独立真实复测授权；重定向网页和 Dockerfile 仍未完成 |
| 验收分支 | `codex/m0-gate-structure-fix` |
| 当前证据提交 | `7660fb0aa2e7607b67e89358930d7ddea4609f53` |
| 生产代码基线（`main` / `origin/main`） | 均为 `0ace869ae2708608d238b77b3ade3153b1307549` |
| 验收日期 | 2026-07-23 |
| 是否允许进入 M1 | 否；真实 Gate 未完整通过 |

## 1. 范围与授权边界

离线阶段只执行 M0-Gate 的独立 QA、隔离安装、回归、迁移、封网、安全、幂等、固定 Fixture 和本地健康检查，没有读取本机 `.env` 或调用外部服务。

随后用户在当前任务中明确授权了六类真实验收，并取消费用上限，但保留逐类请求数硬上限、模型/高德零重试、无副作用和脱敏要求。本轮只为配置门禁读取了完成真实调用所需的本机设置；没有打印或写入密钥、Authorization、Cookie、完整请求/响应、模型名、私人素材或本机用户路径。

## 2. 开始门禁

门禁结果：

- 开始时工作区干净，无未提交用户改动。
- `HEAD`、`main`、`origin/main` 均精确等于指定基线。
- M0-0A 至 M0-5D 的已验收提交均为指定基线祖先。
- Alembic 只有一个 head：`20260722_0006`，六个 revision 为单链。
- 未发现提前实现 PostgreSQL、Worker、SSE、Next.js、Docker Compose 或其他 M1 功能。
- 未发现第二套 `AgentRunner`、`ToolRegistry`、Provider、Repository、地点匹配或计划服务。
- 从指定基线创建了 `codex/m0-regression`。

门禁通过后才开始隔离验收。

## 3. 验收环境

- 系统：macOS 26.5.1，arm64。
- Python：3.13.5。
- pip：25.1.1。
- 安装方式：从指定 commit 的仓库外 `git archive` 快照创建全新虚拟环境，执行 `python -m pip install -e "<快照>/backend[dev]"`。
- 依赖检查：`python -m pip check` 通过，无破损依赖。
- 数据库：仓库外临时 SQLite。
- 网络：正式非真实全集另用仓库外 pytest 插件封锁 DNS `getaddrinfo`、`socket.connect`、`socket.connect_ex` 和 `socket.create_connection`。

## 4. 离线回归结果

| 命令 | 结果 |
|---|---|
| `python -m ruff check .` | 通过 |
| `python -m mypy app migrations nanobot_core` | 通过，93 个源文件 |
| `python -m pytest -q -m "not real_provider and not real_map"` | `1436 passed, 1 skipped, 1 deselected` |
| `python -m pytest -q` | `1436 passed, 2 skipped` |
| `python -m pytest -q tests/core` | `118 passed` |
| `python -m pytest -q tests/integration/test_migrations.py` | `21 passed` |
| `python -m pytest -q tests/contract/test_m0_4d_unified_input.py` | `19 passed` |
| `python -m pytest -q tests/application/test_structured_collection_retrieval.py` | `42 passed` |
| `python -m pytest -q tests/application/test_plan_drafts.py` | `43 passed` |
| `python -m pytest -q tests/application/test_external_place_supplement.py` | `27 passed` |
| 文字、网页、图片、地点、写入和 trace 聚焦组合 | `362 passed` |
| 封网后非真实全集 | `1436 passed, 1 skipped, 1 deselected`；功能断言全部通过，出现第 8.2 节所述偶发收尾 warning |

真实 marker 的两个 skip 符合授权门禁，不计为缺陷。所有命令均显式保持 `RUN_REAL_MODEL_TESTS=0`、`RUN_REAL_MAP_TESTS=0`。

## 5. 迁移与新环境可运行性

临时 SQLite 上依次验证：

1. `alembic upgrade head`；
2. `alembic current` 为 `20260722_0006 (head)`；
3. `alembic check` 报告无新升级操作；
4. `alembic downgrade base`；
5. 再次 `alembic upgrade head`；
6. 最终仍为唯一 `20260722_0006 (head)`。

全部退出 0。按照 README 完成全新环境安装、迁移和测试后，使用临时 SQLite 启动 Uvicorn；`GET /healthz` 返回 HTTP 200 和 `{"status":"ok"}`，Request ID 正常回显，服务可干净关闭。

仓库当前没有 Dockerfile。M0 的 README 本地安装路径已经验证可运行；Dockerfile 是 M0-0B 明确推迟到 Gate 的收尾项，见第 8.3 节。

## 6. M0 场景证据

### 6.1 Agent、错误和循环边界

- Fake Provider 覆盖普通回复、一次 Tool Calling、多轮和单响应多工具调用。
- 覆盖未知工具、非法参数、工具异常、Provider 五类稳定错误、空响应、取消、总超时、循环上限、绝对工具调用上限和重复调用阻断。
- 模型、工具和运行错误只保留稳定错误码及安全摘要。

### 6.2 三种输入

- 文字固定样本覆盖本地价格默认 CNY、无关数字、深圳单地点、多地点、跨城市、Event 完整/缺失时间、结构修复、非法响应和并发隔离。
- URL 固定样本覆盖普通 HTML、纯文本、字符集、可见正文、合法重定向、重定向环、SSRF/DNS rebinding、超时、响应大小和 Cookie/凭证隔离。
- 截图固定样本覆盖清晰 Event、仅店名、模糊截图、多地点、价格与位置不确定、结构修复、格式/尺寸/比例边界和失败清理。
- 每类均明显超过三个离线固定样本，并形成结构化结果或稳定恢复。

### 6.3 地点匹配

深圳固定地点至少包括：

1. 深圳当代艺术与城市规划馆；
2. M Stand 海岸城店；
3. M Stand 万象天地店；
4. 星巴克 COCO Park 店；
5. 星巴克卓悦中心店；
6. 未名咖啡市民中心店；
7. 未名咖啡中心书城店。

覆盖唯一匹配、多候选、无结果、同名分店、区/商圈/地标冲突、深圳与广州显式范围冲突、候选上限和供应商错误。模糊地点不会采用供应商第一项；原唯一首选被收藏去重或活动范围硬约束过滤后，也不会自动晋升较弱候选。

### 6.4 幂等、并发与 trace

- 同一幂等键重复和并发执行只产生一个业务结果，不重复创建收藏、来源、Run、文件或操作。
- 事务中途失败会整体回滚，重试安全；Undo、删除和并发删除保持幂等。
- `trace_id` 可按 owner 查询 AgentRun/ToolRun、顺序、终结原因、Token、费用和安全摘要；跨用户查询按不存在处理。
- 敏感消息、工具参数、异常详情、原始响应、Authorization、Cookie 和文件内容不会进入公开摘要或持久化安全字段。

### 6.5 计划与外部补充

- 20 组具名计划 Fixture 对生成结果逐一断言硬约束违反数为 0。
- 覆盖预算为空、费用未知、已知 CNY、超预算、时间窗、区域、include/exclude 和 Event 边界。
- 收藏充分时外部搜索为 0；无收藏或方案主要依赖外部 Place 时先返回 Approval。
- 拒绝、`collection_only`、Event 缺口、错误 Approval、取消、超时、限流、不可用、非法响应和路线失败均有稳定恢复。
- 不外搜 Event；不会将供应商首项、被过滤首选后的较弱候选或范围冲突候选自动纳入计划。

## 7. 真实验收授权计划与执行边界

六类均已取得当前任务授权。用户明确要求即使无法确认模型费率也继续，但不得突破下列请求数或零重试边界。

| 类别 | 目的与无副作用样本 | 样本数 | 最大请求数 | 可能付费与最大费用 | 超时、重试与总预算 | 脱敏记录 |
|---|---|---:|---:|---|---|---|
| 百炼文本抽取 | 三段合成公开文字：单地点、店名/价格、多地点；验证结构化质量 | 3 | 最多 6 次模型请求（3 次主调用，各至多 1 次结构恢复） | 可能付费；用户取消上限 | 单次 30 秒、SDK 0 重试、每样本端到端 60 秒、该类总墙钟 180 秒 | 模型别名、请求序号、耗时、完成原因、Token、估算费用、稳定错误码 |
| 百炼结构修复 | 对三份固定、无敏感内容的非法结构执行真实修复 | 3 | 3 次模型请求 | 可能付费；用户取消上限 | 单次 30 秒、0 重试、每样本 30 秒、总墙钟 90 秒 | 同上，只记录校验问题类别，不记录完整输入输出 |
| 模型 → Tool → 模型 | 使用纯内存整数加法工具验证一次完整 Tool Calling | 1 | 2 次模型请求、1 次本地工具调用 | 可能付费；用户取消上限 | 模型单次 30 秒、Agent 总时限 60 秒、0 重试 | 两次模型耗时、端到端耗时、工具名、Token、费用、终结原因 |
| 高德搜索/详情/路线 | 深圳馆搜索、详情、步行路线及必要的歧义/空结果只读搜索 | 5 个逻辑样本 | 最多 5 次 HTTP；本轮校准临时设 0 重试，避免把重试混入基线 | 可能消耗配额；用户取消费用上限 | 单次 5 秒、0 重试、每样本 5 秒、总墙钟 25 秒；另用离线结果核对生产 1 次重试的逻辑上限 | endpoint 类别、状态类别、耗时、结果数量、稳定错误码；不记 key、完整查询串或完整响应 |
| 普通网页与重定向网页 | 2 个公开普通页面和 2 个公开重定向页面；只读 GET，无登录、Cookie 或私人 URL | 4 | 最多 14 次 HTTP（每个普通页 1 次；每个重定向页最多 6 hop） | 不应付费 | 每样本总预算 20 秒覆盖全部 hop，连接 5 秒、读取 10 秒、0 重试、总墙钟 80 秒 | origin/页面类型、hop 数、状态类别、字节数区间、耗时、恢复码；不记录 query、Cookie 或正文 |
| 图片识别 | 3 张仓库外脚本生成的合成图片：清晰地点、仅店名、模糊信息；只使用本地私有临时存储 | 3 | 最多 6 次模型请求（3 次识别，各至多 1 次结构恢复） | 可能付费；用户取消上限 | 每样本外层总预算 20 秒覆盖上传、校验、存储、识别与结构校验；SDK 0 重试；总墙钟 60 秒 | 图片类型/尺寸区间、调用与端到端耗时、Token、费用、恢复码；不记录图片、文件名、路径或完整响应 |

原计划费用上限已被用户在执行前明确取消。模型费率未配置，因此只记录 Token，实际费用未知。不会打印完整请求、完整响应、密钥、Authorization、Cookie、私人图片内容或本机路径。

上述小样本只能报告 P50、观测分位值、最大值和原始观测范围，不能声称统计意义上的 P95 已验证。

## 8. 真实验收实际结果

### 8.1 执行环境和调用边界

- 本地 macOS arm64、Python 3.13.5、单进程、同一连接池顺序执行。
- 首次模型调用视为冷连接，后续为同进程热连接；没有另发网络请求定位出口区域，因此只记录运行设备时区为 Asia/Hong_Kong，实际公网出口区域未独立验证。
- 模型 SDK：单次 30 秒、零重试。
- Agent：总时限 60 秒。
- 高德：单次 5 秒、配置为零重试。
- 网页：连接 5 秒、读取 10 秒、每样本总预算 20 秒、零重试。
- 图片：每样本外层总预算 20 秒，覆盖本地生成、校验、私有临时存储、模型识别、结构校验和清理。
- 一次性仓库外脚本在发送前计数，达到类别上限时熔断。没有发生计数越界。

### 8.2 调用次数、成功率和失败

| 类别 | 实际 / 上限 | 底层调用结果 | 端到端验收结果 |
|---|---:|---|---|
| 百炼文本抽取 | 5 / 6 模型请求 | 5/5 成功返回 | 服务 3/3 返回 `ExtractionResult`，但 QA 汇总错误导致具体 outcome 和候选数丢失，结论不完整 |
| 百炼结构修复 | 3 / 3 模型请求 | 3/3 成功返回 | 固定非法首响应后服务 3/3 返回 `ExtractionResult`，但具体 outcome 和候选数丢失，结论不完整 |
| 模型 → Tool → 模型 | 2 / 2 模型请求 | 2/2 成功返回 | 1/1 成功；一次本地加法 Tool，最终答案包含预期值 42 |
| 高德搜索/详情/路线 | 5 / 5 HTTP | 5/5 HTTP 200 | 三次搜索、一次详情和一次步行路线均成功 |
| 普通及重定向网页 | 4 / 14 HTTP | 2 成功、2 ReadTimeout | 普通网页 2/2 成功；两个重定向样本均在首 hop 读取阶段超时，未实际验证 redirect hop |
| 图片识别 | 5 / 6 模型请求 | 5/5 成功返回 | 服务 3/3 返回 `ExtractionResult` 并清理临时存储，但具体 outcome 和候选数丢失，结论不完整 |

模型合计 15 次请求，全部成功返回 Provider 契约；高德 5 次全部成功；网页 4 次中 2 次成功、2 次稳定恢复为 `WEB_TIMEOUT`。没有自动重试，也没有追加样本或替换失败站点。

文字、结构修复和图片的 `AttributeError` 已离线定位到仓库外 QA 汇总脚本：脚本使用了不存在的 `ExtractionOutcome.MODEL_INVALID`，生产枚举实际为 `MODEL_INVALID_OUTPUT`。异常发生在生产服务已经返回 `ExtractionResult` 之后，不是生产代码异常；但由于脚本按安全设计未保存模型正文，具体 outcome 无法在不追加真实调用的情况下恢复。

### 8.3 延迟分布

以下 P95 都只是小样本观测分位值，不具有统计验证含义。

| 类别 | 样本 | P50 | 观测 P95 | 最大 | 超时率 | 重试率 |
|---|---:|---:|---:|---:|---:|---:|
| 文本抽取端到端 | 3 | 8.144 s | 13.686 s | 14.302 s | 0% | 0% |
| 文本抽取模型调用 | 5 | 4.362 s | 7.214 s | 7.257 s | 0% | 0% |
| 结构修复端到端 | 3 | 4.217 s | 4.804 s | 4.869 s | 0% | 0% |
| 结构修复模型调用 | 3 | 4.217 s | 4.803 s | 4.869 s | 0% | 0% |
| 模型 → Tool → 模型端到端 | 1 | 3.052 s | 3.052 s | 3.052 s | 0% | 0% |
| Tool 链模型单次 | 2 | 1.525 s | 1.771 s | 1.798 s | 0% | 0% |
| 高德逻辑调用 | 5 | 176 ms | 300 ms | 304 ms | 0% | 0% |
| 普通网页 | 2 | 128 ms | 178 ms | 184 ms | 0% | 0% |
| 重定向网页样本 | 2 | 13.033 s | 15.236 s | 15.352 s | 100% | 0% |
| 图片端到端 | 3 | 6.208 s | 7.525 s | 7.671 s | 0% | 0% |
| 图片模型调用 | 5 | 3.722 s | 5.749 s | 6.201 s | 0% | 0% |

### 8.4 Token 和费用

| 类别 | 输入 Token | 输出 Token | 总 Token |
|---|---:|---:|---:|
| 文本抽取 | 10,484 | 1,129 | 11,613 |
| 结构修复 | 6,092 | 545 | 6,637 |
| 模型 → Tool → 模型 | 793 | 49 | 842 |
| 图片识别 | 14,333 | 671 | 15,004 |
| 合计 | 31,702 | 2,394 | 34,096 |

本机没有配置模型单价，用户也明确取消了费用上限和“费率未知则停止”的条件，因此实际费用记为“未知”，不推测供应商账单。

### 8.5 超时校准

- 模型单次 30 秒小于 Agent 总时限 60 秒；本轮模型调用最大 7.257 秒，观测 P95 约占单次硬时限 24%，当前余量充足。
- Tool 复合链端到端 3.052 秒，占 Agent 60 秒约 5%；外层时限充足。
- 高德最大 304 ms，占 5 秒约 6%；本轮配置零重试，逻辑总时限明确为每次最多 5 秒。若未来恢复一次重试，必须另行定义包含等待的外层逻辑总预算。
- 普通网页远低于 20 秒。两个重定向目标在首 hop 分别约 10.7 秒和 15.4 秒后恢复为 timeout；外层 20 秒确实覆盖了本次失败恢复，但由于没有成功进入 redirect hop，不能证明 20 秒覆盖最多五次重定向的真实链路。不得据此无限提高时限。
- 图片端到端最大 7.671 秒，占 20 秒约 38%；观测上 20 秒足够。本链仍依赖 20 秒外层预算早于模型 SDK 的 30 秒取消长调用，后续应持续监测外层取消是否稳定。
- 小样本未达到建议的统计 P95 验证量，以上只能作为本次网络条件下的观测结论。

## 9. 未解决风险与缺陷分级

当前没有已确认的生产 P0/P1；存在两个阻塞 Gate 的验收 P1。以下 P2 和验收 P1 都不通过生产特例、白名单、代理、重复校验或放宽断言处理。

### 9.1 P2 / M1 入口前必须解决：进程内幂等锁注册表不淘汰

- 位置：`backend/app/application/text_collection_workflow.py:115-129`。
- 实际：`IdempotencyLockRegistry` 对每个 `(user_id, idempotency_key)` 永久保留一个 `asyncio.Lock`。仓库外探针创建 100,000 个唯一键后，注册表保留 100,000 项，观测内存约 24.7 MB。
- 预期：已完成且无等待者的键应可安全回收，同时保持同键并发串行化和数据库唯一约束的最终权威性。
- 影响：M0 的短期、单进程正确性不受影响；长时间运行且幂等键高基数时会产生无界内存增长。关闭 M0 后仍必须在开始 M1 业务开发前先解决并复测。
- 复现：实例化 `IdempotencyLockRegistry`，连续对 100,000 个不同键调用 `lock()`，检查 `_locks` 长度和内存。
- 修复后复测：同键并发只执行一次、不同用户/键隔离、异常/取消释放、完成后淘汰、高并发压力、数据库唯一约束仍为最终边界。

完整修复 Prompt：

> 在最新 `main` 上只修复 `IdempotencyLockRegistry` 的无界增长，不改变收藏业务契约，不新增第二套幂等服务。先阅读阶段文档和现有幂等/并发测试。设计一个单一、可证明的进程内锁生命周期：同一业务幂等范围的并发请求共享锁；最后一个持有者/等待者离开后安全淘汰；异常和取消也必须清理；不得因淘汰竞态让同键同时出现两个有效锁。数据库唯一约束继续是跨进程最终权威。删除被替代的旧永久字典路径，不使用固定白名单或仅靠任意容量 LRU 掩盖正确性。补充并发、取消、异常、回收和高基数压力测试，运行 Ruff、mypy、聚焦幂等测试、非真实全集和封网全集，并报告净复杂度与内存结果。

### 9.2 P2：全套结束时偶发 aiosqlite worker 收尾 warning

- 相关生命周期边界：`backend/app/infrastructure/db/session.py:20-64`；warning 被 pytest 归因到的业务用例位置不固定，已落在 `test_structured_collection_retrieval.py:669` 和 `:750`。
- 实际：一次封网全集在 1436 个功能用例全部通过后出现 `PytestUnhandledThreadExceptionWarning`；将该 warning 升级为 error 时得到 1436 passed 加 1 个 teardown error。对应目标文件连续五次以 warning-as-error 单独运行均为 `42 passed`，未复现。
- 预期：测试结束前所有 aiosqlite worker 和事件循环回调均已完成，不出现跨测试、跨事件循环的线程异常。
- 判断：这是历史已记录、非稳定、跨套件资源收尾问题；当前证据不能归因到结构检索业务代码，也未观察到数据错误或生产请求失败。它不阻塞 M0 功能结论，但会削弱 warning-as-error 全套测试的确定性。
- 监测条件：M1 入口修复后及每个数据库生命周期变更合并前，至少运行一次完整非真实全集和一次封网全集，并将 `PytestUnhandledThreadExceptionWarning` 升级为 error；若连续两轮复现、出现悬挂进程/连接，或伴随数据与功能失败，则提升为 P1 并停止集成。
- 修复后复测：全套 warning-as-error 多轮、迁移往返、数据库启动/关闭失败、取消和并发 session 生命周期，确认无悬挂线程且不通过过滤 warning 或 sleep 掩盖。

完整修复 Prompt：

> 在最新 `main` 上独立调查全套 pytest 结束时偶发的 aiosqlite worker 向已关闭事件循环回调问题。不要修改结构检索业务规则，不要过滤 warning、增加固定 sleep、放宽 pytest 配置或堆叠重复 close。先用资源跟踪、事件循环与线程诊断定位哪个 Database/engine/session/fixture 未在所属 loop 中完成关闭；构造可重复的最小顺序测试。修复唯一的资源所有权或 fixture 生命周期边界，并删除被替代的旧清理路径。验证 `Database.close()` 的幂等、启动失败、session 异常、取消和多 loop 行为。至少多轮运行完整非真实全集及封网全集，并使用 `-W error::pytest.PytestUnhandledThreadExceptionWarning`；报告复现率、根因、线程/连接收尾证据和净复杂度。

### 9.3 P2 / M0 关闭前必须解决：最小 Dockerfile 仍未落地

- 位置：`docs/DEVELOPMENT_STAGES.md:452`、`README.md:11`。
- 实际：仓库没有 Dockerfile；README 的原生 Python 安装、迁移、测试和健康检查路径已在全新环境验证通过。
- 预期：在进入依赖 Compose 的 M1 前，明确决定并实现最小 API Dockerfile，或在 M1-0 的单一容器化任务中正式接管，不继续悬空。
- 影响：不影响本轮原生新环境 Gate；会影响 M1 Docker Compose 的可交付性。

完整修复 Prompt：

> 在独立的 M0-Gate Dockerfile 收尾任务中，基于现有 `backend` 包建立唯一的最小 API Dockerfile；不得加入 Worker、PostgreSQL、Docker Compose、M1 业务逻辑或第二套启动入口。使用非 root 用户、固定工作目录、可缓存依赖安装、现有 Uvicorn app factory 和 `/healthz`；密钥只通过运行时环境注入，不复制 `.env`。补充 `.dockerignore`，确保 `.env`、Git、虚拟环境、数据库、缓存、测试响应和本机私有文件不进入 build context 或镜像。验证无密钥 build、容器启动、健康检查、干净关闭、镜像内容和 README 命令；更新 M0 验收报告但不宣称其他真实链已通过。完成后交回 M0-Gate 主控复验，不提前实现 Compose。

### 9.4 已关闭 P1（验收工具）：真实结构结果的 outcome 记录丢失

- 位置：仓库外一次性 QA 脚本的文本、修复和图片结果汇总表达式；生产仓库无对应改动。
- 实际：15 次模型请求均返回 Provider 契约，相关服务也返回 `ExtractionResult`，但脚本随后访问不存在的枚举成员并只记录 `AttributeError`，丢失具体 outcome 和候选数。
- 预期：脚本使用 `ExtractionOutcome.MODEL_INVALID_OUTPUT`，并在不保存正文的前提下记录 outcome、候选数和恢复调用次数。
- 影响：不能证明文字、真实结构修复和图片的具体质量结果，M0-Gate 证据不完整；不是生产缺陷。
- 复测范围：三类原样本、原请求上限、零重试、同一脱敏字段；不得重复 Tool、高德和普通网页。
- 关闭证据：2026-07-23 补充复测已改用生产枚举
  `ExtractionOutcome.MODEL_INVALID_OUTPUT`，9/9 原样本均记录 outcome、候选数量、主调用/
  修复调用次数、单次与端到端耗时、Token、费用状态和稳定恢复结果；详见第 10 节。

完整复测 Prompt：

> 在新的 M0-Gate 复测任务中，先读取本报告并取得用户对文字抽取最多 6 次模型请求、结构修复最多 3 次、图片识别最多 6 次的重新授权。修复仓库外 QA 脚本，使其使用生产枚举 `ExtractionOutcome.MODEL_INVALID_OUTPUT`；在任何真实调用前，用 FakeProvider 覆盖 candidates、insufficient、unsupported、model-invalid 四种 outcome 并验证汇总器。脚本只记录 outcome、候选数量、调用次数、延迟、Token、费用和稳定错误码，不保存完整请求/响应或图片。随后严格按原三个样本逐类复测，模型零重试，不增加样本，不重复 Tool、高德或网页。报告每类成功率、结构结果和恢复次数。

### 9.5 P1（外部验收）：重定向网页真实成功链路未建立

- 位置：真实网页验收的两个公开重定向目标；生产 `HttpxWebContentProvider` 离线 redirect/SSRF 契约仍全部通过。
- 实际：两个样本均在首个 HTTP 请求读取响应头时超时，分别稳定恢复为 `WEB_TIMEOUT`；实际 redirect hop 数为 0。
- 预期：至少一个普通重定向和一个相对或多 hop 重定向在 20 秒外层预算内成功，并记录总 hop 与端到端耗时。
- 影响：本轮证明了失败恢复和 20 秒外层终止，但不能完成真实重定向链及“20 秒覆盖全部 hop”的校准；当前无法区分目标站点、网络路径和生产 Provider 的真实兼容性。
- 复测范围：只复测两个由用户重新批准、无登录/无 Cookie/无副作用的受控重定向目标；合计 HTTP 上限应在执行前明确，零重试，不复测其他五类。

完整复测 Prompt：

> 在新的 M0-Gate 重定向网页复测任务中，先取得用户对两个替代公开重定向样本和明确 HTTP 总上限的授权。调用前离线检查目标只允许 GET、无登录、无 Cookie、无私人 query，且 redirect 最终落到公开 HTML/text 页面；不得通过真实预请求探测。使用生产 `HttpxWebContentProvider`、生产 DNS/SSRF 校验、20 秒总预算、最多 5 hop、零重试，并在 transport 层硬计数。只记录样本序号、HTTP 状态类别、hop 数、字节数区间、单 hop/端到端耗时和稳定恢复码，不记录 URL query、正文或响应头。若再次在首 hop 超时，分类为外部目标/网络问题并停止；若进入 hop 后失败，结合离线同型 Fixture 判断是否存在生产 P1。不得重复模型、高德、普通网页或图片调用。

### 9.6 P1（外部验收）：真实严格结构输出兼容性不足

- 位置：当前真实 ModelProvider 输出与生产 `ExtractionResult` 严格契约之间的兼容边界；
  生产解析入口为 `backend/app/application/extraction_output.py`，文本和图片服务分别为
  `text_extraction.py` 与 `image_recognition.py`。
- 实际：补充复测 9 个原样本中只有 2 个返回 `candidates`；其余 7 个在主调用或唯一
  修复后稳定返回 `MODEL_INVALID_OUTPUT`。13 次底层模型请求均成功返回 Provider
  契约，没有 transport、鉴权、限流或超时错误。
- 预期：三类原样本应稳定形成可用候选或语义上合理的
  `insufficient_information` / `unsupported`，真实结构修复应能将固定非法首响应
  修复成通过生产 parse、validate 和 canonicalize 的结果。
- 分类：真实结构兼容性 P1，根因待安全诊断；Prompt、Schema、模型输出、解析器和
  配置均未排除。
- 复现：使用第 10 节相同三个原样本、生产服务、固定非法 Fixture、逐类硬计数、
  SDK 零重试和相同时限；不得保存模型正文或增加样本。
- 下一步：不追加真实调用。先由 M0-Gate 主控决定是否增加只保留校验路径和类型的
  安全诊断，再确定最小生产或配置修复范围；修复后另行取得明确授权，仅复测失败的
  结构类别，不重复 Tool Calling、高德或普通网页。

## 10. 真实结构结果补充复测

### 10.1 门禁、范围与调用边界

- 分支：`codex/m0-gate-structured-retest`；生产代码 merge-base、`main` 和本地
  `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`。分支只继承上轮
  M0-Gate 文档提交，没有生产业务代码改动。
- 仓库外 QA 汇总器只位于 `/tmp`。真实调用前通过 Ruff、strict mypy 和 FakeProvider
  自测，覆盖 `candidates`、`insufficient_information`、`unsupported`、
  `model_invalid_output` 四种 outcome，并断言不存在旧成员 `MODEL_INVALID`。
- 相关生产回归为 `172 passed / 1 deselected`，覆盖 `ExtractionResult` 契约、
  `TextExtractionService`、`ImageRecognitionService` 和
  `OpenAICompatibleProvider`；生产 SDK 构造仍固定 `max_retries=0`。
- 三类均重新取得本任务明确授权。实际模型请求为文本 `5/6`、结构修复 `3/3`、
  图片 `5/6`，合计 `13/15`；13 次均返回 Provider 契约，超时率 0%，重试率
  0%。没有调用 Tool Calling、高德、普通网页或重定向网页。
- 结构修复的每个样本先由本地固定非法 Fixture 提供首响应，再进行一次真实修复；
  每个样本真实请求均为 1。QA 在内存中用生产 `parse_extraction_response`、
  Pydantic 严格校验和 `canonicalize_extraction_result` 核对真实响应；当解析被拒绝
  时，生产服务按契约返回 `MODEL_INVALID_OUTPUT`，没有保存模型正文或校验值。
- 图片仍使用上轮仓库外脚本生成的三张合成素材和仓库外临时私有存储。每张图均经过
  生产 `ImageRecognitionService`，外层总预算 20 秒；三个临时对象和整个临时私有
  根目录均已清理，未记录 `file_key`。

### 10.2 outcome、候选和调用次数

“记录成功率”表示取得完整脱敏 outcome；“可用结构结果率”表示 outcome 为
`candidates`。后者用于判断当前真实结构链是否可通过 Gate。

| 类别 | 样本 | 实际 / 授权上限 | 记录成功率 | 可用结构结果率 | outcome 分布 | 候选数量 |
|---|---:|---:|---:|---:|---|---|
| 百炼文本抽取 | 3 | 5 / 6 | 3/3（100%） | 1/3（33.3%） | `candidates` 1；`model_invalid_output` 2 | `[1, 0, 0]` |
| 百炼结构修复 | 3 | 3 / 3 | 3/3（100%） | 0/3（0%） | `model_invalid_output` 3 | `[0, 0, 0]` |
| 图片识别 | 3 | 5 / 6 | 3/3（100%） | 1/3（33.3%） | `candidates` 1；`model_invalid_output` 2 | `[1, 0, 0]` |
| 合计 | 9 | 13 / 15 | 9/9（100%） | 2/9（22.2%） | `candidates` 2；`model_invalid_output` 7 | 2 个候选 |

结构修复触发情况：

- 文本样本 2、3 触发唯一结构修复；样本 1 首次返回可用候选。
- 结构修复类三个样本都由本地非法 Fixture 触发一次真实修复，不存在真实主调用。
- 图片样本 2、3 触发唯一结构修复；样本 1 首次返回可用候选。

### 10.3 单次及端到端耗时

| 类别 / 样本 | 模型单次耗时 | 端到端耗时 | outcome |
|---|---|---:|---|
| 文本 1 | 4.071 s | 4.071 s | `candidates` |
| 文本 2 | 3.693 s、4.017 s | 7.711 s | `model_invalid_output` |
| 文本 3 | 4.490 s、4.571 s | 9.062 s | `model_invalid_output` |
| 结构修复 1 | 2.903 s | 2.904 s | `model_invalid_output` |
| 结构修复 2 | 4.253 s | 4.254 s | `model_invalid_output` |
| 结构修复 3 | 4.232 s | 4.233 s | `model_invalid_output` |
| 图片 1 | 5.717 s | 5.725 s | `candidates` |
| 图片 2 | 3.955 s、4.709 s | 8.674 s | `model_invalid_output` |
| 图片 3 | 2.557 s、2.676 s | 5.246 s | `model_invalid_output` |

| 类别 | 口径 | P50 | 观测 P95 | 最大 | 超时率 | 重试率 |
|---|---|---:|---:|---:|---:|---:|
| 文本 | 模型单次（5 次） | 4.071 s | 4.555 s | 4.571 s | 0% | 0% |
| 文本 | 端到端（3 个样本） | 7.711 s | 8.927 s | 9.062 s | 0% | 0% |
| 结构修复 | 模型单次（3 次） | 4.232 s | 4.251 s | 4.253 s | 0% | 0% |
| 结构修复 | 端到端（3 个样本） | 4.233 s | 4.252 s | 4.254 s | 0% | 0% |
| 图片 | 模型单次（5 次） | 3.955 s | 5.516 s | 5.717 s | 0% | 0% |
| 图片 | 端到端（3 个样本） | 5.725 s | 8.379 s | 8.674 s | 0% | 0% |

每类只有 3 个端到端样本，表中 P95 只是本次顺序执行下的观测插值，不具有统计验证
意义。耗时仍明显低于文本/结构单次 30 秒、文本端到端 60 秒和图片端到端 20 秒硬
上限；本轮阻塞原因不是超时。

### 10.4 Token、费用与失败恢复

| 类别 | 输入 Token | 输出 Token | 总 Token | 费用 |
|---|---:|---:|---:|---|
| 文本抽取 | 10,328 | 832 | 11,160 | 未配置单价，未知 |
| 结构修复 | 6,092 | 461 | 6,553 | 未配置单价，未知 |
| 图片识别 | 14,331 | 683 | 15,014 | 未配置单价，未知 |
| 合计 | 30,751 | 1,976 | 32,727 | 未配置单价，未知 |

- 13 次请求都没有 Provider transport、鉴权、限流或超时错误；稳定错误码为空。
- 七个失败样本均由生产服务稳定恢复为 `MODEL_INVALID_OUTPUT`，未产生候选或业务
  收藏写入；图片流程产生的临时私有对象均已清理。QA 汇总器没有再丢失 outcome。
- 文本样本 2、3 和图片样本 2、3 在主调用和唯一修复后仍不符合严格结构契约；结构
  修复类 3/3 的唯一真实修复也不符合契约。按本任务的脱敏限制，没有保存模型正文、
  完整异常或校验值，不能进一步从本次证据区分具体字段错误。
- 当前分类为 **真实结构兼容性 P1，根因待安全诊断；Prompt、Schema、模型输出、
  解析器和配置均未排除。** 离线 172 项相关回归及生产
  parse/validate/fallback 路径均通过，未发现 QA 工具或生产解析器再次丢失 outcome。
- 不追加真实调用，不修改生产代码掩盖结果。下一步应由 M0-Gate 主控先决定是否用
  仅记录安全校验路径/类型的离线诊断收窄兼容性问题，再定义最小复测范围并重新取得
  授权；不得复测已经通过的 Tool Calling、高德或普通网页。

## 11. 当前结论

离线功能、架构边界、迁移、幂等、固定样本、安全、新环境运行和封网行为满足 M0 Gate 的离线部分。真实 Tool Calling 和高德通过；普通网页通过；模型和图片底层调用成功且服务返回结构契约；失败恢复稳定。

真实结构结果的 outcome 补证已完成，原 QA 汇总工具 P1 已关闭；但九个样本只有两个
产生可用候选，七个稳定恢复为 `MODEL_INVALID_OUTPUT`。第 12 节的安全诊断进一步
证明失败集中在严格业务语义 `value_error`，而不是 JSON 形态、传输或 Provider 错误。
两个真实重定向样本也仍未进入 redirect hop。

因此：

- 本结构补测任务不创建 Dockerfile；
- 不合并、不推送；
- 不更新 README 或 DEVELOPMENT_STAGES 为 M0 完成；
- 不生成 M1-0 开发窗口 Prompt；
- M0 保持未关闭；将本结果交回 M0-Gate 主控，等待结构兼容性、重定向网页和
  Dockerfile 三项收尾决策。

## 12. 真实结构兼容性安全诊断

### 12.1 门禁、工具与授权

- 诊断分支从包含证据提交 `27c47bb` 的
  `codex/m0-gate-structured-retest` 创建，开始工作区干净；没有合并 `main`。
- 一次性 QA 工具只位于 `/tmp`，外层包装现有 `ModelProvider`，生产服务仍使用
  `TextExtractionService`、`ImageRecognitionService`、
  `OpenAICompatibleProvider` 和 `parse_extraction_response()`；没有复制 JSON、
  Pydantic、`ExtractionResult`、Provider 或 DTO。
- 工具 Ruff、strict mypy 和 19 项离线安全自测通过；自测覆盖全部指定 parser issue、
  三种非错误 outcome、请求上限前后计数、固定非法首响应、取消/ProviderError 脱敏及
  图片失败清理。生产 Ruff、93 文件 strict mypy 和四组指定回归通过：
  `172 passed`，明确排除 `real_provider`。
- 用户分别授权文本 `4`、固定结构修复 `3`、图片 `4` 次模型请求，合计最多 `11`；
  实际严格为 `4/4 + 3/3 + 4/4 = 11/11`。SDK `max_retries=0`，外层也没有自动
  重试、替换或新增样本；没有调用 Tool Calling、高德或网页。
- 图片使用用户指定的 Helvetica 42、尺寸、坐标和模糊参数在仓库外内存生成；
  `/System/Library/Fonts/Helvetica.ttc` 的字体家族校验为 Helvetica。两个成功处理后
  的临时对象、元数据、reservation、临时文件和整个仓库外私有根目录均已清理。

### 12.2 outcome、响应形态与请求结果

| 类别 | 样本 | 实际 / 上限 | 最终 outcome | 候选数 | Provider 错误 | 超时 | 重试 |
|---|---:|---:|---|---:|---:|---:|---:|
| 文本失败样本 | 2 | 4 / 4 | `model_invalid_output` 2 | 0 | 0 | 0 | 0 |
| 固定结构修复 | 3 | 3 / 3 | `model_invalid_output` 3 | 0 | 0 | 0 | 0 |
| 图片失败样本 | 2 | 4 / 4 | `model_invalid_output` 2 | 0 | 0 | 0 | 0 |
| 合计 | 7 | 11 / 11 | `model_invalid_output` 7 | 0 | 0 | 0 | 0 |

十一份真实响应的 `finish_reason` 均为 `stop`，均存在 content，均没有
`tool_calls`；模型响应字符数只记录区间。文本四次和固定修复三次均落在
`257–1024`；第一张图片两次落在 `257–1024`，模糊图片两次落在 `1–256`。
十一份真实响应全部可通过 JSON 解码，但均未通过生产 `ExtractionResult` 语义校验。
没有 `json_invalid`、`missing_json_content`、`unexpected_tool_calls`、`missing`、
`extra_forbidden`、`literal_error`、`union_tag_invalid` 或
`self_declared_model_invalid`。

### 12.3 initial / repair 安全 issue 分布

| 类别与阶段 | path / type | 次数 |
|---|---|---:|
| 文本 initial | `candidates.0.place / value_error` | 2 |
| 文本 initial | `candidates.1.place / value_error` | 1 |
| 文本 repair | `candidates.0.place / value_error` | 2 |
| 文本 repair | `candidates.1.place / value_error` | 1 |
| 固定 Fixture initial | `$ / json_invalid` | 3 |
| 固定修复 repair | `candidates.0.place / value_error` | 2 |
| 固定修复 repair | `candidates.0.event / value_error` | 1 |
| 图片 initial | `candidates.0.place / value_error` | 1 |
| 图片 initial | `$ / value_error` | 1 |
| 图片 repair | `candidates.0.place / value_error` | 1 |
| 图片 repair | `$ / value_error` | 1 |

文本和图片的 initial 与唯一 repair 重复相同 path/type，说明当前 repair 消息没有修复
相应语义问题。三个固定非法首响应从 `json_invalid` 变为候选级 `value_error`，说明
repair 改变了输出形态并形成可解析 JSON，但仍未满足契约。生产
`build_repair_messages()` 已实际把安全 issue 加入 repair 消息；本轮没有增加第二次
repair。

### 12.4 延迟、Token 与费用

| 类别 | 模型单次 P50 / 观测 P95 / 最大 | 端到端 P50 / 观测 P95 / 最大 |
|---|---|---|
| 文本 | `5.414 / 6.986 / 7.094 s` | `11.012 / 13.222 / 13.468 s` |
| 固定结构修复 | `5.648 / 16.122 / 17.286 s` | `5.649 / 16.125 / 17.289 s` |
| 图片 | `3.376 / 4.147 / 4.150 s` | `6.699 / 8.135 / 8.294 s` |

以上 P95 只是 2–4 次调用的观测插值，不具有统计意义。所有真实调用低于模型 30 秒
单次时限；两个图片样本均低于 20 秒外层预算。

| 类别 | 输入 Token | 输出 Token | 总 Token | 费用 |
|---|---:|---:|---:|---|
| 文本 | 8,484 | 944 | 9,428 | 未配置单价，未知 |
| 固定结构修复 | 6,092 | 580 | 6,672 | 未配置单价，未知 |
| 图片 | 11,531 | 420 | 11,951 | 未配置单价，未知 |
| 合计 | 26,107 | 1,944 | 28,051 | 未配置单价，未知 |

### 12.5 根因归类

安全证据支持以下结论：

1. **已经排除本轮 transport/Provider 契约故障。** 11/11 请求返回
   `ModelResponse`，无鉴权、限流、超时、供应商错误、SDK 重试、意外 Tool Call 或
   非 JSON 真实响应。`OpenAICompatibleProvider` 的映射和稳定错误边界不是本轮失败点。
2. **失败集中在 JSON 可解析后的严格业务语义。** 候选级 `value_error` 对应
   `backend/app/domain/collections/extraction.py:137-218` 的价格成对、缺失项/
   不确定项一致性、Place/Event 元数据和 Event 时间语义；根 `$ / value_error`
   对应 `:290-344` 的 outcome 互斥、稳定 reason code、信息缺口和恢复建议语义。
3. **这些规则与 PRD 一致，不应放宽。** PRD 和核心流程要求不确定字段明确标记、
   不编造地点/价格/时间、错误结果不能伪装为空成功、模型结构错误最多修复一次。
   因此当前证据不支持把生产 parser 严格度或领域 DTO 判为缺陷。
4. **JSON Schema 与运行时语义存在表达缺口。** 文本和图片 Prompt 使用
   `ExtractionResult.model_json_schema()`，但本机检查确认生成 Schema 不包含上述
   Pydantic `model_validator` 跨字段语义。Prompt 虽以自然语言覆盖部分规则，模型
   initial 与 repair 仍稳定违反同一语义。
5. **repair 反馈粒度不足。** `extraction_output.py:165-174` 只保留 path/type；
   对 `model_validator`，type 统一退化为 `value_error`。因此
   `build_repair_messages()` 虽正确传入 issue，却无法告诉模型违反了哪一条安全语义
   不变量，文本和图片 repair 复现相同问题。
6. **当前请求未使用 structured output。** `openai_compatible.py:107-114` 只发送
   messages、`enable_thinking=false` 和 `stream=false`，未发送
   `response_format`。本机 OpenAI SDK 2.46.0 已提供 `json_schema` 和
   `json_object` request 类型，但当前配置的远端 endpoint/模型是否支持及支持程度
   未经验证；授权请求已经用尽，不能从 SDK 能力推断远端能力或追加探测。

根因归类为：**Prompt / JSON Schema 表达 / repair 安全反馈 / structured-output
配置之间的兼容性 P1**。生产解析入口是三类输入共享的唯一拒绝边界，但未发现 parser
实现错误；领域 DTO 符合 PRD。当前没有生产 P0；存在阻塞收藏核心链路的生产可用性
P1，修改范围应集中在上述契约桥接，不增加第二套 Parser、DTO 或 Provider。

缺陷记录：

- 文件与行号：`backend/app/application/text_extraction.py:68-98`、
  `backend/app/application/image_recognition.py:62-91`、
  `backend/app/application/extraction_output.py:89-118,165-174`、
  `backend/app/providers/openai_compatible.py:107-114`；领域规则来源为
  `backend/app/domain/collections/extraction.py:137-218,290-344`。
- 实际：模型收到生成 Schema 和自然语言规则，但所有 11 份真实 JSON 在运行时语义
  校验被拒；文本和图片 repair 只得到相同路径的 generic `value_error`，现有
  Provider 请求也没有启用 structured output。
- 预期：初次或唯一 repair 应形成通过同一生产 parser、领域语义和 canonicalization
  的 `candidates`、`insufficient_information` 或 `unsupported`，且不放宽 DTO。
- 复现：使用第 12.2 节同一 7 个失败样本、生产服务、固定非法 Fixture、逐类硬计数、
  SDK 零重试和相同时限；只记录第 12.3 节安全 path/type。
- 影响：文字和图片收藏核心入口在这些合法/可恢复输入上 7/7 无候选，固定结构修复
  3/3 失败，阻塞 M0-Gate；失败恢复安全且没有业务收藏写入或临时图片残留。

### 12.6 独立修复 Prompt

> 在最新已集成基线上修复 M0-Gate 真实结构兼容性 P1，只处理
> `ExtractionResult` Prompt/Schema/repair/structured-output 契约桥接，不开始
> 重定向网页、Dockerfile 或 M1。先完整阅读阶段文档、PRD、核心流程、本报告第 12 节、
> `extraction_output.py`、`text_extraction.py`、`image_recognition.py`、
> `domain/collections/extraction.py`、`openai_compatible.py` 及全部相关测试。
>
> 保留现有唯一 `ExtractionResult`、`parse_extraction_response()`、
> `ModelProvider` 和 `OpenAICompatibleProvider`；不得复制 Parser/DTO/Provider，
> 不得增加默认业务值、样本白名单或第二次 repair，不得放宽价格成对、缺失/
> 不确定项、Place/Event、outcome 和 Event 时间等 PRD 语义。将现有跨字段
> `ValueError` 收敛为不包含 input/value 的稳定安全错误 type，使 repair 仍只接收
> path/type 却能区分具体语义不变量；规则仍只在领域模型执行一次。让用于模型的
> Schema/Prompt 明确表达所有运行时必需形状和跨字段不变量，避免维护与 DTO 漂移的
> 第二份 Schema。
>
> 扩展现有 Provider 请求契约以支持可选 structured-output 参数，并先用离线
> MockTransport 证明请求体、零重试、错误映射、普通 Tool Calling 和非结构调用不受
> 影响。优先验证当前 endpoint/model 的 `json_schema` 能力；若只支持
> `json_object`，记录能力边界并使用同一严格生产 parser 兜底，不得自动额外请求或
> 静默降级。禁止仅根据本机 SDK 类型宣称远端支持。
>
> 增加离线回归：每条稳定语义 issue type、initial/repair 不同与相同问题、文本/
> 图片共享边界、candidates/insufficient/unsupported、固定非法首响应、ProviderError、
> 取消、超长内容、敏感 input/value 不泄漏、最多一次 repair、逐类请求计数和临时图片
> 清理。运行 Ruff、strict mypy、四组现有聚焦测试、Provider MockTransport 测试和
> 非真实全集。
>
> 离线通过后另行取得明确授权，只复测本报告第 12 节的 2 个文本失败样本、3 个固定
> 修复样本和 2 个图片失败 Fixture；上限仍为 `4 + 3 + 4 = 11`、SDK 零重试、图片
> 每样本 20 秒。只记录同一安全白名单。验收要求：不再重复 generic
> `value_error`；7 个样本形成符合语义的 candidates/insufficient/unsupported，
> 或以新的安全 path/type 明确证明剩余最小问题。不得复测 Tool Calling、高德或网页。

## 13. 真实结构兼容性离线修复

### 13.1 门禁与范围

- 工作分支 `codex/m0-gate-structure-fix` 从指定诊断基线
  `bfdaefb0d69bb3562523c58773e5a59c8d31dc5c` 创建；开始工作区干净。
- `main` 与 `origin/main` 均保持
  `0ace869ae2708608d238b77b3ade3153b1307549`，后端生产树在修复前与该提交一致。
- Alembic 唯一 head 保持 `20260722_0006`；没有新增迁移、依赖、Provider、
  Parser、DTO、AgentRunner、ToolRegistry 或 M1 实现。
- 修复提交为 `7660fb0aa2e7607b67e89358930d7ddea4609f53`。范围只包含
  ExtractionResult 的稳定语义错误、共享 Prompt/Schema/repair 桥接、可选
  structured-output 请求契约、显式 capability 配置及对应离线测试。

### 13.2 修复设计

1. Pydantic 跨字段校验继续只在唯一领域模型中执行一次；原有业务规则未放宽。
   `PydanticCustomError` 只把通用 `value_error` 收敛成稳定、无值的规则身份。
2. `extraction_output.py` 成为文字与图片共享的契约桥接：Schema 仍只来自
   `ExtractionResult.model_json_schema()`，每次向调用方返回深拷贝；两类 Prompt
   复用同一语义片段，不维护第二份手写 Schema。
3. repair 仍最多一次，只消费安全 `path/type`。固定 type 映射只给模型提供纠正说明，
   不重新验证对象；未知 type 使用固定通用说明。repair 消息只保留系统契约与安全
   issue，不再携带 source text、图片/Base64 或完整原始模型响应。
4. 唯一 `ModelProvider.chat()` 增加可选、供应商无关的 `StructuredOutput` 请求。
   `OpenAICompatibleProvider` 映射 `json_schema` 与 `json_object`；未提供时请求体与
   历史行为一致。structured output 与 tools 的非法组合在网络前拒绝，不存在
   fallback、能力探测、模型名白名单、额外请求或自动重试。
5. 新配置 `MODEL_STRUCTURED_OUTPUT_MODE` 默认 `none`，只有明确设置
   `json_schema` 或 `json_object` 才启用。该配置表达已验证 capability，不根据 SDK、
   endpoint、供应商或模型名称猜测能力。

主要修改文件：

- `backend/app/domain/collections/extraction.py`
- `backend/app/domain/collections/candidate_metadata.py`
- `backend/app/application/extraction_output.py`
- `backend/app/application/text_extraction.py`
- `backend/app/application/image_recognition.py`
- `backend/nanobot_core/providers/base.py`
- `backend/app/providers/openai_compatible.py`
- `backend/app/config.py`、`backend/app/api/router.py`、`.env.example`
- 对应 core、文字、图片、Provider、配置、API 与运行跟踪测试

### 13.3 稳定安全错误类型

离线测试已直接覆盖以下稳定 type：

- `price_pair_incomplete`
- `price_currency_unsupported`
- `missing_and_uncertain_conflict`
- `present_field_marked_missing`
- `absent_field_not_classified`
- `duplicate_missing_field`
- `duplicate_uncertainty_field`
- `place_has_event_metadata`
- `event_time_order_invalid`
- `event_time_absent_not_classified`
- `candidates_required`
- `candidates_forbidden_for_outcome`
- `reason_code_invalid_for_outcome`
- `unsupported_reason_invalid`
- `insufficient_fields_required`
- `recovery_suggestions_required`
- `model_invalid_self_declared`

另对候选 outcome 携带错误元数据、unsupported 携带字段缺口及 model-invalid 携带模型
派生详情使用独立稳定 type。`_safe_validation_issues()` 仍只输出 `path/type`，测试
证明不包含 `msg`、`ctx`、`input`、`url` 或业务值。

### 13.4 离线验证结果

| 验证 | 结果 |
|---|---|
| `python -m ruff check .` | 通过 |
| `python -m mypy app migrations nanobot_core` | 通过，93 个源文件 |
| 指定文字、图片、Provider 与 core 聚焦组合 | `304 passed` |
| 含配置测试的扩大聚焦组合 | `429 passed` |
| `pytest -m "not real_provider and not real_map"` | `1451 passed, 1 skipped, 1 deselected` |
| 默认 `pytest -q` | `1451 passed, 2 skipped` |
| 仓库外插件封锁 DNS、connect、connect_ex、create_connection 后非真实全集 | `1451 passed, 1 skipped, 1 deselected` |

默认全集与封网全集各观察到一次第 9.2 节已记录的 aiosqlite worker/事件循环收尾
warning，落点不同且所有功能断言通过。本修复未修改数据库生命周期、过滤 warning、
增加 sleep 或跳过测试；该既有 P2 分类不变。

离线覆盖包括三种成功 outcome、应用保留的 model-invalid、全部稳定语义 type、安全
repair、initial/repair 不同及相同问题、最多两次请求、ProviderError、取消、超长
响应、unexpected tool call、文字/图片共享契约、图片清理、输入快照、并发隔离、
普通回复、Tool Calling、json_schema/json_object 请求体、Schema 深拷贝、非法配置
网络前拒绝、零 SDK 重试、错误不 fallback 及安全 repr。

### 13.5 真实能力、调用与 Gate 结论

- 本修复任务未读取 `.env`，未调用真实模型、高德、网页或其他外部服务；新增真实
  请求数、Token 和费用均为 0，未产生新的延迟或 outcome 数据。
- 远端 endpoint/model 的 `json_schema` 与 `json_object` capability 均未验证。
  默认配置因此保持 `none`，不能将本机 SDK 类型或离线请求映射视为远端支持证据。
- 七个原失败样本尚未复测，因此结构兼容性 P1 只能标记为“离线修复完成、等待真实
  复测”，不能关闭。重定向网页验收 P1 与最小 Dockerfile P2 也仍未关闭。
- 当前 P0：无。当前未关闭 P1：结构真实复测、真实重定向链。当前 P2：最小
  Dockerfile、幂等锁注册表、偶发 aiosqlite 收尾 warning。
- 结论：仍不允许进入 M1，也不允许关闭 M0-Gate。

### 13.6 待授权真实复测计划

只有取得本任务新的、分别明确授权后，才读取完成调用所需的 `.env` 设置并执行：

1. 两个原文本失败样本：每样本最多 initial + repair，合计最多 4 次模型请求；
2. 三个固定结构修复样本：首响应为本地固定非法 Fixture，每样本最多 1 次真实
   repair，合计最多 3 次模型请求；
3. 两个原图片失败 Fixture：每样本最多 initial + repair，合计最多 4 次模型请求，
   每样本外层总预算 20 秒。

总上限 `11` 次，SDK `max_retries=0`，外层重试为 0；请求计数在发送前熔断。不得复测
已成功文本/图片、Tool Calling、高德或网页。执行前必须确认
`MODEL_STRUCTURED_OUTPUT_MODE` 对应的远端 capability；若不支持，记录单次稳定
Provider/capability 结果并停止该类别，不切换协议、不追加探测。只记录 initial/repair、
outcome、候选数、安全 `path/type`、耗时、Token、费用和图片清理结果，不记录模型名、
endpoint、请求正文、完整响应、图片、路径或密钥。

## 14. repair 业务证据补充修复

### 14.1 原离线修复不足

第 13 节修复了稳定语义 type、Prompt/Schema 桥接和可选 structured output，但
`build_repair_messages()` 当时只复制 system message，并显式丢弃
`invalid_response`。因此唯一 repair 虽然知道 Schema、错误 path/type 和固定纠正
guidance，却不知道文字用户原始输入，也看不到上一轮模型实际产生的候选结构；图片
repair 同样看不到上一轮候选。离线 FakeProvider 只排队一个任意合法对象，能够证明
第二次响应可通过 Parser，却不能证明修复结果与输入证据属于同一地点或活动。

该缺口允许模型生成结构合法但与业务输入无关的候选，属于阻塞真实复测的 P1。修复
继续集中在唯一共享 `build_repair_messages()` 及两个现有调用方，没有增加 Parser、
DTO、Provider、repair 服务、默认业务值、样本白名单或确定性代修逻辑。

### 14.2 当前证据边界

文字 repair：

- 深拷贝保留初始 system 和原始 user message；
- 在上一轮响应为安全长度的普通文本响应时，以 assistant message 保留该模型文本；
- 最后只追加安全 validation path/type、固定 guidance 和“修复同一候选”的约束；
- 上一轮为空、缺失、超长或含 Tool Call 时不复制不安全响应，但仍可依靠原始文字执行
  唯一 repair。

图片 repair：

- 只保留 system 契约和上一轮安全、可解析且至少含 kind/title 候选身份的结构文本；
- 初始多模态 user message 不进入第二次请求，因此不再次携带 `data:image`、Base64、
  图片字节、原文件名、`file://`、本机私人路径或存储路径；
- repair 指令明确截图不会再次附带，只能修正上一轮已有地点、活动和事实，不得发明；
- 上一轮为空、缺失、超长、含 Tool Call、不可解析、没有候选身份或包含禁止的图片/
  文件证据时，不发起无证据第二次请求，稳定返回 `model_invalid_output`；任意新地点
  不会成为成功候选。

共同边界保持不变：最多 initial + 一次 repair；SDK `max_retries=0`；安全 issue 仍
只有截断后的 `path/type`，不包含 Pydantic `msg`、`ctx`、`input`、`value`、异常文本
或堆栈。完整输入和响应只存在于受控模型请求内，不进入日志、异常、公开 DTO、文档或
测试输出。普通首次请求、普通回复、Tool Calling 和 structured-output 映射未修改。

### 14.3 证据型离线测试

新增测试不使用“第二次固定成功队列即算通过”的结论：

- 文字自定义 Stub 只有在第二次请求同时看到指定原始地点文本与上一轮 assistant
  候选时才返回对应修复结果；
- 图片自定义 Stub 只有在看到上一轮指定候选、且确认请求不含图片载荷、文件名和路径
  时才返回同一候选；
- 图片上一轮完全没有候选证据时，即使 Fake 队列中准备了一个新地点，也只执行一次
  模型调用并返回 `model_invalid_output`；
- 两次含候选证据但仍非法的响应稳定在第二次结束；
- 覆盖 Tool Call、缺失/空白/超长输出、ProviderError、取消、临时图片清理、messages
  深拷贝、response_format/Schema 隔离和安全 validation feedback。

### 14.4 离线验证结果

验证环境为仓库既有 `.venv`：Python 3.13.5、mypy 1.20.2、SQLAlchemy 2.0.51。所有
规定命令退出码均为 0：

| 验证 | 结果 |
|---|---|
| `python -m ruff check .` | 通过 |
| `python -m mypy app migrations nanobot_core` | 通过，93 个源文件 |
| `pytest -q tests/core` | `120 passed` |
| `pytest -q tests/unit/test_openai_compatible_provider.py` | `39 passed` |
| `pytest -q tests/unit/test_text_extraction_contracts.py` | `31 passed` |
| `pytest -q tests/unit/test_text_extraction_service.py` | `62 passed` |
| `pytest -q tests/unit/test_image_recognition_service.py` | `61 passed` |
| `pytest -q tests/test_config.py` | `125 passed` |
| `pytest -q -m "not real_provider and not real_map"` | `1460 passed, 1 skipped, 1 deselected` |
| `pytest -q` | `1460 passed, 2 skipped` |
| 仓库外插件封锁 DNS、connect、connect_ex、create_connection 后非真实全集 | `1460 passed, 1 skipped, 1 deselected` |

默认全集和封网全集各观察到一次第 9.2、13.4 节已记录的 aiosqlite worker/事件循环
收尾 warning，落点不同且所有功能断言通过。本修复没有修改数据库生命周期、过滤
warning、增加 sleep 或 skip。

`git diff --check` 通过；Alembic 仍只有 `20260722_0006` 为最新 revision，没有新增
迁移、依赖、真实配置值或 M1 功能。任务未读取 `.env`，未发起模型、高德、地图、
网页、对象存储、消息或其他外部请求，真实请求数、Token 和费用均为 0。

### 14.5 Gate 结论

原结构兼容性 P1 的 repair 业务证据缺口已完成离线修复，但第 12 节七个真实失败样本
仍未在当前证据修复后复测，远端 structured-output capability 也仍未验证。因此真实
结构 P1 状态继续为“等待真实复测”，不得提前关闭；本结果不允许进入 M1，也不改变
真实重定向链、最小 Dockerfile、幂等锁注册表和 aiosqlite warning 的既有状态。

## 15. 真实结构兼容性最终复测

### 15.1 门禁、环境与样本

- 工作分支 `codex/m0-gate-structure-real-retest` 精确建立在
  `0705eee61b1a5209a886e8925c90c6f7e2f1e8f3`；开始工作区干净，`main` 与
  `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`。
- 生产修复 `7660fb0aa2e7607b67e89358930d7ddea4609f53` 与
  `6d02236e045fdcd923db998c15276e4b9db98b20` 均在当前提交链；没有第三个生产
  代码提交。Alembic 唯一 head 为 `20260722_0006`。
- 首次误用系统 Python 的 mypy `redundant-cast` 结果经用户确认属于验证环境漂移，
  不构成生产缺陷且未修改或删除相关 cast。显式项目环境为 Python `3.13.5`、
  mypy `1.20.2`，`pip check`、Ruff、93 文件 strict mypy 与指定聚焦组合
  `438 passed` 全部通过。
- 复测只使用第 12 节完全相同的两个失败文本、三个固定 repair 文本和两个图片
  Fixture。仓库外 QA 工具在 `/private/tmp` 对齐当前 Provider 签名并增加
  `json_schema` 强制检查、发送前硬计数、候选身份布尔核对和逐类别停止；Ruff、
  strict mypy 与 19 项离线安全自测通过。没有修改生产代码或测试。

### 15.2 授权与执行边界

用户在本窗口明确授权：

> 授权文本复测，最多 4 次；授权固定结构修复，最多 3 次；授权图片复测，最多 4 次。
> 三类均为 0 重试；本轮唯一 structured-output 模式为 json_schema；可能产生模型
> 费用，本轮不设费用上限。若远端不支持该模式，计入已经发出的请求并立即停止对应
> 类别，不得切换 json_object、普通模式或追加探测。

执行严格使用逐类 `4 + 3 + 4 = 11` 发送前硬上限、OpenAI SDK
`max_retries=0`、外层重试 0。进程内显式设置唯一
`MODEL_STRUCTURED_OUTPUT_MODE=json_schema`；未切换 `json_object`、普通模式，
未 fallback、追加 capability 探测、替换样本或扩大调用。

### 15.3 capability、调用与 outcome

| 类别 | 样本范围 | 实际 / 上限 | 真实响应契约 | outcome / 候选 | 安全 Provider 分类 |
|---|---:|---:|---:|---|---|
| 原文本失败样本 | 2 | `1 / 4` | `0 / 1` | 首样本未形成 outcome；第二样本未调用 | `PROVIDER_ERROR` |
| 固定结构修复 | 3 | `1 / 3` | `0 / 1` | 首样本本地 initial 为 `$/json_invalid`，真实 repair 未形成 outcome；其余未调用 | `PROVIDER_ERROR` |
| 原图片失败 Fixture | 2 | `1 / 4` | `0 / 1` | 首样本未形成 outcome；第二样本未调用 | `PROVIDER_ERROR` |
| 合计 | 7 | `3 / 11` | `0 / 3` | 候选成功 `0 / 3` 个已尝试样本 | `PROVIDER_ERROR` 3 |

三个类别的首个真实请求均携带唯一 `json_schema` response format，并在进入
`ModelResponse` 前被远端/SDK API 状态路径拒绝。每类均在该一个已计数请求后立即
停止，没有重复成功样本，也没有触发 initial 后的真实 repair（固定类除本地非法
initial 外，唯一真实调用就是 repair）。

安全结论是：**百炼 OpenAI-compatible Chat Completions 的正式结构化输出模式为
`response_format={"type":"json_object"}`，本轮唯一授权的 `json_schema` 与该协议
不兼容**。官方[结构化输出文档](https://help.aliyun.com/zh/model-studio/qwen-structured-output)
和[错误码说明](https://help.aliyun.com/en/model-studio/error-code)均要求使用
`json_object`。生产 Provider 只公开稳定 `PROVIDER_ERROR`，不保留远端正文；三次
安全失败与官方 capability 边界一致。该结果不是 Parser、严格 Pydantic DTO、
canonicalization、repair 或七个业务样本内容失败；请求在这些边界产生可校验模型
内容之前已经终止。

### 15.4 延迟、Token、费用与清理

| 类别 | 已尝试样本 | 端到端 P50 / 观测 P95 / 最大 | 模型单次延迟 | 超时率 | 重试率 |
|---|---:|---|---|---:|---:|
| 文本 | 1 | `1.248 / 1.248 / 1.248 s` | Provider 未返回，无法取得 | `0%` | `0%` |
| 固定 repair | 1 | `0.353 / 0.353 / 0.353 s` | Provider 未返回，无法取得 | `0%` | `0%` |
| 图片 | 1 | `0.490 / 0.490 / 0.490 s` | Provider 未返回，无法取得 | `0%` | `0%` |

每类只有一个已尝试样本，P95 只是单点观测值，不具有统计验证意义。三个失败请求均
无 Provider Token 记录，输入、输出和总 Token 均不可确认；费率未配置且拒绝请求
是否计费无法确认，费用记录为“费率未知 / 费用不可确认”。

模型 SDK 单次配置时限仍为 30 秒。文本业务外层 60 秒满足单次模型时限小于总时限；
图片复测外层硬预算为 20 秒，当前 30 秒模型时限并不小于外层预算，嵌套预算关系仍
未满足。该问题未造成此次超时，也未在本窗口为通过测试而提高或修改任何时限；应由
后续独立配置校准决定，不能用本次 capability 快速失败证明 20 秒正常余量。

首个图片样本结束后，生产服务失败清理和 QA 私有根检查均通过；`objects`、
`metadata`、临时文件和 reservation 无残留，整个仓库外临时私有根目录已清理。
报告未记录或公开图片、Base64、文件名、路径、哈希、OCR 正文、请求正文或完整响应。

### 15.5 复测后离线回归

真实配置只存在于已经结束的授权进程；后续命令显式清除相关进程环境：

| 验证 | 结果 |
|---|---|
| `python -m ruff check .` | 通过 |
| `python -m mypy app migrations nanobot_core` | 通过，93 个源文件 |
| `pytest -q -m "not real_provider and not real_map"` | `1460 passed, 1 skipped, 1 deselected` |
| 仓库外插件封锁 DNS、`socket.connect`、`connect_ex`、`create_connection` 后再次运行非真实全集 | `1460 passed, 1 skipped, 1 deselected` |

普通非真实全集观察到一次第 9.2 节既有 aiosqlite worker/事件循环收尾 warning；
封网全集没有该 warning。所有功能断言通过，本窗口未修改数据库生命周期、warning
策略、sleep 或 skip，既有 P2 分类不变。

### 15.6 capability 分类与 Gate 结论

- 严重程度：结构兼容性 P1 继续阻塞，但本轮结果属于外部协议 capability 选择，
  不是新的生产代码 P1。
- 边界位置：本轮进程配置选择了百炼 OpenAI-compatible Chat Completions 不支持的
  `json_schema`；现有 `OpenAICompatibleProvider` 和显式 capability 配置已经支持
  官方 `json_object` 请求形态，暂不需要新增生产修复。
- 复现：在当前基线和配置下，使用生产 `OpenAICompatibleProvider`、唯一
  `json_schema`、SDK/外层零重试，对任一原授权样本发送首个请求；发送前计数为 1，
  安全结果为 `PROVIDER_ERROR`，无 `ModelResponse`。
- 实际：三类首请求均在生成可解析内容前失败，七样本业务结构、候选身份和不再出现
  generic `value_error` 的目标无法完成验证。
- 预期：在新的明确授权下使用官方 `json_object` 模式，初次或唯一 repair 返回
  `ModelResponse`，再由唯一生产 Parser、严格 DTO 与 canonicalization 验证七个
  原样本。

因此“真实结构兼容性 P1”**不关闭**，状态改为“等待 `json_object` 模式真实复测”。
本窗口不修改生产代码、不合并、不推送；M0-Gate 继续阻塞，真实重定向链、最小
Dockerfile 和既有 P2 状态均不变。

后续真实复测范围：

> 另开真实复测窗口，在本报告第 12–15 节证据和当前生产实现上重新取得三类明确授权，
> 唯一使用百炼官方 `json_object` 模式复测相同 2 个文本、3 个固定非法 Fixture 和
> 2 个图片 Fixture。总请求上限仍为 `4 + 3 + 4 = 11`，发送前熔断、SDK/外层零
> 重试、图片每样本 20 秒；不得把本轮剩余请求额度结转，也不得切换 `json_schema`、
> 普通模式或增加 capability 探测。逐样本验证 production service → Parser →
> strict DTO → canonicalization、outcome、候选数量、原证据身份、安全 path/type、
> Provider 分类、延迟、Token、费用和图片清理；不得复测 Tool Calling、高德、网页
> 或增加样本。只有七个样本全部通过且无 fallback、ProviderError、超时、重试、额外
> 调用或图片残留时，才关闭结构 P1。

## 16. 百炼官方 json_object 真实结构兼容性复测

### 16.1 基线、门禁与 capability

- 分支 `codex/m0-gate-structure-json-object-retest` 精确从
  `bcd61dfae2be80dca9aa0fc80796a405bae02eee` 创建；开始工作区干净，`main` 与
  `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`。
- `7660fb0`、`6d02236` 与 `bcd61df` 均在提交链；Alembic 唯一 head 仍为
  `20260722_0006`，没有生产代码、迁移、依赖或 M1 变化。
- 项目环境为 Python `3.13.5`、mypy `1.20.2`。`pip check`、Ruff、93 文件 strict
  mypy 与指定聚焦组合 `438 passed` 全部通过。
- 百炼官方结构化输出文档确认 OpenAI-compatible Chat Completions 使用
  `response_format={"type":"json_object"}`，且消息必须包含大小写不敏感的 JSON
  关键词。授权后只读检查的真实配置完整，当前模型类型位于官方列出的支持范围；未
  输出模型、endpoint、密钥或任何配置值。

### 16.2 授权、QA 工具与安全边界

用户在本窗口明确授权文本最多 `4` 次、固定结构 repair 最多 `3` 次、图片最多 `4`
次，合计最多 `11` 次；SDK 与外层重试均为 `0`，唯一 structured-output 模式为
`json_object`，模型单次超时固定为 `8` 秒，图片每样本外层总预算保持 `20` 秒。
禁止切换 `json_schema`、普通模式、模型或 endpoint，也禁止 capability 探测、补充
样本或调用。

仓库外 QA 工具从第 15 节工具机械切换为 `json_object`，保留三类独立发送前计数并
增加总上限 `11` 熔断；原清单从既有任务记录中唯一恢复，没有猜测、重建或替换。
图片继续使用相同生成配方。工具 Ruff、strict mypy 和 19 项离线安全自测通过后才
启动真实请求。真实进程及其清单、结果、图片、私有存储和临时对象均已清理，仓库内
没有保存 QA 工具或结果快照。

### 16.3 调用、outcome 与身份一致性

| 类别 | 样本 | 实际 / 上限 | 通过样本 | production outcome | 身份一致性 |
|---|---:|---:|---:|---|---|
| 原文本失败样本 | 2 | `3 / 4` | `2 / 2` | `candidates` 2 | `2 / 2` |
| 固定结构 repair | 3 | `3 / 3` | `1 / 3` | `candidates` 1；`model_invalid_output` 2 | `1 / 3` |
| 原图片失败 Fixture | 2 | `2 / 4` | `2 / 2` | `candidates` 1；`insufficient_information` 1 | 候选 `1 / 1`；恢复样本 N/A |
| 合计 | 7 | `8 / 11` | `5 / 7` | 候选成功 4；正确恢复 1 | 候选 `4 / 4`；恢复样本 N/A |

两个文本样本分别得到 1、2 个候选，身份均与原证据一致；第二个文本 initial 出现两个
稳定 `absent_field_not_classified`，唯一 repair 后通过。三个固定 Fixture 的本地
initial 均为 `$/json_invalid`；第二个真实 repair 形成 1 个证据一致候选，第一、第三
个 repair 分别在 `candidates.0.place` 与 `candidates.0.event` 留下
`absent_field_not_classified`，最终为 `model_invalid_output`。没有再出现 generic
`value_error`。

清晰图片形成 1 个证据一致候选；模糊图片安全返回 `insufficient_information` 和
0 个候选。后者符合当前生产 Prompt 中“模糊、不可读或信息不足时不得猜测”的规则，
也满足原始 Gate“形成结构化结果或正确恢复”的验收口径，因此判定为正确恢复并通过；
该样本不产生候选，候选身份一致性记为不适用，不能为追求 candidates 要求模型猜测。

全部 8 个真实响应均为 `finish_reason=stop`、存在 content、没有 tool calls。无
ProviderError、鉴权失败、超时、重试、fallback、额外调用或模式切换。图片没有进入
repair，因此“不重传 Base64”继续由离线生产测试证明，本轮没有新增真实 repair
证据。

### 16.4 延迟、Token、费用与预算

| 类别 | 模型单次 P50 / 观测 P95 / 最大 | 端到端 P50 / 观测 P95 / 最大 |
|---|---|---|
| 文本 | `6.318 / 6.699 / 6.741 s` | `8.761 / 12.631 / 13.061 s` |
| 固定结构 repair | `4.048 / 4.520 / 4.572 s` | `4.048 / 4.521 / 4.573 s` |
| 图片 | `2.785 / 3.033 / 3.060 s` | `2.794 / 3.042 / 3.069 s` |

以上 P95 仅为 2–3 次调用的观测插值，不具有统计验证意义。文本观测 P95 为 8 秒硬
超时的约 `83.7%`，高于建议的 60%–75%；固定 repair 约 `56.5%`，图片约 `37.9%`。
所有单次请求均低于 8 秒，文字端到端均低于 60 秒，图片端到端均低于 20 秒。由于两
个图片 initial 都直接形成合法非错误结果，本轮没有实际覆盖“图片 initial + repair
以及上传、存储、校验和清理”在 20 秒内完成，只能确认 `8 + 8 < 20` 的配置嵌套关系，
不能宣称两调用图片链已有真实余量证据。

| 类别 | 输入 Token | 输出 Token | 总 Token | 费用 |
|---|---:|---:|---:|---|
| 文本 | 7,437 | 763 | 8,200 | 费率未知 |
| 固定结构 repair | 7,304 | 504 | 7,808 | 费率未知 |
| 图片 | 6,400 | 169 | 6,569 | 费率未知 |
| 合计 | 21,141 | 1,436 | 22,577 | 费率未知 |

三类超时率、重试率均为 `0%`。图片生产对象、元数据、reservation、临时文件和整个
仓库外私有根均已清理。

### 16.5 复测后离线与封网回归

| 验证 | 结果 |
|---|---|
| `python -m ruff check .` | 通过 |
| `python -m mypy app migrations nanobot_core` | 通过，93 个源文件 |
| `pytest -q -m "not real_provider and not real_map"` | `1460 passed, 1 skipped, 1 deselected` |
| `pytest -q` | `1460 passed, 2 skipped` |
| 封锁 DNS、connect、connect_ex、create_connection 后非真实全集 | `1460 passed, 1 skipped, 1 deselected` |

三轮 pytest 各观察到一次既有 aiosqlite worker/事件循环收尾 warning，功能断言全部
通过；本窗口未修改数据库生命周期、warning 策略、sleep 或 skip，既有 P2 不变。

### 16.6 缺陷分类与 Gate 结论

- P0：无。
- P1：真实结构兼容性继续阻塞。官方 `json_object` transport、Provider、Parser、
  严格 DTO 与 canonicalization 已得到部分真实证据，但固定 repair 只有 `1/3`
  通过，未达到七样本全通过。
- 图片结论：清晰图片候选和模糊图片 `insufficient_information` 分别构成结构成功
  与正确恢复，图片 `2/2` 通过；安全产品规则与原始 Gate 口径一致。
- P1：真实重定向网页链仍未处理。
- P2：最小 Dockerfile、幂等锁注册表与 aiosqlite 收尾 warning 均未处理。
- 超时校准风险：文本观测 P95 占 8 秒硬时限约 `83.7%`，图片 initial + repair
  双调用完整链未获真实覆盖；两项不属于本次结构 P1。

因此真实结构兼容性 P1 **不关闭**，本分支不合并、不推送，M0-Gate 继续阻塞且不得
进入 M1。此次失败不是 `json_object` capability、鉴权、Provider transport、JSON
语法、generic Pydantic 错误、图片正确恢复或临时文件清理问题；唯一剩余结构阻塞是
两个固定 repair 仍未满足缺失字段分类语义。

### 16.7 独立修复任务 Prompt

> 你负责 Shiguang_Nanobot 的 M0-Gate 结构语义收敛，只处理第 16 节两个固定
> repair 暴露的 `absent_field_not_classified`。指定基线为本次文档提交，创建新的
> `codex/` 分支。开始前完整阅读
> AGENTS.md、阶段/状态文档、PRD、核心用户流程、MVP 技术方案、M0 验证报告第
> 12–16 节、共享 extraction output、文字/图片 service、ExtractionResult 领域契约、
> OpenAI-compatible Provider 及全部相关测试。先运行项目 `.venv` 的离线门禁。
>
> 第一项先做只读诊断：用现有固定非法 Fixture 和 Fake/Stub 证明为什么唯一 repair
> 仍会遗漏 absent field 分类。保持一个 Parser、一个严格 DTO、一份领域规则和最多
> 一次 repair；不得放宽 `absent_field_not_classified`，不得添加样本标题白名单、
> 默认业务值、确定性代写候选、第二套 Schema/Parser/repair 服务或额外模型调用。
> 优先收敛共享 Prompt/repair guidance，使模型能从生成 Schema 与稳定 path/type
> 得知必须分类全部缺失字段；同时证明文字与图片共享同一契约、普通回复和 Tool
> Calling 不回归、json_object 不与 tools 混用、图片 repair 不重传图片/Base64。
>
> 默认只做离线修复和测试，不读取 `.env`、不调用真实模型、不测试网页、高德、
> Tool Calling 真实链、Dockerfile、锁注册表、aiosqlite 或 M1。完成后运行 Ruff、
> strict mypy、聚焦测试、非真实全集、默认全集和 socket/DNS 封网全集，更新
> M0_VALIDATION_REPORT.md 与 DEV_STATUS.md。若需再次真实复测，另行给出三类独立
> 请求上限、8 秒模型单次时限和 20 秒图片外层预算，等待新授权；不得结转本轮剩余
> 3 次额度。

## 17. 固定 repair 缺失字段分类语义离线收敛

### 17.1 门禁与根因

- 工作分支 `codex/m0-gate-fixed-repair-semantics` 精确从
  `ae659bc4c799a629228ef90d8488f144b2c27bea` 创建；开始工作区干净，`main` 与
  `origin/main` 均为 `0ace869ae2708608d238b77b3ade3153b1307549`，Alembic 唯一
  head 为 `20260722_0006`
- 第 16 节三个固定 Fixture 的本地非法 initial 均由唯一
  `parse_extraction_response()` 归类为 `$/json_invalid`。该 type 原先不在
  `_REPAIR_GUIDANCE_BY_TYPE`，因此走固定 unknown guidance，只要求“按 Schema 和
  outcome 规则重建对象”
- repair 实际仍收到初始 system、原始文字证据、安全长度的 prior assistant 输出及
  仅含 path/type 的 issue；`EXTRACTION_SEMANTIC_RULES` 也已覆盖候选字段。但当
  initial 完全非法时，通用重建指令没有要求模型在唯一 repair 内依次完成 outcome、
  Place/Event 判别和逐字段闭合审计
- 唯一领域 DTO 要求 Place 的 `city_hint`、`district`、`address`、
  `business_district`、`landmark`、`metro_station`、`price`、`tags`，以及 Event
  额外的 `event_start_at`、`event_end_at`，分别处于“有值 / missing / uncertain”
  三种合法状态之一。第 16 节第一、第三样本正是在这一严格边界留下
  `absent_field_not_classified`
- 第二次 repair 会突破“最多一次结构修复”；默认填 missing 会把未知事实分类成
  缺失并掩盖不确定性；放宽 DTO 会破坏 PRD 的“不确定即标记、不得编造”规则。因此
  修复只能收敛现有共享 repair 契约

### 17.2 最小生产修复与安全设计

生产提交为 `5bcdb9ca302f9298da7a425b7f5deb2805ae7b8b`
（`fix: strengthen extraction repair semantic checklist`）。

`extraction_output.py` 为 `json_invalid` 增加固定、供应商无关 guidance，要求唯一
repair 在输出前：

1. 重建单个完整 JSON 对象，选择合法 outcome，并区分每个 Place/Event；
2. 对 Place 的 8 类字段以及 Event 额外的 2 个时间字段执行闭合审计；
3. 对每个 absent field 准确选择 missing 或 uncertain，禁止重叠，禁止把 present
   field 标为 missing；
4. 保持价格 amount/currency 成对、Place 不带 Event 时间元数据、Event 缺失时间
   必须分类、candidates 不带 result-level error metadata；
5. 不得自报 `model_invalid_output`，不得发明源证据中不存在的事实。

字段列表从既有唯一 `CandidateField` 枚举生成；同一闭合文本同时进入初次
`EXTRACTION_SEMANTIC_RULES` 与 `json_invalid` repair guidance。它只指导模型，不
验证或改写候选；正式校验仍仅由既有 `ExtractionResult`、`PlaceCandidate`、
`EventCandidate` 执行。因此净变化不是第二套业务规则，也没有增加 Schema、Parser、
DTO、Provider、repair 服务、fallback 或模型调用。

guidance 固定且不包含样本输入、Pydantic input/value、异常文本、完整无效响应、
密钥、Header、Cookie、路径、文件名或 Base64；公开 issue 继续只有安全 path/type。
文字 repair 继续使用原始证据和安全 prior output，图片 repair 的既有“不重传图片”
边界未修改。

### 17.3 证据型离线覆盖

- 自定义 repair Stub 在返回结果前检查第二次请求的原始证据身份、`json_invalid`
  专用 guidance、Place 字段清单和 Event 时间字段；固定非法 Place/Event initial
  各只消耗 1 次 repair 等价 Provider 调用，并形成通过唯一 parser/DTO 的证据一致
  候选
- 专门验证 `json_invalid` 不再走 unknown guidance，且静态 guidance 不含私人哨兵、
  Pydantic value 或异常文本
- repair 若仍遗漏 absent field，继续稳定返回 `model_invalid_output`，不发生第三
  次调用
- 既有回归继续覆盖 missing/uncertain 重叠、present 标 missing、absent 未分类、
  价格成对、Place/Event 时间与 outcome 规则、初次成功零 repair、图片 candidates/
  insufficient、图片 repair 无 Base64/路径、普通 Provider 与 Tool Calling、
  json_object/tools 互斥、Schema/messages/response_format 深拷贝、ProviderError、
  取消、超长响应、非法 tool_calls、重复及并发隔离

### 17.4 离线验证结果

环境为项目既有 `.venv`：Python `3.13.5`、mypy `1.20.2`。所有最终规定命令退出
码均为 0：

| 验证 | 结果 |
|---|---|
| `python -m pip check` | 通过 |
| `python -m ruff check .` | 通过 |
| `python -m mypy app migrations nanobot_core` | 通过，93 个源文件 |
| `pytest -q tests/core` | `120 passed` |
| `pytest -q tests/unit/test_openai_compatible_provider.py` | `39 passed` |
| `pytest -q tests/unit/test_text_extraction_contracts.py` | `31 passed` |
| `pytest -q tests/unit/test_text_extraction_service.py` | `66 passed` |
| `pytest -q tests/unit/test_image_recognition_service.py` | `61 passed` |
| `pytest -q tests/test_config.py` | `125 passed` |
| 非真实全集 | `1464 passed, 1 skipped, 1 deselected` |
| 默认全集 | `1464 passed, 2 skipped` |
| 封锁 DNS、connect、connect_ex、create_connection 后非真实全集 | `1464 passed, 1 skipped, 1 deselected` |

第一次封网命令因仓库外临时插件把 `connect/connect_ex` 错写为 `socket` 模块属性，
在 setup 阶段退出 1，项目测试未执行；修正为 `socket.socket` 方法后完整重跑并得到
上表结果，临时目录随后删除。普通非真实全集与默认全集各出现一次第 9.2 节既有的
aiosqlite worker/事件循环收尾 warning，封网全集无 warning；本任务未修改数据库
生命周期、warning 策略、sleep 或 skip。

`git diff --check` 通过。没有新增迁移、依赖、配置、Provider、Parser、DTO、repair
服务、数据库、图片或响应快照；Alembic head 保持 `20260722_0006`。

### 17.5 Gate 状态与待授权真实复测

本任务未读取 `.env`，未运行真实 marker，未调用模型、高德、网页、对象存储、消息
或其他外部服务；真实请求数、Token 和费用均为 0。第 16 节文本 `2/2`、图片 `2/2`
的既有真实结论保持不变，不复测也不修改图片产品行为。

固定 repair P1 当前状态为：**离线修复完成，等待有限真实复测**。它不能在真实
复测前关闭。文本观测 P95 占 8 秒约 `83.7%`、图片 initial + repair 的 20 秒完整
链余量仍是独立超时校准风险，本修复不调整或提前关闭。

下一轮只复测第 16 节相同 3 个固定 repair Fixture：

- initial 均使用本地固定非法 JSON；
- 每个样本最多 1 次真实 repair，总上限 3 次模型请求；
- 唯一模式为 `json_object`，SDK `max_retries=0`，外层重试 0；
- 模型单次时限 8 秒，不结转上一轮剩余额度；
- 不复测已通过的文本或图片，不测试 Tool Calling、高德或网页，不扩大样本。

必须在新的真实复测窗口取得用户明确授权后才能读取调用所需配置并执行。本分支不
合并、不推送、不处理重定向网页、Dockerfile、锁注册表、aiosqlite 或 M1。
