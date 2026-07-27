import type { Metadata } from "next";

import { EmptyRoute } from "@/components/empty-route";

export const metadata: Metadata = { title: "收藏" };

export default function CollectionsPage() {
  return (
    <EmptyRoute
      eyebrow="Collections"
      title="收藏"
      description="未来在这里管理想去、想做和想吃的地点与活动。收藏列表和地点消歧不属于本阶段。"
    />
  );
}
