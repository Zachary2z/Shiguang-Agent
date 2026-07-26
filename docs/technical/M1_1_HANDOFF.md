# M1-1 Web 会话与 Demo 身份交接

## 交付状态

- 状态：待主控验收
- 分支：`codex/m1-1-web-session`
- 指定基线：`272c710259862566586b968f87a64fa1e73e42a8`
- 实现提交：
  - `97c89d0ea1d84ffcd89de1190455f5a926392ad2`（持久 Web Session 身份）
  - `2ad2c501f0e288bb59c64954e52b226c2a1b312b`（浏览器 Demo 沙盒隔离）
  - `bdad9e29a628c2b8e39dd06ed84df71802ea6767`（安全与隔离测试）
- 文档提交及最终 HEAD：以最终交接输出和 `git rev-parse HEAD` 的完整 SHA 为准
- Alembic 唯一 head：`20260727_0010`
- 当前允许阶段仍为 M1-1；主控验收前不得进入 M1-2

## 唯一身份与数据模型

`BrowserSession` 是唯一浏览器会话领域契约，现有 `Session` 继续只表示
Agent/消息会话。`WebSessionService` 和 `SqlAlchemyWebSessionRepository` 分别是
唯一应用服务和持久化实现；API 只通过 `get_request_identity` 解析
`CurrentPrincipal`、选择数据库并执行 CSRF 校验。业务路由继续复用原有 API、
Repository、AgentRun、消息、收藏、Undo、SSE 和 Job 实现，没有第二套认证中间件、
User、消息 Session、Database 类型或业务路由。

迁移 `20260727_0010_web_sessions.py` 只新增 `web_sessions`：稳定 ID、User 外键、唯一
Token 哈希、CSRF 哈希、创建/绝对过期/撤销时间，以及格式、时间顺序和查询索引。
历史 `0001`–`0009` 未修改。明文 Session Token 和 CSRF 只在签发调用栈中短暂存在，
数据库只保存 SHA-256；领域对象 repr、错误、日志、OpenAPI 和公开 DTO 均不暴露
Token、Cookie、哈希或 `user_id`。

## Cookie、CSRF、过期与撤销

- Token 和 CSRF 均由服务端 `secrets.token_urlsafe(32)` 生成，严格为 43 字符
  URL-safe 高熵值；不接受客户端 `user_id` 或 Token 作为启动参数。
- Cookie 名为 `shiguang_session`，属性固定为 `HttpOnly`、`SameSite=Lax`、
  `Path=/`，不设置 `Domain`。production 必须 `Secure`；开发/测试开关集中在
  `Settings`，production 显式关闭会启动失败。
- 所有已认证非安全方法统一要求 `X-CSRF-Token`。缺失/错误 CSRF 稳定返回 403；
  无 Cookie、格式错误、伪造、过期或撤销凭据稳定返回 401。
- Demo 启动响应只返回当次 CSRF 值。有效 Cookie 恢复同一 User 和消息 Session，
  同时原子轮换 Session Token 与 CSRF，旧 Token 立即失效，避免 Session Fixation。
- 过期使用半开区间 `[created_at, expires_at)`；到达等号即失效。请求不滑动续期。
  Demo 默认 2 小时且配置上限 24 小时；真实会话保留默认/上限 30 天能力，但本阶段
  没有真实登录入口。
- `DELETE /api/v1/web-session` 在统一 CSRF 边界内撤销当前设备，并清除当前 Cookie；
  撤销幂等并发不会恢复凭据。

## Demo 沙盒和物理隔离

首次 Demo 访问在 Demo 数据库内创建独立 Demo User、消息 Session 和 Web Session。
固定 `DEMO_USER_ID` 运行时身份已删除。两个 Cookie Jar 得到不同 User/Session，所有
Message、Collection、Source、AgentRun、RunEvent、Job 和 Undo 查询/写入仍经过既有
`user_id` 所有权过滤；跨用户资源与不存在资源保持相同 404，不泄露归属。

正式与 Demo 数据通过两个独立 `Database` 实例和两个独立
`StorageProviderSettings` 路由。production 启用 Demo 时必须显式配置不同的
PostgreSQL `DATABASE_URL` 与 `DEMO_DATABASE_URL`；普通测试使用两个独立临时
SQLite 数据库。Compose 提供 `postgres` 和 `demo-postgres`，API 启动前分别迁移到
head；Demo 请求验证只在 Demo 库产生 User/Web Session，真实库保持空。Demo 没有
外部写操作，也没有引入任何真实 Provider 配置。

## ChannelIdentity 延后

本阶段只定义供应商无关的最小 `ChannelIdentity(channel, subject)` 和
`ChannelIdentityRepository.resolve_user_id()` 协议。没有持久化消费者，因此没有
创建无用途表。微信 OpenID 等供应商字段、登录链接、绑定码、兑换、OAuth 和真实
绑定流程全部延后到 M2-2，由届时确认的渠道事实和消费者驱动持久化设计。

## 自动化与验收结果

- editable 安装和 `pip check`：通过。
- Ruff：通过。
- strict mypy：115 个源文件通过。
- 非真实全集（严格线程告警并使用仓库外 DNS/TCP 封锁插件）：
  `1555 passed, 11 skipped`。
- 身份与迁移封网聚焦：`30 passed`。
- Core：`120 passed`。
- SQLite 迁移：`23 passed`；upgrade、current、check、downgrade 和 re-upgrade
  覆盖通过。
- PostgreSQL 16：`9 passed`，覆盖全新迁移往返、Web Session 并发创建/撤销、
  浏览器与双库隔离、JobQueue、RunEvent 和 SSE replay。
- Compose：正式库、Demo 库、API、Worker 全部 healthy；API/Worker 均为 uid
  `10001`；两库均为 `20260727_0010`。一次 Demo 启动后真实库 User/Web Session
  均为 0，Demo 库各为 1；日志只有安全请求元数据。
- 所有一次性 PostgreSQL 容器、Compose 服务、网络、镜像和测试卷均已清理。

覆盖还包括 Token/CSRF 随机性、格式、哈希和输入不变性，Cookie 属性与 production
门禁，创建/恢复/轮换/伪造/等号过期/撤销，缺失及错误 CSRF，两个 Cookie Jar
隔离，Demo/真实数据库隔离，跨用户 Message、Collection、Source、AgentRun、
RunEvent、Job 和 Undo，重复调用、并发行为，以及日志、异常、repr、OpenAPI 和公开
响应脱敏。现有 M0/M1-0 API、SSE、Job、Core 和迁移回归保持通过。

## 安全、复杂度和剩余风险

安全结论：浏览器身份只来自服务端验证的随机凭据；客户端提供的路径、正文、Header
或 Cookie 中没有可信 `user_id` 通道。过期/撤销在业务数据库 Session 交给路由前
完成验证，写请求在同一依赖边界执行 CSRF。请求日志不记录 query、Cookie、Header
或正文。本轮未读取或提交 `.env`，真实模型、高德、网页、对象存储、消息、微信及
付费 API 调用总数为 0。

复杂度结论：新增的是一个领域契约、一个应用服务、一个 Repository 实现和一张必要
表；既有 AgentRunner、ToolRegistry、Provider、User、消息 Session、Database 类型、
Repository 家族、AgentRun、RunEvent、JobQueue 和业务 API 均继续唯一。身份规则未
复制到各路由，没有固定 Token、用户白名单、测试旁路或框架内部代理。

剩余非阻断风险：

- 本轮只在 macOS/Python 3.13 和 PostgreSQL 16 验证，未在 Windows 或其他
  PostgreSQL 大版本复测。
- 同一浏览器极端并发调用 Demo 启动时可能产生多个轮换响应，其中仅数据库最后保存
  的凭据有效；不会造成跨用户或跨库访问，但前端在 M1-2 应将启动调用串行化。
- Session 清理/归档任务尚未实现；绝对过期记录会保留在数据库中，后续应以独立、
  可审计的维护任务清理，不得改成请求滑动续期。
- ChannelIdentity 持久化需等 M2-2 的正式渠道消费者和字段事实确认。

## 主控复测重点

从指定基线核对线性提交和唯一迁移 head；独立复测旧 Token 在启动恢复轮换后立即
401、等号过期、并发撤销、两个 Cookie Jar 全资源隔离、Demo/真实双库写入计数、
production Secure/显式 Demo 数据库门禁、SSE/Job 所有权，以及 OpenAPI/日志/异常
脱敏。验收通过前不合并、不推送，也不开始 M1-2。
