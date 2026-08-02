import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ShareManagement,
  shareApiClient,
} from "@/components/share-management";
import { ApiError } from "@/lib/api-client";

const inactive = {
  status: "inactive" as const,
  created_at: null,
  expires_at: null,
  share_url: null,
  created: false,
};
const active = {
  status: "active" as const,
  created_at: "2026-07-29T01:00:00Z",
  expires_at: "2026-08-05T10:00:00Z",
  share_url: "/share#new-secret-token",
  created: true,
};
const preview = {
  version: 1,
  confirmed_at: "2026-07-29T01:00:00Z",
  updated_at: "2026-07-29T01:00:00Z",
  start_at: "2026-07-30T02:00:00Z",
  end_at: "2026-07-30T08:00:00Z",
  origin_label: "福田区",
  items: [
    {
      title: "深圳博物馆",
      start_at: "2026-07-30T02:00:00Z",
      end_at: "2026-07-30T04:00:00Z",
      public_address: "福中路184号",
      visit_duration_seconds: 7200,
      transport_mode: "walking",
      travel_duration_seconds: 900,
      travel_distance_meters: 800,
      buffer_after_seconds: 600,
      price_amount: "20.00",
      price_currency: "CNY",
      source_label: "计划地点",
      risks: ["The opening hours need confirmation."],
      queried_at: "2026-07-29T00:00:00Z",
      map_url: "https://uri.amap.com/marker?position=114,22",
    },
  ],
  total_cost_amount: "20.00",
  total_cost_currency: "CNY",
  risks: ["Weather information is temporarily unavailable."],
  expires_at: "2026-08-06T08:00:00Z",
};

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => cleanup());

describe("ShareManagement", () => {
  it("creates and copies a one-time plaintext link", async () => {
    const request = vi
      .spyOn(shareApiClient, "request")
      .mockResolvedValueOnce(inactive)
      .mockResolvedValueOnce(preview)
      .mockResolvedValueOnce(active);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<ShareManagement planId="pln_example" csrfToken="csrf-token" />);

    await userEvent.click(
      await screen.findByRole("button", { name: "预览并生成链接" }),
    );
    expect(request).toHaveBeenLastCalledWith(
      "/api/v1/plans/pln_example/share/preview",
    );
    expect(await screen.findByText("深圳博物馆")).toBeInTheDocument();
    expect(screen.getByText("福中路184号")).toBeInTheDocument();
    expect(screen.getByText(/营业时间待确认/)).toBeInTheDocument();
    expect(screen.getByText(/天气信息暂时不可用/)).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/opening hours|Weather information/);
    expect(screen.getByText(/含公开路线入口/)).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "确认并生成链接" }),
    );
    expect(request).toHaveBeenLastCalledWith("/api/v1/plans/pln_example/share", {
      method: "POST",
      csrfToken: "csrf-token",
      headers: { "Idempotency-Key": expect.any(String) },
    });
    await userEvent.click(
      screen.getByRole("button", { name: "复制新链接" }),
    );
    expect(writeText).toHaveBeenCalledWith(
      "http://localhost:3000/share#new-secret-token",
    );
    expect(screen.getByRole("status")).toHaveTextContent("链接已复制");
  });

  it("shows hashed-only active state, regenerates with confirmation, and revokes", async () => {
    const hashedOnly = { ...active, share_url: null, created: false };
    const request = vi
      .spyOn(shareApiClient, "request")
      .mockResolvedValueOnce(hashedOnly)
      .mockResolvedValueOnce(preview)
      .mockResolvedValueOnce(active)
      .mockResolvedValueOnce(inactive);
    render(<ShareManagement planId="pln_example" csrfToken="csrf-token" />);

    expect(
      await screen.findByText("链接仍有效；为安全起见，服务端不保存明文。"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "复制新链接" }),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "重建链接" }));
    await userEvent.click(
      await screen.findByRole("button", {
        name: "确认重建并使旧链接失效",
      }),
    );
    expect(request).toHaveBeenLastCalledWith(
      "/api/v1/plans/pln_example/share/regenerate",
      {
        method: "POST",
        csrfToken: "csrf-token",
        headers: { "Idempotency-Key": expect.any(String) },
      },
    );
    await userEvent.click(screen.getByRole("button", { name: "撤销分享" }));
    await waitFor(() =>
      expect(request).toHaveBeenLastCalledWith(
        "/api/v1/plans/pln_example/share",
        { method: "DELETE", csrfToken: "csrf-token" },
      ),
    );
    expect(screen.getByRole("status")).toHaveTextContent("旧链接立即失效");
  });

  it("reuses one idempotency key after an uncertain regenerate result", async () => {
    const request = vi
      .spyOn(shareApiClient, "request")
      .mockResolvedValueOnce({ ...active, share_url: null, created: false })
      .mockResolvedValueOnce(preview)
      .mockRejectedValueOnce(new ApiError("network_error", null, null))
      .mockResolvedValueOnce(active);
    render(<ShareManagement planId="pln_example" csrfToken="csrf-token" />);

    await userEvent.click(await screen.findByRole("button", { name: "重建链接" }));
    const confirm = await screen.findByRole("button", {
      name: "确认重建并使旧链接失效",
    });
    await userEvent.click(confirm);
    await screen.findByText("分享状态暂时不可用，请稍后重试。");
    await userEvent.click(confirm);

    await waitFor(() => expect(request).toHaveBeenCalledTimes(4));
    const firstOptions = request.mock.calls[2][1];
    const retryOptions = request.mock.calls[3][1];
    expect(firstOptions?.headers).toEqual(retryOptions?.headers);
  });

  it("exposes accessible busy state and disables mutations while loading", () => {
    vi.spyOn(shareApiClient, "request").mockImplementation(
      () => new Promise(() => undefined),
    );
    render(<ShareManagement planId="pln_example" csrfToken="csrf-token" />);
    expect(
      screen.getByRole("region", { name: "把确认版本交给同行的人" }),
    ).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("status")).toHaveTextContent("正在更新分享状态");
  });
});
