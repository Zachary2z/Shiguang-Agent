"use client";

import { useEffect, useRef, useState } from "react";

import { ApiClient, ApiError } from "@/lib/api-client";
import type {
  OwnerPlanShare,
  SharedPlanSnapshot,
} from "@/lib/share-contracts";

const transportLabels: Record<string, string> = {
  walking: "步行",
  cycling: "骑行",
  transit: "公共交通",
  driving: "驾车",
};

type ShareManagementProps = {
  planId: string;
  csrfToken: string;
};

export const shareApiClient = new ApiClient();

function dateTime(value: string | null) {
  if (!value) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError && error.code === "unauthorized") {
    return "会话已过期，请刷新页面后重试。";
  }
  return "分享状态暂时不可用，请稍后重试。";
}

export function ShareManagement({ planId, csrfToken }: ShareManagementProps) {
  const [share, setShare] = useState<OwnerPlanShare | null>(null);
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<SharedPlanSnapshot | null>(null);
  const [pendingAction, setPendingAction] = useState<"create" | "regenerate" | null>(null);
  const idempotencyKey = useRef<string | null>(null);
  const operation = useRef(0);

  useEffect(() => {
    const owner = ++operation.current;
    void shareApiClient
      .request<OwnerPlanShare>(`/api/v1/plans/${planId}/share`)
      .then((result) => {
        if (operation.current === owner) setShare(result);
      })
      .catch((error: unknown) => {
        if (operation.current === owner) setMessage(errorMessage(error));
      })
      .finally(() => {
        if (operation.current === owner) setBusy(false);
      });
    return () => {
      operation.current += 1;
    };
  }, [planId]);

  async function showPreview(action: "create" | "regenerate") {
    const owner = ++operation.current;
    idempotencyKey.current = crypto.randomUUID();
    setPendingAction(action);
    setBusy(true);
    setMessage("");
    try {
      const result = await shareApiClient.request<SharedPlanSnapshot>(
        `/api/v1/plans/${planId}/share/preview`,
      );
      if (operation.current === owner) setPreview(result);
    } catch (error) {
      if (operation.current === owner) {
        setPendingAction(null);
        idempotencyKey.current = null;
        setMessage(errorMessage(error));
      }
    } finally {
      if (operation.current === owner) setBusy(false);
    }
  }

  async function mutate(path: `/${string}`, method: "POST" | "DELETE") {
    const owner = ++operation.current;
    setBusy(true);
    setMessage("");
    try {
      const result = await shareApiClient.request<OwnerPlanShare>(path, {
        method,
        csrfToken,
        headers:
          method === "POST" && idempotencyKey.current
            ? { "Idempotency-Key": idempotencyKey.current }
            : undefined,
      });
      if (operation.current !== owner) return;
      setShare(result);
      setPreview(null);
      setPendingAction(null);
      idempotencyKey.current = null;
      if (result.share_url) {
        setMessage("新链接已生成。明文只在这一次显示，请立即复制。");
      } else if (method === "DELETE") {
        setMessage("分享已撤销，旧链接立即失效。");
      }
    } catch (error) {
      if (operation.current === owner) setMessage(errorMessage(error));
    } finally {
      if (operation.current === owner) setBusy(false);
    }
  }

  async function copyLink() {
    if (!share?.share_url) return;
    const absolute = new URL(share.share_url, window.location.origin).toString();
    try {
      await navigator.clipboard.writeText(absolute);
      setMessage("链接已复制。");
    } catch {
      setMessage("无法自动复制，请打开链接后从地址栏复制。");
    }
  }

  const active = share?.status === "active";
  const createdLink = share?.share_url ?? null;

  return (
    <section className="share-management" aria-labelledby="share-management-title" aria-busy={busy}>
      <div className="plan-section-title">
        <span>07</span>
        <div>
          <p className="eyebrow">Read-only sharing</p>
          <h2 id="share-management-title">把确认版本交给同行的人</h2>
        </div>
      </div>
      <div className="share-management-grid">
        <div>
          {share && (
            <strong className={`share-status-badge ${share.status}`}>
              {share.status === "active"
                ? "正在分享"
                : share.status === "expired"
                  ? "分享已过期"
                  : "当前未分享"}
            </strong>
          )}
          <p>
            访客无需登录，只能看到最新确认版本的脱敏快照。草稿、收藏正文、
            私人备注与账号信息不会出现。
          </p>
          {share?.expires_at && (
            <p className="share-expiry">
              {share.status === "expired" ? "已于" : "将在"} {dateTime(share.expires_at)}
              {share.status === "expired" ? "过期" : "自动过期"}
            </p>
          )}
        </div>
        <div className="share-actions">
          {!active && share?.status !== "expired" && (
            <button
              className="primary-button"
              type="button"
              disabled={busy}
              onClick={() => void showPreview("create")}
            >
              {busy ? "正在准备" : "预览并生成链接"}
            </button>
          )}
          {active && (
            <>
              {createdLink ? (
                <>
                  <button className="primary-button" type="button" disabled={busy} onClick={() => void copyLink()}>
                    复制新链接
                  </button>
                  <a href={createdLink} target="_blank" rel="noreferrer">预览访客页面</a>
                </>
              ) : (
                <p className="share-once-note">链接仍有效；为安全起见，服务端不保存明文。</p>
              )}
              <button
                type="button"
                disabled={busy}
                onClick={() => void showPreview("regenerate")}
              >
                重建链接
              </button>
              <button
                className="danger-button"
                type="button"
                disabled={busy}
                onClick={() => void mutate(`/api/v1/plans/${planId}/share`, "DELETE")}
              >
                撤销分享
              </button>
            </>
          )}
        </div>
      </div>
      {preview && pendingAction && (
        <section className="share-owner-preview" aria-labelledby="share-preview-title">
          <p className="eyebrow">Redacted preview</p>
          <h3 id="share-preview-title">访客将看到这些内容</h3>
          <p>
            {dateTime(preview.start_at)} · {preview.origin_label} ·
            确认版本 V{preview.version}
          </p>
          <ol>
            {preview.items.map((item) => (
              <li key={`${item.title}-${item.start_at}`}>
                <strong>{item.title}</strong>
                <span>{dateTime(item.start_at)}—{dateTime(item.end_at)}</span>
                <span>{item.public_address ?? "不公开详细地址"}</span>
                <span>
                  {transportLabels[item.transport_mode] ?? item.transport_mode}
                  {" "}{Math.round(item.travel_duration_seconds / 60)} 分钟
                  {item.travel_distance_meters > 0
                    ? ` · ${(item.travel_distance_meters / 1000).toFixed(1)} km`
                    : ""} ·
                  缓冲 {Math.round(item.buffer_after_seconds / 60)} 分钟 ·
                  费用 {item.price_amount === null ? "待确认" : `¥${item.price_amount}`}
                </span>
                <span>
                  风险：{item.risks.length ? item.risks.join("；") : "暂无"}
                  {item.map_url ? " · 含公开路线入口" : " · 暂无路线入口"}
                </span>
                {item.queried_at && <span>地点信息查询于 {dateTime(item.queried_at)}</span>}
              </li>
            ))}
          </ol>
          {preview.risks.length > 0 && <p>整体风险：{preview.risks.join("；")}</p>}
          <p>
            预计总费用：
            {preview.total_cost_amount === null
              ? "待确认"
              : `¥${preview.total_cost_amount}`}
          </p>
          <p>链接将在 {dateTime(preview.expires_at)} 自动过期。</p>
          <div className="share-preview-actions">
            <button
              className="primary-button"
              type="button"
              disabled={busy}
              onClick={() =>
                void mutate(
                  pendingAction === "regenerate"
                    ? `/api/v1/plans/${planId}/share/regenerate`
                    : `/api/v1/plans/${planId}/share`,
                  "POST",
                )
              }
            >
              {busy
                ? "正在确认"
                : pendingAction === "regenerate"
                  ? "确认重建并使旧链接失效"
                  : "确认并生成链接"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setPreview(null);
                setPendingAction(null);
                idempotencyKey.current = null;
              }}
            >
              取消
            </button>
          </div>
        </section>
      )}
      {busy && <p className="share-message" role="status">正在更新分享状态…</p>}
      {!busy && message && <p className="share-message" role="status">{message}</p>}
    </section>
  );
}
