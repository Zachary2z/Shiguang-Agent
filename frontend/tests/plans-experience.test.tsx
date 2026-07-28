import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlansExperience } from "@/components/plans-experience";
import { ApiError, apiClient } from "@/lib/api-client";
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
          plan_id: "pln_1123456789abcdef0123456789abcdef",
          trace_id: "trc_1123456789abcdef0123456789abcdef",
          events_url: "/api/v1/agent-runs/new/events",
          result_url: "/api/v1/plans/new",
        } as never;
      }
      if (path === "/api/v1/plans/new") {
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
    vi.spyOn(apiClient, "request").mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions") return session as never;
      if (path === "/api/v1/plans" && !options?.method) return { items: [plan] } as never;
      if (path.endsWith("/adjustments")) {
        throw new ApiError("request_failed", 422, "request-id");
      }
      throw new Error(`unexpected ${path}`);
    });
    render(<PlansExperience />);
    await screen.findAllByText("海边咖啡");
    await userEvent.type(
      screen.getByRole("textbox", { name: "想怎么调整？" }),
      "把地点换成广州塔",
    );
    await userEvent.click(screen.getByRole("button", { name: "生成新版本" }));

    expect(
      await screen.findByText("暂不支持直接调整精确地点，请新建计划修改活动范围。"),
    ).toBeInTheDocument();
    expect(screen.queryByText("V2 · 当前版本")).not.toBeInTheDocument();
    expect(screen.getByText("V1 · 当前版本")).toBeInTheDocument();
  });
});
