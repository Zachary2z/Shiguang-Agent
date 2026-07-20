# 拾光开发状态

| 项目 | 当前值 |
|---|---|
| 当前总阶段 | M0 技术验证 |
| 当前子阶段 | M0-0B 后端工程骨架 |
| 状态 | 未开始 |
| 当前分支 | main |
| 最近更新 | 2026-07-21 |
| 阻塞项 | 无 |

## 当前任务

M0-0A 已通过主控验收并快进集成到 `main`。下一个允许开始的阶段是 M0-0B；当前尚未创建 M0-0B 分支或实现后端代码。

## M0 状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| M0-0A 项目基线与资料迁移 | 已完成 | 主控验收通过，阶段提交 `79848c7` 已集成到 `main` |
| M0-0B 后端工程骨架 | 未开始 | 前置条件已满足，下一个允许开始的阶段 |
| M0-0C Nanobot 核心迁移 | 未开始 | 依赖 M0-0B |
| M0-1 模型与运行记录 | 未开始 | 依赖 M0-0C |
| M0-2 文字收藏 | 未开始 | 依赖 M0-1 |
| M0-3 地点匹配 | 未开始 | 依赖 M0-2 |
| M0-4 URL 与截图 | 未开始 | 依赖 M0-3 |
| M0-5 计划技术验证 | 未开始 | 依赖 M0-2、M0-3 |
| M0-Gate 阶段验收 | 未开始 | 依赖全部 M0 阶段 |

状态只允许使用：未开始、进行中、待验收、已完成、阻塞。

## 已完成

- 产品 PRD、核心用户流程、竞品分析和 MVP 技术方案已在学习目录完成。
- HTML UX/UI 评审原型已完成，可作为正式前端的设计基线。
- 已创建独立 Git 仓库 Shiguang_Nanobot。
- 已建立完整开发阶段文档和仓库级开发规则。
- M0-0A 已完成：正式产品文档、技术方案与 UX 原型已迁入本仓库，README、Git 忽略规则和 Nanobot 许可证归属说明已建立。

## 下一步

新的阶段开发任务应执行：

1. 从包含 M0-0A 和本状态更新的最新 `main` 创建 `codex/m0-0b-backend-scaffold`。
2. 依次阅读 `AGENTS.md`、`docs/DEVELOPMENT_STAGES.md`、本文件及相关正式技术文档。
3. 只实施 M0-0B：FastAPI、Settings、SQLite、SQLAlchemy、Alembic、基础日志、request ID 与测试基线。
4. 不迁移 Nanobot 核心，不接模型或高德，不创建前端，不提前进入 M0-0C。
5. 完成后运行 M0-0B 规定的 lint、类型检查、测试、迁移和启动验收，将本文件更新为“待验收”并交回主控任务。

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
