const DEFAULT_TIMEOUT_MS = 15_000;
const CSRF_HEADER_NAME = "X-CSRF-Token";

function normalizeBaseUrl(value: string | undefined): string {
  if (!value) return "";
  return value.replace(/\/+$/, "");
}

export const API_BASE_URL = normalizeBaseUrl(
  process.env.NEXT_PUBLIC_API_BASE_URL,
);

export type ApiErrorCode =
  | "aborted"
  | "timeout"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "rate_limited"
  | "server_error"
  | "network_error"
  | "invalid_response"
  | "request_failed";

const statusCodes: Readonly<Record<number, ApiErrorCode>> = {
  401: "unauthorized",
  403: "forbidden",
  404: "not_found",
  409: "conflict",
  429: "rate_limited",
};

export class ApiError extends Error {
  constructor(
    public readonly code: ApiErrorCode,
    public readonly status: number | null,
    public readonly requestId: string | null,
  ) {
    super(code);
    this.name = "ApiError";
  }
}

type ApiRequestOptions = Omit<RequestInit, "body" | "credentials"> & {
  body?: BodyInit | null;
  csrfToken?: string;
  timeoutMs?: number;
};

type FetchLike = typeof fetch;

function createRequestSignal(
  externalSignal: AbortSignal | null | undefined,
  timeoutMs: number,
) {
  const controller = new AbortController();
  let timedOut = false;
  const abortFromExternal = () => controller.abort(externalSignal?.reason);
  externalSignal?.addEventListener("abort", abortFromExternal, { once: true });
  if (externalSignal?.aborted) abortFromExternal();

  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  return {
    signal: controller.signal,
    didTimeOut: () => timedOut,
    cleanup: () => {
      clearTimeout(timeout);
      externalSignal?.removeEventListener("abort", abortFromExternal);
    },
  };
}

export class ApiClient {
  constructor(
    private readonly baseUrl = API_BASE_URL,
    private readonly fetcher: FetchLike = (...arguments_) => fetch(...arguments_),
  ) {}

  async request<T>(
    path: `/${string}`,
    options: ApiRequestOptions = {},
  ): Promise<T> {
    const {
      csrfToken,
      timeoutMs = DEFAULT_TIMEOUT_MS,
      headers: initialHeaders,
      signal: externalSignal,
      ...init
    } = options;
    const headers = new Headers(initialHeaders);
    if (csrfToken) headers.set(CSRF_HEADER_NAME, csrfToken);

    const requestSignal = createRequestSignal(externalSignal, timeoutMs);
    try {
      let response: Response;
      try {
        response = await this.fetcher(`${this.baseUrl}${path}`, {
          ...init,
          credentials: "include",
          headers,
          signal: requestSignal.signal,
        });
      } catch {
        if (requestSignal.didTimeOut()) {
          throw new ApiError("timeout", null, null);
        }
        if (externalSignal?.aborted || requestSignal.signal.aborted) {
          throw new ApiError("aborted", null, null);
        }
        throw new ApiError("network_error", null, null);
      }

      const requestId = response.headers.get("X-Request-ID");
      if (!response.ok) {
        const code =
          statusCodes[response.status] ??
          (response.status >= 500 ? "server_error" : "request_failed");
        throw new ApiError(code, response.status, requestId);
      }

      if (response.status === 204) return undefined as T;
      try {
        return (await response.json()) as T;
      } catch {
        if (requestSignal.didTimeOut()) {
          throw new ApiError("timeout", null, requestId);
        }
        if (externalSignal?.aborted || requestSignal.signal.aborted) {
          throw new ApiError("aborted", null, requestId);
        }
        throw new ApiError("invalid_response", response.status, requestId);
      }
    } finally {
      requestSignal.cleanup();
    }
  }
}

export const apiClient = new ApiClient();
