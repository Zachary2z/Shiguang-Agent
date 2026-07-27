"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Icon, type IconName } from "@/components/icons";

const navigation = [
  { href: "/agent", label: "Agent", icon: "agent" },
  { href: "/collections", label: "收藏", icon: "collections" },
  { href: "/plans", label: "计划", icon: "plans" },
  { href: "/me", label: "我的", icon: "me" },
] as const satisfies ReadonlyArray<{
  href: string;
  label: string;
  icon: IconName;
}>;

export function PrimaryNav({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();

  return (
    <nav
      className={`primary-nav${mobile ? " mobile-nav" : ""}`}
      aria-label="主导航"
    >
      {navigation.map((item) => {
        const current =
          pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            className="nav-link"
            href={item.href}
            aria-current={current ? "page" : undefined}
          >
            <span className="nav-icon" aria-hidden="true">
              <Icon name={item.icon} />
            </span>
            <span className="nav-label">{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export { navigation };
