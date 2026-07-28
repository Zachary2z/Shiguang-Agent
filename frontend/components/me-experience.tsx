"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { ApiError, apiClient } from "@/lib/api-client";

type MemoryType =
  | "positive_preference"
  | "negative_preference"
  | "pace_preference"
  | "usual_area";

type Memory = {
  id: string;
  type: MemoryType;
  content: string;
  value: string;
  source: {
    type: "explicit_user" | "feedback_inference";
    summary: string;
    feedback_id: string | null;
    plan_id: string | null;
  };
  confirmation_status: "confirmed";
  confidence: number;
  expires_at: string | null;
  disabled_at: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  version: number;
};

type MemoryUsage = {
  memory_id: string;
  plan_id: string;
  basis: string;
  used_at: string;
};

type MemorySuggestion = {
  id: string;
  plan_id: string;
  memory_type: MemoryType;
  content: string;
  value: string;
  evidence_summary: string;
  created_at: string;
};

type DemoSession = { csrf_token: string };
type MemoryList = { items: Memory[] };
type SuggestionList = { items: MemorySuggestion[] };
type MemoryDetail = { memory: Memory; usages: MemoryUsage[]; replayed: boolean };
type LoadState = "loading" | "ready" | "error";

const memoryTypeLabels: Record<MemoryType, string> = {
  positive_preference: "喜欢",
  negative_preference: "避开",
  pace_preference: "节奏",
  usual_area: "常用区域",
};

function formatTime(value: string | null): string {
  if (!value) return "尚未使用";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function safeError(error: unknown): string {
  if (!(error instanceof ApiError)) return "记忆中心暂时没有加载完成。";
  if (error.code === "conflict") return "状态已在别处更新，已为你刷新。";
  if (error.code === "not_found") return "这条记忆已不存在，或你没有查看权限。";
  if (error.code === "forbidden") return "会话校验已失效，请刷新页面。";
  if (error.code === "timeout") return "请求等待超时，请重试。";
  return "记忆中心暂时没有完成这次操作。";
}

function operationKey(scope: string): string {
  return `${scope}-${crypto.randomUUID()}`;
}

export function MeExperience() {
  const [csrf, setCsrf] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [memories, setMemories] = useState<Memory[]>([]);
  const [suggestions, setSuggestions] = useState<MemorySuggestion[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<MemoryDetail | null>(null);
  const [content, setContent] = useState("");
  const [value, setValue] = useState("");
  const [feedback, setFeedback] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const loadGeneration = useRef(0);
  const detailGeneration = useRef(0);
  const actionGeneration = useRef(0);
  const csrfRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    const generation = loadGeneration.current + 1;
    loadGeneration.current = generation;
    setLoadState("loading");
    try {
      let token = csrfRef.current;
      if (!token) {
        const session = await apiClient.request<DemoSession>(
          "/api/v1/demo/sessions",
          { method: "POST" },
        );
        if (loadGeneration.current !== generation) return;
        token = session.csrf_token;
        csrfRef.current = token;
        setCsrf(token);
      }
      const [memoryResult, suggestionResult] = await Promise.all([
        apiClient.request<MemoryList>("/api/v1/memories"),
        apiClient.request<SuggestionList>("/api/v1/memory-suggestions"),
      ]);
      if (loadGeneration.current !== generation) return;
      setMemories(memoryResult.items);
      setSuggestions(suggestionResult.items);
      setLoadState("ready");
      setFeedback("");
      setSelectedId((current) =>
        current && memoryResult.items.some((memory) => memory.id === current)
          ? current
          : null,
      );
    } catch (error) {
      if (loadGeneration.current !== generation) return;
      setLoadState("error");
      setFeedback(safeError(error));
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void load());
    return () => {
      loadGeneration.current += 1;
      detailGeneration.current += 1;
      actionGeneration.current += 1;
    };
  }, [load]);

  useEffect(() => {
    if (!selectedId) {
      detailGeneration.current += 1;
      queueMicrotask(() => {
        setDetail(null);
        setConfirmDelete(false);
      });
      return;
    }
    const generation = detailGeneration.current + 1;
    detailGeneration.current = generation;
    queueMicrotask(() => setConfirmDelete(false));
    void apiClient
      .request<MemoryDetail>(`/api/v1/memories/${selectedId}`)
      .then((result) => {
        if (
          detailGeneration.current !== generation ||
          result.memory.id !== selectedId
        )
          return;
        setDetail(result);
        setContent(result.memory.content);
        setValue(result.memory.value);
      })
      .catch((error) => {
        if (detailGeneration.current !== generation) return;
        setFeedback(safeError(error));
      });
  }, [selectedId]);

  async function decide(
    suggestion: MemorySuggestion,
    decision: "confirmed" | "rejected",
  ) {
    if (!csrf) return;
    const generation = actionGeneration.current + 1;
    actionGeneration.current = generation;
    setSaving(true);
    setFeedback("");
    try {
      await apiClient.request(
        `/api/v1/memory-suggestions/${suggestion.id}/decision`,
        {
          method: "POST",
          csrfToken: csrf,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            idempotency_key: operationKey(`suggestion-${suggestion.id}`),
            decision,
          }),
        },
      );
      if (
        actionGeneration.current !== generation ||
        !suggestions.some((item) => item.id === suggestion.id)
      )
        return;
      setSuggestions((items) =>
        items.filter((item) => item.id !== suggestion.id),
      );
      setFeedback(
        decision === "confirmed"
          ? "已确认。它会从下一次计划开始生效。"
          : "已拒绝。相同证据不会再次询问。",
      );
      await load();
    } catch (error) {
      if (actionGeneration.current !== generation) return;
      setFeedback(safeError(error));
      if (error instanceof ApiError && error.code === "conflict") await load();
    } finally {
      if (actionGeneration.current === generation) setSaving(false);
    }
  }

  async function patchMemory(
    memory: Memory,
    patch: {
      content: string | null;
      value: string | null;
      enabled: boolean | null;
    },
  ) {
    if (!csrf) return;
    const generation = actionGeneration.current + 1;
    actionGeneration.current = generation;
    const identity = `${memory.id}:${memory.version}`;
    setSaving(true);
    setFeedback("");
    try {
      const result = await apiClient.request<MemoryDetail>(
        `/api/v1/memories/${memory.id}`,
        {
          method: "PATCH",
          csrfToken: csrf,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            idempotency_key: operationKey(`memory-${identity}`),
            expected_version: memory.version,
            ...patch,
            expires_at: null,
            change_expiry: false,
          }),
        },
      );
      if (
        actionGeneration.current !== generation ||
        selectedId !== memory.id ||
        detail?.memory.version !== memory.version
      )
        return;
      setDetail(result);
      setMemories((items) =>
        items.map((item) => (item.id === memory.id ? result.memory : item)),
      );
      setFeedback(patch.enabled === false ? "记忆已停用。" : "记忆已更新。");
    } catch (error) {
      if (actionGeneration.current !== generation) return;
      setFeedback(safeError(error));
      if (error instanceof ApiError && error.code === "conflict") await load();
    } finally {
      if (actionGeneration.current === generation) setSaving(false);
    }
  }

  async function removeMemory(memory: Memory) {
    if (!csrf) return;
    const generation = actionGeneration.current + 1;
    actionGeneration.current = generation;
    setSaving(true);
    try {
      await apiClient.request(`/api/v1/memories/${memory.id}`, {
        method: "DELETE",
        csrfToken: csrf,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          idempotency_key: operationKey(`delete-${memory.id}-${memory.version}`),
          expected_version: memory.version,
        }),
      });
      if (
        actionGeneration.current !== generation ||
        selectedId !== memory.id ||
        detail?.memory.version !== memory.version
      )
        return;
      setMemories((items) => items.filter((item) => item.id !== memory.id));
      setSelectedId(null);
      setFeedback("记忆已删除；下一次计划不会再使用它。");
    } catch (error) {
      if (actionGeneration.current !== generation) return;
      setFeedback(safeError(error));
      if (error instanceof ApiError && error.code === "conflict") await load();
    } finally {
      if (actionGeneration.current === generation) setSaving(false);
    }
  }

  function submitEdit(event: FormEvent) {
    event.preventDefault();
    if (!detail || !content.trim() || !value.trim()) return;
    void patchMemory(detail.memory, {
      content: content.trim(),
      value: value.trim(),
      enabled: null,
    });
  }

  return (
    <div className="me-page">
      <header className="me-hero">
        <div>
          <p className="page-eyebrow">Memory & data</p>
          <h1 className="page-title">我的</h1>
          <p className="page-description">
            你决定拾光记住什么。只有已确认、有效且未停用的记忆会影响新计划。
          </p>
        </div>
        <div className="memory-count" aria-label={`${memories.length} 条记忆`}>
          <strong>{memories.length}</strong>
          <span>条已确认记忆</span>
        </div>
      </header>

      {feedback ? (
        <p className="me-feedback" role="status">
          {feedback}
        </p>
      ) : null}

      {loadState === "loading" ? (
        <section className="me-state" aria-live="polite">
          正在整理你的记忆…
        </section>
      ) : null}
      {loadState === "error" ? (
        <section className="me-state">
          <button type="button" onClick={() => void load()}>
            重新加载
          </button>
        </section>
      ) : null}

      {loadState === "ready" ? (
        <>
          <section className="memory-section" aria-labelledby="suggestion-title">
            <div className="section-heading">
              <div>
                <p className="page-eyebrow">待你决定</p>
                <h2 id="suggestion-title">记忆建议</h2>
              </div>
              <span>{suggestions.length}</span>
            </div>
            {suggestions.length ? (
              <div className="suggestion-list">
                {suggestions.map((suggestion) => (
                  <article className="suggestion-card" key={suggestion.id}>
                    <span className="memory-type">
                      {memoryTypeLabels[suggestion.memory_type]}
                    </span>
                    <h3>{suggestion.content}</h3>
                    <p>{suggestion.evidence_summary}</p>
                    <small>未经确认，不会进入计划</small>
                    <div className="memory-actions">
                      <button
                        className="primary-button"
                        type="button"
                        disabled={saving}
                        onClick={() => void decide(suggestion, "confirmed")}
                      >
                        确认记住
                      </button>
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() => void decide(suggestion, "rejected")}
                      >
                        这次不记
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="memory-empty">目前没有待确认建议。</p>
            )}
          </section>

          <div className="memory-workspace">
            <section className="memory-section" aria-labelledby="memory-title">
              <div className="section-heading">
                <div>
                  <p className="page-eyebrow">长期记忆</p>
                  <h2 id="memory-title">记忆中心</h2>
                </div>
              </div>
              {memories.length ? (
                <div className="memory-list">
                  {memories.map((memory) => (
                    <button
                      className={`memory-row${selectedId === memory.id ? " selected" : ""}`}
                      type="button"
                      key={memory.id}
                      aria-pressed={selectedId === memory.id}
                      onClick={() => {
                        actionGeneration.current += 1;
                        setSaving(false);
                        setSelectedId(memory.id);
                      }}
                    >
                      <span className="memory-type">
                        {memoryTypeLabels[memory.type]}
                      </span>
                      <strong>{memory.content}</strong>
                      <small>
                        {memory.disabled_at
                          ? "已停用"
                          : `最近使用：${formatTime(memory.last_used_at)}`}
                      </small>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="memory-empty">
                  还没有长期记忆。拾光不会自行确认推断。
                </p>
              )}
            </section>

            <section className="memory-detail-card" aria-labelledby="detail-title">
              {detail ? (
                <>
                  <div className="section-heading">
                    <div>
                      <p className="page-eyebrow">可追溯、可控制</p>
                      <h2 id="detail-title">记忆详情</h2>
                    </div>
                    <span>{detail.memory.disabled_at ? "已停用" : "生效中"}</span>
                  </div>
                  <form className="memory-edit-form" onSubmit={submitEdit}>
                    <label>
                      记忆内容
                      <textarea
                        name="memory_content"
                        value={content}
                        maxLength={500}
                        onChange={(event) => setContent(event.target.value)}
                      />
                    </label>
                    <label>
                      结构化值
                      <input
                        name="memory_value"
                        value={value}
                        maxLength={100}
                        onChange={(event) => setValue(event.target.value)}
                      />
                    </label>
                    <button
                      className="primary-button"
                      type="submit"
                      disabled={saving || !content.trim() || !value.trim()}
                    >
                      保存修改
                    </button>
                  </form>
                  <dl className="memory-provenance">
                    <div>
                      <dt>来源</dt>
                      <dd>{detail.memory.source.summary}</dd>
                    </div>
                    <div>
                      <dt>最近使用</dt>
                      <dd>{formatTime(detail.memory.last_used_at)}</dd>
                    </div>
                    <div>
                      <dt>有效期</dt>
                      <dd>
                        {detail.memory.expires_at
                          ? formatTime(detail.memory.expires_at)
                          : "长期有效，直至你停用或删除"}
                      </dd>
                    </div>
                  </dl>
                  <div className="usage-list">
                    <h3>影响过的计划</h3>
                    {detail.usages.length ? (
                      <ul>
                        {detail.usages.map((usage) => (
                          <li key={`${usage.memory_id}-${usage.plan_id}`}>
                            <strong>{usage.basis}</strong>
                            <span>
                              {formatTime(usage.used_at)} · {usage.plan_id}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>这条记忆还没有实际影响计划。</p>
                    )}
                  </div>
                  <div className="memory-actions danger-zone">
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() =>
                        void patchMemory(detail.memory, {
                          content: null,
                          value: null,
                          enabled: Boolean(detail.memory.disabled_at),
                        })
                      }
                    >
                      {detail.memory.disabled_at ? "重新启用" : "停用记忆"}
                    </button>
                    {confirmDelete ? (
                      <>
                        <span>确认永久删除？</span>
                        <button
                          className="danger-button"
                          type="button"
                          disabled={saving}
                          onClick={() => void removeMemory(detail.memory)}
                        >
                          确认删除
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmDelete(false)}
                        >
                          取消
                        </button>
                      </>
                    ) : (
                      <button
                        className="danger-button"
                        type="button"
                        disabled={saving}
                        onClick={() => setConfirmDelete(true)}
                      >
                        删除记忆
                      </button>
                    )}
                  </div>
                </>
              ) : (
                <div className="detail-placeholder">
                  <p className="page-eyebrow">透明可控</p>
                  <h2 id="detail-title">选择一条记忆查看详情</h2>
                  <p>这里会展示来源、最近使用时间，以及它实际影响过的计划。</p>
                </div>
              )}
            </section>
          </div>

          <section className="data-control-grid" aria-labelledby="data-title">
            <article className="data-control-card">
              <p className="page-eyebrow">Data export</p>
              <h2 id="data-title">导出我的数据</h2>
              <p>下载只属于当前用户的收藏、计划和已确认记忆 JSON。</p>
              <a
                className="primary-button export-link"
                href={apiClient.url("/api/v1/data-export.json")}
                download
              >
                下载私有 JSON
              </a>
            </article>
            <article className="data-control-card muted-card">
              <div className="section-heading">
                <div>
                  <p className="page-eyebrow">Reminders</p>
                  <h2>主动提醒</h2>
                </div>
                <span>尚未实现 · 已关闭</span>
              </div>
              <p>当前版本不会主动发消息，也没有后台提醒任务。</p>
              <button type="button" disabled aria-disabled="true">
                提醒保持关闭
              </button>
            </article>
          </section>
        </>
      ) : null}
    </div>
  );
}
