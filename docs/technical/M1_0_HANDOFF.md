# M1-0 PostgreSQL 与任务基础交接

状态：待主控验收

分支：`codex/m1-0-postgresql-jobs`

基线：`6dbdbbaa49c8493b425870e2ea74682c6f2c0ca6`

Alembic 唯一 head：`20260726_0009`

## 实现边界

- `IdempotencyLockRegistry` 使用单一注册表互斥与参与者计数。同一用户/键的持有者和
  等待者共享一把锁，最后一个参与者在正常、异常或取消退出时同步淘汰；删除了永久
  字典路径，没有 TTL、LRU、后台清扫或第二套幂等服务。数据库唯一约束继续承担跨
  进程最终一致性。
- 正式数据库支持 `postgresql+asyncpg`，生产配置拒绝 SQLite；SQLite 继续用于适合的
  单元测试。所有表继续使用既有 SQLAlchemy `Base`、`Database`、Repository 与
  Alembic 迁移链。
- `JobQueue` 是唯一任务契约，`PostgresJobQueue` 是唯一正式实现。领取使用
  `FOR UPDATE SKIP LOCKED`，失败最多执行三次并持久化 5/30 秒重试时间，运行中任务
  使用 60 秒租约恢复。取消和终态任务不能再次领取。
- `python -m app.worker` 是唯一 Worker 入口。Worker 只调用 `JobQueue`；当前注册的
  `deterministic.noop` 只用于本地基础设施验收。`JobScheduler` 只通过
  APScheduler 定时调用 `JobQueue.create()`，不直接执行业务。
- `run_events` 通过外键附属于既有 `AgentRun`，没有第二套运行主记录。写入先锁定父
  AgentRun，再分配 trace 内递增 sequence。SSE 支持 `Last-Event-ID`，只补发更大
  sequence；终态事件发送后结束当前流。
- Job payload 是只在队列与 Worker 内部流转的有界 JSON，不复用公开 DTO，也不会
  被 SSE 或结果摘要自动透传。Job 结果和七类 RunEvent 摘要分别由显式冻结模型生成；
  未声明字段不能进入持久化公开摘要或 SSE。`apiKey`、`access_token`、
  `modelResponse` 等别名无需黑名单也没有公开字段，合法 `content_sha256` 只在明确
  允许的位置出现；SSE 不输出 Prompt、模型响应、Header、私有 key/路径或思维链。
- 根目录 `compose.yaml` 只包含 PostgreSQL、API、Worker，复用 Dockerfile 和
  `app.main:app`。API 在启动 Uvicorn 前执行 Alembic；Worker 等 API 健康后启动。

## 提交边界

1. `6bd3d71f2b763e8e4543291aa2517275f084b847` — 幂等锁有界生命周期。
2. `8ea7bc454546b35646c62f01ec359d5a16ae91d9` — PostgreSQL 驱动、配置和历史迁移兼容。
3. `d86c9f02c0b95048cf5be0af11f0d0c2b912f960` — JobQueue、Worker、APScheduler、0008。
4. `61db0b2ff4469d7e311a7fe4b6b117da1da81b9a` — RunEvent、SSE、0009、Compose。
5. `b8bbb8ff366614370e1a45b4eab4922c20617fc9` — 原候选文档交接。
6. `67716ea01f9350e3253bace5370e849e61d018b4` — 取消期间确定完成锁清理。
7. `85765af6dce984a60541f0b97cd239215a3175bf` — 统一 SQLAlchemy DML rowcount 类型边界。
8. `2b2f7a3036a411d5a0bd35546f137fd95c1c3a2a` — 删除公共数据启发式黑名单，改用显式摘要契约。
9. 最终文档提交与最终 HEAD 的完整 SHA 由最终交接输出记录。

## 自动化验证

- QA 在原候选 `b8bbb8ff...` 上实际复现 strict mypy 11 个错误；因此原候选“mypy
  已通过”的记录无效，不能作为验收证据。`85765af...` 之后以仓库指定 `.venv`
  重新执行，strict mypy 对 108 个源文件无问题。
- `pip check` 与 Ruff 通过；P1 指定聚焦集合 `37 passed`，既有 SQLite
  Run tracking 加聚焦集合 `61 passed`。
- 非真实 Provider 全集：
  `1546 passed, 8 skipped, 2 deselected`。
- 上述全集将 `PytestUnhandledThreadExceptionWarning` 提升为 error 后仍通过；本次未
  观察到 aiosqlite 收尾 warning，也没有过滤 warning 或使用 sleep 掩盖。
- Core `120 passed`；SQLite 迁移 `23 passed`；Alembic 唯一 head
  `20260726_0009`。
- 显式本地 PostgreSQL 16 加锁聚焦：`17 passed`。覆盖全新迁移/current/check/
  降级 base/重升、
  双 Worker 竞争、Job 幂等、三次重试、取消、租约恢复、UTC、并发事件 sequence、
  用户/trace 隔离、内部 payload 与公开摘要隔离、合法 SHA-256、敏感别名拒绝和
  SSE 重放。
- 幂等锁聚焦回归覆盖同键、不同键/用户、10,000 个高基数键、异常、持有者取消、
  等待者取消、退出清理阶段连续取消和淘汰竞态；清理任务被持有并观察至完成，原始
  `CancelledError` 传播，请求完成后 `active_key_count == 0`。

## Compose 实机结果

- PostgreSQL 16、API、Worker 均启动并通过健康检查；API 与 Worker 均为
  `uid=10001(appuser)`。
- `/healthz` 返回 200；容器内 `alembic current` 为
  `20260726_0009 (head)`。
- 扩容到两个 Worker 后，重复创建同一确定性任务返回同一 Job ID 和
  `replayed=true`；最终为 `succeeded`、`attempt=1`、安全结果摘要
  `{"outcome":"completed"}`。
- SSE 使用 `Last-Event-ID: 1` 只补发 sequence 2 和 3，顺序正确且无重复。
- 日志只出现迁移、健康检查和安全请求元数据，没有 Provider 调用。
- `docker compose down --volumes` 正常停止服务并清除本次本地测试卷。

## 代码唯一性检查

- 保留一套 `AgentRunner`、`ToolRegistry`、Provider、SQLAlchemy Base、Database、
  Repository 家族、JobQueue 契约、Worker 入口、幂等服务和 AgentRun 主记录。
- APScheduler、Worker 和 API 没有业务执行的平行入口；APScheduler 只创建持久化
  Job，Worker 只消费 JobQueue。
- `app.domain.public_data`、关键词黑名单和 Base64 猜测已删除。内部 Job payload、
  显式 Job 结果模型和七类 RunEvent 摘要职责分离；RunEvent 持久化与 SSE 共用同一
  类型化序列化边界。没有字段别名黑名单、测试白名单、固定容量缓存、后台清扫、
  重复安全代理或第二套通用校验器。
- SQLAlchemy UPDATE/DELETE 只通过一个 `execute_dml_rowcount()` 类型边界取得
  `CursorResult.rowcount`；执行仍使用原 `AsyncSession`，CAS、取消和租约恢复语义
  未改变；该类型边界没有 `Any` 返回、`type: ignore` 或逐调用代理。

## 已知风险和 QA 重点

- 任务采用租约式至少一次恢复。若业务处理已经产生外部副作用、但 Worker 在提交
  完成状态前崩溃，恢复后可能再次调用处理器；后续真实业务 handler 必须使用自己的
  业务幂等键。本阶段的确定性无副作用 handler 和双 Worker 行锁竞争均已验证。
- APScheduler 的调度注册本身保留在进程内存中；持久化的是它创建的 Job。未来正式
  周期计划必须在启动时从权威业务数据确定性重建注册，不得把 APScheduler 变成第二
  套队列。
- SSE 当前以 250 ms PostgreSQL 轮询实现跨进程可见性，没有引入 Redis、WebSocket
  或 LISTEN/NOTIFY；正确性已验证，吞吐和长连接容量尚未做压力测试。
- Job payload 是内部持久化 JSON，不等同于“允许持久化凭据”的授权；新增真实业务
  Job 时仍必须定义自己的最小 payload 类型，并禁止把凭据写入任务。当前 M1-0 只有
  无副作用确定性 Job。
- Compose 默认口令仅供本机开发；生产必须由运行环境注入。当前只验证 PostgreSQL
  16，不代表其他大版本已完成兼容验收。
- M1-1 身份/Web Session、M1-2 前端和后续业务 Job 均未实现。

## 主控与 QA 复现

从 `backend` 运行普通离线验收：

```bash
python -m pip install -e ".[dev]"
python -m pip check
python -m ruff check .
python -m mypy app migrations nanobot_core
APP_ENV=test RUN_REAL_MODEL_TESTS=0 RUN_REAL_MAP_TESTS=0 \
python -m pytest -q -W error::pytest.PytestUnhandledThreadExceptionWarning \
  -m "not real_provider and not real_map_provider"
python -m pytest -q tests/core
python -m pytest -q tests/integration/test_migrations.py
```

为一次性 PostgreSQL 测试显式提供本地管理库 URL：

```bash
TEST_POSTGRESQL_URL='postgresql+asyncpg://USER:PASSWORD@127.0.0.1:5432/ADMIN_DB' \
python -m pytest -q -m postgresql
```

从仓库根目录复现 Compose：

```bash
docker compose config --quiet
docker compose up --build -d
docker compose up -d --scale worker=2
docker compose ps
curl --fail http://127.0.0.1:8000/healthz
docker compose exec -T api python -m alembic current --check-heads
docker compose down --volumes
```

该验收不授权真实模型、地图、网页、消息、云部署或其他付费调用。
