import { API_BASE_URL } from "@/lib/api-client";

export type SseConnectionState =
  | "connecting"
  | "open"
  | "disconnected"
  | "closed"
  | "cancelled"
  | "error";

export type SseEvent<T = unknown> = {
  id: string;
  event: string;
  sequence: number;
  data: T;
};

export type SseClientOptions<T> = {
  path: `/${string}`;
  lastEventId?: number;
  signal?: AbortSignal;
  maxReconnectAttempts?: number;
  reconnectDelayMs?: number;
  onEvent: (event: SseEvent<T>) => void;
  onStateChange?: (state: SseConnectionState) => void;
};

type FetchLike = typeof fetch;

const terminalEventTypes = new Set(["run.completed", "run.failed"]);

export class SseClientError extends Error {
  constructor(
    public readonly code:
      | "http_error"
      | "invalid_event"
      | "disconnected"
      | "network_error",
    public readonly status: number | null = null,
  ) {
    super(code);
    this.name = "SseClientError";
  }
}

function parseEventBlock<T>(block: string): SseEvent<T> | null {
  let id = "";
  let event = "message";
  const dataLines: string[] = [];

  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    const rawValue = separator === -1 ? "" : line.slice(separator + 1);
    const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;
    if (field === "id") id = value;
    if (field === "event") event = value;
    if (field === "data") dataLines.push(value);
  }

  if (dataLines.length === 0) return null;
  let data: T & { sequence?: unknown };
  try {
    data = JSON.parse(dataLines.join("\n")) as T & { sequence?: unknown };
  } catch {
    throw new SseClientError("invalid_event");
  }
  const sequenceFromId = /^\d+$/.test(id) ? Number(id) : null;
  const sequenceFromData =
    typeof data === "object" &&
    data !== null &&
    typeof data.sequence === "number" &&
    Number.isSafeInteger(data.sequence)
      ? data.sequence
      : null;
  const sequence = sequenceFromId ?? sequenceFromData;
  if (
    sequence === null ||
    sequence < 0 ||
    !Number.isSafeInteger(sequence)
  ) {
    throw new SseClientError("invalid_event");
  }
  return { id: id || String(sequence), event, sequence, data };
}

async function delay(ms: number, signal: AbortSignal) {
  await new Promise<void>((resolve, reject) => {
    const cleanup = () => signal.removeEventListener("abort", onAbort);
    const timeout = setTimeout(() => {
      cleanup();
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timeout);
      cleanup();
      reject(signal.reason);
    };
    signal.addEventListener("abort", onAbort, { once: true });
    if (signal.aborted) onAbort();
  });
}

export class SseClient {
  constructor(
    private readonly baseUrl = API_BASE_URL,
    private readonly fetcher: FetchLike = fetch,
  ) {}

  connect<T>(options: SseClientOptions<T>) {
    const controller = new AbortController();
    const forwardAbort = () => controller.abort(options.signal?.reason);
    options.signal?.addEventListener("abort", forwardAbort, { once: true });
    if (options.signal?.aborted) forwardAbort();

    const closed = this.run(options, controller.signal).finally(() => {
      options.signal?.removeEventListener("abort", forwardAbort);
    });

    return {
      cancel: () => controller.abort(),
      closed,
    };
  }

  private async run<T>(
    options: SseClientOptions<T>,
    signal: AbortSignal,
  ): Promise<void> {
    const maxAttempts = options.maxReconnectAttempts ?? 2;
    const reconnectDelayMs = options.reconnectDelayMs ?? 500;
    let lastSequence = options.lastEventId ?? 0;
    let reconnects = 0;

    while (!signal.aborted) {
      options.onStateChange?.("connecting");
      try {
        const headers = new Headers({ Accept: "text/event-stream" });
        if (lastSequence > 0) {
          headers.set("Last-Event-ID", String(lastSequence));
        }
        const response = await this.fetcher(`${this.baseUrl}${options.path}`, {
          credentials: "include",
          headers,
          signal,
        });
        if (!response.ok || !response.body) {
          throw new SseClientError("http_error", response.status);
        }
        if (
          !response.headers
            .get("Content-Type")
            ?.toLowerCase()
            .startsWith("text/event-stream")
        ) {
          throw new SseClientError("http_error", response.status);
        }

        options.onStateChange?.("open");
        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";
        let terminal = false;
        while (!signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += value.replace(/\r\n/g, "\n");
          let boundary = buffer.indexOf("\n\n");
          while (boundary !== -1) {
            const block = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            const parsed = parseEventBlock<T>(block);
            if (parsed && parsed.sequence > lastSequence) {
              lastSequence = parsed.sequence;
              options.onEvent(parsed);
              terminal = terminalEventTypes.has(parsed.event);
            }
            boundary = buffer.indexOf("\n\n");
          }
        }

        if (signal.aborted) break;
        if (terminal) {
          options.onStateChange?.("closed");
          return;
        }
        throw new SseClientError("disconnected");
      } catch (error) {
        if (signal.aborted) break;
        const clientError =
          error instanceof SseClientError
            ? error
            : new SseClientError("network_error", null);
        const retryable =
          clientError.code === "disconnected" ||
          clientError.code === "network_error";
        if (!retryable || reconnects >= maxAttempts) {
          options.onStateChange?.(
            clientError.code === "disconnected"
              ? "disconnected"
              : "error",
          );
          throw clientError;
        }
        reconnects += 1;
        options.onStateChange?.("disconnected");
        try {
          await delay(reconnectDelayMs, signal);
        } catch {
          if (signal.aborted) break;
          throw new SseClientError("network_error");
        }
      }
    }
    options.onStateChange?.("cancelled");
  }
}

export const sseClient = new SseClient();
