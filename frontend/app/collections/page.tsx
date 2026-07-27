import type { Metadata } from "next";
import { Suspense } from "react";

import { CollectionsExperience } from "@/components/collections-experience";
import { StatusState } from "@/components/status-state";

export const metadata: Metadata = { title: "收藏" };

export default function CollectionsPage() {
  return (
    <Suspense
      fallback={
        <StatusState
          kind="loading"
          title="正在打开收藏库"
          description="正在恢复你的筛选与收藏。"
        />
      }
    >
      <CollectionsExperience />
    </Suspense>
  );
}
