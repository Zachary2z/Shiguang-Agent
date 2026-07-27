"use client";

import { RetryButton, StatusState } from "@/components/status-state";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <StatusState
      kind="error"
      title="页面暂时无法显示"
      description="你的操作没有被当作成功处理。可以保留当前页面并重新尝试。"
      action={<RetryButton onRetry={reset} />}
    />
  );
}
