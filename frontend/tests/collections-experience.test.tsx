import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CollectionsExperience } from "@/components/collections-experience";
import { ApiError, apiClient } from "@/lib/api-client";

let currentQuery = "";
const push = vi.fn();
const replace = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/collections",
  useRouter: () => ({ push, replace }),
  useSearchParams: () => new URLSearchParams(currentQuery),
}));

const baseItem = {
  id: "col_0123456789abcdef0123456789abcdef",
  kind: "place",
  title: "深圳湾公园",
  city_hint: "深圳",
  city_pending: false,
  formal_city_code: "shenzhen",
  city_group: "shenzhen",
  district: "南山区",
  address: "滨海大道",
  business_district: "后海",
  landmark: "深圳湾",
  metro_station: "深圳湾公园站",
  event_start_date: null,
  event_end_date: null,
  event_start_at: null,
  event_end_at: null,
  event_start_clue: null,
  event_end_clue: null,
  price_amount: "0.00",
  price_currency: "CNY",
  tags: ["公园", "散步"],
  missing_fields: [],
  uncertainties: [],
  status: "active",
  version: 1,
  planning_eligible: true,
  planning_exclusion_reason: null,
};

const eventItem = {
  ...baseItem,
  kind: "event",
  title: "深圳音乐节",
  event_start_date: "2026-08-02",
  event_end_date: "2026-08-04",
  event_start_at: "2026-08-02T07:30:00Z",
  event_end_at: "2026-08-02T12:00:00Z",
  missing_fields: [],
  uncertainties: [
    { field: "event_start_date", reason: "模型建议需要确认" },
    { field: "event_end_date", reason: "模型建议需要确认" },
    { field: "event_start_at", reason: "模型建议需要确认" },
    { field: "event_end_at", reason: "模型建议需要确认" },
  ],
  status: "pending_details",
  version: 1,
  planning_eligible: false,
  planning_exclusion_reason: "event_time_unconfirmed",
};

const emptyPage = { items: [], page: 1, page_size: 8, total: 0 };
const filledPage = { items: [baseItem], page: 1, page_size: 8, total: 1 };
const session = { csrf_token: "csrf-token" };

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function candidatePage(itemId: string) {
  return {
    collection_item_id: itemId,
    expected_version: 1,
    snapshot_fingerprint: "c".repeat(64),
    queried_at: "2026-07-27T00:00:00Z",
    candidates: [
      {
        provider: "amap",
        poi_id: "poi-one",
        name: "一尺花园",
        branch_name: "海上世界店",
        city_code: "shenzhen",
        district: "南山区",
        business_area: "海上世界",
        address: "太子路118号",
        poi_type: "cafe",
        matching_clues: [],
      },
    ],
  };
}

function mockBootstrap(page: object = filledPage) {
  return vi
    .spyOn(apiClient, "request")
    .mockResolvedValueOnce(session)
    .mockResolvedValueOnce(page);
}

beforeEach(() => {
  currentQuery = "";
  push.mockReset();
  replace.mockReset();
  vi.restoreAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("CollectionsExperience", () => {
  it("opens from a card and traps focus until Escape closes the detail", async () => {
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) return filledPage as never;
        return {
          item: baseItem,
          sources: [{ id: "src_one", type: "image", parse_status: "parsed" }],
        } as never;
      },
    );
    const view = render(<CollectionsExperience />);
    const openingCard = await screen.findByRole("button", {
      name: /深圳湾公园/,
    });
    await userEvent.click(openingCard);
    expect(push).toHaveBeenCalledWith(
      `/collections?item=${baseItem.id}`,
      { scroll: false },
    );
    currentQuery = `item=${baseItem.id}`;
    view.rerender(<CollectionsExperience />);

    const routedDialog = await screen.findByRole("dialog");
    expect(within(routedDialog).getByText("地点")).toBeInTheDocument();
    expect(within(routedDialog).getByText("截图 · 已解析")).toBeInTheDocument();
    expect(within(routedDialog).queryByText(/Place|image|parsed/)).not.toBeInTheDocument();
    const close = within(routedDialog).getByRole("button", {
      name: "关闭收藏详情",
    });
    await within(routedDialog).findByRole("textbox", { name: "名称" });
    await waitFor(() => expect(close).toHaveFocus());
    const lastAction = within(routedDialog).getByRole("button", {
      name: "保存修改",
    });
    lastAction.focus();
    await userEvent.tab();
    expect(close).toHaveFocus();

    await userEvent.keyboard("{Escape}");
    expect(push).toHaveBeenLastCalledWith("/collections", { scroll: false });
    currentQuery = "";
    view.rerender(<CollectionsExperience />);
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(openingCard).toHaveFocus());
  });

  it("keeps one Event confirmation form and one collection action set", async () => {
    currentQuery = `item=${eventItem.id}`;
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) {
          return { ...filledPage, items: [eventItem] } as never;
        }
        return { item: eventItem, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("button", { name: "确认并保存" });
    expect(
      within(dialog).getAllByRole("button", { name: "确认并保存" }),
    ).toHaveLength(1);
    expect(
      within(dialog).getAllByRole("button", { name: "保存修改" }),
    ).toHaveLength(1);
    expect(
      within(dialog).getAllByRole("button", { name: "删除收藏" }),
    ).toHaveLength(1);
    expect(dialog.querySelectorAll(".event-time-form")).toHaveLength(1);
    expect(dialog.querySelectorAll(".collection-edit-form")).toHaveLength(1);
  });

  it("shows loading, empty state, and a useful recovery action", async () => {
    mockBootstrap(emptyPage);
    render(<CollectionsExperience />);

    expect(screen.getByText("正在加载收藏…")).toBeInTheDocument();
    expect(await screen.findByText("没有符合条件的收藏")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "去添加收藏" })).toBeInTheDocument();
  });

  it("shows a safe error and retries through the same API client", async () => {
    const request = vi
      .spyOn(apiClient, "request")
      .mockResolvedValueOnce(session)
      .mockRejectedValueOnce(new ApiError("network_error", null, null))
      .mockResolvedValueOnce(filledPage);
    render(<CollectionsExperience />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "收藏库暂时没有加载完成",
    );
    await userEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("深圳湾公园")).toBeInTheDocument();
    expect(request).toHaveBeenCalledTimes(3);
  });

  it("uses explicit search submission and keeps filters/page in the URL", async () => {
    mockBootstrap();
    render(<CollectionsExperience />);
    await screen.findByText("深圳湾公园");

    const search = screen.getByRole("textbox", { name: "搜索收藏" });
    await userEvent.type(search, "公园");
    expect(push).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "搜索" }));
    expect(push).toHaveBeenCalledWith("/collections?search=%E5%85%AC%E5%9B%AD");

    fireEvent.change(screen.getByRole("combobox", { name: "城市" }), {
      target: { value: "pending" },
    });
    expect(push).toHaveBeenCalledWith("/collections?city_group=pending");
  });

  it("renders malicious titles as text rather than HTML", async () => {
    mockBootstrap({
      ...filledPage,
      items: [{ ...baseItem, title: "<img src=x onerror=alert(1)>" }],
    });
    const { container } = render(<CollectionsExperience />);

    expect(
      await screen.findByText("<img src=x onerror=alert(1)>"),
    ).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("opens details, saves the selected item, deletes it, and restores it", async () => {
    currentQuery = `item=${baseItem.id}`;
    let currentPage = filledPage;
    let currentDetail = { item: baseItem, sources: [] };
    const patchBodies: Array<{
      expected_version: number;
      changes: {
        title: string;
        city_hint: string;
        district: string;
        address: string;
        tags: string[];
      };
    }> = [];
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) return currentPage as never;
        if (path.endsWith("/restore")) {
          const restored = {
            ...currentDetail.item,
            status: "active",
            version: currentDetail.item.version + 1,
          };
          currentPage = { ...filledPage, items: [restored] };
          currentDetail = { item: restored, sources: [] };
          return restored as never;
        }
        if (options?.method === "DELETE") {
          const deleted = {
            ...currentDetail.item,
            status: "deleted",
            version: currentDetail.item.version + 1,
          };
          currentPage = emptyPage;
          currentDetail = { item: deleted, sources: [] };
          return deleted as never;
        }
        if (options?.method === "PATCH") {
          const body = JSON.parse(String(options.body)) as (typeof patchBodies)[number];
          patchBodies.push(body);
          const updated = {
            ...currentDetail.item,
            ...body.changes,
            version: currentDetail.item.version + 1,
          };
          currentPage = { ...filledPage, items: [updated] };
          currentDetail = { item: updated, sources: [] };
          return updated as never;
        }
        return currentDetail as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    const title = await within(dialog).findByRole("textbox", { name: "名称" });
    await userEvent.clear(title);
    await userEvent.type(title, "深圳湾海滨公园");
    await userEvent.click(within(dialog).getByRole("button", { name: "保存修改" }));
    expect(await screen.findByText(/Agent 与收藏库会读取同一条数据/)).toBeInTheDocument();
    expect(patchBodies[0]).toEqual({
      expected_version: 1,
      changes: {
        title: "深圳湾海滨公园",
        city_hint: "深圳",
        district: "南山区",
        address: "滨海大道",
        business_district: "后海",
        landmark: "深圳湾",
        metro_station: "深圳湾公园站",
        tags: ["公园", "散步"],
      },
    });

    const tags = within(dialog).getByRole("textbox", { name: "标签" });
    await userEvent.clear(tags);
    await userEvent.type(tags, "海边、夜景");
    await userEvent.click(within(dialog).getByRole("button", { name: "保存修改" }));
    await waitFor(() => expect(patchBodies).toHaveLength(2));
    expect(patchBodies[1].changes.tags).toEqual(["海边", "夜景"]);

    await userEvent.clear(tags);
    await userEvent.click(within(dialog).getByRole("button", { name: "保存修改" }));
    await waitFor(() => expect(patchBodies).toHaveLength(3));
    expect(patchBodies[2].changes.tags).toEqual([]);

    await userEvent.click(within(dialog).getByRole("button", { name: "删除收藏" }));
    expect(await screen.findByRole("button", { name: "恢复" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "恢复" }));
    expect(await screen.findByText("收藏已恢复到删除前的准确状态。")).toBeInTheDocument();
  });

  it("preserves a one-day exact session inside a multi-day effective range", async () => {
    currentQuery = `item=${eventItem.id}`;
    const bodies: Array<{
      expected_version: number;
      changes: Record<string, unknown>;
    }> = [];
    const confirmed = {
      ...eventItem,
      uncertainties: [],
      status: "active",
      version: 2,
      planning_eligible: true,
      planning_exclusion_reason: null,
    };
    let currentItem: Record<string, unknown> = eventItem;
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) {
          return { ...filledPage, items: [currentItem] } as never;
        }
        if (options?.method === "PATCH") {
          bodies.push(JSON.parse(String(options.body)));
          currentItem = confirmed;
          return confirmed as never;
        }
        return { item: currentItem, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByLabelText("活动有效开始日期"),
    ).toHaveValue("2026-08-02");
    expect(
      within(dialog).getByLabelText("活动有效结束日期"),
    ).toHaveValue("2026-08-04");
    const startDate = within(dialog).getByLabelText("活动有效开始日期");
    const endDate = within(dialog).getByLabelText("活动有效结束日期");
    const startTime = within(dialog).getByLabelText("具体开始时间");
    const endTime = within(dialog).getByLabelText("具体结束时间");
    expect(startDate).toHaveAttribute("type", "date");
    expect(endDate).toHaveAttribute("type", "date");
    expect(startTime).toHaveAttribute("type", "time");
    expect(endTime).toHaveAttribute("type", "time");
    expect(startTime).toHaveValue("15:30");
    expect(endTime).toHaveValue("20:00");
    expect(within(dialog).getByText(/以下是模型建议/)).toBeInTheDocument();

    await userEvent.click(
      within(dialog).getByRole("button", { name: "确认并保存" }),
    );
    expect(
      await screen.findByText("活动时间已确认，生成计划时会按时间与范围筛选。"),
    ).toBeInTheDocument();
    expect(bodies).toEqual([
      {
        expected_version: 1,
        changes: {
          event_start_date: "2026-08-02",
          event_end_date: "2026-08-04",
          event_start_at: "2026-08-02T07:30:00Z",
          event_end_at: "2026-08-02T12:00:00Z",
        },
      },
    ]);
    expect(bodies[0].changes).not.toHaveProperty("uncertainties");
    expect(bodies[0].changes).not.toHaveProperty("missing_fields");
    expect(within(dialog).getByText("版本 2")).toBeInTheDocument();
    expect(within(dialog).getByText("基础信息已确认")).toBeInTheDocument();
  });

  it("changes only HH:mm while preserving the original exact-session dates", async () => {
    currentQuery = `item=${eventItem.id}`;
    const bodies: Array<{ changes: Record<string, unknown> }> = [];
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) return filledPage as never;
        if (options?.method === "PATCH") {
          bodies.push(JSON.parse(String(options.body)));
          return { ...eventItem, uncertainties: [], version: 2 } as never;
        }
        return { item: eventItem, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await within(dialog).findByLabelText("具体开始时间"), {
      target: { value: "16:15" },
    });
    fireEvent.change(within(dialog).getByLabelText("具体结束时间"), {
      target: { value: "21:05" },
    });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "确认并保存" }),
    );
    expect(bodies[0].changes).toMatchObject({
      event_start_at: "2026-08-02T16:15:00+08:00",
      event_end_at: "2026-08-02T21:05:00+08:00",
    });
  });

  it("does not move an existing exact session when the effective range changes", async () => {
    currentQuery = `item=${eventItem.id}`;
    const bodies: Array<{ changes: Record<string, unknown> }> = [];
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) return filledPage as never;
        if (options?.method === "PATCH") {
          bodies.push(JSON.parse(String(options.body)));
          return { ...eventItem, event_end_date: "2026-08-03", version: 2 } as never;
        }
        return { item: eventItem, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(
      await within(dialog).findByLabelText("活动有效结束日期"),
      { target: { value: "2026-08-03" } },
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "确认并保存" }),
    );
    expect(bodies[0].changes).toMatchObject({
      event_end_date: "2026-08-03",
      event_start_at: eventItem.event_start_at,
      event_end_at: eventItem.event_end_at,
    });
  });

  it("preserves both original dates for an existing overnight exact session", async () => {
    const overnight = {
      ...eventItem,
      event_start_at: "2026-08-02T15:30:00Z",
      event_end_at: "2026-08-02T17:15:00Z",
    };
    currentQuery = `item=${overnight.id}`;
    const bodies: Array<{ changes: Record<string, unknown> }> = [];
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) return filledPage as never;
        if (options?.method === "PATCH") {
          bodies.push(JSON.parse(String(options.body)));
          return { ...overnight, uncertainties: [], version: 2 } as never;
        }
        return { item: overnight, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByLabelText("具体开始时间")).toHaveValue(
      "23:30",
    );
    expect(within(dialog).getByLabelText("具体结束时间")).toHaveValue("01:15");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "确认并保存" }),
    );
    expect(bodies[0].changes).toMatchObject({
      event_start_at: overnight.event_start_at,
      event_end_at: overnight.event_end_at,
    });
  });

  it("shows and submits only effective dates for a date-range Event", async () => {
    const oneDay = {
      ...eventItem,
      event_end_date: "2026-08-02",
      event_start_at: null,
      event_end_at: null,
    };
    currentQuery = `item=${oneDay.id}`;
    const bodies: Array<{ changes: Record<string, unknown> }> = [];
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) {
          return { ...filledPage, items: [oneDay] } as never;
        }
        if (options?.method === "PATCH") {
          bodies.push(JSON.parse(String(options.body)));
          return {
            ...oneDay,
            uncertainties: [],
            missing_fields: [],
            status: "active",
            version: 2,
            planning_eligible: true,
            planning_exclusion_reason: null,
          } as never;
        }
        return { item: oneDay, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByLabelText("活动有效开始日期");
    expect(within(dialog).queryByLabelText("具体场次日期")).toBeNull();
    expect(within(dialog).queryByLabelText("具体开始时间")).toBeNull();
    expect(within(dialog).queryByLabelText("具体结束时间")).toBeNull();
    expect(
      within(dialog).queryByText(/仅确认日期仍不能参与计划/),
    ).toBeNull();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "确认并保存" }),
    );
    expect(bodies[0].changes).toEqual({
      event_start_date: "2026-08-02",
      event_end_date: "2026-08-02",
    });
    expect(
      await screen.findByText("活动时间已确认，生成计划时会按时间与范围筛选。"),
    ).toBeInTheDocument();
  });

  it("keeps effective-date drafts independent from exact-session dates", async () => {
    const exactOnly = {
      ...eventItem,
      event_start_date: null,
      event_end_date: null,
      event_start_at: "2031-03-14T16:30:00Z",
      event_end_at: "2031-03-15T01:15:00Z",
    };
    currentQuery = `item=${exactOnly.id}`;
    vi.spyOn(apiClient, "request").mockImplementation(async (path) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path.startsWith("/api/v1/collections?")) {
        return { ...filledPage, items: [exactOnly] } as never;
      }
      return { item: exactOnly, sources: [] } as never;
    });

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByLabelText("活动有效开始日期"),
    ).toHaveValue("");
    expect(within(dialog).getByLabelText("活动有效结束日期")).toHaveValue("");
    expect(within(dialog).getByLabelText("具体开始时间")).toHaveValue("00:30");
    expect(within(dialog).getByLabelText("具体结束时间")).toHaveValue("09:15");
  });

  it("keeps a multi-day date-range Event on the existing date inputs", async () => {
    const dateOnly = {
      ...eventItem,
      event_start_at: null,
      event_end_at: null,
    };
    currentQuery = `item=${dateOnly.id}`;
    const bodies: Array<{ changes: Record<string, unknown> }> = [];
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) return filledPage as never;
        if (options?.method === "PATCH") {
          bodies.push(JSON.parse(String(options.body)));
          return { ...dateOnly, uncertainties: [], version: 2 } as never;
        }
        return { item: dateOnly, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByLabelText("活动有效开始日期"),
    ).toHaveValue("2026-08-02");
    expect(within(dialog).getByLabelText("活动有效结束日期")).toHaveValue(
      "2026-08-04",
    );
    expect(within(dialog).queryByLabelText("具体场次日期")).toBeNull();
    expect(within(dialog).queryByLabelText("具体开始时间")).toBeNull();
    expect(within(dialog).queryByLabelText("具体结束时间")).toBeNull();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "确认并保存" }),
    );
    expect(bodies[0].changes).toEqual({
      event_start_date: "2026-08-02",
      event_end_date: "2026-08-04",
    });
  });

  it("rejects an effective-range edit that excludes an existing exact session", async () => {
    currentQuery = `item=${eventItem.id}`;
    const request = vi.spyOn(apiClient, "request").mockImplementation(
      async (path) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) return filledPage as never;
        return { item: eventItem, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(
      await within(dialog).findByLabelText("活动有效开始日期"),
      { target: { value: "2026-08-03" } },
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "确认并保存" }),
    );
    expect(
      await screen.findByText(/具体场次不在活动有效日期范围内/),
    ).toBeInTheDocument();
    expect(
      request.mock.calls.filter(([, options]) => options?.method === "PATCH"),
    ).toHaveLength(0);
  });

  it("makes a date-range Event ready after confirming its current dates", async () => {
    const dateOnly = {
      ...eventItem,
      event_start_at: null,
      event_end_at: null,
      missing_fields: ["event_start_at", "event_end_at"],
      uncertainties: eventItem.uncertainties.slice(0, 2),
    };
    currentQuery = `item=${dateOnly.id}`;
    const bodies: Array<{ changes: Record<string, unknown> }> = [];
    const saved = {
      ...dateOnly,
      uncertainties: [],
      missing_fields: [],
      status: "active",
      version: 2,
      planning_eligible: true,
      planning_exclusion_reason: null,
    };
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) {
          return { ...filledPage, items: [saved] } as never;
        }
        if (options?.method === "PATCH") {
          bodies.push(JSON.parse(String(options.body)));
          return saved as never;
        }
        return { item: dateOnly, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByLabelText("活动有效开始日期");
    expect(within(dialog).queryByLabelText("具体开始时间")).toBeNull();
    await userEvent.click(
      within(dialog).getByRole("button", { name: "确认并保存" }),
    );
    expect(
      await screen.findByText("活动时间已确认，生成计划时会按时间与范围筛选。"),
    ).toBeInTheDocument();
    expect(bodies[0].changes).toEqual({
      event_start_date: "2026-08-02",
      event_end_date: "2026-08-04",
    });
    expect(within(dialog).getByText("基础信息已确认")).toBeInTheDocument();
  });

  it.each(["具体开始时间", "具体结束时间"])(
    "clears both exact-session fields when %s is cleared",
    async (clearedLabel) => {
      currentQuery = `item=${eventItem.id}`;
      const bodies: Array<{ changes: Record<string, unknown> }> = [];
      vi.spyOn(apiClient, "request").mockImplementation(
        async (path, options) => {
          if (path === "/api/v1/demo/sessions") return session as never;
          if (path.startsWith("/api/v1/collections?")) {
            return filledPage as never;
          }
          if (options?.method === "PATCH") {
            bodies.push(JSON.parse(String(options.body)));
            return {
              ...eventItem,
              event_start_at: null,
              event_end_at: null,
              version: 2,
            } as never;
          }
          return { item: eventItem, sources: [] } as never;
        },
      );

      render(<CollectionsExperience />);
      const dialog = await screen.findByRole("dialog");
      await userEvent.clear(await within(dialog).findByLabelText(clearedLabel));
      await userEvent.click(
        within(dialog).getByRole("button", { name: "确认并保存" }),
      );
      expect(bodies[0].changes).toMatchObject({
        event_start_at: null,
        event_end_at: null,
      });
    },
  );

  it.each([
    {
      name: "reversed dates",
      item: eventItem,
      edit: async (dialog: HTMLElement) => {
        fireEvent.change(
          await within(dialog).findByLabelText("活动有效结束日期"),
          { target: { value: "2026-08-01" } },
        );
      },
      message: "活动有效结束日期不能早于开始日期。",
    },
    {
      name: "an earlier same-day end time",
      item: { ...eventItem, event_end_date: "2026-08-02" },
      edit: async (dialog: HTMLElement) => {
        fireEvent.change(
          await within(dialog).findByLabelText("具体结束时间"),
          { target: { value: "15:00" } },
        );
      },
      message: "具体结束时间必须晚于具体开始时间。",
    },
  ])("rejects $name without sending a PATCH", async ({ item, edit, message }) => {
    currentQuery = `item=${item.id}`;
    const request = vi.spyOn(apiClient, "request").mockImplementation(
      async (path) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) {
          return { ...filledPage, items: [item] } as never;
        }
        return { item, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    await edit(dialog);
    await userEvent.click(
      within(dialog).getByRole("button", { name: "确认并保存" }),
    );
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(
      request.mock.calls.filter(([, options]) => options?.method === "PATCH"),
    ).toHaveLength(0);
  });

  it.each([
    ["start_at-only", "2026-08-02T07:30:00Z", null],
    ["end_at-only", null, "2026-08-02T12:00:00Z"],
  ])(
    "clears a historical %s session while confirming its date range",
    async (_name, eventStartAt, eventEndAt) => {
      const incomplete = {
        ...eventItem,
        event_end_date: "2026-08-02",
        event_start_at: eventStartAt,
        event_end_at: eventEndAt,
        missing_fields: [eventStartAt ? "event_end_at" : "event_start_at"],
      };
      currentQuery = `item=${incomplete.id}`;
      const bodies: Array<{ changes: Record<string, unknown> }> = [];
      vi.spyOn(apiClient, "request").mockImplementation(
        async (path, options) => {
          if (path === "/api/v1/demo/sessions") return session as never;
          if (path.startsWith("/api/v1/collections?")) {
            return filledPage as never;
          }
          if (options?.method === "PATCH") {
            bodies.push(JSON.parse(String(options.body)));
            return {
              ...incomplete,
              event_start_at: null,
              event_end_at: null,
              missing_fields: [],
              uncertainties: [],
              status: "active",
              version: 2,
              planning_eligible: true,
              planning_exclusion_reason: null,
            } as never;
          }
          return { item: incomplete, sources: [] } as never;
        },
      );

      render(<CollectionsExperience />);
      const dialog = await screen.findByRole("dialog");
      expect(
        await within(dialog).findByLabelText("活动有效开始日期"),
      ).toBeVisible();
      expect(within(dialog).queryByLabelText("具体开始时间")).toBeNull();
      expect(within(dialog).queryByLabelText("具体结束时间")).toBeNull();
      expect(within(dialog).getByText("活动时间待确认")).toBeInTheDocument();
      await userEvent.click(
        within(dialog).getByRole("button", { name: "确认并保存" }),
      );
      expect(bodies[0].changes).toEqual({
        event_start_date: "2026-08-02",
        event_end_date: "2026-08-02",
        event_start_at: null,
        event_end_at: null,
      });
    },
  );

  it.each([
    ["409", new ApiError("conflict", 409, "request-id")],
    ["422", new ApiError("request_failed", 422, "request-id")],
    ["timeout", new ApiError("timeout", null, null)],
    ["cancel", new ApiError("aborted", null, null)],
    ["network", new ApiError("network_error", null, null)],
  ])("keeps Event time edits after a %s response", async (_label, error) => {
    const dateOnly = {
      ...eventItem,
      event_start_at: null,
      event_end_at: null,
    };
    currentQuery = `item=${dateOnly.id}`;
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) return filledPage as never;
        if (options?.method === "PATCH") throw error;
        return { item: dateOnly, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    const endDate = await within(dialog).findByLabelText("活动有效结束日期");
    fireEvent.change(endDate, { target: { value: "2026-08-05" } });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "确认并保存" }),
    );
    await waitFor(() => expect(endDate).toHaveValue("2026-08-05"));
    expect(within(dialog).queryByLabelText("具体开始时间")).toBeNull();
    expect(
      screen.queryByText("活动时间已确认，生成计划时会按时间与范围筛选。"),
    ).toBeNull();
  });

  it("uses the server response to keep a time-confirmed Event without exact POI unplannable", async () => {
    currentQuery = `item=${eventItem.id}`;
    const timeConfirmed = {
      ...eventItem,
      uncertainties: [],
      version: 2,
      planning_eligible: false,
      planning_exclusion_reason: "location_unconfirmed",
    };
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) {
          return { ...filledPage, items: [timeConfirmed] } as never;
        }
        if (options?.method === "PATCH") return timeConfirmed as never;
        return { item: eventItem, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByLabelText("具体开始时间");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "确认并保存" }),
    );
    expect(
      await screen.findByText("活动时间已确认，准确地点确认后才可参与计划。"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText("确认准确地点后才能参与深圳计划"),
    ).toBeInTheDocument();
  });

  it("does not show Event confirmation controls for a Place detail", async () => {
    currentQuery = `item=${baseItem.id}`;
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) return filledPage as never;
        return { item: baseItem, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).queryByRole("button", { name: "确认并保存" }),
    ).toBeNull();
    expect(within(dialog).queryByLabelText("具体开始时间")).toBeNull();
  });

  it("shows differentiating candidate fields and supports none of the above", async () => {
    currentQuery = `item=${baseItem.id}`;
    const pending = {
      ...baseItem,
      title: "一尺花园",
      status: "pending_selection",
      planning_eligible: false,
      planning_exclusion_reason: "location_unconfirmed",
    };
    const candidatePage = {
      collection_item_id: pending.id,
      expected_version: 1,
      snapshot_fingerprint: "a".repeat(64),
      queried_at: "2026-07-27T00:00:00Z",
      candidates: [
        {
          provider: "amap",
          poi_id: "poi-one",
          name: "一尺花园",
          branch_name: "海上世界店",
          city_code: "shenzhen",
          district: "南山区",
          business_area: "海上世界",
          address: "太子路118号",
          poi_type: "cafe",
          matching_clues: ["name", "business_area"],
        },
      ],
    };
    const none = { ...pending, status: "pending_details", version: 2 };
    let currentItem = pending;
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) {
          return { ...filledPage, items: [currentItem] } as never;
        }
        if (path.endsWith("/poi-candidates")) return candidatePage as never;
        if (path.endsWith("/poi-selection")) {
          currentItem = none;
          return { items: [none], replayed: false } as never;
        }
        return { item: currentItem, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    expect(await screen.findByText(/海上世界店/)).toBeInTheDocument();
    expect(screen.getByText(/南山区 · 海上世界 · 太子路118号/)).toBeInTheDocument();
    expect(screen.getByText(/咖啡店/)).toBeInTheDocument();
    expect(screen.queryByText(/cafe/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /以上都不是/ }));
    expect(await screen.findByText(/原收藏已保留为待补充/)).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("keeps a version conflict recoverable", async () => {
    currentQuery = `item=${baseItem.id}`;
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) return filledPage as never;
        if (options?.method === "PATCH") {
          throw new ApiError("conflict", 409, "request-id");
        }
        return { item: baseItem, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      await within(dialog).findByRole("button", { name: "保存修改" }),
    );
    expect(await screen.findByText(/刚刚被更新.*草稿已保留/)).toBeInTheDocument();
  });

  it("does not report success when the API rejects a patch with 422", async () => {
    currentQuery = `item=${baseItem.id}`;
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) return filledPage as never;
        if (options?.method === "PATCH") {
          throw new ApiError("request_failed", 422, "request-id");
        }
        return { item: baseItem, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    const title = await within(dialog).findByRole("textbox", { name: "名称" });
    await userEvent.clear(title);
    await userEvent.type(title, "未保存草稿");
    await userEvent.click(
      await within(dialog).findByRole("button", { name: "保存修改" }),
    );
    expect(
      await screen.findByText(
        "补充信息未完成处理。你的草稿已保留，请检查后重试。",
      ),
    ).toBeInTheDocument();
    expect(title).toHaveValue("未保存草稿");
    expect(
      screen.queryByText(/Agent 与收藏库会读取同一条数据/),
    ).toBeNull();
  });

  it("loads existing candidates after a successful details save and confirms one", async () => {
    const pendingDetails = {
      ...baseItem,
      status: "pending_details",
      planning_eligible: false,
      planning_exclusion_reason: "location_unconfirmed",
    };
    currentQuery = `item=${pendingDetails.id}`;
    const pendingSelection = {
      ...pendingDetails,
      address: "福中一路",
      status: "pending_selection",
      version: 2,
    };
    const active = {
      ...pendingSelection,
      title: "一尺花园（海上世界店）",
      status: "active",
      version: 3,
      planning_eligible: true,
      planning_exclusion_reason: null,
    };
    const tagged = { ...active, tags: ["朋友聚餐"], version: 4 };
    const choices = {
      ...candidatePage(pendingDetails.id),
      expected_version: 2,
    };
    let currentItem: Record<string, unknown> = pendingDetails;
    let patchCount = 0;
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) {
          return { ...filledPage, items: [currentItem] } as never;
        }
        if (options?.method === "PATCH") {
          patchCount += 1;
          currentItem = patchCount === 1 ? pendingSelection : tagged;
          return currentItem as never;
        }
        if (path.endsWith("/poi-candidates")) return choices as never;
        if (path.endsWith("/poi-selection")) {
          currentItem = active;
          return { items: [active], replayed: false } as never;
        }
        return { item: currentItem, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    const address = await within(dialog).findByRole("textbox", { name: "公开地址" });
    await userEvent.clear(address);
    await userEvent.type(address, "福中一路");
    await userEvent.click(within(dialog).getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("修改已保存，请选择准确地点。")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /一尺花园 · 海上世界店/ }),
    );
    expect(await screen.findByText("准确地点已保存。")).toBeInTheDocument();
    expect(within(dialog).getByText("想去")).toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: "名称" })).toHaveValue(
      "一尺花园（海上世界店）",
    );

    await userEvent.type(
      within(dialog).getByRole("textbox", { name: "标签" }),
      "朋友聚餐",
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "保存修改" }));
    expect(
      await screen.findByText("修改已保存，Agent 与收藏库会读取同一条数据。"),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("想去")).toBeInTheDocument();
  });

  it("keeps a saved detail open and retries candidates without losing drafts", async () => {
    const pendingDetails = {
      ...baseItem,
      status: "pending_details",
      planning_eligible: false,
      planning_exclusion_reason: "location_unconfirmed",
    };
    const pendingSelection = {
      ...pendingDetails,
      landmark: "市民中心",
      status: "pending_selection",
      version: 2,
    };
    currentQuery = `item=${pendingDetails.id}`;
    let candidateLoads = 0;
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) {
          return { ...filledPage, items: [pendingSelection] } as never;
        }
        if (options?.method === "PATCH") return pendingSelection as never;
        if (path.endsWith("/poi-candidates")) {
          candidateLoads += 1;
          if (candidateLoads === 1) {
            throw new ApiError("timeout", null, null);
          }
          return {
            ...candidatePage(pendingSelection.id),
            expected_version: 2,
          } as never;
        }
        return { item: pendingDetails, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    const landmark = await within(dialog).findByRole("textbox", {
      name: "地标",
    });
    await userEvent.clear(landmark);
    await userEvent.type(landmark, "市民中心");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "保存修改" }),
    );

    expect(
      await screen.findByText(/地点候选暂时没有加载完成/),
    ).toBeInTheDocument();
    expect(landmark).toHaveValue("市民中心");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "重新加载候选" }),
    );
    expect(
      await within(dialog).findByRole("button", {
        name: /一尺花园 · 海上世界店/,
      }),
    ).toBeInTheDocument();
    expect(candidateLoads).toBe(2);
  });

  it("reuses the candidate idempotency key after an uncertain failure", async () => {
    currentQuery = `item=${baseItem.id}`;
    const pending = { ...baseItem, status: "pending_selection" };
    const candidatePage = {
      collection_item_id: pending.id,
      expected_version: 1,
      snapshot_fingerprint: "b".repeat(64),
      queried_at: "2026-07-27T00:00:00Z",
      candidates: [
        {
          provider: "amap",
          poi_id: "poi-one",
          name: "一尺花园",
          branch_name: "海上世界店",
          city_code: "shenzhen",
          district: "南山区",
          business_area: "海上世界",
          address: "太子路118号",
          poi_type: "cafe",
          matching_clues: [],
        },
      ],
    };
    const bodies: string[] = [];
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path, options) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) {
          return { ...filledPage, items: [pending] } as never;
        }
        if (path.endsWith("/poi-candidates")) return candidatePage as never;
        if (path.endsWith("/poi-selection")) {
          bodies.push(String(options?.body));
          if (bodies.length === 1) throw new ApiError("network_error", null, null);
          return {
            items: [{ ...pending, status: "pending_details", version: 2 }],
            replayed: false,
          } as never;
        }
        return { item: pending, sources: [] } as never;
      },
    );

    render(<CollectionsExperience />);
    const none = await screen.findByRole("button", { name: /以上都不是/ });
    await userEvent.click(none);
    await screen.findByText("收藏库暂时没有加载完成。");
    await userEvent.click(none);
    await screen.findByText(/原收藏已保留为待补充/);
    expect(JSON.parse(bodies[0]).idempotency_key).toBe(
      JSON.parse(bodies[1]).idempotency_key,
    );
  });

  it.each([
    ["success", null],
    ["failure", new ApiError("conflict", 409, "late-a")],
  ])(
    "does not let a late A save %s overwrite the newly opened B detail",
    async (_outcome, lateError) => {
      const itemB = {
        ...baseItem,
        id: "col_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        title: "收藏 B",
      };
      const late = deferred<typeof baseItem>();
      currentQuery = `item=${baseItem.id}`;
      vi.spyOn(apiClient, "request").mockImplementation(
        async (path, options) => {
          if (path === "/api/v1/demo/sessions") return session as never;
          if (path.startsWith("/api/v1/collections?")) {
            return { ...filledPage, items: [baseItem, itemB], total: 2 } as never;
          }
          if (path === `/api/v1/collections/${baseItem.id}`) {
            if (options?.method === "PATCH") return late.promise as never;
            return { item: baseItem, sources: [] } as never;
          }
          if (path === `/api/v1/collections/${itemB.id}`) {
            return { item: itemB, sources: [] } as never;
          }
          throw new Error(`unexpected request: ${path}`);
        },
      );

      const view = render(<CollectionsExperience />);
      const dialog = await screen.findByRole("dialog");
      await userEvent.click(
        await within(dialog).findByRole("button", { name: "保存修改" }),
      );
      currentQuery = `item=${itemB.id}`;
      view.rerender(<CollectionsExperience />);
      expect(
        await within(dialog).findByRole("textbox", { name: "名称" }),
      ).toHaveValue("收藏 B");

      await act(async () => {
        if (lateError) late.reject(lateError);
        else late.resolve({ ...baseItem, title: "迟到的收藏 A", version: 2 });
        await Promise.resolve();
      });
      expect(within(dialog).getByRole("textbox", { name: "名称" })).toHaveValue(
        "收藏 B",
      );
      expect(screen.queryByText(/Agent 与收藏库会读取同一条数据/)).toBeNull();
      expect(screen.queryByText(/刚刚被更新/)).toBeNull();
      expect(
        within(dialog).getByRole("button", { name: "保存修改" }),
      ).toBeEnabled();
    },
  );

  it.each(["delete", "restore", "selection"] as const)(
    "keeps B untouched when A %s completes late",
    async (operation) => {
      const itemA =
        operation === "restore"
          ? { ...baseItem, status: "deleted" }
          : operation === "selection"
            ? {
                ...baseItem,
                title: "一尺花园",
                status: "pending_selection",
                planning_eligible: false,
              }
            : baseItem;
      const itemB = {
        ...baseItem,
        id: "col_cccccccccccccccccccccccccccccccc",
        title: "收藏 B",
      };
      const late = deferred<object>();
      currentQuery = `item=${itemA.id}`;
      vi.spyOn(apiClient, "request").mockImplementation(
        async (path, options) => {
          if (path === "/api/v1/demo/sessions") return session as never;
          if (path.startsWith("/api/v1/collections?")) {
            return { ...filledPage, items: [itemA, itemB], total: 2 } as never;
          }
          if (path.endsWith("/poi-candidates")) {
            return candidatePage(itemA.id) as never;
          }
          if (
            path.endsWith("/poi-selection") ||
            path.endsWith("/restore") ||
            options?.method === "DELETE"
          ) {
            return late.promise as never;
          }
          if (path === `/api/v1/collections/${itemA.id}`) {
            return { item: itemA, sources: [] } as never;
          }
          if (path === `/api/v1/collections/${itemB.id}`) {
            return { item: itemB, sources: [] } as never;
          }
          throw new Error(`unexpected request: ${path}`);
        },
      );

      const view = render(<CollectionsExperience />);
      const dialog = await screen.findByRole("dialog");
      const action =
        operation === "delete"
          ? await within(dialog).findByRole("button", { name: "删除收藏" })
          : operation === "restore"
            ? await within(dialog).findByRole("button", { name: "恢复收藏" })
            : await within(dialog).findByRole("button", {
                name: /海上世界店/,
              });
      await userEvent.click(action);
      currentQuery = `item=${itemB.id}`;
      view.rerender(<CollectionsExperience />);
      expect(
        await within(dialog).findByRole("textbox", { name: "名称" }),
      ).toHaveValue("收藏 B");

      await act(async () => {
        if (operation === "selection") {
          late.resolve({
            items: [{ ...itemA, status: "active", version: 2 }],
            replayed: false,
          });
        } else {
          late.resolve({
            ...itemA,
            status: operation === "delete" ? "deleted" : "active",
            version: 2,
          });
        }
        await Promise.resolve();
      });
      expect(within(dialog).getByRole("textbox", { name: "名称" })).toHaveValue(
        "收藏 B",
      );
      expect(screen.queryByText(/收藏已删除|收藏已恢复|准确地点已保存/)).toBeNull();
      expect(screen.queryByText(/请选择准确地点/)).toBeNull();
      expect(
        within(dialog).getByRole("button", { name: "保存修改" }),
      ).toBeEnabled();
    },
  );

  it("replaces only the item URL after selection merges into another collection", async () => {
    const pending = {
      ...baseItem,
      title: "一尺花园",
      status: "pending_selection",
      planning_eligible: false,
    };
    const merged = {
      ...baseItem,
      id: "col_dddddddddddddddddddddddddddddddd",
      title: "一尺花园（海上世界店）",
      version: 4,
    };
    currentQuery = `search=%E8%8A%B1%E5%9B%AD&city_group=pending&page=2&item=${pending.id}`;
    vi.spyOn(apiClient, "request").mockImplementation(
      async (path) => {
        if (path === "/api/v1/demo/sessions") return session as never;
        if (path.startsWith("/api/v1/collections?")) {
          return { ...filledPage, items: [merged] } as never;
        }
        if (path.endsWith("/poi-candidates")) {
          return candidatePage(pending.id) as never;
        }
        if (path.endsWith("/poi-selection")) {
          return { items: [merged], replayed: false } as never;
        }
        if (path === `/api/v1/collections/${pending.id}`) {
          return { item: pending, sources: [] } as never;
        }
        if (path === `/api/v1/collections/${merged.id}`) {
          return { item: merged, sources: [] } as never;
        }
        throw new Error(`unexpected request: ${path}`);
      },
    );

    const view = render(<CollectionsExperience />);
    const detailDialog = await screen.findByRole("dialog");
    await userEvent.click(
      await within(detailDialog).findByRole("button", {
        name: /海上世界店/,
      }),
    );
    expect(replace).toHaveBeenCalledWith(
      `/collections?search=%E8%8A%B1%E5%9B%AD&city_group=pending&page=2&item=${merged.id}`,
      { scroll: false },
    );

    currentQuery = `search=%E8%8A%B1%E5%9B%AD&city_group=pending&page=2&item=${merged.id}`;
    view.rerender(<CollectionsExperience />);
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByRole("textbox", { name: "名称" }),
    ).toHaveValue("一尺花园（海上世界店）");

    view.unmount();
    render(<CollectionsExperience />);
    expect(
      await within(await screen.findByRole("dialog")).findByRole("textbox", {
        name: "名称",
      }),
    ).toHaveValue("一尺花园（海上世界店）");
  });

  it("ignores an older list response after the URL query changes", async () => {
    let resolveOld: (value: object) => void = () => undefined;
    const oldResponse = new Promise((resolve) => {
      resolveOld = resolve;
    });
    vi.spyOn(apiClient, "request")
      .mockResolvedValueOnce(session)
      .mockReturnValueOnce(oldResponse as never)
      .mockResolvedValueOnce({
        ...filledPage,
        items: [{ ...baseItem, title: "新的筛选结果" }],
      });
    const view = render(<CollectionsExperience />);
    await waitFor(() => expect(apiClient.request).toHaveBeenCalledTimes(2));

    currentQuery = "search=new";
    view.rerender(<CollectionsExperience />);
    expect(await screen.findByText("新的筛选结果")).toBeInTheDocument();
    resolveOld({ ...filledPage, items: [{ ...baseItem, title: "迟到旧结果" }] });
    await Promise.resolve();
    expect(screen.queryByText("迟到旧结果")).not.toBeInTheDocument();
  });
});
