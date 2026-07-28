"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ApiError, apiClient } from "@/lib/api-client";
import { sseClient, type SseEvent } from "@/lib/sse-client";

type DemoSession = { csrf_token: string };
type PlanStatus =
  | "generating"
  | "waiting_approval"
  | "draft"
  | "confirmed"
  | "superseded"
  | "failed"
  | "cancelled";
type PlanItem = {
  title: string;
  start_at: string;
  end_at: string;
  visit_duration_seconds: number;
  inbound_route: {
    duration_seconds: number;
    distance_meters: number;
    transport_mode: string;
  };
  price_amount: string | null;
  price_currency: string | null;
  source: { kind: "collection_derived" | "external_place"; source_label: string | null };
  selection_reason: string;
  risks: string[];
};
type PlanOption = {
  role: "main" | "alternative";
  items: PlanItem[];
  total_cost_amount: string | null;
  total_cost_currency: string | null;
  risks: string[];
};
type Plan = {
  id: string;
  root_plan_id: string;
  parent_plan_id: string | null;
  version: number;
  status: PlanStatus;
  constraints: {
    start_at: string;
    end_at: string;
    area_districts: string[];
    area_labels: string[];
    budget: string | null;
    pace: "relaxed" | "balanced" | "packed";
    transport_modes: string[];
    include: string[];
    exclude: string[];
    collection_only: boolean;
  };
  adjustment_text: string | null;
  draft: { options: PlanOption[]; exclusions: unknown[] } | null;
  trace_id: string;
  events_url: `/${string}`;
  result_url: `/${string}`;
  error_code: string | null;
  is_current_version: boolean;
  versions: Array<{
    id: string;
    version: number;
    status: PlanStatus;
    adjustment_text: string | null;
  }>;
  approval: {
    id: string;
    display_text: string;
    status: "pending" | "approved" | "rejected" | "expired";
    expires_at: string;
  } | null;
};
type Accepted = {
  plan_id: string;
  trace_id: string;
  events_url: `/${string}`;
  result_url: `/${string}`;
};
type AdjustmentAccepted = {
  base_plan_id: string;
  trace_id: string;
  events_url: `/${string}`;
};
type PlanList = { items: Plan[] };
type ApprovalDecision = {
  trace_id: string | null;
  events_url: `/${string}` | null;
  result_url: `/${string}`;
};
type Phase =
  | "recovering"
  | "editing"
  | "reviewing"
  | "submitting"
  | "following"
  | "ready"
  | "waiting"
  | "failed";
type RunData = { summary?: { stage?: string; status?: string; error_code?: string } };

const paceLabels = { relaxed: "松弛", balanced: "适中", packed: "紧凑" };
const transportLabels: Record<string, string> = {
  walking: "步行",
  cycling: "骑行",
  transit: "公共交通",
  driving: "驾车",
};

function localInput(offsetHours: number) {
  const value = new Date(Date.now() + offsetHours * 3_600_000);
  value.setMinutes(Math.ceil(value.getMinutes() / 15) * 15, 0, 0);
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function messageFor(error: unknown) {
  if (!(error instanceof ApiError)) return "计划暂时没有完成，请稍后重试。";
  const messages: Partial<Record<ApiError["code"], string>> = {
    aborted: "已取消这次操作。",
    conflict: "计划版本已经更新，请读取最新版本后再试。",
    network_error: "网络连接中断，请重试。",
    timeout: "等待超时，稍后可从权威状态继续。",
    unauthorized: "会话已过期，请刷新页面。",
  };
  return messages[error.code] ?? "计划暂时没有完成，请稍后重试。";
}

function clock(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function distance(value: number) {
  return value >= 1000 ? `${(value / 1000).toFixed(1)} km` : `${value} m`;
}

export function PlansExperience() {
  const [session, setSession] = useState<DemoSession | null>(null);
  const [phase, setPhase] = useState<Phase>("recovering");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [startAt, setStartAt] = useState(() => localInput(24));
  const [endAt, setEndAt] = useState(() => localInput(32));
  const [district, setDistrict] = useState("南山区");
  const [areaLabel, setAreaLabel] = useState("海上世界");
  const [budget, setBudget] = useState("");
  const [pace, setPace] = useState<keyof typeof paceLabels>("balanced");
  const [transport, setTransport] = useState("transit");
  const [include, setInclude] = useState("");
  const [exclude, setExclude] = useState("");
  const [collectionOnly, setCollectionOnly] = useState(false);
  const [adjustment, setAdjustment] = useState("");
  const [optionIndex, setOptionIndex] = useState(0);
  const [feedback, setFeedback] = useState("");
  const [stage, setStage] = useState("正在读取计划");
  const [dirty, setDirty] = useState(false);
  const generation = useRef(0);
  const requestController = useRef<AbortController | null>(null);
  const cancelSse = useRef<(() => void) | null>(null);

  const readPlan = useCallback(async (path: `/${string}`, owner: number) => {
    try {
      const authoritative = await apiClient.request<Plan>(path);
      if (generation.current !== owner) return;
      setPlan(authoritative);
      setOptionIndex(0);
      setPhase(
        authoritative.status === "waiting_approval"
          ? "waiting"
          : authoritative.status === "generating"
            ? "following"
            : authoritative.status === "failed" ||
                authoritative.status === "cancelled"
              ? "failed"
              : "ready",
      );
      setFeedback(
        authoritative.error_code
          ? "这版计划未能生成。你可以修改条件后重新生成。"
          : "",
      );
    } catch (error) {
      if (generation.current !== owner) return;
      setPhase("failed");
      setFeedback(messageFor(error));
    }
  }, []);

  const follow = useCallback(
    (
      accepted: Accepted,
      owner: number,
      resolveResult?: (errorCode: string | undefined) => void,
    ) => {
      cancelSse.current?.();
      setPhase("following");
      let resultResolved = false;
      const resolveOnce = (errorCode: string | undefined) => {
        if (resultResolved) return;
        resultResolved = true;
        if (resolveResult) resolveResult(errorCode);
        else void readPlan(accepted.result_url, owner);
      };
      const connection = sseClient.connect<RunData>({
        path: accepted.events_url,
        maxReconnectAttempts: 2,
        onEvent: (event: SseEvent<RunData>) => {
          if (generation.current !== owner) return;
          const next = event.data.summary?.stage;
          if (next === "collections.filtered") setStage("正在筛选可用收藏");
          if (next === "plan.ready") setStage("正在整理时间光轨");
          if (event.event === "approval.required") {
            void readPlan(accepted.result_url, owner);
          }
          if (event.event === "run.completed" || event.event === "run.failed") {
            resolveOnce(event.data.summary?.error_code);
          }
        },
        onStateChange: (state) => {
          if (generation.current !== owner) return;
          if (state === "disconnected") setFeedback("进度连接中断，正在恢复。");
          if (state === "error") resolveOnce(undefined);
        },
      });
      cancelSse.current = connection.cancel;
      void connection.closed.catch(() => {
        if (generation.current === owner) {
          resolveOnce(undefined);
        }
      });
    },
    [readPlan],
  );

  useEffect(() => {
    const owner = ++generation.current;
    void (async () => {
      try {
        const activeSession = await apiClient.request<DemoSession>(
          "/api/v1/demo/sessions",
          { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
        );
        if (generation.current !== owner) return;
        setSession(activeSession);
        const list = await apiClient.request<PlanList>("/api/v1/plans");
        if (generation.current !== owner) return;
        const latest = list.items[0];
        if (!latest) {
          setPhase("editing");
          return;
        }
        setPlan(latest);
        if (latest.status === "generating") {
          follow(
            {
              plan_id: latest.id,
              trace_id: latest.trace_id,
              events_url: latest.events_url,
              result_url: latest.result_url,
            },
            owner,
          );
        } else {
          setPhase(
            latest.status === "waiting_approval"
              ? "waiting"
              : latest.status === "failed" || latest.status === "cancelled"
                ? "failed"
                : "ready",
          );
          setFeedback(
            latest.error_code
              ? "这版计划未能生成。你可以修改条件后重新生成。"
              : "",
          );
        }
      } catch (error) {
        if (generation.current !== owner) return;
        setPhase("failed");
        setFeedback(messageFor(error));
      }
    })();
    return () => {
      generation.current += 1;
      requestController.current?.abort();
      cancelSse.current?.();
    };
  }, [follow]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const constraints = useMemo(
    () => ({
      start_at: new Date(startAt).toISOString(),
      end_at: new Date(endAt).toISOString(),
      area: { districts: district.trim() ? [district.trim()] : [], labels: areaLabel.trim() ? [areaLabel.trim()] : [] },
      budget: budget.trim() || null,
      pace,
      transport_modes: [transport],
      include: include.trim() ? [include.trim()] : [],
      exclude: exclude.trim() ? [exclude.trim()] : [],
      collection_only: collectionOnly,
    }),
    [areaLabel, budget, collectionOnly, district, endAt, exclude, include, pace, startAt, transport],
  );

  function beginReview(event: FormEvent) {
    event.preventDefault();
    if (!startAt || !endAt || (!district.trim() && !areaLabel.trim())) {
      setFeedback("请补全时间和活动范围。");
      return;
    }
    if (new Date(endAt) <= new Date(startAt)) {
      setFeedback("结束时间需要晚于开始时间。");
      return;
    }
    setFeedback("");
    setPhase("reviewing");
  }

  async function generate() {
    if (!session) return;
    const owner = ++generation.current;
    setPhase("submitting");
    setFeedback("");
    setStage("正在创建计划任务");
    const controller = new AbortController();
    requestController.current = controller;
    try {
      const accepted = await apiClient.request<Accepted>("/api/v1/plans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idempotency_key: crypto.randomUUID(), ...constraints }),
        csrfToken: session.csrf_token,
        signal: controller.signal,
      });
      if (generation.current !== owner) return;
      setDirty(false);
      follow(accepted, owner);
    } catch (error) {
      if (generation.current !== owner) return;
      setPhase("failed");
      setFeedback(messageFor(error));
    } finally {
      requestController.current = null;
    }
  }

  async function adjustPlan(event: FormEvent) {
    event.preventDefault();
    if (!session || !plan || !adjustment.trim()) return;
    const owner = ++generation.current;
    setPhase("submitting");
    setStage("正在创建新版本");
    try {
      const accepted = await apiClient.request<AdjustmentAccepted>(
        `/api/v1/plans/${plan.id}/adjustments`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            idempotency_key: crypto.randomUUID(),
            instruction: adjustment.trim(),
          }),
          csrfToken: session.csrf_token,
        },
      );
      if (generation.current !== owner) return;
      setAdjustment("");
      follow(
        {
          plan_id: accepted.base_plan_id,
          trace_id: accepted.trace_id,
          events_url: accepted.events_url,
          result_url: `/api/v1/plans/${accepted.base_plan_id}`,
        },
        owner,
        (errorCode) => {
          void (async () => {
            const base = await apiClient.request<Plan>(
              `/api/v1/plans/${accepted.base_plan_id}`,
            );
            if (generation.current !== owner) return;
            const latest = base.versions.at(-1);
            await readPlan(
              latest && latest.id !== base.id
                ? `/api/v1/plans/${latest.id}`
                : `/api/v1/plans/${base.id}`,
              owner,
            );
            if (
              generation.current === owner &&
              errorCode === "PLAN_ADJUSTMENT_UNSUPPORTED"
            ) {
              setPhase("ready");
              setFeedback(
                "暂不支持直接调整精确地点，请新建计划修改活动范围。",
              );
            } else if (generation.current === owner && errorCode) {
              setPhase("ready");
              setFeedback("这次调整未完成，已保留当前版本，请稍后重试。");
            }
          })();
        },
      );
    } catch (error) {
      if (generation.current !== owner) return;
      setPhase("ready");
      setFeedback(messageFor(error));
    }
  }

  async function decideApproval(approved: boolean) {
    if (!session || !plan?.approval) return;
    const owner = ++generation.current;
    setPhase("submitting");
    try {
      const decision = await apiClient.request<ApprovalDecision>(
        `/api/v1/approvals/${plan.approval.id}/decision`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision: approved ? "approved" : "rejected" }),
          csrfToken: session.csrf_token,
        },
      );
      if (generation.current !== owner) return;
      if (decision.trace_id && decision.events_url) {
        follow(
          {
            plan_id: plan.id,
            trace_id: decision.trace_id,
            events_url: decision.events_url,
            result_url: decision.result_url,
          },
          owner,
        );
      } else {
        await readPlan(decision.result_url, owner);
      }
    } catch (error) {
      if (generation.current !== owner) return;
      setPhase("waiting");
      setFeedback(messageFor(error));
    }
  }

  async function confirmPlan() {
    if (!session || !plan) return;
    const owner = ++generation.current;
    setPhase("submitting");
    try {
      const result = await apiClient.request<{ plan: Plan }>(
        `/api/v1/plans/${plan.id}/confirm`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ idempotency_key: crypto.randomUUID() }),
          csrfToken: session.csrf_token,
        },
      );
      if (generation.current !== owner) return;
      setPlan(result.plan);
      setPhase("ready");
      setFeedback("已确认这一版本。只有已确认计划才可进入后续执行。");
    } catch (error) {
      if (generation.current !== owner) return;
      setPhase("ready");
      setFeedback(messageFor(error));
    }
  }

  async function switchVersion(id: string) {
    const owner = ++generation.current;
    cancelSse.current?.();
    setPhase("recovering");
    await readPlan(`/api/v1/plans/${id}`, owner);
  }

  function cancelOperation() {
    generation.current += 1;
    requestController.current?.abort();
    cancelSse.current?.();
    setPhase(plan ? "ready" : "editing");
    setFeedback("已停止等待；后台权威状态会在下次进入时恢复。");
  }

  function startNewPlan() {
    generation.current += 1;
    requestController.current?.abort();
    cancelSse.current?.();
    setPlan(null);
    setAdjustment("");
    setFeedback("");
    setDirty(false);
    setPhase("editing");
  }

  const option = plan?.draft?.options[optionIndex];
  const busy = ["recovering", "submitting", "following"].includes(phase);

  return (
    <section className="plans-page" aria-busy={busy}>
      <header className="plans-heading">
        <div>
          <p className="eyebrow">Plans · Shenzhen</p>
          <h1>把一天，排成一条光轨</h1>
          <p>先确认边界，再让收藏成为今天的主角。</p>
        </div>
        {plan && (
          <div className="plan-heading-actions">
            <span className={`plan-status ${plan.status}`}>V{plan.version} · {plan.status === "confirmed" ? "已确认" : plan.is_current_version ? "当前版本" : "历史版本"}</span>
            {plan.draft && (
              <button type="button" onClick={startNewPlan}>新建计划</button>
            )}
          </div>
        )}
      </header>

      {(phase === "editing" || phase === "reviewing") && (
        <div className="plan-compose">
          <form className="plan-form" onSubmit={beginReview}>
            <div className="plan-section-title"><span>01</span><h2>时间与范围</h2></div>
            <div className="plan-form-grid">
              <label>开始时间<input name="start_at" type="datetime-local" value={startAt} onChange={(event) => { setStartAt(event.target.value); setDirty(true); }} autoComplete="off" required /></label>
              <label>结束时间<input name="end_at" type="datetime-local" value={endAt} onChange={(event) => { setEndAt(event.target.value); setDirty(true); }} autoComplete="off" required /></label>
              <label>行政区<input name="district" value={district} onChange={(event) => { setDistrict(event.target.value); setDirty(true); }} autoComplete="address-level2" placeholder="例如：南山区" /></label>
              <label>活动范围<input name="area_label" value={areaLabel} onChange={(event) => { setAreaLabel(event.target.value); setDirty(true); }} autoComplete="off" placeholder="例如：海上世界" /></label>
            </div>
            <div className="plan-section-title"><span>02</span><h2>可选偏好</h2></div>
            <div className="plan-form-grid">
              <label>预算（元，可留空）<input name="budget" type="number" min="0" step="0.01" value={budget} onChange={(event) => { setBudget(event.target.value); setDirty(true); }} inputMode="decimal" autoComplete="off" placeholder="费用未知也可以生成" /></label>
              <label>节奏<select name="pace" value={pace} onChange={(event) => { setPace(event.target.value as keyof typeof paceLabels); setDirty(true); }}><option value="relaxed">松弛</option><option value="balanced">适中</option><option value="packed">紧凑</option></select></label>
              <label>主要交通<select name="transport_mode" value={transport} onChange={(event) => { setTransport(event.target.value); setDirty(true); }}><option value="walking">步行</option><option value="cycling">骑行</option><option value="transit">公共交通</option><option value="driving">驾车</option></select></label>
              <label>希望包含<input name="include" value={include} onChange={(event) => { setInclude(event.target.value); setDirty(true); }} autoComplete="off" placeholder="例如：海边咖啡" /></label>
              <label>希望避开<input name="exclude" value={exclude} onChange={(event) => { setExclude(event.target.value); setDirty(true); }} autoComplete="off" placeholder="例如：大型商场" /></label>
              <label className="plan-check"><input name="collection_only" type="checkbox" checked={collectionOnly} onChange={(event) => { setCollectionOnly(event.target.checked); setDirty(true); }} /><span>只使用我的收藏</span></label>
            </div>
            <button className="primary-button plan-primary" type="submit">检查生成条件</button>
          </form>

          {phase === "reviewing" && (
            <aside className="constraint-card" aria-label="生成前条件确认">
              <p className="eyebrow">Ready to compose</p>
              <h2>确认这次出发</h2>
              <dl>
                <div><dt>时间</dt><dd>{clock(constraints.start_at)}—{clock(constraints.end_at)}</dd></div>
                <div><dt>范围</dt><dd>{[district, areaLabel].filter(Boolean).join(" · ")}</dd></div>
                <div><dt>预算</dt><dd>{budget ? `¥${budget}` : "未设置 · 费用未知会明确标记"}</dd></div>
                <div><dt>节奏 / 交通</dt><dd>{paceLabels[pace]} · {transportLabels[transport]}</dd></div>
                <div><dt>包含 / 避开</dt><dd>{include || "无指定"} / {exclude || "无指定"}</dd></div>
                <div><dt>地点来源</dt><dd>{collectionOnly ? "仅收藏" : "优先收藏；不足时先征求外部补充授权"}</dd></div>
              </dl>
              <div className="constraint-actions">
                <button type="button" onClick={() => setPhase("editing")}>返回修改</button>
                <button type="button" className="primary-button" onClick={() => void generate()}>确认并生成</button>
              </div>
            </aside>
          )}
        </div>
      )}

      {busy && (
        <div className="plan-progress" role="status">
          <span className="plan-orbit" aria-hidden="true" />
          <div><p className="eyebrow">Composing</p><h2>{stage}</h2><p>页面刷新或重新进入后，会继续读取后端权威状态。</p></div>
          <button type="button" onClick={cancelOperation}>停止等待</button>
        </div>
      )}

      {phase === "waiting" && plan?.approval && (
        <section className="approval-card" aria-labelledby="approval-title">
          <p className="eyebrow">Permission required</p>
          <h2 id="approval-title">收藏还不足以拼成完整计划</h2>
          <p>{plan.approval.display_text}</p>
          <p className="approval-note">外部地点会标记为“高德补充 · 未收藏”，确认计划也不会自动收藏它。</p>
          <div>
            <button type="button" onClick={() => void decideApproval(false)}>不允许，使用现有收藏</button>
            <button className="primary-button" type="button" onClick={() => void decideApproval(true)}>允许补充一次</button>
          </div>
        </section>
      )}

      {plan && plan.versions.length > 0 && ["ready", "failed"].includes(phase) && (
        <nav className="version-strip" aria-label="计划版本">
          {plan.versions.map((version) => (
            <button key={version.id} type="button" aria-current={version.id === plan.id ? "page" : undefined} onClick={() => void switchVersion(version.id)}>
              V{version.version}{version.status === "confirmed" ? " · 已确认" : version.status === "failed" || version.status === "cancelled" ? " · 失败" : ""}
            </button>
          ))}
        </nav>
      )}

      {plan?.draft && ["ready", "failed"].includes(phase) && (
        <>
          <div className="option-tabs" role="tablist" aria-label="计划方案">
            {plan.draft.options.map((candidate, index) => (
              <button key={`${candidate.role}-${index}`} type="button" role="tab" aria-selected={index === optionIndex} onClick={() => setOptionIndex(index)}>
                {candidate.role === "main" ? "主方案" : `备选 ${index}`}
              </button>
            ))}
          </div>
          {option && (
            <article className="plan-result">
              <header>
                <div><p className="eyebrow">{option.role === "main" ? "Main route" : "Alternative"}</p><h2>{option.items.map((item) => item.title).join(" → ")}</h2></div>
                <div className="cost-stamp"><span>预计费用</span><strong>{option.total_cost_amount === null ? "未知" : `¥${option.total_cost_amount}`}</strong></div>
              </header>
              <ol className="time-rail">
                {option.items.map((item, index) => (
                  <li key={`${item.title}-${item.start_at}`}>
                    <time>{clock(item.start_at)}</time>
                    <span className="rail-node" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                    <div className="rail-card">
                      <div className="rail-title"><h3>{item.title}</h3><span className={item.source.kind === "external_place" ? "source-external" : "source-collection"}>{item.source.kind === "external_place" ? item.source.source_label ?? "外部补充 · 未收藏" : "来自收藏"}</span></div>
                      <p>{clock(item.start_at)}—{clock(item.end_at)} · 停留 {Math.round(item.visit_duration_seconds / 60)} 分钟</p>
                      <p>抵达：{transportLabels[item.inbound_route.transport_mode] ?? item.inbound_route.transport_mode} · {Math.round(item.inbound_route.duration_seconds / 60)} 分钟 · {distance(item.inbound_route.distance_meters)}</p>
                      <p className="selection-reason">{item.selection_reason}</p>
                      {item.risks.length > 0 && <ul className="risk-list">{item.risks.map((risk) => <li key={risk}>{risk}</li>)}</ul>}
                    </div>
                  </li>
                ))}
              </ol>
              {option.risks.length > 0 && <p className="option-risk">出发前留意：{option.risks.join("；")}</p>}
            </article>
          )}
          {plan.is_current_version && plan.status !== "confirmed" && (
            <form className="adjust-card" onSubmit={adjustPlan}>
              <label htmlFor="plan-adjustment">想怎么调整？</label>
              <div><input id="plan-adjustment" name="instruction" value={adjustment} onChange={(event) => setAdjustment(event.target.value)} autoComplete="off" placeholder="例如：节奏轻松一点，预算改成 300" /><button type="submit" disabled={!adjustment.trim()}>生成新版本</button></div>
              <p>每次有效调整都会保留上一版，并创建不可变的新版本。</p>
            </form>
          )}
          <div className="plan-confirm-bar">
            <div><strong>{plan.status === "confirmed" ? "这一版已确认" : plan.is_current_version ? "确认当前版本" : "这是历史版本"}</strong><span>{plan.status === "confirmed" ? "已记录你的明确选择" : "未确认计划不会产生执行动作"}</span></div>
            <button className="primary-button" type="button" disabled={!plan.is_current_version || plan.status !== "draft"} onClick={() => void confirmPlan()}>{plan.status === "confirmed" ? "已确认" : "明确确认 V" + plan.version}</button>
          </div>
        </>
      )}

      {feedback && <p className="plan-feedback" role="status">{feedback}</p>}
      {phase === "failed" && !plan?.draft && (
        <div className="plan-empty"><h2>这一版没有生成结果</h2><p>{plan && plan.versions.length > 1 ? "可以从上方版本索引返回上一份计划，或新建独立计划。" : "修改条件后可以重新生成；不会自动重试或隐式确认。"}</p><button className="primary-button" type="button" onClick={startNewPlan}>新建计划</button></div>
      )}
    </section>
  );
}
