import type { Metadata } from "next";

import { EmptyRoute } from "@/components/empty-route";

export const metadata: Metadata = { title: "计划" };

export default function PlansPage() {
  return (
    <EmptyRoute
      eyebrow="Plans"
      title="计划"
      description="未来在这里查看草案与已确认计划。计划生成、确认、提醒和分享均未在本阶段实现。"
    />
  );
}
