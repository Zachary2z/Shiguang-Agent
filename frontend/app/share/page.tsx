import type { Metadata } from "next";

import { PublicShareExperience } from "@/components/public-share-experience";

export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "只读行程 · 拾光",
  description: "拾光最新确认行程的只读分享。",
  robots: { index: false, follow: false, noarchive: true },
  referrer: "no-referrer",
};

export default function SharedPlanPage() {
  return <PublicShareExperience />;
}
