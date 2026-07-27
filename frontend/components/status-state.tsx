import type { ReactNode } from "react";

export type StatusKind = "loading" | "empty" | "error" | "offline";

const defaults: Record<
  StatusKind,
  { title: string; description: string; symbol: string }
> = {
  loading: {
    title: "正在准备",
    description: "内容就绪后会在这里更新。",
    symbol: "···",
  },
  empty: {
    title: "这里还没有内容",
    description: "完成第一步后，结果会出现在这里。",
    symbol: "○",
  },
  error: {
    title: "暂时没有完成",
    description: "保留现有内容，你可以重新尝试。",
    symbol: "!",
  },
  offline: {
    title: "连接已断开",
    description: "网络恢复后可以从上次进度继续。",
    symbol: "↯",
  },
};

type StatusStateProps = {
  kind: StatusKind;
  title?: string;
  description?: string;
  action?: ReactNode;
};

export function StatusState({
  kind,
  title,
  description,
  action,
}: StatusStateProps) {
  const copy = defaults[kind];
  const isAsync = kind === "loading" || kind === "offline";

  return (
    <section
      className="status-panel"
      data-tone={kind}
      aria-live={isAsync ? "polite" : undefined}
      aria-busy={kind === "loading" ? true : undefined}
    >
      <div className="status-content">
        <span
          className={`status-symbol${kind === "loading" ? " loading-pulse" : ""}`}
          aria-hidden="true"
        >
          {copy.symbol}
        </span>
        <h2 className="status-title">{title ?? copy.title}</h2>
        <p className="status-description">
          {description ?? copy.description}
        </p>
        {action}
      </div>
    </section>
  );
}

export function RetryButton({
  onRetry,
  children = "重新尝试",
}: {
  onRetry: () => void;
  children?: ReactNode;
}) {
  return (
    <button className="button" type="button" onClick={onRetry}>
      {children}
    </button>
  );
}
