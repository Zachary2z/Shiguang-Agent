# M1-1 Web 会话与 Demo 身份交接

## 交付状态

- 状态：已通过主控验收
- 分支：`codex/m1-1-web-session`
- 指定基线：`272c710259862566586b968f87a64fa1e73e42a8`
- 实现提交：
  - `97c89d0ea1d84ffcd89de1190455f5a926392ad2`（持久 Web Session 身份）
  - `2ad2c501f0e288bb59c64954e52b226c2a1b312b`（浏览器 Demo 沙盒隔离）
  - `bdad9e29a628c2b8e39dd06ed84df71802ea6767`（安全与隔离测试）
  - `4aca9bf7990af21ba3e7787aa2ddda857daba870`（并发安全恢复与 Cookie 剩余寿命修复）
- 文档提交及最终 HEAD：以最终交接输出和 `git rev-parse HEAD` 的完整 SHA 为准
- Alembic 唯一 head：`20260727_0010`
- M1-1 已完成；当前唯一允许阶段为 M1-2

## 唯一身份与数据模型

`BrowserSession` 是唯一浏览器会话领域契约，现有 `Session` 继续只表示
Agent/消息会话。`WebSessionService` 和 `SqlAlchemyWebSessionRepository` 分别是
唯一应用服务和持久化实现；API 只通过 `get_request_identity` 解析
`CurrentPrincipal`、选择数据库并执行 CSRF 校验。业务路由继续复用原有 API、
Repository、AgentRun、消息、收藏、Undo、SSE 和 Job 实现，没有第二套认证中间件、
User、消息 Session、Database 类型或业务路由。

迁移 `20260727_0010_web_sessions.py` 只新增 `web_sessions`：稳定 ID、User 外键、唯一
Token 哈希、CSRF 哈希、创建/绝对过期/撤销时间，以及格式、时间顺序和查询索引。
历史 `0001`–`0009` 未修改；本次并发修复无需表结构变化，没有制造空迁移。明文
Session Token 和 CSRF 只在请求处理调用栈中短暂存在，数据库只保存 SHA-256；
领域对象 repr、错误、日志、OpenAPI 和公开 DTO 均不暴露 Token、Cookie、哈希或
`user_id`。

## Cookie、CSRF、过期与撤销

- Session Token 由服务端 `secrets.token_urlsafe(32)` 生成，严格为 43 字符
  URL-safe 256-bit 高熵值。CSRF 使用 Session Token 作为密钥，通过版本化领域上下文
  `shiguang:web-session:csrf:v1` 的 HMAC-SHA-256 确定性派生；数据库仍只保存
  Token 与 CSRF 的 SHA-256，不接受客户端 `user_id` 或 Token 作为启动参数。
- Cookie 名为 `shiguang_session`，属性固定为 `HttpOnly`、`SameSite=Lax`、
  `Path=/`，不设置 `Domain`。production 必须 `Secure`；开发/测试开关集中在
  `Settings`，production 显式关闭会启动失败。
- 所有已认证非安全方法统一要求 `X-CSRF-Token`。缺失/错误 CSRF 稳定返回 403；
  无 Cookie、格式错误、伪造、过期或撤销凭据稳定返回 401。
- Demo 启动响应只返回可由合法 Cookie 重建的 CSRF。普通恢复保持 Session Token
  稳定且不写库，返回同一 User、消息 Session 和同一组可用凭据；跨进程并发恢复
  不会互相覆盖。Token 只在创建新 Session 或未来明确的安全事件中更换。无效、
  伪造、过期或撤销 Cookie 一律创建全新随机 Demo 沙盒，不采用攻击者提供的值。
- 过期使用半开区间 `[created_at, expires_at)`；到达等号即失效。请求不滑动续期。
  新建 Cookie 使用完整配置 TTL；恢复 Cookie 的 `Max-Age` 为数据库绝对过期时间的
  剩余整秒且同时设置准确 `Expires`，不会恢复完整 TTL。Demo 默认 2 小时且配置
  上限 24 小时；真实会话保留默认/上限 30 天能力，但本阶段没有真实登录入口。
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
- 非真实全集（严格线程告警）：`1559 passed, 10 skipped, 2 deselected`；使用仓库外
  插件同时封锁 `getaddrinfo`、`connect`、`connect_ex` 和 `create_connection`
  后结果相同。
- 身份与迁移封网聚焦：`34 passed`；包含 SQLite 上事件门控的 8 路同 Cookie 并发
  恢复、每个返回 Cookie 的后续读取、每个响应 CSRF 的统一写边界验证、恢复/撤销
  竞态，以及 User/消息 Session/BrowserSession 均不增生。
- PostgreSQL 16：`10 passed, 1561 deselected`，覆盖全新迁移往返、8 路 API 并发
  恢复与 CSRF 写验证、Web Session 并发创建/撤销、浏览器与双库隔离、JobQueue、
  RunEvent 和 SSE replay。
- Compose：正式库、Demo 库、API、Worker 全部 healthy；API/Worker 均为 uid
  `10001`；两库均为 `20260727_0010`。一次 Demo 启动后真实库 User/Web Session
  均为 0，Demo 库各为 1；日志只有安全请求元数据。
- 所有一次性 PostgreSQL 容器、Compose 服务、网络、镜像和测试卷均已清理。

覆盖还包括 Token 随机性、CSRF 确定性领域分离、格式、哈希和输入不变性，Cookie
属性与 production 门禁，创建/稳定恢复/伪造/等号过期/撤销，缺失及错误 CSRF，
临近过期 `Max-Age`/`Expires`，两个 Cookie Jar
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
- Session 清理/归档任务尚未实现；绝对过期记录会保留在数据库中，后续应以独立、
  可审计的维护任务清理，不得改成请求滑动续期。
- ChannelIdentity 持久化需等 M2-2 的正式渠道消费者和字段事实确认。

## 主控验收结论

主控从指定基线核对了线性提交与唯一迁移 head，并独立复测同一有效 Cookie 的多路
并发恢复、恢复 Cookie 剩余寿命、等号过期、恢复/撤销竞态、两个 Cookie Jar 全资源
隔离、Demo/真实双库写入计数、production Secure/显式 Demo 数据库门禁、SSE/Job
所有权及 OpenAPI/日志/异常脱敏。

验收结果：`pip check`、Ruff、strict mypy、身份/迁移聚焦、普通与封网非真实全集、
Core、PostgreSQL 16 标记组和独立 Compose 双库均通过。仓库外压力探针连续
5 轮、每轮 16 个并发恢复客户端，所有成功响应凭据均可继续读取并通过 CSRF 边界；
容器内 8 路并发结果一致。当前无未关闭 P0/P1，M1-1 允许完成；当前唯一允许阶段为
M1-2。本次验收未读取 `.env`，真实或付费 API 调用为 0。
