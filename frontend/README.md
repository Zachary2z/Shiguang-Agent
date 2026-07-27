# 拾光正式前端

M1-2 使用 Next.js App Router、TypeScript strict 和单一响应式代码库，为 Web/H5
提供正式前端基础。当前只有 `/agent`、`/collections`、`/plans`、`/me` 四个空业务
路由，不包含内容导入、收藏、计划或“我的”业务。M1-2 已完成开发并等待主控验收；
M1-3 及后续阶段未开始。

## 本地运行

需要 Node.js 20.9 或更高版本。仓库只提交 npm 的 `package-lock.json`：

```bash
cd frontend
npm ci
npm run dev
```

打开 <http://127.0.0.1:3000/>，根路径会重定向到 `/agent`。

## 配置

API 默认使用同源路径，不需要环境变量。如开发环境确实采用独立 API origin，可设置
`NEXT_PUBLIC_API_BASE_URL`；该值会进入浏览器构建产物，因此只能放公开 origin，
不能包含密钥、Token 或凭据。

所有 API 请求通过 `lib/api-client.ts`，所有运行事件通过 `lib/sse-client.ts`。
写请求把当前 Session 契约返回的 CSRF 值作为 `csrfToken` 传给 API Client，由唯一
入口写入 `X-CSRF-Token`；Cookie 始终由浏览器以 `credentials: "include"` 发送。

## 验证

```bash
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Vitest + Testing Library 是唯一组件测试工具；Playwright 是唯一浏览器测试工具。
普通测试使用 Mock/Fake Fetch 和本地 Next.js 服务，不连接后端、模型、地图或其他
第三方 API。
