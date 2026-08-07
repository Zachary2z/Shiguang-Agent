import { expect, test } from "@playwright/test";

const recoveryViewports = [
  { name: "mobile-320", width: 320, height: 740 },
  { name: "mobile-390", width: 390, height: 844 },
  { name: "desktop", width: 1280, height: 900 },
] as const;

for (const viewport of recoveryViewports) {
  test(`recovers one long-running import after the first SSE cycle at ${viewport.name}`, async ({
    page,
    request,
  }) => {
    await page.setViewportSize(viewport);
    let eventRequests = 0;
    let resultRequests = 0;
    let messagePosts = 0;

    page.on("request", (browserRequest) => {
      if (
        browserRequest.method() === "POST" &&
        /\/api\/v1\/sessions\/[^/]+\/messages$/.test(browserRequest.url())
      ) {
        messagePosts += 1;
      }
    });
    await page.route("**/api/v1/agent-runs/*/events", async (route) => {
      eventRequests += 1;
      if (eventRequests <= 3) {
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body: "",
        });
        return;
      }
      await route.continue();
    });
    await page.route("**/api/v1/agent-runs/*/result", async (route) => {
      resultRequests += 1;
      if (resultRequests === 1) {
        const response = await route.fetch();
        const authoritative = (await response.json()) as Record<string, unknown>;
        await route.fulfill({
          response,
          json: {
            ...authoritative,
            run_status: "running",
            extraction: null,
            collections: [],
            recovery_actions: [],
            error_code: null,
            tool_steps: [],
          },
        });
        return;
      }
      await route.continue();
    });

    await page.goto("/agent");
    const submission = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        /\/api\/v1\/sessions\/[^/]+\/messages$/.test(response.url()),
    );
    await page
      .getByRole("textbox", { name: "收藏内容" })
      .fill("周末想去深圳天文台看星星");
    await page.getByRole("button", { name: "发送" }).click();
    const accepted = (await (await submission).json()) as { trace_id: string };

    await expect(page.locator(".process-card")).toContainText("正在识别");
    await expect(page.getByRole("heading", { name: "深圳天文台" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.locator(".process-card")).toHaveCount(0);
    await expect(
      page.getByRole("textbox", { name: "收藏内容" }),
    ).toBeEditable();

    expect(messagePosts).toBe(1);
    expect(eventRequests).toBe(4);
    expect(resultRequests).toBe(2);
    const stats = await request.get(
      `http://127.0.0.1:8100/__e2e/run-stats/${accepted.trace_id}`,
    );
    expect(stats.ok()).toBe(true);
    expect(await stats.json()).toEqual({
      agent_runs: 1,
      jobs: 1,
      messages: 1,
      sources: 1,
      business_writes: 1,
    });
  });
}

test("Agent plan shortcut enters the unified Agent input", async ({
  page,
}) => {
  await page.goto("/agent");
  await page.getByRole("button", { name: "帮我安排时间" }).click();

  const input = page.getByRole("textbox", { name: "收藏内容" });
  await expect(page).toHaveURL(/\/agent$/);
  await expect(input).toHaveValue("帮我安排时间");
  await expect(input).toBeFocused();
});

test("real FastAPI offline flow saves, edits, undoes, restores, and continues", async ({
  page,
}) => {
  await page.goto("/agent");
  await expect(page.getByRole("heading", { name: "把想去的地方，交给拾光" })).toBeVisible();

  const input = page.getByRole("textbox", { name: "收藏内容" });
  await input.fill("周末想去深圳天文台看星星");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.locator(".process-card")).toContainText("正在识别");
  await expect(page.getByText("待补充", { exact: true })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByRole("heading", { name: "深圳天文台" })).toBeVisible();

  await page.getByRole("button", { name: "修改" }).click();
  await page.getByLabel("名称").fill("深圳天文台 · 西涌");
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(
    page.getByRole("heading", { name: "深圳天文台 · 西涌" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "撤销" }).click();
  await expect(page.getByText("已撤销", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "恢复收藏" }).click();
  await expect(page.getByText("待补充", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "继续添加" }).click();
  await expect(input).toBeEditable();
  await expect(input).toHaveValue("");
});

test("real FastAPI collection detail preserves existing tags when saving", async ({
  page,
}) => {
  await page.goto("/agent");
  const input = page.getByRole("textbox", { name: "收藏内容" });
  await input.fill("周末想去深圳天文台看星星");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("heading", { name: "深圳天文台" })).toBeVisible({
    timeout: 15_000,
  });

  await page.getByRole("link", { name: "收藏", exact: true }).click();
  await page.getByRole("button", { name: /深圳天文台/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("textbox", { name: "标签" })).toHaveValue(
    "观星、周末",
  );
  await dialog
    .getByRole("textbox", { name: "名称" })
    .fill("深圳天文台 · 收藏详情");
  await dialog.getByRole("button", { name: "保存修改" }).click();
  await expect(
    page.getByText("修改已保存，Agent 与收藏库会读取同一条数据。"),
  ).toBeVisible();

  await dialog.getByRole("button", { name: "关闭收藏详情" }).click();
  await page.getByRole("button", { name: /深圳天文台 · 收藏详情/ }).click();
  await expect(dialog.getByRole("textbox", { name: "名称" })).toHaveValue(
    "深圳天文台 · 收藏详情",
  );
  await expect(dialog.getByRole("textbox", { name: "标签" })).toHaveValue(
    "观星、周末",
  );
});
