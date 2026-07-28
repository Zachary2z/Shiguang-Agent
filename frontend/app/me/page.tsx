import type { Metadata } from "next";

import { MeExperience } from "@/components/me-experience";

export const metadata: Metadata = { title: "我的" };

export default function MePage() {
  return <MeExperience />;
}
