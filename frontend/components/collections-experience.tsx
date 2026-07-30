"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { ApiError, apiClient } from "@/lib/api-client";

type CollectionStatus =
  | "active"
  | "pending_selection"
  | "pending_details"
  | "visited"
  | "archived"
  | "deleted";

type CollectionItem = {
  id: string;
  kind: "place" | "event";
  title: string;
  city_hint: string | null;
  city_pending: boolean;
  formal_city_code: string | null;
  city_group: string;
  district: string | null;
  address: string | null;
  business_district: string | null;
  landmark: string | null;
  metro_station: string | null;
  event_start_date: string | null;
  event_end_date: string | null;
  event_start_at: string | null;
  event_end_at: string | null;
  event_start_clue: string | null;
  event_end_clue: string | null;
  price_amount: string | number | null;
  price_currency: string | null;
  tags: string[];
  missing_fields: string[];
  uncertainties: Array<{ field: string; reason: string }>;
  status: CollectionStatus;
  version: number;
  planning_eligible: boolean;
  planning_exclusion_reason: string | null;
};

type CollectionPage = {
  items: CollectionItem[];
  page: number;
  page_size: number;
  total: number;
};

type CollectionDetail = {
  item: CollectionItem;
  sources: Array<{
    id: string;
    type: "text" | "url" | "image";
    parse_status: string;
    created_at: string;
  }>;
};

type PlaceCandidate = {
  provider: "amap";
  poi_id: string;
  name: string;
  branch_name: string | null;
  city_code: string;
  district: string | null;
  business_area: string | null;
  address: string;
  poi_type: string;
  matching_clues: string[];
};

type CandidatePage = {
  collection_item_id: string;
  expected_version: number;
  snapshot_fingerprint: string;
  queried_at: string;
  candidates: PlaceCandidate[];
};

type DemoSession = { csrf_token: string };
type LoadState = "loading" | "ready" | "error";
type DetailOperationOwnership = {
  detailGeneration: number;
  collectionId: string;
};

const statusLabels: Record<CollectionStatus, string> = {
  active: "想去",
  pending_selection: "待选择",
  pending_details: "待补充",
  visited: "去过",
  archived: "已归档",
  deleted: "已删除",
};

const exclusionLabels: Record<string, string> = {
  pending_confirmation: "确认地点后才能参与深圳计划",
  other_city: "属于其他城市，当前深圳计划不会使用",
  inactive: "当前状态不会参与计划",
  city_or_location_unconfirmed: "城市或位置待确认，暂不参与计划",
};

const eventTemporalLabels: Readonly<Record<string, string>> = {
  event_start_date: "活动有效开始日期",
  event_end_date: "活动有效结束日期",
  event_start_at: "准确开始时间",
  event_end_at: "准确结束时间",
};

const eventTemporalFields = Object.keys(eventTemporalLabels);
const requiredEventTimeFields = new Set([
  "event_start_at",
  "event_end_at",
]);

function eventTimeNeedsAttention(item: CollectionItem): boolean {
  return (
    item.missing_fields.some((field) => requiredEventTimeFields.has(field)) ||
    item.uncertainties.some((entry) =>
      eventTemporalFields.includes(entry.field),
    )
  );
}

function planningExclusionLabel(item: CollectionItem): string {
  if (
    item.kind === "event" &&
    item.planning_exclusion_reason === "pending_confirmation" &&
    eventTimeNeedsAttention(item)
  ) {
    return "确认活动时间和准确地点后才能参与深圳计划";
  }
  return (
    exclusionLabels[item.planning_exclusion_reason ?? ""] ??
    "暂不参与当前计划"
  );
}

function isoToShanghaiLocal(value: string | null): string {
  if (!value) return "";
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return "";
  const shanghai = new Date(instant.getTime() + 8 * 60 * 60 * 1000);
  const pad = (part: number) => String(part).padStart(2, "0");
  return [
    shanghai.getUTCFullYear(),
    "-",
    pad(shanghai.getUTCMonth() + 1),
    "-",
    pad(shanghai.getUTCDate()),
    "T",
    pad(shanghai.getUTCHours()),
    ":",
    pad(shanghai.getUTCMinutes()),
  ].join("");
}

function shanghaiLocalToIso(value: string): string {
  const withSeconds = value.length === 16 ? `${value}:00` : value;
  return `${withSeconds}+08:00`;
}

function errorCopy(error: unknown): string {
  if (!(error instanceof ApiError)) return "收藏库暂时没有加载完成。";
  if (error.code === "conflict") return "这条收藏刚刚被更新，请刷新后继续。";
  if (error.code === "forbidden") return "会话校验已失效，请刷新页面。";
  if (error.code === "not_found") return "这条收藏不存在，或你没有查看权限。";
  if (error.code === "timeout") return "请求等待超时，请重试。";
  if (error.status === 422 || error.code === "request_failed") {
    return "补充信息没有保存，请检查后重试。";
  }
  return "收藏库暂时没有加载完成。";
}

function cityLabel(item: CollectionItem): string {
  if (item.city_group === "shenzhen") return "深圳";
  if (item.formal_city_code === "guangzhou") return "广州";
  if (item.formal_city_code) return item.formal_city_code;
  return "城市待确认";
}

function priceLabel(item: CollectionItem): string {
  if (item.price_amount === null) return "价格待确认";
  return `约 ¥${item.price_amount}`;
}

function eventLabel(item: CollectionItem): string | null {
  if (item.kind !== "event") return null;
  if (item.event_start_at && item.event_end_at) {
    return `${new Date(item.event_start_at).toLocaleString("zh-CN")} – ${new Date(
      item.event_end_at,
    ).toLocaleTimeString("zh-CN")}`;
  }
  if (item.event_start_date && item.event_end_date) {
    return `${item.event_start_date} – ${item.event_end_date} · 准确时段待确认`;
  }
  return item.event_start_clue ?? "活动时间待确认";
}

function CollectionSearchForm({
  initialValue,
  onSearch,
}: {
  initialValue: string;
  onSearch: (value: string) => void;
}) {
  const [value, setValue] = useState(initialValue);
  return (
    <form
      className="collection-search"
      onSubmit={(event) => {
        event.preventDefault();
        onSearch(value);
      }}
    >
      <label htmlFor="collection-search">搜索收藏</label>
      <div>
        <input
          id="collection-search"
          name="search"
          autoComplete="off"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="名称、地址、商圈或标签"
        />
        <button type="submit">搜索</button>
      </div>
    </form>
  );
}

export function CollectionsExperience() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryString = searchParams.toString();
  const selectedId = searchParams.get("item");
  const [csrf, setCsrf] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [pageData, setPageData] = useState<CollectionPage | null>(null);
  const [feedback, setFeedback] = useState("");
  const [deletedItem, setDeletedItem] = useState<CollectionItem | null>(null);
  const [detail, setDetail] = useState<CollectionDetail | null>(null);
  const [candidates, setCandidates] = useState<CandidatePage | null>(null);
  const [detailState, setDetailState] = useState<LoadState>("ready");
  const [saving, setSaving] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftCity, setDraftCity] = useState("");
  const [draftDistrict, setDraftDistrict] = useState("");
  const [draftAddress, setDraftAddress] = useState("");
  const [draftTags, setDraftTags] = useState("");
  const [draftEventStartDate, setDraftEventStartDate] = useState("");
  const [draftEventEndDate, setDraftEventEndDate] = useState("");
  const [draftEventStartAt, setDraftEventStartAt] = useState("");
  const [draftEventEndAt, setDraftEventEndAt] = useState("");
  const listGeneration = useRef(0);
  const detailGeneration = useRef(0);
  const activeDetailId = useRef<string | null>(selectedId);
  const detailCloseButton = useRef<HTMLButtonElement>(null);
  const selectionAttempt = useRef<{
    identity: string;
    idempotencyKey: string;
  } | null>(null);

  function restoreDrafts(item: CollectionItem) {
    setDraftTitle(item.title);
    setDraftCity(item.city_hint ?? "");
    setDraftDistrict(item.district ?? "");
    setDraftAddress(item.address ?? "");
    setDraftTags(item.tags.join("、"));
    setDraftEventStartDate(item.event_start_date ?? "");
    setDraftEventEndDate(item.event_end_date ?? "");
    setDraftEventStartAt(isoToShanghaiLocal(item.event_start_at));
    setDraftEventEndAt(isoToShanghaiLocal(item.event_end_at));
  }
  useLayoutEffect(() => {
    if (activeDetailId.current === selectedId) return;
    activeDetailId.current = selectedId;
    detailGeneration.current += 1;
    selectionAttempt.current = null;
    queueMicrotask(() => setSaving(false));
  }, [selectedId]);

  const replaceQuery = useCallback(
    (changes: Record<string, string | null>, replace = false) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(changes)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      const target = `${pathname}${next.size ? `?${next}` : ""}`;
      if (replace) router.replace(target);
      else router.push(target);
    },
    [pathname, router, searchParams],
  );

  const navigateDetail = useCallback(
    (collectionId: string | null, replace = false) => {
      activeDetailId.current = collectionId;
      detailGeneration.current += 1;
      selectionAttempt.current = null;
      setSaving(false);
      replaceQuery({ item: collectionId }, replace);
    },
    [replaceQuery],
  );

  function detailOperation(collectionId: string): DetailOperationOwnership {
    return {
      detailGeneration: detailGeneration.current,
      collectionId,
    };
  }

  function ownsDetailOperation(operation: DetailOperationOwnership): boolean {
    return (
      detailGeneration.current === operation.detailGeneration &&
      (activeDetailId.current === operation.collectionId ||
        activeDetailId.current === null)
    );
  }

  const loadList = useCallback(async () => {
    const generation = listGeneration.current + 1;
    listGeneration.current = generation;
    const controller = new AbortController();
    setLoadState("loading");
    try {
      const currentQuery = new URLSearchParams(queryString);
      const params = new URLSearchParams();
      for (const key of ["search", "kind", "status", "city_group", "page"]) {
        const value = currentQuery.get(key);
        if (value) params.set(key, value);
      }
      params.set("page_size", "8");
      const result = await apiClient.request<CollectionPage>(
        `/api/v1/collections?${params}`,
        { signal: controller.signal },
      );
      if (listGeneration.current !== generation) return;
      setPageData(result);
      setLoadState("ready");
    } catch (error) {
      if (listGeneration.current !== generation) return;
      if (error instanceof ApiError && error.code === "aborted") return;
      setLoadState("error");
      setFeedback(errorCopy(error));
    }
  }, [queryString]);

  useEffect(() => {
    let active = true;
    void apiClient
      .request<DemoSession>("/api/v1/demo/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      })
      .then((session) => {
        if (active) setCsrf(session.csrf_token);
      })
      .catch((error) => {
        if (active) {
          setLoadState("error");
          setFeedback(errorCopy(error));
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (csrf) queueMicrotask(() => void loadList());
  }, [csrf, loadList]);

  useEffect(() => {
    if (!csrf || !selectedId) {
      return;
    }
    const generation = detailGeneration.current;
    const controller = new AbortController();
    void (async () => {
      await Promise.resolve();
      if (detailGeneration.current !== generation) return;
      setDetailState("loading");
      setFeedback("");
      try {
        const loaded = await apiClient.request<CollectionDetail>(
          `/api/v1/collections/${selectedId}`,
          { signal: controller.signal },
        );
        if (detailGeneration.current !== generation) return;
        setDetail(loaded);
        restoreDrafts(loaded.item);
        if (loaded.item.status === "pending_selection") {
          const choices = await apiClient.request<CandidatePage>(
            `/api/v1/collections/${selectedId}/poi-candidates`,
            { signal: controller.signal },
          );
          if (detailGeneration.current !== generation) return;
          setCandidates(choices);
        } else {
          setCandidates(null);
        }
        setDetailState("ready");
      } catch (error) {
        if (detailGeneration.current !== generation) return;
        if (error instanceof ApiError && error.code === "aborted") return;
        setDetailState("error");
        setFeedback(errorCopy(error));
      }
    })();
    return () => controller.abort();
  }, [csrf, selectedId]);

  useEffect(() => {
    if (selectedId && detailState === "ready") {
      detailCloseButton.current?.focus();
    }
  }, [detailState, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") navigateDetail(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [navigateDetail, selectedId]);

  async function runDetailOperation(
    collectionId: string,
    request: () => Promise<CollectionItem>,
    onSuccess: (result: CollectionItem) => void | Promise<void>,
    onFailure?: () => void,
  ) {
    if (!csrf) return;
    const operation = detailOperation(collectionId);
    if (!ownsDetailOperation(operation)) return;
    setSaving(true);
    setFeedback("");
    try {
      const result = await request();
      if (!ownsDetailOperation(operation)) return;
      if (result.id !== collectionId) return;
      await onSuccess(result);
      await loadList();
    } catch (error) {
      if (!ownsDetailOperation(operation)) return;
      onFailure?.();
      setFeedback(errorCopy(error));
    } finally {
      if (ownsDetailOperation(operation)) setSaving(false);
    }
  }

  async function saveDetail(event: FormEvent) {
    event.preventDefault();
    if (!detail || !csrf) return;
    const collectionId = detail.item.id;
    await runDetailOperation(
      collectionId,
      () =>
        apiClient.request<CollectionItem>(
          `/api/v1/collections/${collectionId}`,
          {
            method: "PATCH",
            csrfToken: csrf,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              expected_version: detail.item.version,
              changes: {
                title: draftTitle,
                city_hint: draftCity.trim() || null,
                district: draftDistrict.trim() || null,
                address: draftAddress.trim() || null,
                tags: draftTags
                  .split(/[、,]/)
                  .map((tag) => tag.trim())
                  .filter(Boolean),
              },
            }),
          },
        ),
      async (item) => {
        setDetail((current) => (current ? { ...current, item } : current));
        restoreDrafts(item);
        if (item.status === "pending_selection") {
          const candidateGeneration = detailGeneration.current;
          let choices: CandidatePage;
          try {
            choices = await apiClient.request<CandidatePage>(
              `/api/v1/collections/${collectionId}/poi-candidates`,
            );
          } catch {
            setCandidates(null);
            setFeedback("修改已保存，但地点候选暂时没有加载完成，请重新打开详情。");
            return;
          }
          if (
            detailGeneration.current !== candidateGeneration ||
            activeDetailId.current !== collectionId
          ) {
            return;
          }
          setCandidates(choices);
          setFeedback("修改已保存，请选择准确地点。");
        } else {
          setCandidates(null);
          setFeedback("修改已保存，Agent 与收藏库会读取同一条数据。");
        }
      },
      () => restoreDrafts(detail.item),
    );
  }

  async function confirmEventTime(event: FormEvent) {
    event.preventDefault();
    if (!detail || !csrf || detail.item.kind !== "event") return;
    if (
      draftEventStartDate &&
      draftEventEndDate &&
      draftEventEndDate < draftEventStartDate
    ) {
      setFeedback("活动有效结束日期不能早于开始日期。");
      return;
    }
    const startAt = draftEventStartAt
      ? shanghaiLocalToIso(draftEventStartAt)
      : null;
    const endAt = draftEventEndAt
      ? shanghaiLocalToIso(draftEventEndAt)
      : null;
    if (
      startAt &&
      endAt &&
      Date.parse(endAt) <= Date.parse(startAt)
    ) {
      setFeedback("准确结束时间必须晚于准确开始时间。");
      return;
    }

    const changes: Record<string, string | null> = {};
    for (const [field, draft, current] of [
      ["event_start_date", draftEventStartDate, detail.item.event_start_date],
      ["event_end_date", draftEventEndDate, detail.item.event_end_date],
      ["event_start_at", startAt, detail.item.event_start_at],
      ["event_end_at", endAt, detail.item.event_end_at],
    ] as const) {
      if (draft || current) changes[field] = draft || null;
    }

    const collectionId = detail.item.id;
    await runDetailOperation(
      collectionId,
      () =>
        apiClient.request<CollectionItem>(
          `/api/v1/collections/${collectionId}`,
          {
            method: "PATCH",
            csrfToken: csrf,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              expected_version: detail.item.version,
              changes,
            }),
          },
        ),
      (item) => {
        setDetail((current) => (current ? { ...current, item } : current));
        restoreDrafts(item);
        const uncertain = new Set(
          item.uncertainties.map((entry) => entry.field),
        );
        const exactTimeConfirmed = Boolean(
          item.event_start_at &&
            item.event_end_at &&
            !uncertain.has("event_start_at") &&
            !uncertain.has("event_end_at"),
        );
        if (item.planning_eligible) {
          setFeedback("活动时间已确认，可参与当前计划。");
        } else if (!exactTimeConfirmed) {
          setFeedback("已保存当前活动时间，准确时段待补充。");
        } else {
          setFeedback("活动时间已确认，准确地点确认后才可参与计划。");
        }
      },
    );
  }

  async function deleteCollection() {
    if (!detail || !csrf) return;
    const previous = detail.item;
    await runDetailOperation(
      previous.id,
      () =>
        apiClient.request<CollectionItem>(
          `/api/v1/collections/${previous.id}?expected_version=${previous.version}`,
          { method: "DELETE", csrfToken: csrf },
        ),
      (item) => {
        setDeletedItem(item);
        setDetail((current) => (current ? { ...current, item } : current));
        setFeedback("收藏已删除，你可以立即恢复。");
      },
    );
  }

  async function restoreCollection(target = deletedItem) {
    if (!target || !csrf) return;
    await runDetailOperation(
      target.id,
      () =>
        apiClient.request<CollectionItem>(
          `/api/v1/collections/${target.id}/restore`,
          { method: "POST", csrfToken: csrf },
        ),
      (item) => {
        setDeletedItem(null);
        setFeedback("收藏已恢复到删除前的准确状态。");
        setDetail((current) => (current ? { ...current, item } : current));
      },
    );
  }

  async function chooseCandidate(candidate: PlaceCandidate | null) {
    if (!candidates || !detail || !csrf) return;
    const collectionId = detail.item.id;
    const operation = detailOperation(collectionId);
    const identity = [
      collectionId,
      candidates.snapshot_fingerprint,
      candidate?.provider ?? "none",
      candidate?.poi_id ?? "none",
    ].join(":");
    if (selectionAttempt.current?.identity !== identity) {
      selectionAttempt.current = {
        identity,
        idempotencyKey: `web-${crypto.randomUUID()}`,
      };
    }
    setSaving(true);
    setFeedback("");
    try {
      const result = await apiClient.request<{
        items: CollectionItem[];
        replayed: boolean;
      }>(`/api/v1/collections/${collectionId}/poi-selection`, {
        method: "POST",
        csrfToken: csrf,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_version: candidates.expected_version,
          snapshot_fingerprint: candidates.snapshot_fingerprint,
          idempotency_key: selectionAttempt.current.idempotencyKey,
          choice: candidate ? "candidate" : "none_of_above",
          provider: candidate?.provider ?? null,
          poi_id: candidate?.poi_id ?? null,
        }),
      });
      const item = result.items[0];
      if (!item || !ownsDetailOperation(operation)) return;
      setDetail((current) => (current && item ? { ...current, item } : current));
      setCandidates(null);
      selectionAttempt.current = null;
      setFeedback(
        candidate
          ? "准确地点已保存。"
          : "候选均未采用，原收藏已保留为待补充。",
      );
      if (item.id !== collectionId) {
        navigateDetail(item.id, true);
        await loadList();
        return;
      }
      await loadList();
    } catch (error) {
      if (!ownsDetailOperation(operation)) return;
      setFeedback(errorCopy(error));
    } finally {
      if (ownsDetailOperation(operation)) setSaving(false);
    }
  }

  const totalPages = Math.max(
    1,
    Math.ceil((pageData?.total ?? 0) / (pageData?.page_size ?? 8)),
  );

  return (
    <section className="collections-page" aria-busy={loadState === "loading"}>
      <header className="collections-heading">
        <div>
          <p className="page-eyebrow">Your city memory</p>
          <h1 className="page-title">收藏</h1>
          <p className="page-description">
            管理所有城市的 Place 与 Event。只有已确认的深圳地点会进入当前计划。
          </p>
        </div>
        <div className="collection-count" aria-label="收藏总数">
          <strong>{pageData?.total ?? "—"}</strong>
          <span>个结果</span>
        </div>
      </header>

      <div className="planning-boundary">
        <strong>当前计划城市 · 深圳</strong>
        <span>城市待确认、待选择、待补充和其他城市收藏会保留，但不会误入计划。</span>
      </div>

      <CollectionSearchForm
        key={searchParams.get("search") ?? ""}
        initialValue={searchParams.get("search") ?? ""}
        onSearch={(value) =>
          replaceQuery({ search: value.trim() || null, page: null })
        }
      />

      <div className="collection-filters" aria-label="筛选收藏">
        <label>
          城市
          <select
            name="city_group"
            value={searchParams.get("city_group") ?? ""}
            onChange={(event) =>
              replaceQuery({ city_group: event.target.value || null, page: null })
            }
          >
            <option value="">全部城市</option>
            <option value="shenzhen">深圳</option>
            <option value="other">其他城市</option>
            <option value="pending">城市待确认</option>
          </select>
        </label>
        <label>
          类型
          <select
            name="kind"
            value={searchParams.get("kind") ?? ""}
            onChange={(event) =>
              replaceQuery({ kind: event.target.value || null, page: null })
            }
          >
            <option value="">Place 与 Event</option>
            <option value="place">Place</option>
            <option value="event">Event</option>
          </select>
        </label>
        <label>
          状态
          <select
            name="status"
            value={searchParams.get("status") ?? ""}
            onChange={(event) =>
              replaceQuery({ status: event.target.value || null, page: null })
            }
          >
            <option value="">全部有效状态</option>
            <option value="active">想去</option>
            <option value="pending_selection">待选择</option>
            <option value="pending_details">待补充</option>
            <option value="visited">去过</option>
            <option value="archived">已归档</option>
            <option value="deleted">已删除</option>
          </select>
        </label>
        <button
          type="button"
          className="filter-clear"
          onClick={() =>
            router.push(pathname)
          }
        >
          清除筛选
        </button>
      </div>

      {deletedItem ? (
        <div className="restore-banner" role="status">
          <span>“{deletedItem.title}”已删除。</span>
          <button type="button" onClick={() => void restoreCollection()} disabled={saving}>
            恢复
          </button>
        </div>
      ) : null}
      {feedback ? <p className="collection-feedback" role="status">{feedback}</p> : null}

      {loadState === "loading" ? (
        <div className="collection-state" role="status">正在加载收藏…</div>
      ) : null}
      {loadState === "error" ? (
        <div className="collection-state" role="alert">
          <p>{feedback}</p>
          <button type="button" onClick={() => void loadList()}>重试</button>
        </div>
      ) : null}
      {loadState === "ready" && pageData?.items.length === 0 ? (
        <div className="collection-state">
          <h2>没有符合条件的收藏</h2>
          <p>可以清除筛选，或从 Agent 页面继续添加。</p>
          <button type="button" onClick={() => router.push("/agent")}>去添加收藏</button>
        </div>
      ) : null}

      {loadState === "ready" && pageData?.items.length ? (
        <div className="collection-grid">
          {pageData.items.map((item) => (
            <button
              type="button"
              className="collection-card"
              key={item.id}
              onClick={() => navigateDetail(item.id)}
            >
              <span className={`collection-kind ${item.kind}`}>{item.kind === "place" ? "P" : "E"}</span>
              <span className="collection-card-copy">
                <span className="collection-card-topline">
                  <span>{cityLabel(item)}</span>
                  <span>{statusLabels[item.status]}</span>
                </span>
                <strong>{item.title}</strong>
                <span>
                  {[item.district, item.business_district, priceLabel(item)]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                {eventLabel(item) ? <span>{eventLabel(item)}</span> : null}
                <span className={item.planning_eligible ? "eligible" : "excluded"}>
                  {item.planning_eligible
                    ? "可参与当前深圳计划"
                    : planningExclusionLabel(item)}
                </span>
                <span className="collection-tag-row">
                  {item.tags.slice(0, 3).map((tag) => <span key={tag}>{tag}</span>)}
                </span>
              </span>
            </button>
          ))}
        </div>
      ) : null}

      {pageData && pageData.total > 0 ? (
        <nav className="collection-pagination" aria-label="收藏分页">
          <button
            type="button"
            disabled={pageData.page <= 1}
            onClick={() => replaceQuery({ page: String(pageData.page - 1) })}
          >
            上一页
          </button>
          <span>第 {pageData.page} / {totalPages} 页</span>
          <button
            type="button"
            disabled={pageData.page >= totalPages}
            onClick={() => replaceQuery({ page: String(pageData.page + 1) })}
          >
            下一页
          </button>
        </nav>
      ) : null}

      {selectedId ? (
        <div className="detail-backdrop" role="presentation">
          <section
            className="collection-detail"
            role="dialog"
            aria-modal="true"
            aria-labelledby="collection-detail-title"
          >
            <header>
              <div>
                <p className="page-eyebrow">Collection detail</p>
                <h2 id="collection-detail-title">{detail?.item.title ?? "收藏详情"}</h2>
              </div>
              <button
                ref={detailCloseButton}
                type="button"
                aria-label="关闭收藏详情"
                onClick={() => navigateDetail(null)}
              >
                关闭
              </button>
            </header>
            {detailState === "loading" ? <p role="status">正在读取详情…</p> : null}
            {detailState === "error" ? (
              <div role="alert"><p>{feedback}</p><button type="button" onClick={() => navigateDetail(null)}>返回列表</button></div>
            ) : null}
            {detailState === "ready" && detail ? (
              <>
                <div className="detail-summary">
                  <span>{detail.item.kind === "place" ? "Place" : "Event"}</span>
                  <span>{cityLabel(detail.item)}</span>
                  <span>{statusLabels[detail.item.status]}</span>
                  <span>版本 {detail.item.version}</span>
                </div>
                {candidates ? (
                  <fieldset className="candidate-list" disabled={saving}>
                    <legend>请选择准确地点</legend>
                    <p>排名第一不代表已经确认。请根据行政区、商圈和公开地址选择。</p>
                    {candidates.candidates.map((candidate) => (
                      <button
                        type="button"
                        key={`${candidate.provider}:${candidate.poi_id}`}
                        onClick={() => void chooseCandidate(candidate)}
                      >
                        <strong>
                          {candidate.name}
                          {candidate.branch_name ? ` · ${candidate.branch_name}` : ""}
                        </strong>
                        <span>
                          {[candidate.district, candidate.business_area, candidate.address]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                        <small>{candidate.poi_type} · 高德候选</small>
                      </button>
                    ))}
                    <button
                      type="button"
                      className="candidate-none"
                      onClick={() => void chooseCandidate(null)}
                    >
                      <strong>以上都不是</strong>
                      <span>保留原始收藏，并转为待补充状态</span>
                    </button>
                  </fieldset>
                ) : null}
                {detail.item.kind === "event" ? (
                  <form className="event-time-form" onSubmit={confirmEventTime}>
                    <div className="event-time-heading">
                      <div>
                        <strong>确认活动时间</strong>
                        <p>
                          {eventTimeNeedsAttention(detail.item)
                            ? "以下是模型建议。即使内容正确，也需要你明确确认后才能用于计划。"
                            : "以下是已保存的活动时间；修改后需要再次明确保存。"}
                        </p>
                      </div>
                      <span>
                        {detail.item.planning_eligible
                          ? "可参与计划"
                          : eventTimeNeedsAttention(detail.item)
                            ? "活动时间待确认"
                            : "准确地点待确认"}
                      </span>
                    </div>
                    <div className="event-time-fields">
                      <label>
                        活动有效开始日期
                        <input
                          name="event_start_date"
                          type="date"
                          value={draftEventStartDate}
                          onChange={(event) =>
                            setDraftEventStartDate(event.target.value)
                          }
                        />
                      </label>
                      <label>
                        活动有效结束日期
                        <input
                          name="event_end_date"
                          type="date"
                          min={draftEventStartDate || undefined}
                          value={draftEventEndDate}
                          onChange={(event) =>
                            setDraftEventEndDate(event.target.value)
                          }
                        />
                      </label>
                      <label>
                        准确开始时间
                        <input
                          name="event_start_at"
                          type="datetime-local"
                          value={draftEventStartAt}
                          onChange={(event) =>
                            setDraftEventStartAt(event.target.value)
                          }
                        />
                      </label>
                      <label>
                        准确结束时间
                        <input
                          name="event_end_at"
                          type="datetime-local"
                          min={draftEventStartAt || undefined}
                          value={draftEventEndAt}
                          onChange={(event) =>
                            setDraftEventEndAt(event.target.value)
                          }
                        />
                      </label>
                    </div>
                    <div className="event-time-state">
                      <p>
                        <strong>待补充：</strong>
                        {detail.item.missing_fields
                          .filter((field) => eventTemporalFields.includes(field))
                          .map((field) => eventTemporalLabels[field] ?? field)
                          .join("、") || "无"}
                      </p>
                      <p>
                        <strong>待确认：</strong>
                        {detail.item.uncertainties
                          .filter((entry) =>
                            eventTemporalFields.includes(entry.field),
                          )
                          .map(
                            (entry) =>
                              eventTemporalLabels[entry.field] ?? entry.field,
                          )
                          .join("、") || "无"}
                      </p>
                      {!detail.item.event_start_at ||
                      !detail.item.event_end_at ? (
                        <p>准确时段待补充；仅确认日期仍不能参与计划。</p>
                      ) : null}
                    </div>
                    <button
                      className="primary-button"
                      type="submit"
                      disabled={saving}
                    >
                      {saving ? "正在确认…" : "确认并保存"}
                    </button>
                  </form>
                ) : null}
                <form className="collection-edit-form" onSubmit={saveDetail}>
                  <label>名称<input name="title" required maxLength={200} value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} /></label>
                  <label>城市线索<input name="city_hint" maxLength={100} value={draftCity} onChange={(event) => setDraftCity(event.target.value)} placeholder="线索不等于正式城市" /></label>
                  <label>行政区<input name="district" maxLength={100} value={draftDistrict} onChange={(event) => setDraftDistrict(event.target.value)} /></label>
                  <label>公开地址<input name="address" maxLength={500} value={draftAddress} onChange={(event) => setDraftAddress(event.target.value)} /></label>
                  <label>标签<input name="tags" value={draftTags} onChange={(event) => setDraftTags(event.target.value)} placeholder="用逗号分隔" /></label>
                  <div className="detail-sources">
                    <strong>来源</strong>
                    {detail.sources.map((source) => (
                      <span key={source.id}>{source.type} · {source.parse_status}</span>
                    ))}
                  </div>
                  <div className="detail-actions">
                    {detail.item.status === "deleted" ? (
                      <button type="button" onClick={() => {
                        void restoreCollection(detail.item);
                      }}>恢复收藏</button>
                    ) : (
                      <button className="danger-button" type="button" onClick={() => void deleteCollection()} disabled={saving}>删除收藏</button>
                    )}
                    <button className="primary-button" type="submit" disabled={saving}>
                      {saving ? "正在保存…" : "保存修改"}
                    </button>
                  </div>
                </form>
              </>
            ) : null}
          </section>
        </div>
      ) : null}
    </section>
  );
}
