# 拾光 Shiguang

拾光是一款“把收藏变成行动”的个人生活 Agent：用户保存想去、想做或想吃的地点与活动，之后由 Agent 结合时间、范围、天气、路线和费用生成可执行的深圳同城计划。

## 当前阶段

项目当前处于 **M0 技术验证**。本分支完成的是 **M0-0A 项目基线与资料迁移**，仅建立正式仓库的规划、产品、技术和 UX 原型基线。

当前尚未安装后端依赖，未创建后端、前端或数据库工程，也未接入模型、高德或其他外部服务。下一阶段是 **M0-0B 后端工程骨架**，必须在 M0-0A 经主控任务验收后再开始。

## 仓库目录

```text
Shiguang_Nanobot/
├── AGENTS.md                    # 仓库级开发与协作规则
├── README.md                    # 项目入口与当前阶段说明
├── NOTICE.md                    # 第三方来源与许可证说明
├── docs/
│   ├── DEVELOPMENT_STAGES.md   # 完整开发阶段、分支与验收标准
│   ├── DEV_STATUS.md           # 当前阶段、状态和交接记录
│   ├── product/                # 正式产品需求、流程与竞品文档
│   └── technical/              # 正式技术方案
└── prototypes/
    └── ux/                     # 静态 HTML UX/UI 评审原型
```

目录会随阶段逐步创建，不预先生成 `backend`、`frontend`、`infra` 等空工程。

## 开始开发前

后续开发任务必须依次完整阅读：

1. `AGENTS.md`
2. `docs/DEVELOPMENT_STAGES.md`
3. `docs/DEV_STATUS.md`
4. `docs/product/` 与 `docs/technical/` 中和当前阶段相关的文档

每个任务只处理 `docs/DEV_STATUS.md` 指定的一个阶段或子阶段，并遵守 `docs/DEVELOPMENT_STAGES.md` 中的分支与验收标准。

## 查看 UX 原型

原型是评审用静态页面，不是正式前端，也不连接真实 API 或用户数据。

可以直接打开 `prototypes/ux/index.html`。若浏览器限制本地脚本，在仓库根目录运行：

```bash
cd prototypes/ux
python3 -m http.server 4173 --bind 127.0.0.1
```

然后访问 <http://127.0.0.1:4173/>。

## 只读参考来源

旧的“Nanobot 学习”目录仅是 M0-0A 迁移前的只读资料来源和后续 Nanobot 核心迁移参考，不是本项目的运行依赖，也不进行双向同步。M0-0A 之后，产品、技术和原型资料以本仓库内版本为正式维护来源。
