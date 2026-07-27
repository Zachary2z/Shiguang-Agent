"use client";

import {
  type ChangeEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { ApiError, apiClient } from "@/lib/api-client";
import { sseClient, type SseEvent } from "@/lib/sse-client";

type AgentState =
  | "idle"
  | "submitting"
  | "queued"
  | "processing"
  | "saved"
  | "pending_selection"
  | "pending_details"
  | "failed"
  | "undone";

type DemoSession = {
  session_id: string;
  csrf_token: string;
  resumed: boolean;
};

type AcceptedImport = {
  message_id: string;
  trace_id: string;
  input_type: "text" | "url" | "image";
  run_status: "queued";
  events_url: `/${string}`;
  result_url: `/${string}`;
  replayed: boolean;
};

type CollectionItem = {
  id: string;
  title: string;
  kind: "place" | "event";
  city_hint: string | null;
  city_pending: boolean;
  district: string | null;
  address: string | null;
  tags: string[];
  missing_fields: string[];
  uncertainties: Array<{ field: string; reason: string }>;
  status:
    | "active"
    | "pending_selection"
    | "pending_details"
    | "visited"
    | "archived"
    | "deleted";
  version: number;
};

type ImportResult = {
  message_id: string;
  trace_id: string;
  input_type: "text" | "url" | "image";
  run_status:
    | "queued"
    | "running"
    | "succeeded"
    | "partially_succeeded"
    | "failed"
    | "cancelled";
  extraction: {
    outcome: string;
    missing_fields: string[];
    recovery_suggestions: string[];
  } | null;
  collections: CollectionItem[];
  recovery_actions: string[];
  error_code: string | null;
  tool_steps: Array<{
    tool_name: string;
    stage: string;
    status: string;
    source: string;
    duration_ms: number | null;
    error_code: string | null;
  }>;
};

type RunEventData = {
  summary?: { stage?: string; status?: string; error_code?: string };
};

type Conversation = {
  messages: Array<{
    run_status: ImportResult["run_status"];
    events_url: `/${string}`;
    result_url: `/${string}`;
    trace_id: string;
    message_id: string;
    input_type: AcceptedImport["input_type"];
  }>;
};

const stageLabels: Readonly<Record<string, string>> = {
  content_receiving: "内容接收",
  place_recognition: "地点识别",
  result_organizing: "结果整理",
};

const toolLabels: Readonly<Record<string, string>> = {
  web_content_fetch: "读取网页内容",
  image_recognition: "识别截图",
};

const acceptedImageTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
const maxImageBytes = 10_000_000;

function resultState(result: ImportResult): AgentState {
  if (result.run_status === "failed" || result.run_status === "cancelled") {
    return "failed";
  }
  const status = result.collections[0]?.status;
  if (status === "active") return "saved";
  if (status === "pending_selection") return "pending_selection";
  if (status === "pending_details") return "pending_details";
  if (result.run_status === "queued") return "queued";
  if (result.run_status === "running") return "processing";
  return result.extraction?.outcome === "candidates"
    ? "pending_details"
    : "failed";
}

function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "暂时没有完成，请重新试一次。";
  const messages: Partial<Record<ApiError["code"], string>> = {
    unauthorized: "会话已过期，正在为你重新建立。",
    forbidden: "会话校验已失效，请刷新页面后重试。",
    conflict: "这次提交与先前内容不同，请重新添加。",
    timeout: "上传等待超时，请检查网络后重试。",
    aborted: "已取消这次上传。",
    network_error: "网络连接中断，请重试。",
  };
  return messages[error.code] ?? "暂时没有完成，请重新试一次。";
}

export function AgentExperience() {
  const [session, setSession] = useState<DemoSession | null>(null);
  const [state, setState] = useState<AgentState>("idle");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [feedback, setFeedback] = useState("");
  const [stage, setStage] = useState("准备接收");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [editing, setEditing] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftDistrict, setDraftDistrict] = useState("");
  const [showTools, setShowTools] = useState(false);
  const submitController = useRef<AbortController | null>(null);
  const sseCancel = useRef<(() => void) | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const startSession = useCallback(async () => {
    try {
      const next = await apiClient.request<DemoSession>("/api/v1/demo/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      setSession(next);
      setFeedback("");
      return next;
    } catch (error) {
      setState("failed");
      setFeedback(errorMessage(error));
      return null;
    }
  }, []);

  useEffect(() => {
    const sessionStart = window.setTimeout(() => void startSession(), 0);
    return () => {
      window.clearTimeout(sessionStart);
      submitController.current?.abort();
      sseCancel.current?.();
    };
  }, [startSession]);

  const readAuthoritativeResult = useCallback(
    async (path: `/${string}`) => {
      try {
        const authoritative = await apiClient.request<ImportResult>(path);
        setResult(authoritative);
        setState(resultState(authoritative));
        const item = authoritative.collections[0];
        if (item) {
          setDraftTitle(item.title);
          setDraftDistrict(item.district ?? "");
        }
        setFeedback(
          authoritative.error_code
            ? "识别没有完成，你可以补充文字、改发截图或重试。"
            : "",
        );
      } catch (error) {
        setState("failed");
        setFeedback(errorMessage(error));
      }
    },
    [],
  );

  const followRun = useCallback(
    (accepted: AcceptedImport) => {
      let lastSequence = 0;
      const connection = sseClient.connect<RunEventData>({
        path: accepted.events_url,
        maxReconnectAttempts: 2,
        onEvent: (event: SseEvent<RunEventData>) => {
          if (event.sequence <= lastSequence) return;
          lastSequence = event.sequence;
          const nextStage = event.data.summary?.stage;
          if (nextStage) setStage(stageLabels[nextStage] ?? "正在处理");
          if (event.event === "run.started") setState("processing");
          if (event.event === "run.completed" || event.event === "run.failed") {
            void readAuthoritativeResult(accepted.result_url);
          }
        },
        onStateChange: (connectionState) => {
          if (connectionState === "disconnected") {
            setFeedback("连接短暂中断，正在从上次进度恢复。");
          }
          if (connectionState === "error") {
            setFeedback("进度连接已断开，正在读取最终结果。");
            void readAuthoritativeResult(accepted.result_url);
          }
        },
      });
      sseCancel.current = connection.cancel;
      void connection.closed.catch(() => {
        void readAuthoritativeResult(accepted.result_url);
      });
    },
    [readAuthoritativeResult],
  );

  useEffect(() => {
    if (!session) return;
    const recover = window.setTimeout(() => {
      void apiClient
        .request<Conversation>(`/api/v1/sessions/${session.session_id}/messages`)
        .then((conversation) => {
          const latest = conversation.messages.at(-1);
          if (!latest) return;
          if (latest.run_status === "queued" || latest.run_status === "running") {
            setState(latest.run_status === "queued" ? "queued" : "processing");
            followRun({
              ...latest,
              run_status: "queued",
              replayed: true,
            });
            return;
          }
          void readAuthoritativeResult(latest.result_url);
        })
        .catch(() => {
          // A fresh session legitimately has no recoverable conversation.
        });
    }, 0);
    return () => window.clearTimeout(recover);
  }, [followRun, readAuthoritativeResult, session]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!session || ["submitting", "queued", "processing"].includes(state)) return;
    if (!file && !text.trim()) {
      setFeedback("写下一个地点、粘贴链接，或选择一张截图。");
      return;
    }

    setState("submitting");
    setFeedback("");
    setStage("内容接收");
    setResult(null);
    const controller = new AbortController();
    submitController.current = controller;
    const key = crypto.randomUUID();
    const path = `/api/v1/sessions/${session.session_id}/messages` as const;
    try {
      const requestHeaders = file
        ? new Headers({
            "Content-Type": file.type,
            "Idempotency-Key": key,
          })
        : new Headers({ "Content-Type": "application/json" });
      const options = file
        ? {
            method: "POST",
            headers: requestHeaders,
            body: file,
            csrfToken: session.csrf_token,
            signal: controller.signal,
            timeoutMs: 30_000,
          }
        : {
            method: "POST",
            headers: requestHeaders,
            body: JSON.stringify(
              /^https?:\/\/\S+$/i.test(text.trim())
                ? { type: "url", idempotency_key: key, url: text.trim() }
                : { type: "text", idempotency_key: key, text: text.trim() },
            ),
            csrfToken: session.csrf_token,
            signal: controller.signal,
          };
      const accepted = await apiClient.request<AcceptedImport>(path, options);
      setState("queued");
      setStage("正在识别");
      followRun(accepted);
    } catch (error) {
      if (error instanceof ApiError && error.code === "unauthorized") {
        await startSession();
      }
      setState("failed");
      setFeedback(errorMessage(error));
    } finally {
      submitController.current = null;
    }
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    if (!selected) return;
    if (!acceptedImageTypes.has(selected.type)) {
      setFeedback("请选择 JPEG、PNG 或 WebP 图片。");
      event.target.value = "";
      return;
    }
    if (selected.size > maxImageBytes) {
      setFeedback("图片不能超过 10 MB，请压缩后再试。");
      event.target.value = "";
      return;
    }
    setFile(selected);
    setText("");
    setFeedback("");
  }

  async function saveEdit() {
    const item = result?.collections[0];
    if (!item || !session || !draftTitle.trim()) return;
    try {
      const updated = await apiClient.request<CollectionItem>(
        `/api/v1/collections/${item.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          csrfToken: session.csrf_token,
          body: JSON.stringify({
            expected_version: item.version,
            changes: {
              title: draftTitle.trim(),
              district: draftDistrict.trim() || null,
            },
          }),
        },
      );
      setResult({ ...result, collections: [updated, ...result.collections.slice(1)] });
      setEditing(false);
    } catch (error) {
      setFeedback(errorMessage(error));
    }
  }

  async function undo() {
    const item = result?.collections[0];
    if (!item || !session) return;
    try {
      const deleted = await apiClient.request<CollectionItem>(
        `/api/v1/collections/${item.id}?expected_version=${item.version}`,
        { method: "DELETE", csrfToken: session.csrf_token },
      );
      setResult({ ...result, collections: [deleted, ...result.collections.slice(1)] });
      setState("undone");
      setFeedback("已撤销收藏，你可以恢复。");
    } catch (error) {
      setFeedback(errorMessage(error));
    }
  }

  async function restore() {
    const item = result?.collections[0];
    if (!item || !session) return;
    try {
      const restored = await apiClient.request<CollectionItem>(
        `/api/v1/collections/${item.id}/restore`,
        { method: "POST", csrfToken: session.csrf_token },
      );
      setResult({ ...result, collections: [restored, ...result.collections.slice(1)] });
      setState(resultState({ ...result, collections: [restored] }));
      setFeedback("已恢复收藏。");
    } catch (error) {
      setFeedback(errorMessage(error));
    }
  }

  function continueAdding() {
    sseCancel.current?.();
    setText("");
    setFile(null);
    setResult(null);
    setState("idle");
    setStage("准备接收");
    setFeedback("");
    fileInput.current?.focus();
  }

  const busy = ["submitting", "queued", "processing"].includes(state);
  const item = result?.collections[0] ?? null;

  return (
    <section className="agent-page" aria-labelledby="agent-title">
      <header className="agent-hero">
        <p className="page-eyebrow">生活收藏 Agent</p>
        <h1 className="agent-title" id="agent-title">
          把想去的地方，交给拾光
        </h1>
        <p className="agent-lede">
          写一句话、贴一个链接，或发一张截图。拾光会识别地点并告诉你还缺什么。
        </p>
        <div className="intent-switch" aria-label="Agent 能力">
          <span aria-current="true">收藏一个地点</span>
          <button type="button" disabled title="将在 M1-5 开放">
            帮我安排时间 · 稍后开放
          </button>
        </div>
      </header>

      <div className="agent-conversation">
        {state === "idle" && (
          <article className="welcome-card">
            <span className="welcome-index">01</span>
            <div>
              <h2>从一个念头开始</h2>
              <p>例如“周末想去深圳天文台”，或者直接粘贴小红书/公众号链接。</p>
            </div>
          </article>
        )}

        {busy && (
          <article className="process-card" aria-live="polite" aria-busy="true">
            <div className="light-trail" aria-hidden="true"><span /></div>
            <div>
              <p className="process-kicker">正在识别</p>
              <h2>{stage}</h2>
              <p>结果确认前不会提前收藏，也不会显示虚假进度。</p>
            </div>
          </article>
        )}

        {item && state !== "undone" && (
          <article className="result-card" aria-live="polite">
            <div className="result-status">
              <span>
                {state === "saved"
                  ? "已收藏"
                  : state === "pending_selection"
                    ? "待选择"
                    : "待补充"}
              </span>
              <small>{item.kind === "place" ? "地点" : "活动"}</small>
            </div>
            {editing ? (
              <div className="quick-edit">
                <label>
                  名称
                  <input
                    value={draftTitle}
                    onChange={(event) => setDraftTitle(event.target.value)}
                  />
                </label>
                <label>
                  区域
                  <input
                    value={draftDistrict}
                    onChange={(event) => setDraftDistrict(event.target.value)}
                  />
                </label>
                <div className="inline-actions">
                  <button type="button" onClick={() => void saveEdit()}>保存修改</button>
                  <button type="button" className="quiet-button" onClick={() => setEditing(false)}>取消</button>
                </div>
              </div>
            ) : (
              <>
                <h2>{item.title}</h2>
                <p className="place-line">
                  {[item.city_hint, item.district, item.address].filter(Boolean).join(" · ") ||
                    "地点信息还需要补充"}
                </p>
                {item.tags.length > 0 && (
                  <ul className="tag-list" aria-label="标签">
                    {item.tags.map((tag) => <li key={tag}>{tag}</li>)}
                  </ul>
                )}
                {(item.missing_fields.length > 0 || item.uncertainties.length > 0) && (
                  <div className="result-notes">
                    {item.missing_fields.length > 0 && (
                      <p><strong>待补充：</strong>{item.missing_fields.join("、")}</p>
                    )}
                    {item.uncertainties.length > 0 && (
                      <p><strong>待确认：</strong>{item.uncertainties.map((entry) => entry.field).join("、")}</p>
                    )}
                  </div>
                )}
                {state === "pending_selection" && (
                  <p className="next-stage-note">已找到多个可能地点，完整候选选择将在收藏阶段继续处理。</p>
                )}
                <div className="result-actions">
                  <button type="button" onClick={() => setEditing(true)}>修改</button>
                  <button type="button" className="quiet-button" onClick={() => void undo()}>撤销</button>
                  <button type="button" className="quiet-button" onClick={continueAdding}>继续添加</button>
                </div>
              </>
            )}
          </article>
        )}

        {state === "undone" && item && (
          <article className="undo-card" aria-live="polite">
            <div><p>已撤销</p><h2>{item.title}</h2></div>
            <div className="result-actions">
              <button type="button" onClick={() => void restore()}>恢复收藏</button>
              <button type="button" className="quiet-button" onClick={continueAdding}>继续添加</button>
            </div>
          </article>
        )}

        {state === "failed" && (
          <article className="failure-card" role="status">
            <p className="process-kicker">这次没有认出来</p>
            <h2>换一种最短路径继续</h2>
            <p>{feedback || "补充地点名称，改发清晰截图，或重新提交即可。"}</p>
            <div className="recovery-list">
              <button type="button" onClick={() => setState("idle")}>补充文字</button>
              <button type="button" className="quiet-button" onClick={() => fileInput.current?.click()}>改发截图</button>
              <button type="button" className="quiet-button" onClick={() => setState("idle")}>重试</button>
            </div>
          </article>
        )}

        {result && result.tool_steps.length > 0 && (
          <details className="tool-process" open={showTools} onToggle={(event) => setShowTools(event.currentTarget.open)}>
            <summary>Agent 工具过程</summary>
            <ul>
              {result.tool_steps.map((tool, index) => (
                <li key={`${tool.tool_name}-${index}`}>
                  <span>{toolLabels[tool.tool_name] ?? "内容处理"}</span>
                  <small>{stageLabels[tool.stage] ?? "结果整理"} · {tool.status}</small>
                  {tool.duration_ms !== null && <time>{tool.duration_ms} ms</time>}
                  {tool.error_code && <code>{tool.error_code}</code>}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>

      <form className="input-dock" onSubmit={submit}>
        <div className="dock-input-row">
          <textarea
            aria-label="收藏内容"
            placeholder="写下地点，或粘贴 HTTP(S) 链接…"
            value={text}
            rows={2}
            disabled={busy}
            onChange={(event) => {
              setText(event.target.value);
              setFile(null);
              setFeedback("");
            }}
          />
          <button className="send-button" type="submit" disabled={busy || !session}>
            {busy ? "处理中" : "发送"}
          </button>
        </div>
        <div className="dock-meta">
          <label className="file-button">
            <input
              ref={fileInput}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={busy}
              onChange={chooseFile}
            />
            添加截图
          </label>
          {file && <span className="file-name">{file.name}</span>}
          {state === "submitting" && (
            <button type="button" className="cancel-upload" onClick={() => submitController.current?.abort()}>
              取消上传
            </button>
          )}
          <p className="dock-feedback" aria-live="polite">{feedback}</p>
        </div>
      </form>
    </section>
  );
}
