import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlansExperience } from "@/components/plans-experience";
import { apiClient } from "@/lib/api-client";
import { sseClient } from "@/lib/sse-client";

const session = { csrf_token: "csrf-token" };
const plan = {
  id: "pln_0123456789abcdef0123456789abcdef",
  root_plan_id: "pln_0123456789abcdef0123456789abcdef",
  parent_plan_id: null,
  version: 1,
  status: "draft",
  constraints: {
    start_at: "2026-07-29T02:00:00Z",
    end_at: "2026-07-29T10:00:00Z",
    area_districts: ["南山区"],
    area_labels: ["海上世界"],
    budget: null,
    pace: "balanced",
    transport_modes: ["transit"],
    include: [],
    exclude: [],
    collection_only: false,
  },
  adjustment_text: null,
  draft: {
    exclusions: [],
    options: [
      {
        role: "main",
        total_cost_amount: null,
        total_cost_currency: null,
        risks: ["The item price needs confirmation."],
        items: [
          {
            title: "海边咖啡",
            start_at: "2026-07-29T02:15:00Z",
            end_at: "2026-07-29T03:15:00Z",
            visit_duration_seconds: 3600,
            inbound_route: {
              duration_seconds: 900,
              distance_meters: 3200,
              transport_mode: "transit",
            },
            price_amount: null,
            price_currency: null,
            source: { kind: "collection_derived", source_label: null },
            selection_reason: "Selected first by stable ranking.",
            risks: ["The item price needs confirmation."],
          },
        ],
      },
      {
        role: "alternative",
        total_cost_amount: "88.00",
        total_cost_currency: "CNY",
        risks: [],
        items: [
          {
            title: "外部花园",
            start_at: "2026-07-29T03:00:00Z",
            end_at: "2026-07-29T04:00:00Z",
            visit_duration_seconds: 3600,
            inbound_route: {
              duration_seconds: 600,
              distance_meters: 900,
              transport_mode: "walking",
            },
            price_amount: "88.00",
            price_currency: "CNY",
            source: {
              kind: "external_place",
              source_label: "高德补充 · 未收藏",
            },
            selection_reason: "Stable alternative.",
            risks: [],
          },
        ],
      },
    ],
  },
  trace_id: "trc_0123456789abcdef0123456789abcdef",
  events_url: "/api/v1/agent-runs/trc_0123456789abcdef0123456789abcdef/events",
  result_url: "/api/v1/plans/pln_0123456789abcdef0123456789abcdef",
  error_code: null,
  is_current_version: true,
  versions: [
    {
      id: "pln_0123456789abcdef0123456789abcdef",
      version: 1,
      status: "draft",
      adjustment_text: null,
    },
  ],
  approval: null,
};

const confirmedPlan = {
  ...plan,
  status: "confirmed",
  versions: [{ ...plan.versions[0], status: "confirmed" }],
};

const execution = {
  plan_id: plan.id,
  items: [
    {
      id: "pit_0123456789abcdef0123456789abcdef",
      title: "海边咖啡",
      start_at: "2026-07-29T02:15:00Z",
      end_at: "2026-07-29T03:15:00Z",
      address: "南山区海上世界广场",
      collection_item_ids: ["col_0123456789abcdef0123456789abcdef"],
      is_external: false,
      status: "pending",
      navigation_uri: "geo:22.479400,113.918800?q=22.479400,113.918800%28poi-one%29",
    },
    {
      id: "pit_1123456789abcdef0123456789abcdef",
      title: "外部花园",
      start_at: "2026-07-29T03:30:00Z",
      end_at: "2026-07-29T04:30:00Z",
      address: null,
      collection_item_ids: [],
      is_external: true,
      status: "pending",
      navigation_uri: null,
    },
  ],
  feedback: null,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

const secondPlan = {
  ...confirmedPlan,
  id: "pln_1123456789abcdef0123456789abcdef",
  parent_plan_id: plan.id,
  version: 2,
  versions: [
    { ...plan.versions[0], status: "superseded" },
    {
      id: "pln_1123456789abcdef0123456789abcdef",
      version: 2,
      status: "confirmed",
      adjustment_text: "节奏轻松一点",
    },
  ],
};

const versionedPlan = {
  ...confirmedPlan,
  versions: secondPlan.versions,
};

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => cleanup());

function bootstrap(items: object[] = []) {
  return vi
    .spyOn(apiClient, "request")
    .mockResolvedValueOnce(session)
    .mockResolvedValueOnce({ items });
}

describe("PlansExperience", () => {
  it("collects required conditions and shows a confirmation card before generation", async () => {
    bootstrap();
    render(<PlansExperience />);

    expect(await screen.findByRole("heading", { name: "时间与范围" })).toBeInTheDocument();
    expect(screen.getByLabelText("预算（元，可留空）")).toHaveAttribute(
      "placeholder",
      "费用未知也可以生成",
    );
    expect(screen.getByLabelText("开始时间")).toHaveAttribute("name", "start_at");
    expect(screen.getByLabelText("结束时间")).toHaveAttribute("name", "end_at");
    expect(screen.getByLabelText("节奏")).toHaveAttribute("name", "pace");
    expect(screen.getByLabelText("主要交通")).toHaveAttribute(
      "name",
      "transport_mode",
    );
    expect(screen.getByLabelText("只使用我的收藏")).toHaveAttribute(
      "name",
      "collection_only",
    );
    await userEvent.click(screen.getByRole("button", { name: "检查生成条件" }));

    const card = screen.getByLabelText("生成前条件确认");
    expect(within(card).getByText("确认这次出发")).toBeInTheDocument();
    expect(within(card).getByText(/费用未知会明确标记/)).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "确认并生成" })).toBeInTheDocument();
  });

  it("renders main and alternative time rails with cost, route, source, and risk", async () => {
    bootstrap([plan]);
    render(<PlansExperience />);

    expect((await screen.findAllByText("海边咖啡")).length).toBeGreaterThan(0);
    expect(screen.getByText("未知")).toBeInTheDocument();
    expect(screen.getByText("来自收藏")).toBeInTheDocument();
    expect(screen.getByText(/公共交通 · 15 分钟 · 3.2 km/)).toBeInTheDocument();
    expect(screen.getAllByText("The item price needs confirmation.").length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("tab", { name: "备选 1" }));
    expect(screen.getAllByText("外部花园").length).toBeGreaterThan(0);
    expect(screen.getByText("高德补充 · 未收藏")).toBeInTheDocument();
    expect(screen.getByText("¥88.00")).toBeInTheDocument();
  });

  it("never labels a historical version as the current version", async () => {
    bootstrap([
      {
        ...plan,
        is_current_version: false,
        versions: [
          ...plan.versions,
          {
            id: "pln_1123456789abcdef0123456789abcdef",
            version: 2,
            status: "failed",
            adjustment_text: "换一个地点",
          },
        ],
      },
    ]);
    render(<PlansExperience />);

    expect(await screen.findByText("V1 · 历史版本")).toBeInTheDocument();
    expect(screen.queryByText("V1 · 当前版本")).not.toBeInTheDocument();
  });

  it("shows external supplement approval without treating it as confirmation", async () => {
    bootstrap([
      {
        ...plan,
        status: "waiting_approval",
        draft: null,
        approval: {
          id: "apr_0123456789abcdef0123456789abcdef",
          display_text: "允许一次只读外部地点搜索。",
          status: "pending",
          expires_at: "2026-07-29T02:15:00Z",
        },
      },
    ]);
    render(<PlansExperience />);

    expect(await screen.findByText("收藏还不足以拼成完整计划")).toBeInTheDocument();
    expect(screen.getByText(/不会自动收藏/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "不允许，使用现有收藏" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /明确确认/ })).not.toBeInTheDocument();
  });

  it("closes a rejected external supplement decision with the authoritative reason", async () => {
    const waitingPlan = {
      ...plan,
      status: "waiting_approval" as const,
      draft: null,
      approval: {
        id: "apr_0123456789abcdef0123456789abcdef",
        display_text: "允许一次只读外部地点搜索。",
        status: "pending" as const,
        expires_at: "2026-07-29T02:15:00Z",
      },
    };
    const failedPlan = {
      ...waitingPlan,
      status: "failed" as const,
      error_code: "ADD_COLLECTIONS",
      approval: { ...waitingPlan.approval, status: "rejected" as const },
    };
    vi.spyOn(apiClient, "request").mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path === "/api/v1/plans" && !options?.method) {
        return { items: [waitingPlan] } as never;
      }
      if (path.endsWith("/decision")) {
        return {
          trace_id: null,
          events_url: null,
          result_url: waitingPlan.result_url,
        } as never;
      }
      if (path === waitingPlan.result_url) return failedPlan as never;
      throw new Error(`unexpected ${path}`);
    });
    render(<PlansExperience />);

    await userEvent.click(
      await screen.findByRole("button", {
        name: "不允许，使用现有收藏",
      }),
    );
    expect(
      await screen.findByText(
        "当前没有可用于这次规划的收藏，请先补充并确认地点或活动信息。",
      ),
    ).toBeInTheDocument();
  });

  it("creates a new adjustment version and refreshes from its authoritative result", async () => {
    const callbacks: Array<(event: never) => void> = [];
    vi.spyOn(sseClient, "connect").mockImplementation((options) => {
      callbacks.push(options.onEvent as (event: never) => void);
      return { cancel: vi.fn(), closed: new Promise<void>(() => {}) };
    });
    vi.spyOn(apiClient, "request").mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path === "/api/v1/plans" && !options?.method) return { items: [plan] } as never;
      if (path.endsWith("/adjustments")) {
        return {
          base_plan_id: plan.id,
          trace_id: "trc_1123456789abcdef0123456789abcdef",
          events_url: "/api/v1/agent-runs/new/events",
        } as never;
      }
      if (path === `/api/v1/plans/${plan.id}`) {
        return {
          ...plan,
          versions: [
            ...plan.versions,
            {
              id: "pln_1123456789abcdef0123456789abcdef",
              version: 2,
              status: "draft",
              adjustment_text: "节奏轻松一点",
            },
          ],
        } as never;
      }
      if (path === "/api/v1/plans/pln_1123456789abcdef0123456789abcdef") {
        return {
          ...plan,
          id: "pln_1123456789abcdef0123456789abcdef",
          parent_plan_id: plan.id,
          version: 2,
          adjustment_text: "节奏轻松一点",
        } as never;
      }
      throw new Error(`unexpected ${path}`);
    });
    render(<PlansExperience />);
    await screen.findAllByText("海边咖啡");
    await userEvent.type(
      screen.getByRole("textbox", { name: "想怎么调整？" }),
      "节奏轻松一点",
    );
    await userEvent.click(screen.getByRole("button", { name: "生成新版本" }));
    expect(await screen.findByText("正在创建新版本")).toBeInTheDocument();

    callbacks[0]?.({
      id: "1",
      event: "run.completed",
      sequence: 1,
      data: { summary: { status: "succeeded" } },
    } as never);
    await waitFor(() => expect(screen.getByText("V2 · 当前版本")).toBeInTheDocument());
  });

  it("keeps the current version when an exact-place adjustment is unsupported", async () => {
    const callbacks: Array<(event: never) => void> = [];
    vi.spyOn(sseClient, "connect").mockImplementation((options) => {
      callbacks.push(options.onEvent as (event: never) => void);
      return { cancel: vi.fn(), closed: new Promise<void>(() => {}) };
    });
    vi.spyOn(apiClient, "request").mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path === "/api/v1/plans" && !options?.method) return { items: [plan] } as never;
      if (path.endsWith("/adjustments")) {
        return {
          base_plan_id: plan.id,
          trace_id: "trc_2123456789abcdef0123456789abcdef",
          events_url: "/api/v1/agent-runs/unsupported/events",
        } as never;
      }
      if (path === `/api/v1/plans/${plan.id}`) return plan as never;
      throw new Error(`unexpected ${path}`);
    });
    render(<PlansExperience />);
    await screen.findAllByText("海边咖啡");
    await userEvent.type(
      screen.getByRole("textbox", { name: "想怎么调整？" }),
      "把地点换成广州塔",
    );
    await userEvent.click(screen.getByRole("button", { name: "生成新版本" }));
    callbacks[0]?.({
      id: "1",
      event: "run.failed",
      sequence: 1,
      data: {
        summary: {
          status: "failed",
          error_code: "PLAN_ADJUSTMENT_UNSUPPORTED",
        },
      },
    } as never);

    expect(
      await screen.findByText("暂不支持直接调整精确地点，请新建计划修改活动范围。"),
    ).toBeInTheDocument();
    expect(screen.queryByText("V2 · 当前版本")).not.toBeInTheDocument();
    expect(screen.getByText("V1 · 当前版本")).toBeInTheDocument();
  });

  it("downloads the calendar, opens exact navigation, and submits selected visits", async () => {
    const requests = vi
      .spyOn(apiClient, "request")
      .mockResolvedValueOnce(session)
      .mockResolvedValueOnce({ items: [confirmedPlan] })
      .mockResolvedValueOnce(execution)
      .mockResolvedValueOnce({
        feedback: {
          id: "fdb_0123456789abcdef0123456789abcdef",
          plan_id: plan.id,
          revision: 1,
          completion_status: "partially_completed",
          visited_plan_item_ids: [execution.items[0].id],
          reason: null,
          preference_suggestion: {
            content: "是否要把本次完成情况作为以后计划的长期偏好依据？",
            confirmation_status: "pending",
          },
          created_at: "2026-07-29T12:00:00Z",
        },
        replayed: false,
      })
      .mockResolvedValueOnce({
        ...execution,
        items: [
          { ...execution.items[0], status: "visited" },
          { ...execution.items[1], status: "not_visited" },
        ],
        feedback: {
          id: "fdb_0123456789abcdef0123456789abcdef",
          plan_id: plan.id,
          revision: 1,
          completion_status: "partially_completed",
          visited_plan_item_ids: [execution.items[0].id],
          reason: null,
          preference_suggestion: {
            content: "是否要把本次完成情况作为以后计划的长期偏好依据？",
            confirmation_status: "pending",
          },
          created_at: "2026-07-29T12:00:00Z",
        },
      });
    render(<PlansExperience />);

    await userEvent.click(
      await screen.findByRole("button", { name: "查看路线、日历与完成反馈" }),
    );
    expect(await screen.findByRole("link", { name: /下载日历/ })).toHaveAttribute(
      "href",
      `/api/v1/plans/${plan.id}/calendar.ics`,
    );
    expect(screen.getByRole("link", { name: /打开地点/ })).toHaveAttribute(
      "href",
      execution.items[0].navigation_uri,
    );
    expect(screen.getByText(/没有准确 POI，不生成导航入口/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("radio", { name: /部分完成/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /海边咖啡/ }));
    await userEvent.click(
      screen.getByRole("checkbox", { name: /把一项明确偏好送到“我的”待确认/ }),
    );
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "候选类型" }),
      "pace_preference",
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: "候选内容" }),
      "以后默认使用轻松节奏",
    );
    const paceValue = screen.getByRole("combobox", { name: "结构化值" });
    expect(within(paceValue).getAllByRole("option")).toHaveLength(3);
    await userEvent.selectOptions(
      paceValue,
      "relaxed",
    );
    await userEvent.type(
      screen.getByRole("textbox", { name: "候选依据" }),
      "我在本次反馈中明确选择了这项候选",
    );
    await userEvent.click(screen.getByRole("button", { name: "保存完成反馈" }));

    await waitFor(() => expect(screen.getByText("完成反馈已保存。")).toBeInTheDocument());
    expect(screen.getByText("待确认的长期偏好建议")).toBeInTheDocument();
    expect(screen.getByText(/本阶段不会自动写入长期记忆/)).toBeInTheDocument();
    expect(requests).toHaveBeenNthCalledWith(
      4,
      `/api/v1/plans/${plan.id}/feedback`,
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining(execution.items[0].id),
      }),
    );
    const submittedBody = JSON.parse(
      (requests.mock.calls[3]?.[1]?.body as string) ?? "{}",
    ) as {
      completion_status?: string;
      visited_plan_item_ids?: string[];
      expected_revision?: number | null;
      preference_candidate?: {
        memory_type: string;
        content: string;
        value: string;
        evidence_summary: string;
      };
    };
    expect(submittedBody).toMatchObject({
      completion_status: "partially_completed",
      visited_plan_item_ids: [execution.items[0].id],
      expected_revision: null,
      preference_candidate: {
        memory_type: "pace_preference",
        content: "以后默认使用轻松节奏",
        value: "relaxed",
        evidence_summary: "我在本次反馈中明确选择了这项候选",
      },
    });
  });

  it("ignores a V1 execution response that arrives after switching to V2", async () => {
    const lateExecution = deferred<typeof execution>();
    vi.spyOn(apiClient, "request").mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path === "/api/v1/plans" && !options?.method) {
        return { items: [versionedPlan] } as never;
      }
      if (path === `/api/v1/plans/${plan.id}/execution`) {
        return lateExecution.promise as never;
      }
      if (path === `/api/v1/plans/${secondPlan.id}`) return secondPlan as never;
      throw new Error(`unexpected ${path}`);
    });
    render(<PlansExperience />);
    await userEvent.click(
      await screen.findByRole("button", { name: "查看路线、日历与完成反馈" }),
    );
    await userEvent.click(screen.getByRole("button", { name: /^V2/ }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^V2/ })).toHaveAttribute(
        "aria-current",
        "page",
      ),
    );

    await act(async () => lateExecution.resolve(execution));
    expect(screen.queryByRole("link", { name: /打开地点/ })).not.toBeInTheDocument();
    expect(screen.queryByText("这次计划完成得怎么样？")).not.toBeInTheDocument();
  });

  it("does not let a late V1 feedback response modify V2", async () => {
    const lateFeedback = deferred<{
      feedback: {
        id: string;
        plan_id: string;
        revision: number;
        completion_status: string;
        visited_plan_item_ids: string[];
        reason: null;
        preference_suggestion: null;
        created_at: string;
      };
    }>();
    vi.spyOn(apiClient, "request").mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path === "/api/v1/plans" && !options?.method) {
        return { items: [versionedPlan] } as never;
      }
      if (path === `/api/v1/plans/${plan.id}/execution`) return execution as never;
      if (path === `/api/v1/plans/${plan.id}/feedback`) {
        return lateFeedback.promise as never;
      }
      if (path === `/api/v1/plans/${secondPlan.id}`) return secondPlan as never;
      throw new Error(`unexpected ${path}`);
    });
    render(<PlansExperience />);
    await userEvent.click(
      await screen.findByRole("button", { name: "查看路线、日历与完成反馈" }),
    );
    await screen.findByText("这次计划完成得怎么样？");
    await userEvent.click(screen.getByRole("radio", { name: /部分完成/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /海边咖啡/ }));
    await userEvent.click(screen.getByRole("button", { name: "保存完成反馈" }));
    await userEvent.click(screen.getByRole("button", { name: /^V2/ }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^V2/ })).toHaveAttribute(
        "aria-current",
        "page",
      ),
    );

    await act(async () =>
      lateFeedback.resolve({
        feedback: {
          id: "fdb_2123456789abcdef0123456789abcdef",
          plan_id: plan.id,
          revision: 1,
          completion_status: "partially_completed",
          visited_plan_item_ids: [execution.items[0].id],
          reason: null,
          preference_suggestion: null,
          created_at: "2026-07-29T12:00:00Z",
        },
      }),
    );
    expect(screen.getByRole("button", { name: /^V2/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.queryByText("完成反馈已保存。")).not.toBeInTheDocument();
    expect(screen.queryByText("第 1 次记录")).not.toBeInTheDocument();
  });

  it("does not restore a late execution after starting a new plan", async () => {
    const lateExecution = deferred<typeof execution>();
    vi.spyOn(apiClient, "request").mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path === "/api/v1/plans" && !options?.method) {
        return { items: [confirmedPlan] } as never;
      }
      if (path === `/api/v1/plans/${plan.id}/execution`) {
        return lateExecution.promise as never;
      }
      throw new Error(`unexpected ${path}`);
    });
    render(<PlansExperience />);
    await userEvent.click(
      await screen.findByRole("button", { name: "查看路线、日历与完成反馈" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "新建计划" }));
    expect(await screen.findByRole("heading", { name: "时间与范围" })).toBeInTheDocument();

    await act(async () => lateExecution.resolve(execution));
    expect(screen.queryByRole("link", { name: /打开地点/ })).not.toBeInTheDocument();
    expect(screen.queryByText("这次计划完成得怎么样？")).not.toBeInTheDocument();
  });

  it("reuses the same feedback key after an uncertain network result", async () => {
    const submittedBodies: Array<{ idempotency_key: string }> = [];
    let submission = 0;
    vi.spyOn(apiClient, "request").mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path === "/api/v1/plans" && !options?.method) {
        return { items: [confirmedPlan] } as never;
      }
      if (path === `/api/v1/plans/${plan.id}/execution`) return execution as never;
      if (path === `/api/v1/plans/${plan.id}/feedback`) {
        submittedBodies.push(JSON.parse(String(options?.body)));
        submission += 1;
        if (submission === 1) throw new Error("uncertain network result");
        return {
          feedback: {
            id: "fdb_3123456789abcdef0123456789abcdef",
            plan_id: plan.id,
            revision: 1,
            completion_status: "partially_completed",
            visited_plan_item_ids: [execution.items[0].id],
            reason: null,
            preference_suggestion: null,
            created_at: "2026-07-29T12:00:00Z",
          },
        } as never;
      }
      throw new Error(`unexpected ${path}`);
    });
    render(<PlansExperience />);
    await userEvent.click(
      await screen.findByRole("button", { name: "查看路线、日历与完成反馈" }),
    );
    await screen.findByText("这次计划完成得怎么样？");
    await userEvent.click(screen.getByRole("radio", { name: /部分完成/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /海边咖啡/ }));
    await userEvent.click(screen.getByRole("button", { name: "保存完成反馈" }));
    await waitFor(() => expect(submittedBodies).toHaveLength(1));
    await userEvent.click(screen.getByRole("button", { name: "保存完成反馈" }));
    await waitFor(() => expect(submittedBodies).toHaveLength(2));

    expect(submittedBodies[0].idempotency_key).toBe(
      submittedBodies[1].idempotency_key,
    );
  });

  it("reuses the same creation key after an uncertain response", async () => {
    const submittedBodies: Array<{ idempotency_key: string }> = [];
    vi.spyOn(sseClient, "connect").mockReturnValue({
      cancel: vi.fn(),
      closed: new Promise<void>(() => {}),
    });
    let submissions = 0;
    vi.spyOn(apiClient, "request").mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path === "/api/v1/plans" && !options?.method) {
        return { items: [] } as never;
      }
      if (path === "/api/v1/plans" && options?.method === "POST") {
        submittedBodies.push(JSON.parse(String(options.body)));
        submissions += 1;
        if (submissions === 1) throw new Error("response lost");
        return {
          plan_id: plan.id,
          trace_id: plan.trace_id,
          events_url: plan.events_url,
          result_url: plan.result_url,
        } as never;
      }
      throw new Error(`unexpected ${path}`);
    });
    render(<PlansExperience />);

    await userEvent.click(
      await screen.findByRole("button", { name: "检查生成条件" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "确认并生成" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "重试同一生成请求" }),
    );

    expect(submittedBodies).toHaveLength(2);
    expect(submittedBodies[0].idempotency_key).toBe(
      submittedBodies[1].idempotency_key,
    );
  });

  it("uses a new creation key only after the input changes", async () => {
    const submittedBodies: Array<{ idempotency_key: string }> = [];
    vi.spyOn(apiClient, "request").mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path === "/api/v1/plans" && !options?.method) {
        return { items: [] } as never;
      }
      if (path === "/api/v1/plans" && options?.method === "POST") {
        submittedBodies.push(JSON.parse(String(options.body)));
        throw new Error("response lost");
      }
      throw new Error(`unexpected ${path}`);
    });
    render(<PlansExperience />);

    await userEvent.click(
      await screen.findByRole("button", { name: "检查生成条件" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "确认并生成" }));
    await screen.findByRole("button", { name: "重试同一生成请求" });
    await userEvent.click(screen.getByRole("button", { name: "返回修改" }));
    await userEvent.clear(screen.getByLabelText("活动范围"));
    await userEvent.type(screen.getByLabelText("活动范围"), "深圳湾");
    await userEvent.click(screen.getByRole("button", { name: "检查生成条件" }));
    await userEvent.click(screen.getByRole("button", { name: "确认并生成" }));

    expect(submittedBodies).toHaveLength(2);
    expect(submittedBodies[0].idempotency_key).not.toBe(
      submittedBodies[1].idempotency_key,
    );
  });

  it("reuses adjustment and confirmation keys after uncertain responses", async () => {
    const adjustmentBodies: Array<{ idempotency_key: string }> = [];
    const confirmationBodies: Array<{ idempotency_key: string }> = [];
    let adjustmentSubmissions = 0;
    let confirmationSubmissions = 0;
    vi.spyOn(sseClient, "connect").mockReturnValue({
      cancel: vi.fn(),
      closed: new Promise<void>(() => {}),
    });
    vi.spyOn(apiClient, "request").mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path === "/api/v1/plans" && !options?.method) {
        return { items: [plan] } as never;
      }
      if (path.endsWith("/adjustments")) {
        adjustmentBodies.push(JSON.parse(String(options?.body)));
        adjustmentSubmissions += 1;
        if (adjustmentSubmissions === 1) throw new Error("response lost");
        return {
          base_plan_id: plan.id,
          trace_id: "trc_1123456789abcdef0123456789abcdef",
          events_url: "/api/v1/agent-runs/adjust/events",
        } as never;
      }
      if (path.endsWith("/confirm")) {
        confirmationBodies.push(JSON.parse(String(options?.body)));
        confirmationSubmissions += 1;
        if (confirmationSubmissions === 1) throw new Error("response lost");
        return { plan: confirmedPlan } as never;
      }
      throw new Error(`unexpected ${path}`);
    });
    render(<PlansExperience />);
    await screen.findAllByText("海边咖啡");

    await userEvent.type(
      screen.getByRole("textbox", { name: "想怎么调整？" }),
      "节奏轻松一点",
    );
    await userEvent.click(screen.getByRole("button", { name: "生成新版本" }));
    await screen.findByText("计划暂时没有完成，请稍后重试。");
    await userEvent.click(screen.getByRole("button", { name: "生成新版本" }));
    expect(adjustmentBodies[0].idempotency_key).toBe(
      adjustmentBodies[1].idempotency_key,
    );

    await userEvent.click(screen.getByRole("button", { name: "停止等待" }));
    await userEvent.click(screen.getByRole("button", { name: "明确确认 V1" }));
    await screen.findByText("计划暂时没有完成，请稍后重试。");
    await userEvent.click(screen.getByRole("button", { name: "明确确认 V1" }));
    expect(confirmationBodies[0].idempotency_key).toBe(
      confirmationBodies[1].idempotency_key,
    );
  });

  it("recovers a broken SSE stream from the authoritative plan", async () => {
    let stateChange: ((state: "error") => void) | undefined;
    vi.spyOn(sseClient, "connect").mockImplementation((options) => {
      stateChange = options.onStateChange as (state: "error") => void;
      return { cancel: vi.fn(), closed: new Promise<void>(() => {}) };
    });
    const generating = { ...plan, status: "generating" as const, draft: null };
    vi.spyOn(apiClient, "request")
      .mockResolvedValueOnce(session)
      .mockResolvedValueOnce({ items: [generating] })
      .mockResolvedValueOnce(generating)
      .mockResolvedValueOnce(plan);
    render(<PlansExperience />);
    await waitFor(() => expect(stateChange).toBeDefined());

    act(() => stateChange?.("error"));
    expect(
      await screen.findByRole("button", { name: "刷新权威状态" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "刷新权威状态" }));
    expect((await screen.findAllByText("海边咖啡")).length).toBeGreaterThan(0);
  });

  it.each([
    [
      "EVENT_NOT_SEARCHABLE",
      "收藏中没有时间与地点均已确认的 Event；MVP 不会外部搜索活动。",
    ],
    [
      "LOCATION_UNCONFIRMED",
      "现有收藏的具体地点尚未确认，请先完成地点确认。",
    ],
    [
      "EVENT_TIME_UNKNOWN",
      "现有 Event 的具体开始和结束时间尚未确认，请先补充准确场次。",
    ],
    [
      "CITY_MISMATCH",
      "现有收藏位于其他城市，当前计划只会使用已确认的深圳收藏。",
    ],
    [
      "PLAN_PROVIDER_NOT_CONFIGURED",
      "计划 Provider 尚未配置，未生成替代或伪成功结果。",
    ],
  ])(
    "shows the authoritative %s failure reason instead of a generic success-like state",
    async (errorCode, expectedMessage) => {
    bootstrap([
      {
        ...plan,
        status: "failed",
        draft: null,
        error_code: errorCode,
      },
    ]);
    render(<PlansExperience />);

    expect(await screen.findByText(expectedMessage)).toBeInTheDocument();
    expect(screen.queryByText("这一版已确认")).not.toBeInTheDocument();
    },
  );
});
