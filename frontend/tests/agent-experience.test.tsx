import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentExperience } from "@/components/agent-experience";

const { request, connect } = vi.hoisted(() => ({
  request: vi.fn(),
  connect: vi.fn(),
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>(
    "@/lib/api-client",
  );
  return {
    ...actual,
    apiClient: { request },
  };
});

vi.mock("@/lib/sse-client", () => ({
  sseClient: { connect },
}));

const session = {
  session_id: "ses_0123456789abcdef0123456789abcdef",
  csrf_token: "runtime-only-csrf",
  resumed: false,
};

describe("Agent experience", () => {
  afterEach(cleanup);

  beforeEach(() => {
    request.mockReset();
    connect.mockReset();
    request
      .mockResolvedValueOnce(session)
      .mockResolvedValueOnce({ messages: [] });
    connect.mockReturnValue({
      cancel: vi.fn(),
      closed: Promise.resolve(),
    });
  });

  it("establishes a session and gives clear empty/file feedback", async () => {
    const user = userEvent.setup();
    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(
      screen.getByText("写下一个地点、粘贴链接，或选择一张截图。"),
    ).toBeInTheDocument();

    const invalid = new File(["plain"], "notes.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText("添加截图"), {
      target: { files: [invalid] },
    });
    expect(
      screen.getByText("请选择 JPEG、PNG 或 WebP 图片。"),
    ).toBeInTheDocument();
  });

  it("waits for terminal SSE then renders malicious backend text literally", async () => {
    const user = userEvent.setup();
    request
      .mockResolvedValueOnce({
        message_id: "msg_0123456789abcdef0123456789abcdef",
        trace_id: "trc_0123456789abcdef0123456789abcdef",
        input_type: "text",
        run_status: "queued",
        events_url:
          "/api/v1/agent-runs/trc_0123456789abcdef0123456789abcdef/events",
        result_url:
          "/api/v1/agent-runs/trc_0123456789abcdef0123456789abcdef/result",
        replayed: false,
      })
      .mockResolvedValueOnce({
        message_id: "msg_0123456789abcdef0123456789abcdef",
        trace_id: "trc_0123456789abcdef0123456789abcdef",
        input_type: "text",
        run_status: "succeeded",
        extraction: { outcome: "candidates", missing_fields: [], recovery_suggestions: [] },
        collections: [
          {
            id: "col_0123456789abcdef0123456789abcdef",
            title: "<img src=x onerror=alert(1)>",
            kind: "place",
            city_hint: "深圳",
            city_pending: false,
            district: "南山区",
            address: null,
            tags: [],
            missing_fields: [],
            uncertainties: [],
            status: "active",
            version: 1,
          },
        ],
        recovery_actions: [],
        error_code: null,
        tool_steps: [],
      });
    connect.mockImplementation((options: {
      onEvent: (event: unknown) => void;
    }) => {
      window.setTimeout(
        () =>
          options.onEvent({
            id: "4",
            event: "run.completed",
            sequence: 4,
            data: { summary: { status: "succeeded" } },
          }),
        0,
      );
      return { cancel: vi.fn(), closed: new Promise<void>(() => {}) };
    });

    const { container } = render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "深圳地点");
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });
});
