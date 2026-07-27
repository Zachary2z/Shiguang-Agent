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
  status: "active" | "pending_details" | "deleted" = "active",
) {
  return {
    id,
    title,
    kind: "place",
    city_hint: "深圳",
    city_pending: false,
    district: "南山区",
    address: null,
    tags: [],
    missing_fields: [],
    uncertainties: [],
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

  it("reuses one idempotency key after an uncertain network failure", async () => {
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
    await user.click(screen.getByRole("button", { name: "发送" }));

    const submissions = request.mock.calls.filter(
      ([path, options]) =>
        String(path).endsWith("/messages") && options?.method === "POST",
    );
    expect(submissions).toHaveLength(2);
    const first = JSON.parse(String(submissions[0][1]?.body));
    const second = JSON.parse(String(submissions[1][1]?.body));
    expect(second.idempotency_key).toBe(first.idempotency_key);
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
});
