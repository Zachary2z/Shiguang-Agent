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
  | "recovering"
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

type CollectionMutationOwner = {
  generation: number;
  traceId: string;
  collectionId: string;
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
  const statuses = new Set(result.collections.map((item) => item.status));
  if (statuses.size > 0 && statuses.size === 1 && statuses.has("deleted")) {
    return "undone";
  }
  if (statuses.has("pending_selection")) return "pending_selection";
  if (statuses.has("pending_details")) return "pending_details";
  if (
    statuses.has("active") ||
    statuses.has("visited") ||
    statuses.has("archived")
  ) {
    return "saved";
  }
  if (result.run_status === "queued") return "queued";
  if (result.run_status === "running") return "processing";
  return result.extraction?.outcome === "candidates"
    ? "pending_details"
    : "failed";
}

function collectionStatusLabel(status: CollectionItem["status"]): string {
  return {
    active: "已收藏",
    pending_selection: "待选择",
    pending_details: "待补充",
    visited: "已到访",
    archived: "已归档",
    deleted: "已撤销",
  }[status];
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
  const [state, setState] = useState<AgentState>("recovering");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [feedback, setFeedback] = useState("");
  const [stage, setStage] = useState("准备接收");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftDistrict, setDraftDistrict] = useState("");
  const [showTools, setShowTools] = useState(false);
  const submitController = useRef<AbortController | null>(null);
  const sseCancel = useRef<(() => void) | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const mainInput = useRef<HTMLTextAreaElement | null>(null);
  const operationGeneration = useRef(0);

  const readAuthoritativeResult = useCallback(
    async (path: `/${string}`, generation: number) => {
      try {
        const authoritative = await apiClient.request<ImportResult>(path);
        if (operationGeneration.current !== generation) return;
        setResult(authoritative);
        setState(resultState(authoritative));
        setFeedback(
          authoritative.error_code
            ? "识别没有完成，你可以补充文字、改发截图或重试。"
            : "",
        );
      } catch (error) {
        if (operationGeneration.current !== generation) return;
        setState("failed");
        setFeedback(errorMessage(error));
      }
    },
    [],
  );

  const followRun = useCallback(
    (accepted: AcceptedImport, generation: number) => {
      sseCancel.current?.();
      let lastSequence = 0;
      const connection = sseClient.connect<RunEventData>({
        path: accepted.events_url,
        maxReconnectAttempts: 2,
        onEvent: (event: SseEvent<RunEventData>) => {
          if (operationGeneration.current !== generation) return;
          if (event.sequence <= lastSequence) return;
          lastSequence = event.sequence;
          const nextStage = event.data.summary?.stage;
          if (nextStage) setStage(stageLabels[nextStage] ?? "正在处理");
          if (event.event === "run.started") setState("processing");
          if (event.event === "run.completed" || event.event === "run.failed") {
            void readAuthoritativeResult(accepted.result_url, generation);
          }
        },
        onStateChange: (connectionState) => {
          if (operationGeneration.current !== generation) return;
          if (connectionState === "disconnected") {
            setFeedback("连接短暂中断，正在从上次进度恢复。");
          }
          if (connectionState === "error") {
            setFeedback("进度连接已断开，正在读取最终结果。");
            void readAuthoritativeResult(accepted.result_url, generation);
          }
        },
      });
      sseCancel.current = connection.cancel;
      void connection.closed.catch(() => {
        if (operationGeneration.current === generation) {
          void readAuthoritativeResult(accepted.result_url, generation);
        }
      });
    },
    [readAuthoritativeResult],
  );

  useEffect(() => {
    const generation = operationGeneration.current + 1;
    operationGeneration.current = generation;
    const bootstrap = window.setTimeout(() => {
      void (async () => {
        try {
          const next = await apiClient.request<DemoSession>(
            "/api/v1/demo/sessions",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: "{}",
            },
          );
          if (operationGeneration.current !== generation) return;
          setSession(next);
          const conversation = await apiClient.request<Conversation>(
            `/api/v1/sessions/${next.session_id}/messages`,
          );
          if (operationGeneration.current !== generation) return;
          const latest = conversation.messages.at(-1);
          if (!latest) {
            setState("idle");
            return;
          }
          if (latest.run_status === "queued" || latest.run_status === "running") {
            setState(latest.run_status === "queued" ? "queued" : "processing");
            followRun(
              { ...latest, run_status: "queued", replayed: true },
              generation,
            );
            return;
          }
          await readAuthoritativeResult(latest.result_url, generation);
        } catch (error) {
          if (operationGeneration.current !== generation) return;
          setState("failed");
          setFeedback(errorMessage(error));
        }
      })();
    }, 0);
    return () => {
      window.clearTimeout(bootstrap);
      operationGeneration.current += 1;
      submitController.current?.abort();
      sseCancel.current?.();
    };
  }, [followRun, readAuthoritativeResult]);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (
      !session ||
      ["recovering", "submitting", "queued", "processing"].includes(state)
    ) {
      return;
    }
    if (!file && !text.trim()) {
      setFeedback("写下一个地点、粘贴链接，或选择一张截图。");
      return;
    }

    const generation = operationGeneration.current + 1;
    operationGeneration.current = generation;
    sseCancel.current?.();
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
        ? new Headers()
        : new Headers({ "Content-Type": "application/json" });
      const form = new FormData();
      if (file) {
        form.set("idempotency_key", key);
        if (text.trim()) form.set("text", text.trim());
        form.set("image", file);
      }
      const options = file
        ? {
            method: "POST",
            headers: requestHeaders,
            body: form,
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
      if (operationGeneration.current !== generation) return;
      setState("queued");
      setStage("正在识别");
      followRun(accepted, generation);
    } catch (error) {
      if (operationGeneration.current !== generation) return;
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
    setFeedback("");
  }

  function mutationOwner(item: CollectionItem): CollectionMutationOwner | null {
    if (!result?.collections.some((current) => current.id === item.id)) return null;
    return {
      generation: operationGeneration.current,
      traceId: result.trace_id,
      collectionId: item.id,
    };
  }

  function mutationIsCurrent(
    owner: CollectionMutationOwner,
    updated?: CollectionItem,
  ) {
    return (
      operationGeneration.current === owner.generation &&
      (!updated || updated.id === owner.collectionId)
    );
  }

  function replaceCollection(
    owner: CollectionMutationOwner,
    updated: CollectionItem,
  ) {
    setResult((current) => {
      if (
        updated.id !== owner.collectionId ||
        current?.trace_id !== owner.traceId ||
        !current.collections.some((item) => item.id === owner.collectionId)
      ) {
        return current;
      }
      return {
        ...current,
        collections: current.collections.map((item) =>
          item.id === owner.collectionId ? updated : item,
        ),
      };
    });
  }

  function beginEdit(item: CollectionItem) {
    setDraftTitle(item.title);
    setDraftDistrict(item.district ?? "");
    setEditingId(item.id);
  }

  async function saveEdit(item: CollectionItem) {
    const owner = mutationOwner(item);
    if (!owner || !session || !draftTitle.trim()) return;
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
      if (!mutationIsCurrent(owner, updated)) return;
      replaceCollection(owner, updated);
      setEditingId(null);
    } catch (error) {
      if (!mutationIsCurrent(owner)) return;
      setFeedback(errorMessage(error));
    }
  }

  async function undo(item: CollectionItem) {
    const owner = mutationOwner(item);
    if (!owner || !session) return;
    try {
      const deleted = await apiClient.request<CollectionItem>(
        `/api/v1/collections/${item.id}?expected_version=${item.version}`,
        { method: "DELETE", csrfToken: session.csrf_token },
      );
      if (!mutationIsCurrent(owner, deleted)) return;
      replaceCollection(owner, deleted);
      setFeedback(`已撤销“${item.title}”，你可以单独恢复。`);
    } catch (error) {
      if (!mutationIsCurrent(owner)) return;
      setFeedback(errorMessage(error));
    }
  }

  async function restore(item: CollectionItem) {
    const owner = mutationOwner(item);
    if (!owner || !session) return;
    try {
      const restored = await apiClient.request<CollectionItem>(
        `/api/v1/collections/${item.id}/restore`,
        { method: "POST", csrfToken: session.csrf_token },
      );
      if (!mutationIsCurrent(owner, restored)) return;
      replaceCollection(owner, restored);
      setFeedback(`已恢复“${item.title}”。`);
    } catch (error) {
      if (!mutationIsCurrent(owner)) return;
      setFeedback(errorMessage(error));
    }
  }

  function continueAdding() {
    operationGeneration.current += 1;
    sseCancel.current?.();
    setText("");
    setFile(null);
    setResult(null);
    setState("idle");
    setStage("准备接收");
    setFeedback("");
    window.setTimeout(() => mainInput.current?.focus(), 0);
  }

  function returnToInput() {
    setState("idle");
    window.setTimeout(() => mainInput.current?.focus(), 0);
  }

  const busy = ["recovering", "submitting", "queued", "processing"].includes(
    state,
  );
  const displayState =
    result &&
    result.run_status !== "failed" &&
    result.run_status !== "cancelled"
      ? resultState(result)
      : state;

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
          <a href="/plans">帮我安排时间</a>
        </div>
      </header>

      <div className="agent-conversation">
        {displayState === "idle" && (
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

        {result && result.collections.length > 0 && (
          <section className="collection-results" aria-live="polite" aria-label="识别结果">
            <div className="collection-results-heading">
              <p>本次整理出 {result.collections.length} 项收藏</p>
              <button type="button" className="quiet-button" onClick={continueAdding}>
                继续添加
              </button>
            </div>
            {result.collections.map((item) => (
              <article className="result-card" key={item.id}>
                <div className="result-status">
                  <span>{collectionStatusLabel(item.status)}</span>
                  <small>{item.kind === "place" ? "地点" : "活动"}</small>
                </div>
                {editingId === item.id ? (
                  <div className="quick-edit">
                    <label>
                      名称
                      <input
                        name="collection_title"
                        autoComplete="off"
                        value={draftTitle}
                        onChange={(event) => setDraftTitle(event.target.value)}
                      />
                    </label>
                    <label>
                      区域
                      <input
                        name="collection_district"
                        autoComplete="address-level2"
                        value={draftDistrict}
                        onChange={(event) => setDraftDistrict(event.target.value)}
                      />
                    </label>
                    <div className="inline-actions">
                      <button type="button" onClick={() => void saveEdit(item)}>
                        保存修改
                      </button>
                      <button
                        type="button"
                        className="quiet-button"
                        onClick={() => setEditingId(null)}
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <h2>{item.title}</h2>
                    <p className="place-line">
                      {[item.city_hint, item.district, item.address]
                        .filter(Boolean)
                        .join(" · ") || "地点信息还需要补充"}
                    </p>
                    {item.tags.length > 0 && (
                      <ul className="tag-list" aria-label={`${item.title}的标签`}>
                        {item.tags.map((tag) => <li key={tag}>{tag}</li>)}
                      </ul>
                    )}
                    {(item.missing_fields.length > 0 ||
                      item.uncertainties.length > 0) && (
                      <div className="result-notes">
                        {item.missing_fields.length > 0 && (
                          <p><strong>待补充：</strong>{item.missing_fields.join("、")}</p>
                        )}
                        {item.uncertainties.length > 0 && (
                          <p><strong>待确认：</strong>{item.uncertainties.map((entry) => entry.field).join("、")}</p>
                        )}
                      </div>
                    )}
                    {item.status === "pending_selection" && (
                      <p className="next-stage-note">
                        已找到多个可能地点，完整候选选择将在收藏阶段继续处理。
                      </p>
                    )}
                    <div className="result-actions">
                      {item.status !== "deleted" ? (
                        <>
                          <button type="button" onClick={() => beginEdit(item)}>
                            修改
                          </button>
                          <button
                            type="button"
                            className="quiet-button"
                            onClick={() => void undo(item)}
                          >
                            撤销
                          </button>
                        </>
                      ) : (
                        <button type="button" onClick={() => void restore(item)}>
                          恢复收藏
                        </button>
                      )}
                    </div>
                  </>
                )}
              </article>
            ))}
          </section>
        )}

        {displayState === "failed" && (
          <article className="failure-card" role="status" aria-live="polite">
            <p className="process-kicker">这次没有认出来</p>
            <h2>换一种最短路径继续</h2>
            <p>{feedback || "补充地点名称，改发清晰截图，或重新提交即可。"}</p>
            <div className="recovery-list">
              <button type="button" onClick={returnToInput}>补充文字</button>
              <button type="button" className="quiet-button" onClick={() => fileInput.current?.click()}>改发截图</button>
              <button
                type="button"
                className="quiet-button"
                disabled={busy}
                onClick={() => void submit()}
              >
                重试
              </button>
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
            ref={mainInput}
            name="collection_input"
            autoComplete="off"
            aria-label="收藏内容"
            placeholder="写下地点，或粘贴 HTTP(S) 链接…"
            value={text}
            rows={2}
            disabled={busy}
            onChange={(event) => {
              setText(event.target.value);
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
              name="collection_image"
              accept="image/jpeg,image/png,image/webp"
              disabled={busy}
              onChange={chooseFile}
            />
            添加截图
          </label>
          {file && (
            <span className="file-name">
              {file.name}
              <button
                type="button"
                className="quiet-button"
                disabled={busy}
                onClick={() => {
                  setFile(null);
                  if (fileInput.current) fileInput.current.value = "";
                }}
              >
                删除截图
              </button>
            </span>
          )}
          {state === "submitting" && (
            <button type="button" className="cancel-upload" onClick={() => submitController.current?.abort()}>
              取消上传
            </button>
          )}
          {displayState !== "failed" && (
            <p className="dock-feedback" aria-live="polite">{feedback}</p>
          )}
        </div>
      </form>
    </section>
  );
}
