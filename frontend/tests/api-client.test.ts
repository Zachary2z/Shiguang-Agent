import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError } from "@/lib/api-client";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

describe("ApiClient", () => {
  it("uses the central base URL, browser credentials, and CSRF header", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({ ok: true }),
    );
    const client = new ApiClient("https://api.example.test", fetcher);

    await expect(
      client.request<{ ok: boolean }>("/api/v1/resource", {
        method: "POST",
        body: JSON.stringify({ private: "never logged" }),
        csrfToken: "csrf-secret",
      }),
    ).resolves.toEqual({ ok: true });

    expect(fetcher).toHaveBeenCalledOnce();
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe("https://api.example.test/api/v1/resource");
    expect(init?.credentials).toBe("include");
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("csrf-secret");
  });

  it.each([
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "not_found"],
    [409, "conflict"],
    [429, "rate_limited"],
    [503, "server_error"],
  ] as const)("maps HTTP %s to %s without response details", async (status, code) => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        jsonResponse(
          { secret: "sensitive-response" },
          { status, headers: { "X-Request-ID": "request-1" } },
        ),
      );
    const client = new ApiClient("", fetcher);

    const error = await client.request("/api/v1/resource").catch((reason) => reason);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code, status, requestId: "request-1" });
    expect(JSON.stringify(error)).not.toContain("sensitive-response");
  });

  it("maps timeout and external cancellation separately", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );
    const client = new ApiClient("", fetcher);

    await expect(
      client.request("/api/v1/slow", { timeoutMs: 1 }),
    ).rejects.toMatchObject({ code: "timeout" });

    const controller = new AbortController();
    const pending = client.request("/api/v1/slow", {
      signal: controller.signal,
      timeoutMs: 1_000,
    });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ code: "aborted" });
  });

  it("maps transport failures without exposing error messages", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new Error("cookie=private"));
    const client = new ApiClient("", fetcher);

    const error = await client.request("/api/v1/resource").catch((reason) => reason);
    expect(error).toMatchObject({ code: "network_error" });
    expect(String(error)).not.toContain("cookie=private");
  });
});
