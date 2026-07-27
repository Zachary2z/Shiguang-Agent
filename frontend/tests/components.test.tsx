import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PrimaryNav } from "@/components/primary-nav";
import {
  RetryButton,
  StatusState,
} from "@/components/status-state";
import { TextField } from "@/components/text-field";

const usePathname = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => usePathname(),
}));

describe("foundation components", () => {
  beforeEach(() => usePathname.mockReturnValue("/collections"));

  it("uses links and marks only the current route", () => {
    render(<PrimaryNav />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(4);
    expect(screen.getByRole("link", { name: "收藏" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Agent" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it.each([
    ["loading", "正在准备"],
    ["empty", "这里还没有内容"],
    ["error", "暂时没有完成"],
    ["offline", "连接已断开"],
  ] as const)("renders the %s foundation state", (kind, title) => {
    render(<StatusState kind={kind} />);
    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
  });

  it("provides a working retry action", async () => {
    const retry = vi.fn();
    render(
      <StatusState
        kind="error"
        action={<RetryButton onRetry={retry} />}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "重新尝试" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("requires an accessible form label, name, and autocomplete", () => {
    render(
      <TextField label="称呼" name="displayName" autoComplete="name" />,
    );
    const input = screen.getByRole("textbox", { name: "称呼" });
    expect(input).toHaveAttribute("name", "displayName");
    expect(input).toHaveAttribute("autocomplete", "name");
  });
});
