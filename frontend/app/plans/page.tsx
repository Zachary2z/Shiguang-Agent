import type { Metadata } from "next";

import { PlansExperience } from "@/components/plans-experience";

export const metadata: Metadata = { title: "计划" };

export default function PlansPage() {
  return <PlansExperience />;
}
