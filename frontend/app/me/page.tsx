import type { Metadata } from "next";

import { EmptyRoute } from "@/components/empty-route";

export const metadata: Metadata = { title: "我的" };

export default function MePage() {
  return (
    <EmptyRoute
      eyebrow="Me"
      title="我的"
      description="未来在这里管理记忆、设备与数据。真实账号、微信和个人业务设置均未在本阶段实现。"
    />
  );
}
