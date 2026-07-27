import type { Metadata } from "next";

import { EmptyRoute } from "@/components/empty-route";

export const metadata: Metadata = { title: "Agent" };

export default function AgentPage() {
  return (
    <EmptyRoute
      eyebrow="Agent"
      title="今天，想从哪一束光开始？"
      description="收藏与规划入口将在下一阶段接入。本阶段只保留正式页面结构，不展示模拟对话或业务状态。"
    />
  );
}
