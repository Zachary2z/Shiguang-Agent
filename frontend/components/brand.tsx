import Link from "next/link";

import { Icon } from "@/components/icons";

export function Brand() {
  return (
    <Link className="brand-lockup" href="/agent" aria-label="拾光 Agent 首页">
      <span className="brand-mark" aria-hidden="true">
        <Icon name="spark" />
      </span>
      <span className="brand-name">拾光</span>
    </Link>
  );
}
