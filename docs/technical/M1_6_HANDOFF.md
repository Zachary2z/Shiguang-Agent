# M1-6 执行入口与手动反馈交接

状态：**已实现，待主控验收**

## 基线与提交

- 指定基线：`7d66aa8310436fd9ef37561f533e455e0c664c61`。
- 开发分支：`codex/m1-6-execution-feedback`。
- 完整开发提交：`c10b68a123eafb1c0c114857d95aabec77c393ea`。
- 初始交接提交：`d57996defa4f2c343ddcb21d799a09c6060afc7b`；本文件所在的
  后续提交为主控 QA 联合修复提交，完整 SHA 由交接方从分支 HEAD 返回。
- 开始门禁确认 `main` 与 `origin/main` 精确等于指定基线，工作区干净，
  Alembic 唯一 head 为 `20260728_0014`，M1-5 已完成且 M1-6 是唯一允许阶段。
- 未合并 `main`，未推送 GitHub，未开始 M1-7。

## 产品行为

- 继续复用唯一 `require_confirmed_for_execution`。只有 `confirmed` 以及由其产生的
  `completed / partially_completed / not_completed` 终态可读取日历、导航和当前
  反馈；草案及其他状态统一拒绝。
- `GET /api/v1/plans/{plan_id}/calendar.ics` 为完整主计划生成可下载 RFC 5545
  日历。使用 `Asia/Shanghai`、稳定 Plan UID、CRLF、UTF-8 75 字节折行以及反斜杠、
  换行、逗号、分号转义；地址只来自冻结的准确 POI。
- `GET /api/v1/plans/{plan_id}/execution` 是现有计划 DTO 旁的最小只读执行视图，
  不建立第二套计划。每个主方案 PlanItem 通过既有
  `MapProvider.build_navigation_uri` 生成准确 POI/坐标入口；该方法本身不发 HTTP，
  未知 POI 返回无导航入口而不伪造地点。
- `POST /api/v1/plans/{plan_id}/feedback` 支持已完成、部分完成和未完成。已完成按
  全部主方案项计算；部分完成必须选择至少一项但不能选择全部；未完成禁止携带到访
  项，原因可留空。
- 只有选择到访、且来源已绑定当前用户收藏的 PlanItem 才写 visited。外部未收藏
  地点只更新 PlanItem 状态，不创建 Collection。未完成不产生收藏到访来源。
- 反馈允许更正。每次更正创建不可变审计 revision，当前状态单独保存；更正会重算
  Plan、PlanItem 和受影响 Collection。收藏的初始 visited 状态以及其他仍有效计划
  的到访来源都会保留，因此不会被一次更正错误撤销。
- 同一用户幂等键和请求指纹承担重放边界；串行/并发相同请求只保留一条审计，
  同键不同载荷冲突。计划当前状态行、revision 唯一约束、行锁与单事务提交共同承担
  并发冲突和原子回滚。PostgreSQL 中等待 Plan 行锁的请求会在取得串行化边界后、
  比较 expected revision 前重新读取幂等审计，因此同 key 同载荷并发得到两个
  `200`，其中一个 `replayed=false`、另一个 `replayed=true`；不同 key 仍由乐观
  revision 拒绝第二个写入。
- 完成情况可生成 `pending` 的长期偏好建议，只展示给用户确认；本阶段没有 Memory
  写入、模型调用、关键词规则或 M1-7 管理入口。

## 数据与正式入口

新增线性迁移 `20260728_0015_execution_feedback.py`，直接继承
`20260728_0014`，Alembic 唯一 head 为 `20260728_0015`。迁移：

- 扩展 Plan 终态并保持 draft/confirmed_at 形状约束；
- 为 PlanItem 增加 `pending / visited / not_visited` 执行状态；
- 新增当前反馈、不可变反馈审计、收藏到访基线和收藏到访来源四张表；
- 用复合外键绑定 Plan、PlanItem、Collection、Feedback 的用户所有权；当前反馈
  指针和更正指针都只能引用同一 `plan_id + user_id` 的审计；
- 将每个 root 的唯一可执行版本索引覆盖确认及三个完成终态；
- 有反馈审计数据时拒绝破坏性降级。

四类能力各只有一个正式应用服务入口：

- `PlanCalendarService`
- `PlanNavigationService`
- `PlanFeedbackService`
- `PreferenceSuggestionService`

没有新增 Plan Repository、Provider、Job、Worker、AgentRun、状态机、API Client 或
前端全局状态；保留 M1-5 高基数候选截断 P2，未增加第二套预排序。

## Web/H5 M06

`/plans` 继续复用 App Shell、`apiClient` 和组件内现有 operation generation：

- 确认后才展示行动入口；
- 下载完整日历并显示 `Asia/Shanghai`；
- 为准确地点显示导航，为未知地点明确显示不可用；
- 手动选择已完成、部分完成、未完成；
- 部分完成逐项选择实际到访 PlanItem，并区分收藏与外部未收藏地点；
- 刷新后读取权威反馈、选择和 revision；
- 可更正反馈，并明确偏好建议尚未写入长期记忆。
- execution 加载和反馈提交冻结 plan id 与 operation generation，并复用既有
  AbortController；切换版本、新建计划或卸载后，旧响应及其 `finally` 均不能覆盖
  新版本状态。网络结果不确定时，同一载荷继续复用原幂等键，成功或载荷改变后才
  生成新键。

真实离线 Playwright 流程未 mock 计划、执行、反馈、Job、SSE 或结果接口，穿过本地
Next.js、FastAPI、临时 SQLite、既有 JobQueue/Worker、计划服务和 StubMapProvider：

1. 生成 V1，异步调整为 V2 并明确确认；
2. 下载 `.ics`；
3. 点击由准确坐标生成的 `geo:` 导航入口；
4. 选择部分完成和一个实际到访项；
5. 刷新后恢复第 1 次反馈与选择；
6. 更正为未完成并恢复第 2 次审计状态。

## 测试结果

后端：

- `../.venv/bin/python -m pip check`：通过。
- `../.venv/bin/python -m ruff check .`：通过。
- `../.venv/bin/python -m mypy app migrations nanobot_core`：
  `129 source files`，0 错误。
- M1-6 聚焦：`7 passed`。
- 非真实全集：`1617 passed, 14 skipped, 2 deselected`；新增的 3 项 PostgreSQL
  专测在未提供 PostgreSQL URL 的普通全集中按既有 fixture 跳过。
- SQLite 迁移专测：`24 passed`。
- 一次性本地 PostgreSQL 16：反馈并发/约束 3 项与迁移往返 1 项合计
  `4 passed`。同 key 并发实测两个响应均成功，审计、revision、收藏来源和
  PlanItem 更新各一次，replayed 标志一真一假；同 key 不同载荷冲突，不同 key
  同 revision 只有一个成功；事务失败后原 key 可安全重试。
- `alembic heads`：`20260728_0015 (head)`。
- 仓库外 pytest 插件同时封锁 DNS、`create_connection`、`connect`、
  `connect_ex` 后，M1-6 聚焦再次 `7 passed`，非真实全集再次
  `1617 passed, 14 skipped, 2 deselected`。

前端：

- `npm run lint`：通过。
- `npm run typecheck`：通过。
- Vitest：`65 passed`，包含 3 类迟到 execution/feedback 隔离及不确定网络重试
  稳定幂等键。
- `npm run build`：通过。
- Playwright：`26 passed`，包含上述真实离线 M06 闭环。

覆盖包括：未确认拒绝、成熟独立 `icalendar` 解析器、时区/时间/地址/稳定 UID/
中文/特殊字符/折行、准确导航、外部地点、三种完成状态、空选择、跨计划 PlanItem、用户隔离、
串行/并发重放、同键冲突、反馈更正、事务回滚、其他有效到访来源保留以及偏好建议
不写长期记忆。

## 安全、复杂度与剩余风险

- 未读取或打印 `.env`；真实模型、地图、网页及其他外部/付费 API 调用为 0。
- 日历和导航输出不包含密钥、Cookie、本机私人路径或用户凭据。日历下载使用
  `private, no-store` 和 `nosniff`；日历不再生成没有可信公开 Base URL 的虚假
  URL；导航 URI 仍由既有安全契约验证。
- 没有自动收藏外部地点、自动写长期记忆、主动询问、提醒、微信消息、分享链接、
  数据导出、云部署或 M1-7 功能。
- 新增复杂度对应四个产品行为边界；反馈来源表用于解决“更正不能撤销其他有效
  visited 依据”，不是重复状态机。测试故障注入证明中途异常不会留下审计、收藏或
  PlanItem 部分写入。
- 当前没有已知未关闭 P0/P1。此前发现的 PostgreSQL 同 key 并发版本冲突、反馈
  指针所有权缺口和前端迟到响应三个 P1 已关闭；日历虚假 URL/自制测试解析器 P2
  已关闭。
- 保留的非阻塞风险：M1-5 高基数候选截断 P2 不变；日历已通过成熟独立解析器，
  但尚未在各手机厂商日历客户端逐一导入；高德 URI 尚未做真实
  设备拉起验证。以上不授权真实网络或设备调用。

## 主控验收建议

从完整开发提交独立运行本节命令，重点复核：

1. `20260728_0015` 的 PostgreSQL/SQLite 线性迁移和所有权复合外键；
2. 同键并发、不同载荷冲突、更正 revision 与事务回滚；
3. 多条有效到访来源下的 Collection visited 重算；
4. `.ics` 在目标日历客户端的导入及高德 URI 的真实设备拉起（如需真实验证，
   必须另行取得用户授权）；
5. M06 刷新恢复和更正交互。

验收通过前保持 M1-6“待主控验收”，不合并、不推送、不开始 M1-7。
