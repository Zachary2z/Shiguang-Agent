import { expect, test } from "@playwright/test";

test("Agent plan shortcut reaches the authoritative plans experience", async ({
  page,
}) => {
  await page.goto("/agent");
  await page.getByRole("link", { name: "帮我安排时间" }).click();

  await expect(page).toHaveURL(/\/plans$/);
  await expect(page.getByRole("heading", { name: "时间与范围" })).toBeVisible();
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
