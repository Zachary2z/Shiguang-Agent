import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MeExperience } from "@/components/me-experience";
import { apiClient } from "@/lib/api-client";

const firstMemory = {
  id: "mem_11111111111111111111111111111111",
  type: "pace_preference",
  content: "以后优先安排更轻松、留白更多的计划",
  value: "relaxed",
  source: {
    type: "feedback_inference",
    summary: "来自你对一次计划的反馈：节奏太赶",
    feedback_id: "fdb_11111111111111111111111111111111",
    plan_id: "pln_11111111111111111111111111111111",
  },
  confirmation_status: "confirmed",
  confidence: 70,
  expires_at: null,
  disabled_at: null,
  deleted_at: null,
  created_at: "2026-07-28T08:00:00Z",
  updated_at: "2026-07-28T08:00:00Z",
  last_used_at: "2026-07-28T09:00:00Z",
  version: 1,
} as const;

const secondMemory = {
  ...firstMemory,
  id: "mem_22222222222222222222222222222222",
  type: "positive_preference",
  content: "喜欢安静的室内展览",
  value: "室内 安静 展览",
  source: {
    type: "explicit_user",
    summary: "由你明确设置并授权保存",
    feedback_id: null,
    plan_id: null,
  },
} as const;

const suggestion = {
  id: "fdb_33333333333333333333333333333333",
  plan_id: "pln_33333333333333333333333333333333",
  memory_type: "pace_preference",
  content: "以后优先安排更轻松、留白更多的计划",
  value: "relaxed",
  evidence_summary: "来自你对本次计划的反馈：只完成了一半",
  created_at: "2026-07-28T09:00:00Z",
} as const;

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined;
  const promise = new Promise<T>((fulfill) => {
    resolve = fulfill;
  });
  return { promise, resolve };
}

describe("MeExperience", () => {
  beforeEach(() => {
    vi.spyOn(apiClient, "request").mockImplementation(async (path) => {
      if (path === "/api/v1/demo/sessions")
        return { csrf_token: "csrf-runtime-only" } as never;
      if (path === "/api/v1/memories")
        return { items: [firstMemory, secondMemory] } as never;
      if (path === "/api/v1/memory-suggestions")
        return { items: [suggestion] } as never;
      if (path === `/api/v1/memories/${firstMemory.id}`)
        return {
          memory: firstMemory,
          usages: [
            {
              memory_id: firstMemory.id,
              plan_id: firstMemory.source.plan_id,
              basis: "主方案采用了更轻松的节奏",
              used_at: "2026-07-28T09:00:00Z",
            },
          ],
          replayed: false,
        } as never;
      if (path === `/api/v1/memories/${secondMemory.id}`)
        return { memory: secondMemory, usages: [], replayed: false } as never;
      if (String(path).includes("/memory-suggestions/"))
        return {
          decision: "confirmed",
          memory: firstMemory,
          replayed: false,
        } as never;
      throw new Error(`unexpected request: ${path}`);
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows suggestions, provenance, usage, export, and an honest reminder state", async () => {
    const user = userEvent.setup();
    render(<MeExperience />);
    expect(screen.getByText("正在整理你的记忆…")).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "记忆建议" }),
    ).toBeInTheDocument();
    expect(screen.getByText("未经确认，不会进入计划")).toBeInTheDocument();
    expect(screen.getByText("尚未实现 · 已关闭")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "提醒保持关闭" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("link", { name: "下载私有 JSON" }),
    ).toHaveAttribute("href", "/api/v1/data-export.json");

    await user.click(
      screen.getByRole("button", {
        name: /以后优先安排更轻松、留白更多的计划/,
      }),
    );
    expect(await screen.findByText("来自你对一次计划的反馈：节奏太赶")).toBeVisible();
    expect(screen.getByText("主方案采用了更轻松的节奏")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "记忆内容" })).toHaveValue(
      firstMemory.content,
    );
  });

  it("confirms or rejects a suggestion and keeps it out until the decision returns", async () => {
    const user = userEvent.setup();
    const decision = deferred<{
      decision: string;
      memory: typeof firstMemory;
      replayed: boolean;
    }>();
    let decisionStarted = false;
    vi.mocked(apiClient.request).mockImplementation(async (path) => {
      if (String(path).includes("/decision")) {
        decisionStarted = true;
        return decision.promise as never;
      }
      if (path === "/api/v1/demo/sessions")
        return { csrf_token: "csrf-runtime-only" } as never;
      if (path === "/api/v1/memories") return { items: [] } as never;
      if (path === "/api/v1/memory-suggestions")
        return { items: decisionStarted ? [] : [suggestion] } as never;
      throw new Error("unexpected");
    });
    render(<MeExperience />);
    const confirm = await screen.findByRole("button", { name: "确认记住" });
    await user.click(confirm);
    expect(screen.getByText("未经确认，不会进入计划")).toBeInTheDocument();
    expect(confirm).toBeDisabled();
    decision.resolve({
      decision: "confirmed",
      memory: firstMemory,
      replayed: false,
    });
    await waitFor(() =>
      expect(screen.queryByText("未经确认，不会进入计划")).not.toBeInTheDocument(),
    );
  });

  it("supports edit, disable, and explicit two-step deletion with version payloads", async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.request).mockImplementation(async (path, options) => {
      if (path === "/api/v1/demo/sessions")
        return { csrf_token: "csrf-runtime-only" } as never;
      if (path === "/api/v1/memories")
        return { items: [firstMemory] } as never;
      if (path === "/api/v1/memory-suggestions") return { items: [] } as never;
      if (path === `/api/v1/memories/${firstMemory.id}`) {
        if (options?.method === "PATCH") {
          const body = JSON.parse(String(options.body));
          return {
            memory: {
              ...firstMemory,
              content: body.content ?? firstMemory.content,
              disabled_at:
                body.enabled === false ? "2026-07-28T10:00:00Z" : null,
              version: 2,
            },
            usages: [],
            replayed: false,
          } as never;
        }
        if (options?.method === "DELETE")
          return { memory: { ...firstMemory, deleted_at: "now" } } as never;
        return { memory: firstMemory, usages: [], replayed: false } as never;
      }
      throw new Error("unexpected");
    });
    render(<MeExperience />);
    await user.click(
      await screen.findByRole("button", { name: new RegExp(firstMemory.content) }),
    );
    const editor = await screen.findByRole("textbox", { name: "记忆内容" });
    await user.clear(editor);
    await user.type(editor, "以后每天少安排一个地点");
    await user.click(screen.getByRole("button", { name: "保存修改" }));
    expect(await screen.findByText("记忆已更新。")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "停用记忆" }));
    expect(await screen.findByText("记忆已停用。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "删除记忆" }));
    expect(screen.getByText("确认永久删除？")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认删除" }));
    expect(
      await screen.findByText("记忆已删除；下一次计划不会再使用它。"),
    ).toBeInTheDocument();
  });

  it("does not let a late detail response overwrite the newer selection", async () => {
    const user = userEvent.setup();
    const lateFirst = deferred<{
      memory: typeof firstMemory;
      usages: never[];
      replayed: boolean;
    }>();
    vi.mocked(apiClient.request).mockImplementation(async (path) => {
      if (path === "/api/v1/demo/sessions")
        return { csrf_token: "csrf-runtime-only" } as never;
      if (path === "/api/v1/memories")
        return { items: [firstMemory, secondMemory] } as never;
      if (path === "/api/v1/memory-suggestions") return { items: [] } as never;
      if (path === `/api/v1/memories/${firstMemory.id}`)
        return lateFirst.promise as never;
      if (path === `/api/v1/memories/${secondMemory.id}`)
        return { memory: secondMemory, usages: [], replayed: false } as never;
      throw new Error("unexpected");
    });
    render(<MeExperience />);
    await user.click(
      await screen.findByRole("button", { name: new RegExp(firstMemory.content) }),
    );
    await user.click(
      screen.getByRole("button", { name: new RegExp(secondMemory.content) }),
    );
    const detailCard = screen.getByRole("heading", { name: "记忆详情" }).parentElement
      ?.parentElement?.parentElement;
    expect(
      await within(detailCard!).findByRole("textbox", { name: "记忆内容" }),
    ).toHaveValue(secondMemory.content);
    lateFirst.resolve({ memory: firstMemory, usages: [], replayed: false });
    await waitFor(() =>
      expect(
        within(detailCard!).getByRole("textbox", { name: "记忆内容" }),
      ).toHaveValue(secondMemory.content),
    );
  });
});
