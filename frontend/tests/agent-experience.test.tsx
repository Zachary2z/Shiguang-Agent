import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AgentExperience } from "@/components/agent-experience";
import { ApiError } from "@/lib/api-client";

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

const accepted = {
  message_id: "msg_0123456789abcdef0123456789abcdef",
  trace_id: "trc_0123456789abcdef0123456789abcdef",
  input_type: "text",
  run_status: "queued",
  events_url:
    "/api/v1/agent-runs/trc_0123456789abcdef0123456789abcdef/events",
  result_url:
    "/api/v1/agent-runs/trc_0123456789abcdef0123456789abcdef/result",
  replayed: false,
};

function collection(
  id: string,
  title: string,
  status:
    | "active"
    | "pending_selection"
    | "pending_details"
    | "deleted" = "active",
  kind: "place" | "event" = "place",
) {
  return {
    id,
    title,
    kind,
    city_hint: "深圳",
    city_pending: false,
    district: "南山区",
    address: null,
    tags: [],
    missing_fields: [] as string[],
    uncertainties: [] as Array<{ field: string; reason: string }>,
    status,
    version: 1,
  };
}

function completedResult(collections: ReturnType<typeof collection>[]) {
  return {
    message_id: accepted.message_id,
    trace_id: accepted.trace_id,
    input_type: "text",
    run_status: "succeeded",
    extraction: {
      outcome: "candidates",
      missing_fields: [],
      recovery_suggestions: [],
    },
    collections,
    recovery_actions: [],
    error_code: null,
    tool_steps: [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

type MockSseOptions = {
  lastEventId?: number;
  onEvent: (event: {
    id: string;
    event: string;
    sequence: number;
    data: { summary?: { stage?: string; status?: string } };
  }) => void;
  onStateChange?: (state: string) => void;
};

function terminalEvent(
  options: MockSseOptions,
  sequence: number,
  event: "run.completed" | "run.failed" = "run.completed",
) {
  options.onEvent({
    id: String(sequence),
    event,
    sequence,
    data: { summary: { status: event === "run.failed" ? "failed" : "succeeded" } },
  });
}

function queueCompletedImport(
  collections: ReturnType<typeof collection>[],
  mutationResponses: Promise<ReturnType<typeof collection>>[] = [],
) {
  request
    .mockResolvedValueOnce(accepted)
    .mockResolvedValueOnce(completedResult(collections));
  for (const response of mutationResponses) {
    request.mockReturnValueOnce(response);
  }
  connect.mockImplementationOnce((options: {
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
}

async function submitAndShowCollections() {
  const user = userEvent.setup();
  render(<AgentExperience />);
  await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
  await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "两个地点");
  await user.click(screen.getByRole("button", { name: "发送" }));
  await screen.findByText("本次整理出 2 项收藏");
  return user;
}

describe("Agent experience", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

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

  it("keeps internal fields, tool states, and error codes out of the page", async () => {
    const user = userEvent.setup();
    const pending = collection(
      "col_0123456789abcdef0123456789abcdee",
      "待确认活动",
      "pending_details",
      "event",
    );
    pending.missing_fields = ["event_start_at"];
    pending.uncertainties = [{ field: "event_end_at", reason: "needs review" }];
    request
      .mockResolvedValueOnce(accepted)
      .mockResolvedValueOnce({
        ...completedResult([pending]),
        tool_steps: [
          {
            tool_name: "image_recognition",
            stage: "result_organizing",
            status: "failed",
            source: "user_submission",
            duration_ms: 10,
            error_code: "MODEL_INVALID_RESPONSE",
          },
        ],
      });
    connect.mockImplementationOnce((options: MockSseOptions) => {
      window.setTimeout(() => terminalEvent(options, 4), 0);
      return { cancel: vi.fn(), closed: new Promise<void>(() => {}) };
    });

    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "活动截图");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByRole("heading", { name: "待确认活动" });
    await user.click(screen.getByText("Agent 工具过程"));

    expect(screen.getByText(/活动具体开始时间/)).toBeInTheDocument();
    expect(screen.getByText(/活动具体结束时间/)).toBeInTheDocument();
    expect(screen.getByText(/失败/)).toBeInTheDocument();
    expect(screen.queryByText(/event_start_at|event_end_at/)).not.toBeInTheDocument();
    expect(screen.queryByText(/MODEL_INVALID_RESPONSE/)).not.toBeInTheDocument();
  });

  it("reuses the prepared input key after uncertain network delivery", async () => {
    const user = userEvent.setup();
    request
      .mockRejectedValueOnce(new ApiError("network_error", null, null))
      .mockResolvedValueOnce(accepted);
    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));

    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "深圳天文台");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByText("网络连接中断，请重试。");
    await user.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => {
      const submissions = request.mock.calls.filter(
        ([path, options]) =>
          String(path).endsWith("/messages") && options?.method === "POST",
      );
      expect(submissions).toHaveLength(2);
    });

    const submissions = request.mock.calls.filter(
      ([path, options]) =>
        String(path).endsWith("/messages") && options?.method === "POST",
    );
    expect(submissions).toHaveLength(2);
    const first = JSON.parse(String(submissions[0][1]?.body));
    const second = JSON.parse(String(submissions[1][1]?.body));
    expect(first.type).toBe("agent_text");
    expect(second.text).toBe(first.text);
    expect(second.idempotency_key).toBe(first.idempotency_key);
  });

  it("shows routed plan results from the authoritative run", async () => {
    const user = userEvent.setup();
    request
      .mockResolvedValueOnce(accepted)
      .mockResolvedValueOnce({
        ...completedResult([]),
        extraction: null,
        intent: "plan",
        question: null,
        plan_id: "pln_0123456789abcdef0123456789abcdef",
        memory_id: null,
      });
    connect.mockImplementationOnce((options: MockSseOptions) => {
      window.setTimeout(() => terminalEvent(options, 4), 0);
      return { cancel: vi.fn(), closed: new Promise<void>(() => {}) };
    });

    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "帮我安排时间");
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByRole("heading", { name: "计划任务" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看计划与方案" })).toHaveAttribute(
      "href",
      "/plans?plan=pln_0123456789abcdef0123456789abcdef",
    );
  });

  it("uses a new key when retrying an authoritative terminal failure", async () => {
    const user = userEvent.setup();
    const failedResult = {
      ...completedResult([]),
      run_status: "failed",
      error_code: "MODEL_INVALID_RESPONSE",
      recovery_actions: ["retry_later"],
    };
    request
      .mockResolvedValueOnce(accepted)
      .mockResolvedValueOnce(failedResult)
      .mockResolvedValueOnce(accepted);
    connect.mockImplementationOnce((options: {
      onEvent: (event: unknown) => void;
    }) => {
      window.setTimeout(
        () =>
          options.onEvent({
            id: "4",
            event: "run.failed",
            sequence: 4,
            data: { summary: { status: "failed" } },
          }),
        0,
      );
      return { cancel: vi.fn(), closed: new Promise<void>(() => {}) };
    });
    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));

    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "深圳天文台");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByText("识别没有完成，你可以补充文字、改发截图或重试。");
    await user.click(screen.getByRole("button", { name: "重试" }));

    const submissions = request.mock.calls.filter(
      ([path, options]) =>
        String(path).endsWith("/messages") && options?.method === "POST",
    );
    expect(submissions).toHaveLength(2);
    const first = JSON.parse(String(submissions[0][1]?.body));
    const second = JSON.parse(String(submissions[1][1]?.body));
    expect(second.idempotency_key).not.toBe(first.idempotency_key);
  });

  it("keeps screenshot and text together, submits both, and allows explicit removal", async () => {
    const user = userEvent.setup();
    request.mockResolvedValueOnce({ ...accepted, input_type: "image" });
    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));

    const input = screen.getByRole("textbox", { name: "收藏内容" });
    await user.type(input, "南山区这家分店");
    const image = new File(["jpeg"], "place.jpg", { type: "image/jpeg" });
    await user.upload(screen.getByLabelText("添加截图"), image);
    expect(input).toHaveValue("南山区这家分店");
    await user.type(input, "，靠近地铁");
    expect(screen.getByText("place.jpg")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "发送" }));
    const submission = request.mock.calls.find(
      ([path, options]) =>
        String(path).endsWith("/messages") && options?.method === "POST",
    );
    expect(submission).toBeDefined();
    const body = submission?.[1]?.body;
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get("text")).toBe("南山区这家分店，靠近地铁");
    expect((body as FormData).get("image")).toBe(image);
  });

  it("keeps a combined-input key across uncertainty and replaces it after image change", async () => {
    const user = userEvent.setup();
    request
      .mockRejectedValueOnce(new ApiError("network_error", null, null))
      .mockRejectedValueOnce(new ApiError("timeout", null, null))
      .mockResolvedValueOnce({ ...accepted, input_type: "image" });
    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));

    const input = screen.getByRole("textbox", { name: "收藏内容" });
    const firstImage = new File(["jpeg-one"], "first.jpg", { type: "image/jpeg" });
    await user.type(input, "同一份图片补充");
    await user.upload(screen.getByLabelText("添加截图"), firstImage);
    await user.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByText("网络连接中断，请重试。");
    await user.click(screen.getByRole("button", { name: "重试" }));
    await screen.findByText("上传等待超时，请检查网络后重试。");

    await user.click(screen.getByRole("button", { name: "补充文字" }));
    const replacement = new File(["jpeg-two"], "replacement.jpg", {
      type: "image/jpeg",
    });
    await user.upload(screen.getByLabelText("添加截图"), replacement);
    await user.click(screen.getByRole("button", { name: "发送" }));

    const submissions = request.mock.calls
      .filter(
        ([path, options]) =>
          String(path).endsWith("/messages") && options?.method === "POST",
      )
      .map((call) => call[1]?.body as FormData);
    expect(submissions).toHaveLength(3);
    expect(submissions[1].get("idempotency_key")).toBe(
      submissions[0].get("idempotency_key"),
    );
    expect(submissions[2].get("idempotency_key")).not.toBe(
      submissions[0].get("idempotency_key"),
    );
    expect(submissions.map((body) => body.get("text"))).toEqual([
      "同一份图片补充",
      "同一份图片补充",
      "同一份图片补充",
    ]);
    expect(submissions[0].get("image")).toBe(firstImage);
    expect(submissions[2].get("image")).toBe(replacement);
  });

  it("removes a selected screenshot without clearing typed text", async () => {
    const user = userEvent.setup();
    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    const input = screen.getByRole("textbox", { name: "收藏内容" });
    await user.type(input, "保留这段文字");
    await user.upload(
      screen.getByLabelText("添加截图"),
      new File(["jpeg"], "place.jpg", { type: "image/jpeg" }),
    );
    await user.click(screen.getByRole("button", { name: "删除截图" }));
    expect(input).toHaveValue("保留这段文字");
    expect(screen.queryByText("place.jpg")).toBeNull();
    await user.click(screen.getByRole("button", { name: "帮我安排时间" }));
    expect(input).toHaveValue("帮我安排时间");
    expect(input).toHaveFocus();
  });

  it("uses a new key after deleting a screenshot from a failed prepared input", async () => {
    const user = userEvent.setup();
    request
      .mockRejectedValueOnce(new ApiError("network_error", null, null))
      .mockResolvedValueOnce(accepted);
    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));

    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "保留文字");
    await user.upload(
      screen.getByLabelText("添加截图"),
      new File(["jpeg"], "place.jpg", { type: "image/jpeg" }),
    );
    await user.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByText("网络连接中断，请重试。");
    await user.click(screen.getByRole("button", { name: "补充文字" }));
    await user.click(screen.getByRole("button", { name: "删除截图" }));
    await user.click(screen.getByRole("button", { name: "发送" }));

    const submissions = request.mock.calls.filter(
      ([path, options]) =>
        String(path).endsWith("/messages") && options?.method === "POST",
    );
    const firstKey = (submissions[0][1]?.body as FormData).get("idempotency_key");
    const second = JSON.parse(String(submissions[1][1]?.body));
    expect(second.text).toBe("保留文字");
    expect(second.idempotency_key).not.toBe(firstKey);
  });

  it("creates a new submission identity only after the input changes", async () => {
    const user = userEvent.setup();
    request
      .mockRejectedValueOnce(new ApiError("timeout", null, null))
      .mockResolvedValueOnce(accepted);
    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    const input = screen.getByRole("textbox", { name: "收藏内容" });

    await user.type(input, "深圳天文台");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByText("上传等待超时，请检查网络后重试。");
    await user.click(screen.getByRole("button", { name: "补充文字" }));
    await user.type(input, " 西涌");
    await user.click(screen.getByRole("button", { name: "发送" }));

    const submissions = request.mock.calls.filter(
      ([path, options]) =>
        String(path).endsWith("/messages") && options?.method === "POST",
    );
    const first = JSON.parse(String(submissions[0][1]?.body));
    const second = JSON.parse(String(submissions[1][1]?.body));
    expect(second.idempotency_key).not.toBe(first.idempotency_key);
  });

  it("keeps submission gated until delayed conversation recovery finishes", async () => {
    const user = userEvent.setup();
    let resolveConversation:
      | ((value: { messages: never[] }) => void)
      | undefined;
    const delayedConversation = new Promise<{ messages: never[] }>((resolve) => {
      resolveConversation = resolve;
    });
    request.mockReset();
    request
      .mockResolvedValueOnce(session)
      .mockReturnValueOnce(delayedConversation)
      .mockResolvedValueOnce(accepted);
    render(<AgentExperience />);
    const input = screen.getByRole("textbox", { name: "收藏内容" });
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("button", { name: "处理中" })).toBeDisabled();

    resolveConversation?.({ messages: [] });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "发送" })).toBeEnabled(),
    );
    await user.type(input, "恢复完成后的新提交");
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(connect).toHaveBeenCalledTimes(1);
  });

  it("shows and independently edits, removes, and restores every collection", async () => {
    const user = userEvent.setup();
    const first = collection(
      "col_11111111111111111111111111111111",
      "深圳天文台",
    );
    const second = collection(
      "col_22222222222222222222222222222222",
      "西涌海滩",
      "pending_details",
    );
    request
      .mockResolvedValueOnce(accepted)
      .mockResolvedValueOnce(completedResult([first, second]))
      .mockResolvedValueOnce({ ...first, title: "深圳天文台 · 西涌", version: 2 })
      .mockResolvedValueOnce({ ...second, status: "deleted", version: 2 })
      .mockResolvedValueOnce({ ...second, status: "pending_details", version: 3 });
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
    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "两个地点");
    await user.click(screen.getByRole("button", { name: "发送" }));

    const firstCard = (await screen.findByText("深圳天文台")).closest("article");
    const secondCard = screen.getByText("西涌海滩").closest("article");
    expect(firstCard).not.toBeNull();
    expect(secondCard).not.toBeNull();
    expect(screen.getByText("本次整理出 2 项收藏")).toBeInTheDocument();

    await user.click(within(firstCard!).getByRole("button", { name: "修改" }));
    const title = within(firstCard!).getByRole("textbox", { name: "名称" });
    expect(title).toHaveAttribute("name", "collection_title");
    expect(title).toHaveAttribute("autocomplete", "off");
    await user.clear(title);
    await user.type(title, "深圳天文台 · 西涌");
    await user.click(within(firstCard!).getByRole("button", { name: "保存修改" }));
    await screen.findByText("深圳天文台 · 西涌");

    await user.click(within(secondCard!).getByRole("button", { name: "撤销" }));
    await user.click(
      within(secondCard!).getByRole("button", { name: "恢复收藏" }),
    );
    await waitFor(() =>
      expect(within(secondCard!).getByText("待补充")).toBeInTheDocument(),
    );

    const mainInput = screen.getByRole("textbox", { name: "收藏内容" });
    expect(mainInput).toHaveAttribute("name", "collection_input");
    expect(mainInput).toHaveAttribute("autocomplete", "off");
    await user.click(screen.getByRole("button", { name: "继续添加" }));
    await waitFor(() => expect(mainInput).toHaveFocus());
  });

  it("links a pending Event to the single collection time confirmation entry", async () => {
    const event = {
      ...collection(
        "col_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        "深圳音乐节",
        "pending_details",
        "event",
      ),
      uncertainties: [
        { field: "event_start_at", reason: "模型建议需要确认" },
      ],
    };
    queueCompletedImport([
      event,
      collection(
        "col_ffffffffffffffffffffffffffffffff",
        "深圳天文台",
      ),
    ]);
    await submitAndShowCollections();

    const card = screen.getByText(event.title).closest("article");
    expect(card).not.toBeNull();
    expect(
      within(card!).getByRole("link", { name: "确认活动时间" }),
    ).toHaveAttribute(
      "href",
      `/collections?item=${event.id}`,
    );
    expect(
      within(card!).queryByLabelText("准确开始时间"),
    ).toBeNull();
  });

  it("links only pending selection cards to the existing place chooser", async () => {
    const pending = collection(
      "col_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "<img src=x onerror=alert(1)>",
      "pending_selection",
    );
    const active = collection(
      "col_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "深圳天文台",
    );
    queueCompletedImport([pending, active]);
    const { container } = render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "两个地点");
    await user.click(screen.getByRole("button", { name: "发送" }));

    const pendingCard = (await screen.findByText(pending.title)).closest("article");
    const activeCard = screen.getByText(active.title).closest("article");
    expect(pendingCard).not.toBeNull();
    expect(activeCard).not.toBeNull();
    expect(
      within(pendingCard!).getByRole("link", { name: "选择地点" }),
    ).toHaveAttribute("href", `/collections?item=${pending.id}`);
    expect(
      within(activeCard!).queryByRole("link", { name: "选择地点" }),
    ).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it.each([
    ["B 撤销先完成、A 修改后完成", "undo-first"],
    ["A 修改先完成、B 撤销后完成", "edit-first"],
  ])(
    "keeps both collection updates when %s",
    async (_label, completionOrder) => {
      const first = collection(
        "col_44444444444444444444444444444444",
        "深圳天文台",
      );
      const second = collection(
        "col_55555555555555555555555555555555",
        "西涌海滩",
        "pending_details",
      );
      const edited = { ...first, title: "深圳天文台 · 西涌", version: 2 };
      const deleted = {
        ...second,
        status: "deleted" as const,
        version: 2,
      };
      const editResponse = deferred<typeof edited>();
      const undoResponse = deferred<typeof deleted>();
      queueCompletedImport(
        [first, second],
        [editResponse.promise, undoResponse.promise],
      );
      const user = await submitAndShowCollections();
      const firstCard = screen.getByText(first.title).closest("article");
      const secondCard = screen.getByText(second.title).closest("article");
      expect(firstCard).not.toBeNull();
      expect(secondCard).not.toBeNull();

      await user.click(within(firstCard!).getByRole("button", { name: "修改" }));
      const title = within(firstCard!).getByRole("textbox", { name: "名称" });
      await user.clear(title);
      await user.type(title, edited.title);
      await user.click(
        within(firstCard!).getByRole("button", { name: "保存修改" }),
      );
      await user.click(
        within(secondCard!).getByRole("button", { name: "撤销" }),
      );

      if (completionOrder === "undo-first") {
        await act(async () => undoResponse.resolve(deleted));
        await act(async () => editResponse.resolve(edited));
      } else {
        await act(async () => editResponse.resolve(edited));
        await act(async () => undoResponse.resolve(deleted));
      }

      expect(
        await screen.findByRole("heading", { name: edited.title }),
      ).toBeInTheDocument();
      expect(
        within(secondCard!).getByRole("button", { name: "恢复收藏" }),
      ).toBeInTheDocument();
    },
  );

  it("ignores a collection success that arrives after continuing", async () => {
    const first = collection(
      "col_66666666666666666666666666666666",
      "深圳天文台",
    );
    const second = collection(
      "col_77777777777777777777777777777777",
      "西涌海滩",
    );
    const deleted = { ...second, status: "deleted" as const, version: 2 };
    const undoResponse = deferred<typeof deleted>();
    queueCompletedImport([first, second], [undoResponse.promise]);
    const user = await submitAndShowCollections();
    const secondCard = screen.getByText(second.title).closest("article");
    expect(secondCard).not.toBeNull();

    await user.click(within(secondCard!).getByRole("button", { name: "撤销" }));
    await user.click(screen.getByRole("button", { name: "继续添加" }));
    await act(async () => undoResponse.resolve(deleted));

    expect(screen.queryByText("本次整理出 2 项收藏")).not.toBeInTheDocument();
    expect(screen.queryByText(second.title)).not.toBeInTheDocument();
    expect(
      screen.queryByText(`已撤销“${second.title}”，你可以单独恢复。`),
    ).not.toBeInTheDocument();
  });

  it("ignores an old collection failure after a new run starts", async () => {
    const first = collection(
      "col_88888888888888888888888888888888",
      "深圳天文台",
    );
    const second = collection(
      "col_99999999999999999999999999999999",
      "西涌海滩",
    );
    const undoResponse = deferred<ReturnType<typeof collection>>();
    queueCompletedImport([first, second], [undoResponse.promise]);
    request.mockResolvedValueOnce({
      ...accepted,
      message_id: "msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      trace_id: "trc_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      events_url:
        "/api/v1/agent-runs/trc_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/events",
      result_url:
        "/api/v1/agent-runs/trc_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/result",
    });
    const user = await submitAndShowCollections();
    const secondCard = screen.getByText(second.title).closest("article");
    expect(secondCard).not.toBeNull();

    await user.click(within(secondCard!).getByRole("button", { name: "撤销" }));
    const input = screen.getByRole("textbox", { name: "收藏内容" });
    await user.clear(input);
    await user.type(input, "新的收藏");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByRole("heading", { name: "正在识别" });
    await act(async () =>
      undoResponse.reject(new ApiError("network_error", null, null)),
    );

    expect(
      screen.getByRole("heading", { name: "正在识别" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("网络连接中断，请重试。")).not.toBeInTheDocument();
    expect(screen.queryByText("这次没有认出来")).not.toBeInTheDocument();
  });

  it("cancels the previous SSE connection before following a new run", async () => {
    const user = userEvent.setup();
    const firstCancel = vi.fn();
    request
      .mockResolvedValueOnce(accepted)
      .mockResolvedValueOnce(completedResult([
        collection("col_33333333333333333333333333333333", "第一项"),
      ]))
      .mockResolvedValueOnce({ ...accepted, trace_id: "trc_new" });
    connect
      .mockImplementationOnce((options: {
        onEvent: (event: unknown) => void;
      }) => {
        window.setTimeout(
          () =>
            options.onEvent({
              id: "4",
              event: "run.completed",
              sequence: 4,
              data: {},
            }),
          0,
        );
        return { cancel: firstCancel, closed: new Promise<void>(() => {}) };
      })
      .mockReturnValueOnce({
        cancel: vi.fn(),
        closed: new Promise<void>(() => {}),
      });
    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    const input = screen.getByRole("textbox", { name: "收藏内容" });
    await user.type(input, "第一项");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByRole("heading", { name: "第一项" });
    await user.clear(input);
    await user.type(input, "第二项");
    await user.click(screen.getByRole("button", { name: "发送" }));
    expect(firstCancel).toHaveBeenCalled();
  });

  it("reads a terminal event authoritatively and resumes from the last sequence when it is still running", async () => {
    const user = userEvent.setup();
    const running = {
      ...completedResult([]),
      run_status: "running",
      extraction: null,
    };
    const finalItem = collection(
      "col_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaab",
      "恢复后的收藏",
    );
    request
      .mockResolvedValueOnce(accepted)
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(completedResult([finalItem]));
    const observers: MockSseOptions[] = [];
    let activeConnections = 0;
    let maximumActiveConnections = 0;
    connect.mockImplementation((options: MockSseOptions) => {
      observers.push(options);
      activeConnections += 1;
      maximumActiveConnections = Math.max(
        maximumActiveConnections,
        activeConnections,
      );
      let cancelled = false;
      return {
        cancel: vi.fn(() => {
          if (cancelled) return;
          cancelled = true;
          activeConnections -= 1;
        }),
        closed: new Promise<void>(() => {}),
      };
    });

    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "慢任务");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(observers).toHaveLength(1));
    act(() => terminalEvent(observers[0], 4));
    await waitFor(() => expect(observers).toHaveLength(2), { timeout: 2_000 });
    expect(observers[1].lastEventId).toBe(4);

    act(() => {
      observers[1].onEvent({
        id: "4",
        event: "stage.changed",
        sequence: 4,
        data: { summary: { stage: "should_not_replay" } },
      });
      terminalEvent(observers[1], 5);
    });

    expect(
      await screen.findByRole("heading", { name: finalItem.title }),
    ).toBeInTheDocument();
    expect(screen.queryByText("should_not_replay")).not.toBeInTheDocument();
    expect(maximumActiveConnections).toBe(1);
  });

  it("recovers a terminal authoritative result after the SSE client exhausts reconnects", async () => {
    const user = userEvent.setup();
    const item = collection(
      "col_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbc",
      "断线后收藏",
    );
    request
      .mockResolvedValueOnce(accepted)
      .mockResolvedValueOnce(completedResult([item]));
    connect.mockReturnValueOnce({
      cancel: vi.fn(),
      closed: Promise.resolve(),
    });

    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "断线任务");
    await user.click(screen.getByRole("button", { name: "发送" }));

    expect(
      await screen.findByRole("heading", { name: item.title }),
    ).toBeInTheDocument();
    expect(connect).toHaveBeenCalledTimes(1);
  });

  it("recovers through the authoritative result when an SSE reader never settles", async () => {
    vi.useFakeTimers();
    const item = collection(
      "col_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaab",
      "长任务收藏",
    );
    const cancel = vi.fn();
    request.mockReset();
    request
      .mockResolvedValueOnce(session)
      .mockResolvedValueOnce({ messages: [{ ...accepted, run_status: "running" }] })
      .mockResolvedValueOnce(completedResult([item]));
    connect.mockReturnValueOnce({
      cancel,
      closed: new Promise<void>(() => {}),
    });

    render(<AgentExperience />);
    await act(async () => vi.advanceTimersByTimeAsync(0));
    expect(connect).toHaveBeenCalledTimes(1);

    await act(async () => vi.advanceTimersByTimeAsync(30_000));
    await act(async () => Promise.resolve());

    expect(cancel).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("heading", { name: item.title })).toBeInTheDocument();
  });

  it("bounds automatic re-observation and lets the user refresh the same run without another POST", async () => {
    const user = userEvent.setup();
    const running = {
      ...completedResult([]),
      run_status: "running",
      extraction: null,
    };
    const item = collection(
      "col_cccccccccccccccccccccccccccccccd",
      "人工恢复结果",
    );
    request
      .mockResolvedValueOnce(accepted)
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(completedResult([item]));
    const observers: MockSseOptions[] = [];
    connect.mockImplementation((options: MockSseOptions) => {
      observers.push(options);
      if (observers.length === 1) {
        options.onEvent({
          id: "2",
          event: "stage.changed",
          sequence: 2,
          data: { summary: { stage: "place_recognition" } },
        });
      }
      return {
        cancel: vi.fn(),
        closed: Promise.resolve(),
      };
    });

    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "后台任务");
    await user.click(screen.getByRole("button", { name: "发送" }));

    const refresh = await screen.findByRole(
      "button",
      { name: "刷新结果/继续等待" },
      { timeout: 4_500 },
    );
    expect(connect).toHaveBeenCalledTimes(3);
    expect(
      request.mock.calls.filter(([path]) => path === accepted.result_url),
    ).toHaveLength(3);

    await user.click(refresh);
    expect(
      await screen.findByRole(
        "heading",
        { name: item.title },
        { timeout: 2_000 },
      ),
    ).toBeInTheDocument();
    const submissions = request.mock.calls.filter(
      ([path, options]) =>
        String(path).endsWith("/messages") && options?.method === "POST",
    );
    expect(submissions).toHaveLength(1);
    expect(connect).toHaveBeenCalledTimes(4);
    expect(observers.slice(1).map((observer) => observer.lastEventId)).toEqual([
      2, 2, 2,
    ]);
  });

  it("uses the same recovery coordinator for a running run restored on page load", async () => {
    const latest = {
      ...accepted,
      run_status: "running",
    };
    const item = collection(
      "col_ddddddddddddddddddddddddddddddde",
      "刷新页面恢复结果",
    );
    request.mockReset();
    request
      .mockResolvedValueOnce(session)
      .mockResolvedValueOnce({ messages: [latest] })
      .mockResolvedValueOnce(completedResult([item]));
    let observer: MockSseOptions | undefined;
    connect.mockImplementationOnce((options: MockSseOptions) => {
      observer = options;
      return { cancel: vi.fn(), closed: new Promise<void>(() => {}) };
    });

    render(<AgentExperience />);
    await waitFor(() => expect(observer).toBeDefined());
    act(() => terminalEvent(observer!, 8));

    expect(
      await screen.findByRole("heading", { name: item.title }),
    ).toBeInTheDocument();
    expect(observer?.lastEventId).toBe(0);
  });

  it.each([
    ["failed", "run.failed"],
    ["cancelled", "run.failed"],
  ] as const)(
    "renders the authoritative %s terminal state",
    async (runStatus, eventName) => {
      const user = userEvent.setup();
      request
        .mockResolvedValueOnce(accepted)
        .mockResolvedValueOnce({
          ...completedResult([]),
          run_status: runStatus,
          error_code:
            runStatus === "failed" ? "MODEL_INVALID_RESPONSE" : "RUN_CANCELLED",
        });
      connect.mockImplementationOnce((options: MockSseOptions) => {
        window.setTimeout(
          () => terminalEvent(options, 4, eventName),
          0,
        );
        return { cancel: vi.fn(), closed: new Promise<void>(() => {}) };
      });

      render(<AgentExperience />);
      await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
      await user.type(
        screen.getByRole("textbox", { name: "收藏内容" }),
        `${runStatus} task`,
      );
      await user.click(screen.getByRole("button", { name: "发送" }));

      expect(await screen.findByText("这次没有认出来")).toBeInTheDocument();
      expect(
        screen.getByText("识别没有完成，你可以补充文字、改发截图或重试。"),
      ).toBeInTheDocument();
    },
  );

  it("renders partially_succeeded through the authoritative collection statuses", async () => {
    const user = userEvent.setup();
    const pending = collection(
      "col_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeef",
      "部分成功收藏",
      "pending_details",
    );
    request
      .mockResolvedValueOnce(accepted)
      .mockResolvedValueOnce({
        ...completedResult([pending]),
        run_status: "partially_succeeded",
        error_code: "PARTIAL_IMPORT",
      });
    connect.mockImplementationOnce((options: MockSseOptions) => {
      window.setTimeout(() => terminalEvent(options, 4), 0);
      return { cancel: vi.fn(), closed: new Promise<void>(() => {}) };
    });

    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "部分成功");
    await user.click(screen.getByRole("button", { name: "发送" }));

    const card = (await screen.findByText(pending.title)).closest("article");
    expect(card).not.toBeNull();
    expect(within(card!).getByText("待补充")).toBeInTheDocument();
  });

  it("ignores a late authoritative result after continuing and starting a new run", async () => {
    const user = userEvent.setup();
    const partial = collection(
      "col_ffffffffffffffffffffffffffffff10",
      "旧任务的临时结果",
      "pending_details",
    );
    const runningWithCollection = {
      ...completedResult([partial]),
      run_status: "running",
      extraction: null,
    };
    const oldResult = deferred<ReturnType<typeof completedResult>>();
    const newAccepted = {
      ...accepted,
      message_id: "msg_11111111111111111111111111111111",
      trace_id: "trc_11111111111111111111111111111111",
      events_url:
        "/api/v1/agent-runs/trc_11111111111111111111111111111111/events",
      result_url:
        "/api/v1/agent-runs/trc_11111111111111111111111111111111/result",
    };
    request
      .mockResolvedValueOnce(accepted)
      .mockResolvedValueOnce(runningWithCollection)
      .mockReturnValueOnce(oldResult.promise)
      .mockResolvedValueOnce(newAccepted);
    const observers: MockSseOptions[] = [];
    const cancels: ReturnType<typeof vi.fn>[] = [];
    connect.mockImplementation((options: MockSseOptions) => {
      observers.push(options);
      const cancel = vi.fn();
      cancels.push(cancel);
      return { cancel, closed: new Promise<void>(() => {}) };
    });

    render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    const input = screen.getByRole("textbox", { name: "收藏内容" });
    await user.type(input, "旧任务");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(observers).toHaveLength(1));
    act(() => terminalEvent(observers[0], 3));
    await screen.findByText(partial.title);
    await waitFor(() => expect(observers).toHaveLength(2), { timeout: 2_000 });
    act(() => terminalEvent(observers[1], 4));

    await user.click(screen.getByRole("button", { name: "继续添加" }));
    await user.type(input, "新任务");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(observers).toHaveLength(3));
    await act(async () =>
      oldResult.resolve(
        completedResult([
          collection(
            "col_12121212121212121212121212121212",
            "不应覆盖的新结果",
          ),
        ]),
      ),
    );
    act(() => {
      observers[1].onStateChange?.("error");
      terminalEvent(observers[1], 5);
    });

    expect(
      screen.getByRole("heading", { name: "正在识别" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("不应覆盖的新结果")).not.toBeInTheDocument();
    expect(cancels[1]).toHaveBeenCalled();
  });

  it("cancels a scheduled recovery when the component unmounts", async () => {
    const running = {
      ...completedResult([]),
      run_status: "running",
      extraction: null,
    };
    request
      .mockResolvedValueOnce(accepted)
      .mockResolvedValueOnce(running);
    connect.mockReturnValue({
      cancel: vi.fn(),
      closed: Promise.resolve(),
    });
    const user = userEvent.setup();
    const view = render(<AgentExperience />);
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
    await user.type(screen.getByRole("textbox", { name: "收藏内容" }), "卸载任务");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() =>
      expect(
        request.mock.calls.filter(([path]) => path === accepted.result_url),
      ).toHaveLength(1),
    );
    view.unmount();
    await new Promise((resolve) => window.setTimeout(resolve, 5));
    expect(connect).toHaveBeenCalledTimes(1);
  });
});
