import { StatusState } from "@/components/status-state";

export default function NotFound() {
  return (
    <StatusState
      kind="empty"
      title="没有找到这个页面"
      description="请使用主导航回到拾光的现有页面。"
    />
  );
}
