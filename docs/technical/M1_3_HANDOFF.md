# M1-3 Agent 与内容导入页面交接

## 范围与结论

M1-3 在基线 `d1832e9ae8355fe1e58faae0e101b9f8e0a4d2c8` 上完成。实现复用
M1-0 的唯一 JobQueue/Worker/RunEvent、M0 的唯一 TextCollectionWorkflow 和
CollectionWriteService，以及 M1-2 的唯一 API/SSE Client、Token 与 App Shell。
没有实现 M1-4 收藏库、候选选择或完整详情，也没有实现计划、真实登录或外部发布。

## 接口变化

- `POST /api/v1/sessions/{session_id}/messages`：改为 `202 Accepted`，返回
  `message_id`、`trace_id`、`run_status`、`events_url`、`result_url` 和
  `replayed`。文字/URL 使用 JSON，截图使用原始 JPEG/PNG/WebP 与
  `Idempotency-Key`。
- `GET /api/v1/agent-runs/{trace_id}/events`：沿用既有单调 sequence、SSE replay
  与 `Last-Event-ID`。
- `GET /api/v1/agent-runs/{trace_id}/result`：读取持久化权威终态、收藏、来源、
  恢复动作及安全工具步骤；不从 SSE 摘要推断结果。
- `GET /api/v1/sessions/{session_id}/messages`：恢复当前对话和未完成运行。
- `POST /api/v1/collections/{item_id}/restore`：在既有写服务内幂等恢复删除前状态。

正式内容导入 Job 类型为 `content.import`。Job payload 只含 session/message/source
标识与输入类型；用户正文、URL、文件 key、图片字节和 Base64 均留在既有持久化或
私有存储边界。Worker 只恢复输入并调用 TextCollectionWorkflow。

## 前端状态机

```text
idle
  -> submitting
  -> queued / processing
  -> saved | pending_selection | pending_details | failed
  -> undone
```

提交后立即进入 queued/processing。SSE 阶段仅映射为“内容接收、地点识别、结果
整理”，不显示百分比；有限重连后仍读取权威结果。收藏卡展示确认字段、缺失项和
不确定项。修改、撤销、恢复和继续添加均调用正式接口。工具过程默认折叠，只显示
工具名、阶段、状态、来源、耗时与安全错误码。

## 数据迁移

新增 `20260727_0011_collection_restore_status.py`，为 `collection_items` 增加
`deleted_from_status`。现有 `status=deleted` 无法表达删除前是 active、
pending_selection 还是 pending_details，因此无法保证真实无损恢复；这就是新增
字段的必要性。迁移可升降级，Alembic 只有 `20260727_0011` 一个 head。

## 测试结果

- 后端：`pip check`、Ruff、严格 mypy 通过；core `120 passed`；迁移
  `23 passed`；完整离线回归 `1563 passed, 10 skipped, 2 deselected`。
- 前端：生产依赖 audit 为 0；lint、typecheck、build 通过；Vitest
  `29 passed`。
- 浏览器：Playwright `14 passed`，覆盖 320/390/768/1024/1440px、44px 目标、
  键盘焦点、reduced motion，以及真实 FastAPI + 离线 Fake Provider 的
  “首次进入 → 提交 → 识别 → 权威结果 → 修改 → 撤销/恢复 → 继续添加”。
- M1-3 聚焦后端契约 `4 passed`，覆盖 202/SSE/权威结果、幂等复用、图片安全引用、
  删除恢复及 Session/CSRF 边界。

所有测试默认离线，未读取 `.env`，未调用真实模型、地图、网页或付费 API。

## 安全、清理与冗余

- CSRF 仅保存在 React 运行内存；Cookie 由浏览器管理。
- 图片先完整校验并进入既有私有存储；上传中断不会创建 Job/Source/文件，存储写入
  失败会清空临时文件和预留记录并终结 queued run。
- 已登记原图沿用既有 30 天保留策略；识别失败不立即删除该原图，这是可恢复性与
  生命周期策略的当前取舍。
- 工具 DTO 不含 Prompt、思维链、模型原文、敏感参数或供应商响应。
- 页面不使用 `dangerouslySetInnerHTML`；用户输入、文件名与后端内容按文本渲染。
- 没有新增第二套 API Client、SSE Client、JobQueue、Worker、AgentRunner、
  ToolRegistry、Parser、收藏工作流或 Undo/Restore 系统。

## 已知风险与主控复测

- 当前浏览器联调使用 SQLite 与离线 Fake Provider；请主控补测 PostgreSQL 的
  API/Worker 分进程并发与 SSE replay。
- 请重点复测刷新恢复、断线重放、同键并发、上传中断、终态前不显示成功、恶意
  HTML 文本化、跨 Cookie 所有权、删除前各状态的精确恢复。
- 尚未覆盖 Node 20/22、Windows/Linux、Safari/Firefox；不阻塞当前 macOS/
  Chromium 阶段验收。
