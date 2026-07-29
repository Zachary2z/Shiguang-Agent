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
  memory_type: MemoryType | null;
  content: string;
  value: string | null;
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

type SuggestionMemoryDraft = {
  memory_type: Exclude<MemoryType, "usual_area"> | "";
  content: string;
  value: string;
};

type WriteAttempt = {
  identity: string;
  payload: string;
  key: string;
};

function SuggestionCard({
  suggestion,
  saving,
  onDecision,
}: {
  suggestion: MemorySuggestion;
  saving: boolean;
  onDecision: (
    suggestion: MemorySuggestion,
    decision: "confirmed" | "rejected",
    draft?: SuggestionMemoryDraft,
  ) => Promise<void>;
}) {
  const [draft, setDraft] = useState<SuggestionMemoryDraft>({
    memory_type:
      suggestion.memory_type === "usual_area"
        ? ""
        : suggestion.memory_type ?? "",
    content: suggestion.content,
    value: suggestion.value ?? "",
  });
  const canConfirm = Boolean(
    draft.memory_type && draft.content.trim() && draft.value.trim(),
  );

  return (
    <article className="suggestion-card">
      <span className="memory-type">
        {suggestion.memory_type ? "结构化证据候选" : "中性证据候选"}
      </span>
      <h3>{suggestion.content}</h3>
      <p>{suggestion.evidence_summary}</p>
      <small>未经确认，不会进入计划。请明确要保存的长期含义。</small>
      <form
        className="memory-edit-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (canConfirm) void onDecision(suggestion, "confirmed", draft);
        }}
      >
        <label>
          记忆类型
          <select
            name={`suggestion_type_${suggestion.id}`}
            value={draft.memory_type}
            onChange={(event) => {
              const memoryType = event.target
                .value as SuggestionMemoryDraft["memory_type"];
              setDraft((current) => ({
                ...current,
                memory_type: memoryType,
                value: memoryType === "pace_preference" ? "balanced" : "",
              }));
            }}
          >
            <option value="">请选择</option>
            <option value="positive_preference">喜欢</option>
            <option value="negative_preference">避开</option>
            <option value="pace_preference">节奏</option>
          </select>
        </label>
        <label>
          要记住的内容
          <textarea
            value={draft.content}
            maxLength={500}
            onChange={(event) =>
              setDraft((current) => ({ ...current, content: event.target.value }))
            }
          />
        </label>
        <label>
          结构化值
          {draft.memory_type === "pace_preference" ? (
            <select
              value={draft.value}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  value: event.target.value,
                }))
              }
            >
              <option value="relaxed">轻松</option>
              <option value="balanced">均衡</option>
              <option value="packed">紧凑</option>
            </select>
          ) : (
            <input
              value={draft.value}
              maxLength={100}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  value: event.target.value,
                }))
              }
            />
          )}
        </label>
        <div className="memory-actions">
          <button
            className="primary-button"
            type="submit"
            disabled={saving || !canConfirm}
          >
            确认记住
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => void onDecision(suggestion, "rejected")}
          >
            这次不记
          </button>
        </div>
      </form>
    </article>
  );
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
  const [areaKind, setAreaKind] = useState<"district" | "label">("district");
  const [areaName, setAreaName] = useState("");
  const [feedback, setFeedback] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const loadGeneration = useRef(0);
  const detailGeneration = useRef(0);
  const actionGeneration = useRef(0);
  const csrfRef = useRef<string | null>(null);
  const selectedIdRef = useRef<string | null>(null);
  const writeAttempt = useRef<WriteAttempt | null>(null);

  const idempotencyKey = useCallback((identity: string, payload: object) => {
    const serialized = JSON.stringify(payload);
    if (
      writeAttempt.current?.identity === identity &&
      writeAttempt.current.payload === serialized
    ) {
      return writeAttempt.current.key;
    }
    const key = `${identity}-${crypto.randomUUID()}`;
    writeAttempt.current = { identity, payload: serialized, key };
    return key;
  }, []);

  const completeAttempt = useCallback((key: string) => {
    if (writeAttempt.current?.key === key) writeAttempt.current = null;
  }, []);

  const loadDetail = useCallback(async (memoryId: string) => {
    const generation = detailGeneration.current + 1;
    detailGeneration.current = generation;
    try {
      const result = await apiClient.request<MemoryDetail>(
        `/api/v1/memories/${memoryId}`,
      );
      if (
        detailGeneration.current !== generation ||
        selectedIdRef.current !== memoryId ||
        result.memory.id !== memoryId
      )
        return;
      setDetail(result);
      setContent(result.memory.content);
      setValue(result.memory.value);
      if (result.memory.type === "usual_area") {
        try {
          const area = JSON.parse(result.memory.value) as {
            districts?: string[];
            labels?: string[];
          };
          const district = area.districts?.[0];
          setAreaKind(district ? "district" : "label");
          setAreaName(district ?? area.labels?.[0] ?? "");
        } catch {
          setAreaKind("district");
          setAreaName("");
        }
      }
    } catch (error) {
      if (
        detailGeneration.current !== generation ||
        selectedIdRef.current !== memoryId
      )
        return;
      setFeedback(safeError(error));
    }
  }, []);

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
    selectedIdRef.current = selectedId;
    if (!selectedId) {
      detailGeneration.current += 1;
      queueMicrotask(() => {
        setDetail(null);
        setConfirmDelete(false);
      });
      return;
    }
    queueMicrotask(() => {
      setConfirmDelete(false);
      void loadDetail(selectedId);
    });
  }, [loadDetail, selectedId]);

  async function decide(
    suggestion: MemorySuggestion,
    decision: "confirmed" | "rejected",
    draft?: SuggestionMemoryDraft,
  ) {
    if (!csrf) return;
    const generation = actionGeneration.current + 1;
    actionGeneration.current = generation;
    setSaving(true);
    setFeedback("");
    const decisionFields =
      decision === "confirmed"
        ? {
            memory_type: draft?.memory_type || null,
            content: draft?.content.trim() || null,
            value: draft?.value.trim() || null,
          }
        : {};
    const payload = { decision, ...decisionFields };
    const key = idempotencyKey(`suggestion-${suggestion.id}`, payload);
    try {
      await apiClient.request(
        `/api/v1/memory-suggestions/${suggestion.id}/decision`,
        {
          method: "POST",
          csrfToken: csrf,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            idempotency_key: key,
            ...payload,
          }),
        },
      );
      completeAttempt(key);
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
      area?: { districts: string[]; labels: string[] } | null;
    },
  ) {
    if (!csrf) return;
    const generation = actionGeneration.current + 1;
    actionGeneration.current = generation;
    setSaving(true);
    setFeedback("");
    const payload = {
      expected_version: memory.version,
      ...patch,
      expires_at: null,
      change_expiry: false,
    };
    const key = idempotencyKey(`memory-${memory.id}`, payload);
    try {
      const result = await apiClient.request<MemoryDetail>(
        `/api/v1/memories/${memory.id}`,
        {
          method: "PATCH",
          csrfToken: csrf,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            idempotency_key: key,
            ...payload,
          }),
        },
      );
      completeAttempt(key);
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
      if (error instanceof ApiError && error.code === "conflict") {
        await Promise.all([load(), loadDetail(memory.id)]);
      }
    } finally {
      if (actionGeneration.current === generation) setSaving(false);
    }
  }

  async function removeMemory(memory: Memory) {
    if (!csrf) return;
    const generation = actionGeneration.current + 1;
    actionGeneration.current = generation;
    setSaving(true);
    const payload = { expected_version: memory.version };
    const key = idempotencyKey(`delete-${memory.id}`, payload);
    try {
      await apiClient.request(`/api/v1/memories/${memory.id}`, {
        method: "DELETE",
        csrfToken: csrf,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          idempotency_key: key,
          ...payload,
        }),
      });
      completeAttempt(key);
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
      if (error instanceof ApiError && error.code === "conflict") {
        await Promise.all([load(), loadDetail(memory.id)]);
      }
    } finally {
      if (actionGeneration.current === generation) setSaving(false);
    }
  }

  function submitEdit(event: FormEvent) {
    event.preventDefault();
    if (!detail) return;
    if (detail.memory.type === "usual_area") {
      if (!areaName.trim()) return;
      void patchMemory(detail.memory, {
        content: null,
        value: null,
        enabled: null,
        area:
          areaKind === "district"
            ? { districts: [areaName.trim()], labels: [] }
            : { districts: [], labels: [areaName.trim()] },
      });
      return;
    }
    if (!content.trim() || !value.trim()) return;
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
                  <SuggestionCard
                    key={suggestion.id}
                    suggestion={suggestion}
                    saving={saving}
                    onDecision={decide}
                  />
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
                        selectedIdRef.current = memory.id;
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
                    {detail.memory.type === "usual_area" ? (
                      <>
                        <p role="note">
                          这里只保存区级或商圈级粗区域，不接受地址、坐标或具体地点。
                        </p>
                        <label>
                          区域类型
                          <select
                            name="usual_area_kind"
                            value={areaKind}
                            onChange={(event) =>
                              setAreaKind(event.target.value as "district" | "label")
                            }
                          >
                            <option value="district">行政区</option>
                            <option value="label">商圈或粗区域</option>
                          </select>
                        </label>
                        <label>
                          常用区域
                          <input
                            name="usual_area_name"
                            value={areaName}
                            maxLength={40}
                            onChange={(event) => setAreaName(event.target.value)}
                            placeholder="例如：南山区、大学城附近"
                          />
                        </label>
                      </>
                    ) : null}
                    {detail.memory.type !== "usual_area" ? (
                      <>
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
                      </>
                    ) : null}
                    <button
                      className="primary-button"
                      type="submit"
                      disabled={
                        saving ||
                        (detail.memory.type === "usual_area"
                          ? !areaName.trim()
                          : !content.trim() || !value.trim())
                      }
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
