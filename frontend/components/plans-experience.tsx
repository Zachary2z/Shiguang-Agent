"use client";

import {
  type FormEvent,
  type MutableRefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { ShareManagement } from "@/components/share-management";
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
  | "cancelled"
  | "completed"
  | "partially_completed"
  | "not_completed";
type PlanItem = {
  title: string;
  start_at: string;
  end_at: string;
  visit_duration_seconds: number;
  inbound_route: {
    duration_seconds: number | null;
    distance_meters: number | null;
    transport_mode: string;
  };
  price_amount: string | null;
  price_currency: string | null;
  source: { kind: "collection_derived" | "external_place"; source_label: string | null };
  selection_reason_code:
    | "PRIMARY_STABLE_RANK"
    | "STABLE_ALTERNATIVE"
    | "AUXILIARY_FITS_KNOWN_ROUTE";
  selection_reason: string;
  risk_codes: PlanRiskCode[];
  risks: string[];
};
type PlanRiskCode =
  | "PRICE_UNKNOWN"
  | "BUDGET_UNVERIFIED"
  | "WEATHER_UNKNOWN"
  | "WEATHER_PROVIDER_FAILED"
  | "ROUTE_UNKNOWN"
  | "OPENING_HOURS_UNKNOWN";
type PlanOption = {
  role: "main" | "alternative";
  items: PlanItem[];
  total_cost_amount: string | null;
  total_cost_currency: string | null;
  risk_codes: PlanRiskCode[];
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
    pace_source: "user_request" | "system_default" | "memory_default";
    transport_modes: string[];
    include: string[];
    exclude: string[];
    collection_only: boolean;
  };
  adjustment_text: string | null;
  draft: {
    options: PlanOption[];
    exclusions: unknown[];
    weather_status?: "compatible" | "conflict" | "unknown" | "provider_failed" | null;
    weather_source?: string | null;
    weather_queried_at?: string | null;
    weather_summary?: string | null;
  } | null;
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
type CompletionStatus = "completed" | "partially_completed" | "not_completed";
type ExecutionItem = {
  id: string;
  title: string;
  start_at: string;
  end_at: string;
  address: string | null;
  collection_item_ids: string[];
  is_external: boolean;
  status: "pending" | "visited" | "not_visited";
  navigation_uri: string | null;
};
type FeedbackRecord = {
  id: string;
  revision: number;
  completion_status: CompletionStatus;
  reason: string | null;
  visited_plan_item_ids: string[];
  preference_suggestion: {
    content: string;
    memory_type: "positive_preference" | "negative_preference" | "pace_preference" | null;
    value: string | null;
    evidence_summary: string | null;
    confirmation_status: "pending";
  } | null;
};
type Execution = {
  plan_id: string;
  items: ExecutionItem[];
  feedback: FeedbackRecord | null;
};

type FeedbackAttempt = {
  fingerprint: string;
  key: string;
};
type MutationAttempt = {
  fingerprint: string;
  key: string;
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
const completionLabels: Partial<Record<PlanStatus, string>> = {
  confirmed: "已确认",
  completed: "已完成",
  partially_completed: "部分完成",
  not_completed: "未完成",
};
const selectionReasonLabels: Readonly<Record<PlanItem["selection_reason_code"], string>> = {
  PRIMARY_STABLE_RANK: "优先选择路线已知且排序稳定的收藏。",
  STABLE_ALTERNATIVE: "从其余可执行候选中选为稳定备选。",
  AUXILIARY_FITS_KNOWN_ROUTE: "停留和路线时间适合当前剩余窗口。",
};
const riskLabels: Readonly<Record<PlanRiskCode, string>> = {
  PRICE_UNKNOWN: "价格待确认。",
  BUDGET_UNVERIFIED: "价格确认前无法核验预算。",
  WEATHER_UNKNOWN: "天气情况待确认。",
  WEATHER_PROVIDER_FAILED: "天气信息暂时不可用。",
  ROUTE_UNKNOWN: "未提供精确起点，首段路线待确认。",
  OPENING_HOURS_UNKNOWN: "营业时间待确认。",
};
const weatherStatusLabels: Readonly<Record<string, string>> = {
  compatible: "天气条件适合",
  conflict: "天气条件可能不适合",
  unknown: "天气情况待确认",
  provider_failed: "天气信息暂时不可用",
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

function failureMessage(errorCode: string | null) {
  if (errorCode === null) return "";
  const messages: Record<string, string> = {
    ADD_COLLECTIONS: "当前没有可用于这次规划的收藏，请先补充并确认地点或活动信息。",
    CITY_UNCONFIRMED: "收藏的城市尚未确认，请先补充并确认城市。",
    CITY_MISMATCH: "现有收藏位于其他城市，当前计划只会使用已确认的深圳收藏。",
    LOCATION_UNCONFIRMED: "现有收藏的具体地点尚未确认，请先完成地点确认。",
    EVENT_TIME_UNKNOWN: "现有 Event 的具体开始和结束时间尚未确认，请先补充准确场次。",
    NO_INCLUDED_CANDIDATES: "当前没有符合时间、范围和状态要求的可规划收藏。",
    COLLECTION_ONLY: "当前只允许使用收藏，但现有收藏无法组成可执行计划。",
    EVENT_NOT_SEARCHABLE: "收藏中没有时间与地点均已确认的 Event；MVP 不会外部搜索活动。",
    PLACE_NOT_FOUND: "没有找到可靠的外部地点，请补充收藏或收窄地点要求。",
    PLACE_AMBIGUOUS: "外部地点仍有多个可能结果，请先确认具体地点。",
    ROUTE_FACTS_MISSING: "当前无法确认可执行路线，因此没有生成计划。",
    MAP_TIMEOUT: "地图查询超时，未伪造路线或地点；可稍后重试或只使用收藏。",
    MAP_RATE_LIMITED: "地图服务当前限流，未伪造计划结果；请稍后重试。",
    MAP_UNAVAILABLE: "地图服务暂时不可用，未伪造计划结果；请稍后重试。",
    MAP_INVALID_RESPONSE: "地图结果无法通过校验，未把不可靠地点加入计划。",
    NO_EXECUTABLE_DRAFT: "已知收藏和路线事实无法组成可执行计划，请调整条件。",
    NO_EXECUTABLE_OPTION: "没有候选能在当前连续时间和活动范围内完成。",
    POST_GENERATION_VALIDATION_FAILED: "候选方案未通过硬约束复核，因此没有保存伪成功计划。",
    PLAN_CONSTRAINTS_EXPIRED: "本次计划条件已经过期，请重新确认时间后生成。",
    PLAN_ADJUSTMENT_NOT_UNDERSTOOD: "没有理解这次调整，请换一种更明确的说法。",
    PLAN_ADJUSTMENT_UNSUPPORTED: "暂不支持直接调整精确地点，请新建计划修改活动范围。",
    STALE_VERSION: "计划版本已经更新，旧任务没有覆盖当前版本。",
    PROVIDER_TIMEOUT: "计划服务等待超时，未保存伪成功结果。",
    PROVIDER_AUTHENTICATION_FAILED: "计划服务配置不可用，请稍后再试。",
    PROVIDER_RATE_LIMITED: "计划服务当前限流，请稍后再试。",
    PLAN_PROVIDER_NOT_CONFIGURED: "计划 Provider 尚未配置，未生成替代或伪成功结果。",
    ROUTE_PROVIDER_FAILED: "路线 Provider 暂时失败，无法验证可执行路线。",
    WEATHER_PROVIDER_FAILED: "天气 Provider 暂时失败，无法验证计划条件。",
    AVAILABILITY_PROVIDER_FAILED: "营业状态 Provider 暂时失败，无法验证地点可用性。",
    BRANCH_PROVIDER_FAILED: "分店 Provider 暂时失败，无法确认可执行分店。",
    RUN_CANCELLED: "计划任务已取消，未保存未完成结果。",
  };
  return messages[errorCode] ?? "计划未完成，未保存未确认结果。";
}

function inputToIso(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

function keyForAttempt(
  attempt: MutableRefObject<MutationAttempt | null>,
  fingerprint: string,
) {
  if (attempt.current?.fingerprint !== fingerprint) {
    attempt.current = { fingerprint, key: crypto.randomUUID() };
  }
  return attempt.current.key;
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

function routeLabel(route: PlanItem["inbound_route"]) {
  if (route.duration_seconds === null) return "首段路线待确认（未提供精确起点）";
  const mode = transportLabels[route.transport_mode] ?? "其他交通方式";
  return `抵达：${mode} · ${Math.round(route.duration_seconds / 60)} 分钟 · ${distance(route.distance_meters ?? 0)}`;
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
  const [execution, setExecution] = useState<Execution | null>(null);
  const [feedbackMode, setFeedbackMode] = useState<CompletionStatus | null>(null);
  const [visitedItems, setVisitedItems] = useState<Set<string>>(new Set());
  const [incompleteReason, setIncompleteReason] = useState("");
  const [suggestPreference, setSuggestPreference] = useState(false);
  const [suggestionType, setSuggestionType] = useState<
    "positive_preference" | "negative_preference" | "pace_preference"
  >("positive_preference");
  const [suggestionContent, setSuggestionContent] = useState("");
  const [suggestionValue, setSuggestionValue] = useState("");
  const [suggestionEvidence, setSuggestionEvidence] = useState("");
  const [executionBusy, setExecutionBusy] = useState(false);
  const [stage, setStage] = useState("正在读取计划");
  const [dirty, setDirty] = useState(false);
  const [createRetryAvailable, setCreateRetryAvailable] = useState(false);
  const generation = useRef(0);
  const currentPlanId = useRef<string | null>(null);
  const requestController = useRef<AbortController | null>(null);
  const cancelSse = useRef<(() => void) | null>(null);
  const createAttempt = useRef<MutationAttempt | null>(null);
  const adjustmentAttempt = useRef<MutationAttempt | null>(null);
  const confirmationAttempt = useRef<MutationAttempt | null>(null);
  const feedbackAttempt = useRef<FeedbackAttempt | null>(null);

  const readPlan = useCallback(async (path: `/${string}`, owner: number) => {
    try {
      const authoritative = await apiClient.request<Plan>(path);
      if (generation.current !== owner) return;
      currentPlanId.current = authoritative.id;
      setPlan(authoritative);
      setExecution(null);
      setFeedbackMode(null);
      setOptionIndex(0);
      setPhase(
        authoritative.status === "waiting_approval"
          ? "waiting"
          : authoritative.status === "generating"
            ? "failed"
            : authoritative.status === "failed" ||
                authoritative.status === "cancelled"
              ? "failed"
              : "ready",
      );
      if (authoritative.status !== "generating") {
        createAttempt.current = null;
        adjustmentAttempt.current = null;
        setCreateRetryAvailable(false);
      }
      setFeedback(
        authoritative.status === "generating"
          ? "任务仍在后台处理。刷新权威状态可继续追踪，不会自动重复提交。"
          : failureMessage(authoritative.error_code),
      );
      return authoritative;
    } catch (error) {
      if (generation.current !== owner) return;
      setPhase("failed");
      setFeedback(messageFor(error));
      return undefined;
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
        currentPlanId.current = latest.id;
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
          createAttempt.current = null;
          adjustmentAttempt.current = null;
          setPhase(
            latest.status === "waiting_approval"
              ? "waiting"
              : latest.status === "failed" || latest.status === "cancelled"
                ? "failed"
                : "ready",
          );
          setFeedback(
            failureMessage(latest.error_code),
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
      currentPlanId.current = null;
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
      start_at: inputToIso(startAt),
      end_at: inputToIso(endAt),
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
    const fingerprint = JSON.stringify(constraints);
    const idempotencyKey = keyForAttempt(createAttempt, fingerprint);
    try {
      const accepted = await apiClient.request<Accepted>("/api/v1/plans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idempotency_key: idempotencyKey, ...constraints }),
        csrfToken: session.csrf_token,
        signal: controller.signal,
      });
      if (generation.current !== owner) return;
      setCreateRetryAvailable(false);
      setDirty(false);
      follow(accepted, owner);
    } catch (error) {
      if (generation.current !== owner) return;
      setCreateRetryAvailable(true);
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
    const instruction = adjustment.trim();
    const fingerprint = JSON.stringify({ plan_id: plan.id, instruction });
    const idempotencyKey = keyForAttempt(adjustmentAttempt, fingerprint);
    try {
      const accepted = await apiClient.request<AdjustmentAccepted>(
        `/api/v1/plans/${plan.id}/adjustments`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            idempotency_key: idempotencyKey,
            instruction,
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
              adjustmentAttempt.current = null;
              setPhase("ready");
              setFeedback(failureMessage(errorCode));
            } else if (generation.current === owner && errorCode) {
              adjustmentAttempt.current = null;
              setPhase("ready");
              setFeedback(failureMessage(errorCode));
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
    const idempotencyKey = keyForAttempt(
      confirmationAttempt,
      JSON.stringify({ plan_id: plan.id }),
    );
    try {
      const result = await apiClient.request<{ plan: Plan }>(
        `/api/v1/plans/${plan.id}/confirm`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ idempotency_key: idempotencyKey }),
          csrfToken: session.csrf_token,
        },
      );
      if (generation.current !== owner) return;
      currentPlanId.current = result.plan.id;
      confirmationAttempt.current = null;
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
    currentPlanId.current = id;
    requestController.current?.abort();
    cancelSse.current?.();
    confirmationAttempt.current = null;
    adjustmentAttempt.current = null;
    setExecutionBusy(false);
    setPhase("recovering");
    await readPlan(`/api/v1/plans/${id}`, owner);
  }

  function cancelOperation() {
    generation.current += 1;
    requestController.current?.abort();
    cancelSse.current?.();
    setPhase(plan?.status === "generating" ? "failed" : plan ? "ready" : "editing");
    setFeedback("已停止等待；后台权威状态会在下次进入时恢复。");
  }

  function startNewPlan() {
    generation.current += 1;
    currentPlanId.current = null;
    requestController.current?.abort();
    cancelSse.current?.();
    createAttempt.current = null;
    adjustmentAttempt.current = null;
    confirmationAttempt.current = null;
    setExecutionBusy(false);
    setPlan(null);
    setExecution(null);
    setFeedbackMode(null);
    setAdjustment("");
    setFeedback("");
    setDirty(false);
    setCreateRetryAvailable(false);
    setPhase("editing");
  }

  async function refreshAuthoritativeState() {
    if (!plan) return;
    const owner = ++generation.current;
    requestController.current?.abort();
    cancelSse.current?.();
    setPhase("recovering");
    setStage("正在读取后台权威状态");
    const authoritative = await readPlan(`/api/v1/plans/${plan.id}`, owner);
    if (
      generation.current === owner &&
      authoritative?.status === "generating"
    ) {
      follow(
        {
          plan_id: authoritative.id,
          trace_id: authoritative.trace_id,
          events_url: authoritative.events_url,
          result_url: authoritative.result_url,
        },
        owner,
      );
    }
  }

  const option = plan?.draft?.options[optionIndex];
  const busy = ["recovering", "submitting", "following"].includes(phase);
  const executable = plan !== null && [
    "confirmed",
    "completed",
    "partially_completed",
    "not_completed",
  ].includes(plan.status);
  const priorConfirmed = plan?.versions.filter((version) =>
    ["confirmed", "completed", "partially_completed", "not_completed"].includes(version.status),
  ).at(-1);

  async function loadExecution() {
    if (!plan) return;
    const planId = plan.id;
    const owner = ++generation.current;
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    setExecutionBusy(true);
    try {
      const loaded = await apiClient.request<Execution>(
        `/api/v1/plans/${planId}/execution`,
        { signal: controller.signal },
      );
      if (
        generation.current !== owner ||
        currentPlanId.current !== planId
      ) return;
      setExecution(loaded);
      setVisitedItems(new Set(loaded.feedback?.visited_plan_item_ids ?? []));
      setIncompleteReason(loaded.feedback?.reason ?? "");
      setFeedbackMode(loaded.feedback?.completion_status ?? null);
      setFeedback("");
    } catch (error) {
      if (
        generation.current !== owner ||
        currentPlanId.current !== planId
      ) return;
      setFeedback(messageFor(error));
    } finally {
      if (
        generation.current === owner &&
        currentPlanId.current === planId
      ) {
        if (requestController.current === controller) {
          requestController.current = null;
        }
        setExecutionBusy(false);
      }
    }
  }

  async function submitFeedback() {
    if (!session || !plan || !execution || !feedbackMode) return;
    if (
      feedbackMode === "partially_completed" &&
      (visitedItems.size === 0 || visitedItems.size === execution.items.length)
    ) {
      setFeedback("部分完成需要选择至少一项、但不能选择全部地点。");
      return;
    }
    const pagePlanId = plan.id;
    const executionPlanId = execution.plan_id;
    const owner = ++generation.current;
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    const payload = {
      completion_status: feedbackMode,
      visited_plan_item_ids:
        feedbackMode === "completed" ? [] : [...visitedItems].sort(),
      reason: incompleteReason.trim() || null,
      preference_candidate: suggestPreference
        ? {
            memory_type: suggestionType,
            content: suggestionContent.trim(),
            value: suggestionValue.trim(),
            evidence_summary: suggestionEvidence.trim(),
          }
        : null,
      expected_revision: execution.feedback?.revision ?? null,
    };
    if (
      suggestPreference &&
      (!suggestionContent.trim() ||
        !suggestionValue.trim() ||
        !suggestionEvidence.trim())
    ) {
      setFeedback("请完整填写偏好候选的内容、结构化值和依据。");
      return;
    }
    const fingerprint = JSON.stringify({ plan_id: executionPlanId, ...payload });
    if (feedbackAttempt.current?.fingerprint !== fingerprint) {
      feedbackAttempt.current = {
        fingerprint,
        key: crypto.randomUUID(),
      };
    }
    const idempotencyKey = feedbackAttempt.current.key;
    setExecutionBusy(true);
    try {
      const result = await apiClient.request<{ feedback: FeedbackRecord }>(
        `/api/v1/plans/${executionPlanId}/feedback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            idempotency_key: idempotencyKey,
            ...payload,
          }),
          csrfToken: session.csrf_token,
          signal: controller.signal,
        },
      );
      if (feedbackAttempt.current?.key === idempotencyKey) {
        feedbackAttempt.current = null;
      }
      if (
        generation.current !== owner ||
        currentPlanId.current !== pagePlanId
      ) return;
      const loaded = await apiClient.request<Execution>(
        `/api/v1/plans/${pagePlanId}/execution`,
        { signal: controller.signal },
      );
      if (
        generation.current !== owner ||
        currentPlanId.current !== pagePlanId
      ) return;
      setExecution(loaded);
      setVisitedItems(new Set(loaded.feedback?.visited_plan_item_ids ?? []));
      setPlan((current) =>
        current?.id === pagePlanId && pagePlanId === executionPlanId
          ? { ...current, status: result.feedback.completion_status }
          : current,
      );
      setFeedback(
        result.feedback.revision > 1
          ? "反馈已更正，相关状态已重新计算并保留记录。"
          : "完成反馈已保存。",
      );
    } catch (error) {
      if (
        generation.current !== owner ||
        currentPlanId.current !== pagePlanId
      ) return;
      setFeedback(messageFor(error));
    } finally {
      if (
        generation.current === owner &&
        currentPlanId.current === pagePlanId
      ) {
        if (requestController.current === controller) {
          requestController.current = null;
        }
        setExecutionBusy(false);
      }
    }
  }

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
            <span className={`plan-status ${plan.status}`}>V{plan.version} · {completionLabels[plan.status] ?? (plan.is_current_version ? "当前版本" : "历史版本")}</span>
            {plan.draft && (
              <button type="button" onClick={startNewPlan}>新建计划</button>
            )}
          </div>
        )}
      </header>

      {(phase === "editing" || phase === "reviewing") && (
        <div className="plan-compose">
          <form className="plan-form" noValidate onSubmit={beginReview}>
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
              V{version.version}{completionLabels[version.status] ? ` · ${completionLabels[version.status]}` : version.status === "failed" || version.status === "cancelled" ? " · 失败" : ""}
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
                      <p>{routeLabel(item.inbound_route)}</p>
                      <p className="selection-reason">{selectionReasonLabels[item.selection_reason_code] ?? "按当前条件选入方案。"}</p>
                      {item.risk_codes.length > 0 && <ul className="risk-list">{item.risk_codes.map((risk) => <li key={risk}>{riskLabels[risk] ?? "有信息待确认。"}</li>)}</ul>}
                    </div>
                  </li>
                ))}
              </ol>
              {plan.draft.weather_status && (
                <p className="option-risk">
                  天气事实：{plan.draft.weather_status === "provider_failed" ? weatherStatusLabels.provider_failed : plan.draft.weather_summary ?? weatherStatusLabels[plan.draft.weather_status] ?? "天气情况待确认"}
                  {plan.draft.weather_source ? ` · ${plan.draft.weather_source === "amap" ? "高德" : "天气服务"}` : ""}
                  {plan.draft.weather_queried_at ? ` · ${new Date(plan.draft.weather_queried_at).toLocaleString("zh-CN")}` : ""}
                </p>
              )}
              {option.risk_codes.length > 0 && <p className="option-risk">出发前留意：{option.risk_codes.map((risk) => riskLabels[risk] ?? "有信息待确认。").join("；")}</p>}
            </article>
          )}
          {plan.is_current_version && plan.status === "draft" && (
            <form className="adjust-card" onSubmit={adjustPlan}>
              <label htmlFor="plan-adjustment">想怎么调整？</label>
              <div><input id="plan-adjustment" name="instruction" value={adjustment} onChange={(event) => setAdjustment(event.target.value)} autoComplete="off" placeholder="例如：节奏轻松一点，预算改成 300" /><button type="submit" disabled={!adjustment.trim()}>生成新版本</button></div>
              <p>每次有效调整都会保留上一版，并创建不可变的新版本。</p>
            </form>
          )}
          <div className="plan-confirm-bar">
            <div>
              <strong>{executable ? "这一版已确认" : priorConfirmed && plan.is_current_version ? "已有确认版本，但有新草案" : plan.is_current_version ? "确认当前版本" : "这是历史版本"}</strong>
              <span>{executable ? "执行入口与反馈只属于这一确认版本" : priorConfirmed && plan.is_current_version ? `V${priorConfirmed.version} 仍是日历、路线和分享的执行版本` : "未确认计划不会产生执行动作"}</span>
            </div>
            <button className="primary-button" type="button" disabled={!plan.is_current_version || plan.status !== "draft"} onClick={() => void confirmPlan()}>{executable ? "已确认" : "明确确认 V" + plan.version}</button>
          </div>
        </>
      )}

      {executable && ["ready", "failed"].includes(phase) && (
        <>
          <ShareManagement
            key={plan.id}
            planId={plan.id}
            csrfToken={session?.csrf_token ?? ""}
          />
          <section className="execution-panel" aria-label="计划执行与完成反馈">
          <div className="plan-section-title"><span>06</span><h2>行动入口</h2></div>
          {!execution ? (
            <button className="primary-button" type="button" disabled={executionBusy} onClick={() => void loadExecution()}>
              {executionBusy ? "正在准备执行入口" : "查看路线、日历与完成反馈"}
            </button>
          ) : (
            <>
              <div className="execution-actions">
                <a
                  className="execution-action"
                  href={apiClient.url(`/api/v1/plans/${plan.id}/calendar.ics`)}
                  download={`shiguang-${plan.id}.ics`}
                >
                  <strong>下载日历</strong>
                  <span>完整计划 · Asia/Shanghai</span>
                </a>
                {execution.items.map((item, index) =>
                  item.navigation_uri ? (
                    <a
                      className="execution-action"
                      href={item.navigation_uri}
                      key={item.id}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <strong>{index === 0 ? "打开地点" : "打开下一段路线"}</strong>
                      <span>{item.title} · {item.address}</span>
                    </a>
                  ) : (
                    <div className="execution-action unavailable" key={item.id}>
                      <strong>地点待确认</strong>
                      <span>{item.title} 没有准确 POI，不生成导航入口</span>
                    </div>
                  ),
                )}
              </div>

              <div className="feedback-card">
                <header>
                  <div>
                    <p className="eyebrow">Manual feedback</p>
                    <h2>{execution.feedback ? "更正完成反馈" : "这次计划完成得怎么样？"}</h2>
                  </div>
                  {execution.feedback && <span>第 {execution.feedback.revision} 次记录</span>}
                </header>
                <div className="feedback-options" role="radiogroup" aria-label="完成状态">
                  {([
                    ["completed", "已完成", "按计划到访全部地点"],
                    ["partially_completed", "部分完成", "继续选择实际到访项"],
                    ["not_completed", "未完成", "收藏保持原状态"],
                  ] as const).map(([value, label, detail]) => (
                    <label key={value}>
                      <input
                        type="radio"
                        name="completion_status"
                        value={value}
                        checked={feedbackMode === value}
                        onChange={() => {
                          setFeedbackMode(value);
                          if (value !== "not_completed") setIncompleteReason("");
                          if (value === "completed") {
                            setVisitedItems(new Set(execution.items.map((item) => item.id)));
                          }
                          if (value === "not_completed") setVisitedItems(new Set());
                        }}
                      />
                      <strong>{label}</strong>
                      <span>{detail}</span>
                    </label>
                  ))}
                </div>
                {feedbackMode === "partially_completed" && (
                  <fieldset className="visited-choices">
                    <legend>选择实际到访的 PlanItem</legend>
                    {execution.items.map((item) => (
                      <label key={item.id}>
                        <input
                          type="checkbox"
                          name="visited_plan_items"
                          value={item.id}
                          checked={visitedItems.has(item.id)}
                          onChange={(event) => {
                            setVisitedItems((current) => {
                              const next = new Set(current);
                              if (event.target.checked) next.add(item.id);
                              else next.delete(item.id);
                              return next;
                            });
                          }}
                        />
                        <span>{item.title}<small>{item.is_external ? "外部未收藏 · 只更新计划项" : "你的收藏 · 到访后标记去过"}</small></span>
                      </label>
                    ))}
                  </fieldset>
                )}
                {feedbackMode === "not_completed" && (
                  <label className="feedback-reason">
                    未完成原因（选填）
                    <textarea
                      name="incomplete_reason"
                      maxLength={500}
                      value={incompleteReason}
                      onChange={(event) => setIncompleteReason(event.target.value)}
                      placeholder="例如：临时有事、天气变化；留空也可以提交"
                    />
                  </label>
                )}
                <fieldset className="visited-choices">
                  <legend>长期偏好候选（选填）</legend>
                  <label>
                    <input
                      type="checkbox"
                      name="suggest_preference"
                      checked={suggestPreference}
                      onChange={(event) => setSuggestPreference(event.target.checked)}
                    />
                    <span>
                      把一项明确偏好送到“我的”待确认
                      <small>完成状态和原因本身不会自动推断长期偏好</small>
                    </span>
                  </label>
                  {suggestPreference ? (
                    <>
                      <label>
                        候选类型
                        <select
                          name="preference_candidate_type"
                          value={suggestionType}
                          onChange={(event) => {
                            const nextType = event.target
                              .value as typeof suggestionType;
                            setSuggestionType(nextType);
                            setSuggestionValue(
                              nextType === "pace_preference" ? "balanced" : "",
                            );
                          }}
                        >
                          <option value="positive_preference">喜欢</option>
                          <option value="negative_preference">避开</option>
                          <option value="pace_preference">节奏</option>
                        </select>
                      </label>
                      <label>
                        候选内容
                        <input
                          name="preference_candidate_content"
                          value={suggestionContent}
                          maxLength={500}
                          onChange={(event) => setSuggestionContent(event.target.value)}
                        />
                      </label>
                      <label>
                        结构化值
                        {suggestionType === "pace_preference" ? (
                          <select
                            name="preference_candidate_value"
                            value={suggestionValue}
                            onChange={(event) =>
                              setSuggestionValue(event.target.value)
                            }
                          >
                            <option value="relaxed">轻松</option>
                            <option value="balanced">均衡</option>
                            <option value="packed">紧凑</option>
                          </select>
                        ) : (
                          <input
                            name="preference_candidate_value"
                            value={suggestionValue}
                            maxLength={100}
                            onChange={(event) =>
                              setSuggestionValue(event.target.value)
                            }
                          />
                        )}
                      </label>
                      <label>
                        候选依据
                        <textarea
                          name="preference_candidate_evidence"
                          value={suggestionEvidence}
                          maxLength={500}
                          onChange={(event) => setSuggestionEvidence(event.target.value)}
                        />
                      </label>
                    </>
                  ) : null}
                </fieldset>
                <button
                  className="primary-button"
                  type="button"
                  disabled={!feedbackMode || executionBusy}
                  onClick={() => void submitFeedback()}
                >
                  {executionBusy ? "正在保存" : execution.feedback ? "保存更正" : "保存完成反馈"}
                </button>
                {execution.feedback?.preference_suggestion && (
                  <aside className="preference-suggestion">
                    <strong>待确认的长期偏好建议</strong>
                    <p>{execution.feedback.preference_suggestion.content}</p>
                    <span>
                      {execution.feedback.preference_suggestion.evidence_summary ??
                        "历史候选需在记忆中心补充明确含义。"}
                      本阶段不会自动写入长期记忆。
                    </span>
                  </aside>
                )}
              </div>
            </>
          )}
          </section>
        </>
      )}

      {feedback && <p className="plan-feedback" role="status">{feedback}</p>}
      {phase === "failed" && !plan?.draft && (
        <div className="plan-empty">
          <h2>这一版没有生成结果</h2>
          <p>{plan?.status === "generating" ? "后台任务可能仍在处理；先读取权威状态，不会自动重复提交。" : plan && plan.versions.length > 1 ? "可以从上方版本索引返回上一份计划，或新建独立计划。" : "修改条件后可以重新生成；不会自动重试或隐式确认。"}</p>
          {plan?.status === "generating" ? (
            <button className="primary-button" type="button" onClick={() => void refreshAuthoritativeState()}>刷新权威状态</button>
          ) : plan === null && createRetryAvailable ? (
            <div>
              <button type="button" onClick={() => setPhase("editing")}>返回修改</button>
              <button className="primary-button" type="button" onClick={() => void generate()}>重试同一生成请求</button>
            </div>
          ) : (
            <button className="primary-button" type="button" onClick={startNewPlan}>新建计划</button>
          )}
        </div>
      )}
    </section>
  );
}
