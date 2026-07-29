"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Brand } from "@/components/brand";
import { PrimaryNav } from "@/components/primary-nav";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/share" || pathname.startsWith("/share/")) {
    return (
      <div className="public-shell" id="main-content" tabIndex={-1}>
        {children}
      </div>
    );
  }
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
        <h2>收藏入口</h2>
        <p>输入文字、HTTP(S) 链接或截图。识别结果来自后台任务的权威终态。</p>
      </aside>

      <div className="mobile-nav-wrap">
        <PrimaryNav mobile />
      </div>
    </div>
  );
}
