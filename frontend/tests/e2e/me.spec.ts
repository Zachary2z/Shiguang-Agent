import { expect, type Page, test } from "@playwright/test";

const suggestion = {
  id: "fdb_0123456789abcdef0123456789abcdef",
  plan_id: "pln_0123456789abcdef0123456789abcdef",
  memory_type: null,
  content: "以后优先安排更轻松、留白更多的计划",
  value: null,
  evidence_summary: "来自一次历史反馈建议，尚未形成长期偏好",
  created_at: "2026-07-28T08:00:00Z",
};

const confirmedMemory = {
  id: "mem_0123456789abcdef0123456789abcdef",
  type: "pace_preference",
  content: suggestion.content,
  value: "relaxed",
  source: {
    type: "feedback_inference",
    summary: suggestion.evidence_summary,
    feedback_id: suggestion.id,
    plan_id: suggestion.plan_id,
  },
  confirmation_status: "confirmed",
  confidence: 70,
  expires_at: null,
  disabled_at: null as string | null,
  deleted_at: null as string | null,
  created_at: "2026-07-28T08:00:00Z",
  updated_at: "2026-07-28T08:00:00Z",
  last_used_at: null,
  version: 1,
};

async function mockMemoryCenter(page: Page) {
  let suggestions = [suggestion];
  let memories: Array<typeof confirmedMemory> = [];
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/demo/sessions") {
      await route.fulfill({ json: { csrf_token: "m07-e2e-csrf" } });
      return;
    }
    if (path === "/api/v1/memory-suggestions") {
      await route.fulfill({ json: { items: suggestions } });
      return;
    }
    if (path.endsWith("/decision")) {
      suggestions = [];
      memories = [{ ...confirmedMemory }];
      await route.fulfill({
        json: {
          decision: "confirmed",
          memory: confirmedMemory,
          replayed: false,
        },
      });
      return;
    }
    if (path === "/api/v1/memories") {
      await route.fulfill({ json: { items: memories } });
      return;
    }
    if (path === `/api/v1/memories/${confirmedMemory.id}`) {
      if (request.method() === "PATCH") {
        const body = request.postDataJSON();
        memories = memories.map((memory) => ({
          ...memory,
          content: body.content ?? memory.content,
          value: body.value ?? memory.value,
          disabled_at:
            body.enabled === false
              ? "2026-07-28T10:00:00Z"
              : body.enabled === true
                ? null
                : memory.disabled_at,
          version: memory.version + 1,
        }));
      }
      if (request.method() === "DELETE") memories = [];
      await route.fulfill({
        json: {
          memory: memories[0] ?? {
            ...confirmedMemory,
            deleted_at: "2026-07-28T11:00:00Z",
          },
          usages: [],
          replayed: false,
        },
      });
      return;
    }
    if (path === "/api/v1/data-export.json") {
      await route.fulfill({
        contentType: "application/json",
        headers: {
          "Content-Disposition": 'attachment; filename="shiguang-data.json"',
        },
        body: JSON.stringify({ collections: [], plans: [], memories }),
      });
      return;
    }
    await route.abort();
  });
}

test("M07 memory and data controls survive refresh on mobile", async ({ page }) => {
  await mockMemoryCenter(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/me");

  await expect(page.getByText(/未经确认，不会进入计划/)).toBeVisible();
  await page.getByRole("combobox", { name: "记忆类型" }).selectOption(
    "pace_preference",
  );
  const paceValue = page.getByRole("combobox", { name: "结构化值" });
  await expect(paceValue.locator("option")).toHaveCount(3);
  await paceValue.selectOption("relaxed");
  await page.getByRole("button", { name: "确认记住" }).focus();
  await expect(page.getByRole("button", { name: "确认记住" })).toBeFocused();
  await page.getByRole("button", { name: "确认记住" }).click();
  await expect(page.getByText("目前没有待确认建议。")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /以后优先安排更轻松/ }),
  ).toBeVisible();

  await page.reload();
  const memory = page.getByRole("button", { name: /以后优先安排更轻松/ });
  await expect(memory).toBeVisible();
  await memory.click();
  await expect(page.getByRole("textbox", { name: "记忆内容" })).toHaveValue(
    suggestion.content,
  );
  await page.getByRole("button", { name: "停用记忆" }).click();
  await expect(page.getByText("记忆已停用。")).toBeVisible();
  await expect(page.getByText("尚未实现 · 已关闭")).toBeVisible();
  await expect(page.getByRole("button", { name: "提醒保持关闭" })).toBeDisabled();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载私有 JSON" }).click();
  expect((await downloadPromise).suggestedFilename()).toMatch(
    /^(?:shiguang-data|data-export)\.json$/,
  );
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    ),
  ).toBeLessThanOrEqual(0);
});
