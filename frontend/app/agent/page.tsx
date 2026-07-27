import type { Metadata } from "next";

import { AgentExperience } from "@/components/agent-experience";

export const metadata: Metadata = { title: "Agent" };

export default function AgentPage() {
  return <AgentExperience />;
}
