import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ShareManagement,
  shareApiClient,
} from "@/components/share-management";

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

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => cleanup());

describe("ShareManagement", () => {
  it("creates and copies a one-time plaintext link", async () => {
    const request = vi
      .spyOn(shareApiClient, "request")
      .mockResolvedValueOnce(inactive)
      .mockResolvedValueOnce(active);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<ShareManagement planId="pln_example" csrfToken="csrf-token" />);

    await userEvent.click(
      await screen.findByRole("button", { name: "生成只读链接" }),
    );
    expect(request).toHaveBeenLastCalledWith("/api/v1/plans/pln_example/share", {
      method: "POST",
      csrfToken: "csrf-token",
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
      .mockResolvedValueOnce(active)
      .mockResolvedValueOnce(inactive);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<ShareManagement planId="pln_example" csrfToken="csrf-token" />);

    expect(
      await screen.findByText("链接仍有效；为安全起见，服务端不保存明文。"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "复制新链接" }),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "重建链接" }));
    expect(request).toHaveBeenLastCalledWith(
      "/api/v1/plans/pln_example/share/regenerate",
      { method: "POST", csrfToken: "csrf-token" },
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
