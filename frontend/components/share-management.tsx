"use client";

import { useEffect, useRef, useState } from "react";

import { ApiClient, ApiError } from "@/lib/api-client";
import type { OwnerPlanShare } from "@/lib/share-contracts";

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

  async function mutate(path: `/${string}`, method: "POST" | "DELETE") {
    const owner = ++operation.current;
    setBusy(true);
    setMessage("");
    try {
      const result = await shareApiClient.request<OwnerPlanShare>(path, {
        method,
        csrfToken,
      });
      if (operation.current !== owner) return;
      setShare(result);
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
              onClick={() => void mutate(`/api/v1/plans/${planId}/share`, "POST")}
            >
              {busy ? "正在生成" : "生成只读链接"}
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
                onClick={() => {
                  if (window.confirm("重建后旧链接会立即失效。继续吗？")) {
                    void mutate(`/api/v1/plans/${planId}/share/regenerate`, "POST");
                  }
                }}
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
      {busy && <p className="share-message" role="status">正在更新分享状态…</p>}
      {!busy && message && <p className="share-message" role="status">{message}</p>}
    </section>
  );
}
