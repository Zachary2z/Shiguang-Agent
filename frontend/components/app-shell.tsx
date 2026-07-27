import type { ReactNode } from "react";

import { Brand } from "@/components/brand";
import { PrimaryNav } from "@/components/primary-nav";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <header className="mobile-header">
        <Brand />
        <span className="mobile-context">深圳 · H5</span>
      </header>

      <aside className="desktop-sidebar" aria-label="产品导航">
        <Brand />
        <PrimaryNav />
        <p className="desktop-sidebar-footer">
          把收藏变成一次真实出发
        </p>
      </aside>

      <main className="main-content" id="main-content" tabIndex={-1}>
        {children}
      </main>

      <aside className="context-panel" aria-label="页面上下文">
        <h2>当前阶段</h2>
        <p>
          正式前端基础已就位。业务内容将在后续阶段按来源、风险与授权规则逐步接入。
        </p>
      </aside>

      <div className="mobile-nav-wrap">
        <PrimaryNav mobile />
      </div>
    </div>
  );
}
