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

  it("shows differentiating candidate fields and supports none of the above", async () => {
    currentQuery = `item=${baseItem.id}`;
    const pending = {
      ...baseItem,
      title: "一尺花园",
      status: "pending_selection",
      planning_eligible: false,
      planning_exclusion_reason: "pending_confirmation",
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
    expect(await screen.findByText(/刚刚被更新，请刷新后继续/)).toBeInTheDocument();
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
    await userEvent.click(
      await within(dialog).findByRole("button", { name: "保存修改" }),
    );
    expect(
      await screen.findByText("收藏库暂时没有加载完成。"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Agent 与收藏库会读取同一条数据/),
    ).toBeNull();
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
