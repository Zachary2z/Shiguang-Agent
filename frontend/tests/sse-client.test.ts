import { describe, expect, it, vi } from "vitest";

import { SseClient, SseClientError } from "@/lib/sse-client";

function streamResponse(chunks: string[], status = 200) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/event-stream" },
  });
}

describe("SseClient", () => {
  it("delivers increasing sequences and stops on a terminal event", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      streamResponse([
        'id: 1\nevent: run.started\ndata: {"sequence":1}\n\n',
        'id: 2\nevent: run.completed\ndata: {"sequence":2}\n\n',
      ]),
    );
    const events: number[] = [];
    const states: string[] = [];

    const connection = new SseClient("", fetcher).connect({
      path: "/api/v1/agent-runs/trc_1/events",
      onEvent: (event) => events.push(event.sequence),
      onStateChange: (state) => states.push(state),
    });
    await connection.closed;

    expect(events).toEqual([1, 2]);
    expect(states).toEqual(["connecting", "open", "closed"]);
    expect(fetcher.mock.calls[0][1]?.credentials).toBe("include");
  });

  it("replays from Last-Event-ID and ignores duplicate sequences", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      streamResponse([
        'id: 3\nevent: stage.changed\ndata: {"sequence":3}\n\n',
        'id: 4\nevent: run.completed\ndata: {"sequence":4}\n\n',
      ]),
    );
    const events: number[] = [];

    const connection = new SseClient("", fetcher).connect({
      path: "/api/v1/agent-runs/trc_1/events",
      lastEventId: 3,
      onEvent: (event) => events.push(event.sequence),
    });
    await connection.closed;

    expect(new Headers(fetcher.mock.calls[0][1]?.headers).get("Last-Event-ID")).toBe(
      "3",
    );
    expect(events).toEqual([4]);
  });

  it("reports a non-terminal disconnect after reconnect attempts are exhausted", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(streamResponse([]));
    const states: string[] = [];
    const connection = new SseClient("", fetcher).connect({
      path: "/api/v1/agent-runs/trc_1/events",
      maxReconnectAttempts: 1,
      reconnectDelayMs: 0,
      onEvent: vi.fn(),
      onStateChange: (state) => states.push(state),
    });

    await expect(connection.closed).rejects.toMatchObject({
      code: "disconnected",
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(states.at(-1)).toBe("disconnected");
  });

  it("sanitizes transport failures after reconnect attempts are exhausted", async () => {
    const transportDetails =
      "GET https://private.example/api?token=secret failed";
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new DOMException(transportDetails, "NetworkError"));
    const states: string[] = [];
    const connection = new SseClient("", fetcher).connect({
      path: "/api/v1/agent-runs/private-trace/events",
      maxReconnectAttempts: 1,
      reconnectDelayMs: 0,
      onEvent: vi.fn(),
      onStateChange: (state) => states.push(state),
    });

    const error = await connection.closed.catch((reason) => reason);

    expect(error).toBeInstanceOf(SseClientError);
    expect(error).toMatchObject({ code: "network_error", status: null });
    expect(error.message).toBe("network_error");
    expect(JSON.stringify(error)).not.toContain(transportDetails);
    expect(String(error)).not.toContain("private.example");
    expect(String(error)).not.toContain("private-trace");
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(states.at(-1)).toBe("error");
  });

  it("sanitizes reader failures after reconnect attempts are exhausted", async () => {
    const readerDetails = "stream for /private-endpoint exposed bearer-secret";
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => {
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.error(new Error(readerDetails));
        },
      });
      return new Response(body, {
        headers: { "Content-Type": "text/event-stream" },
      });
    });
    const connection = new SseClient("", fetcher).connect({
      path: "/api/v1/agent-runs/private-trace/events",
      maxReconnectAttempts: 1,
      reconnectDelayMs: 0,
      onEvent: vi.fn(),
    });

    const error = await connection.closed.catch((reason) => reason);

    expect(error).toBeInstanceOf(SseClientError);
    expect(error).toMatchObject({ code: "network_error", status: null });
    expect(String(error)).toBe("SseClientError: network_error");
    expect(JSON.stringify(error)).not.toContain(readerDetails);
    expect(String(error)).not.toContain("private-endpoint");
    expect(String(error)).not.toContain("private-trace");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("reconnects with the last delivered sequence", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        streamResponse([
          'id: 1\nevent: stage.changed\ndata: {"sequence":1}\n\n',
        ]),
      )
      .mockResolvedValueOnce(
        streamResponse([
          'id: 2\nevent: run.completed\ndata: {"sequence":2}\n\n',
        ]),
      );
    const events: number[] = [];
    const connection = new SseClient("", fetcher).connect({
      path: "/api/v1/agent-runs/trc_1/events",
      reconnectDelayMs: 0,
      onEvent: (event) => events.push(event.sequence),
    });
    await connection.closed;

    expect(events).toEqual([1, 2]);
    expect(
      new Headers(fetcher.mock.calls[1][1]?.headers).get("Last-Event-ID"),
    ).toBe("1");
  });

  it("cancels the active stream and reports cancellation", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(
      async (_input, init) =>
        new Response(
          new ReadableStream({
            start(controller) {
              init?.signal?.addEventListener("abort", () =>
                controller.error(new DOMException("aborted", "AbortError")),
              );
            },
          }),
          { headers: { "Content-Type": "text/event-stream" } },
        ),
    );
    const states: string[] = [];
    const connection = new SseClient("", fetcher).connect({
      path: "/api/v1/agent-runs/trc_1/events",
      onEvent: vi.fn(),
      onStateChange: (state) => states.push(state),
    });

    await vi.waitFor(() => expect(states).toContain("open"));
    connection.cancel();
    await connection.closed;
    expect(states.at(-1)).toBe("cancelled");
  });

  it("cancels while waiting to reconnect", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(streamResponse([]));
    const states: string[] = [];
    const connection = new SseClient("", fetcher).connect({
      path: "/api/v1/agent-runs/trc_1/events",
      reconnectDelayMs: 10_000,
      onEvent: vi.fn(),
      onStateChange: (state) => states.push(state),
    });

    await vi.waitFor(() => expect(states).toContain("disconnected"));
    connection.cancel();
    await connection.closed;
    expect(states.at(-1)).toBe("cancelled");
  });
});
