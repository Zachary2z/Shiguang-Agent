import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PublicShareExperience } from "@/components/public-share-experience";
import type { PublicPlanShare } from "@/lib/share-contracts";

const active: PublicPlanShare = {
  status: "active",
  plan: {
    version: 2,
    confirmed_at: "2026-07-29T01:00:00Z",
    updated_at: "2026-07-29T02:00:00Z",
    start_at: "2026-07-30T02:00:00Z",
    end_at: "2026-07-30T10:00:00Z",
    origin_label: "南山区 · 海上世界",
    total_cost_amount: "88.00",
    total_cost_currency: "CNY",
    risks: ["Weather information is temporarily unavailable."],
    weather_status: "compatible",
    weather_source: "amap",
    weather_queried_at: "2026-07-29T01:30:00Z",
    weather_summary: "晴，28°C",
    expires_at: "2026-08-06T10:00:00Z",
    items: [
      {
        title: "海边咖啡",
        start_at: "2026-07-30T02:15:00Z",
        end_at: "2026-07-30T03:15:00Z",
        public_address: "南山区望海路",
        visit_duration_seconds: 3600,
        transport_mode: "transit",
        travel_duration_seconds: 900,
        travel_distance_meters: 3200,
        buffer_after_seconds: 1200,
        price_amount: "88.00",
        price_currency: "CNY",
        source_label: "计划地点",
        risks: ["The item price needs confirmation."],
        queried_at: "2026-07-29T01:30:00Z",
        map_url: "https://uri.amap.com/marker?position=113.9,22.4",
      },
    ],
  },
};

function respond(payload: PublicPlanShare) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => cleanup());

describe("PublicShareExperience", () => {
  it("loads anonymously without cookies or referrer and renders only the confirmed snapshot", async () => {
    const fetcher = vi.spyOn(globalThis, "fetch").mockImplementation(() => respond(active));
    render(<PublicShareExperience token="public bearer" />);

    expect(
      await screen.findByRole("heading", { level: 1, name: "海边咖啡" }),
    ).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/public/plan-share",
      expect.objectContaining({
        cache: "no-store",
        credentials: "omit",
        headers: { Authorization: "Share public bearer" },
        referrerPolicy: "no-referrer",
      }),
    );
    expect(screen.getByText("V2")).toBeInTheDocument();
    expect(screen.getByText("南山区望海路")).toBeInTheDocument();
    expect(screen.getByText(/晴，28°C.*amap/)).toBeInTheDocument();
    expect(screen.getByText("价格待确认。")).toBeInTheDocument();
    expect(screen.getByText("天气信息暂时不可用。")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/The item price|Weather information/);
    expect(screen.getByRole("link", { name: "查看路线" })).toHaveAttribute(
      "rel",
      "noreferrer",
    );
    expect(screen.queryByRole("button", { name: /编辑|确认|调整/ })).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/session|trace|收藏正文|用户姓名/);
  });

  it.each([
    ["cancelled", "行程已取消"],
    ["unavailable", "这份行程暂时无法查看"],
  ] as const)("renders the %s state without route details", async (status, heading) => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() =>
      respond({ status, plan: null }),
    );
    render(<PublicShareExperience token="token" />);
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.queryByText("海边咖啡")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "生成我的计划" })).toBeInTheDocument();
  });

  it("shows an announced loading state", () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      () => new Promise(() => undefined),
    );
    render(<PublicShareExperience token="token" />);
    expect(screen.getByRole("main")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveTextContent("正在读取只读行程");
  });
});
