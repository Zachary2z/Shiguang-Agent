import { expect, test } from "@playwright/test";

const activeShare = {
  status: "active",
  plan: {
    version: 3,
    confirmed_at: "2026-07-29T01:00:00Z",
    updated_at: "2026-07-29T02:00:00Z",
    start_at: "2026-07-30T02:00:00Z",
    end_at: "2026-07-30T10:00:00Z",
    origin_label: "南山区 · 海上世界",
    total_cost_amount: "68.00",
    total_cost_currency: "CNY",
    risks: ["阵雨时注意路滑"],
    expires_at: "2026-08-06T10:00:00Z",
    items: [
      {
        title: "海边咖啡",
        start_at: "2026-07-30T02:15:00Z",
        end_at: "2026-07-30T03:15:00Z",
        public_address: "南山区望海路",
        visit_duration_seconds: 3600,
        transport_mode: "walking",
        travel_duration_seconds: 900,
        travel_distance_meters: 850,
        buffer_after_seconds: 1200,
        price_amount: "68.00",
        price_currency: "CNY",
        source_label: "计划地点",
        risks: ["营业时间出发前再确认"],
        queried_at: "2026-07-29T01:30:00Z",
        map_url: "https://uri.amap.com/marker?position=113.9,22.4",
      },
    ],
  },
};

test("anonymous mobile visitor sees a responsive read-only snapshot", async ({
  page,
}) => {
  await page.route("**/api/v1/public/plan-share", (route) =>
    route.fulfill({ json: activeShare }),
  );
  await page.setViewportSize({ width: 320, height: 740 });
  await page.goto("/share#e2e-token");

  await expect(page.getByRole("heading", { level: 1, name: "海边咖啡" })).toBeVisible();
  await expect(page.getByText("READ ONLY")).toBeVisible();
  await expect(page.getByText("V3")).toBeVisible();
  await expect(page.getByText("南山区望海路")).toBeVisible();
  await expect(page.getByRole("link", { name: "查看路线" })).toHaveAttribute(
    "rel",
    "noreferrer",
  );
  await expect(page.getByLabel("产品导航")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /编辑|调整|确认|撤销|重建/ }),
  ).toHaveCount(0);
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    ),
  ).toBeLessThanOrEqual(0);
});

test("cancelled and unavailable links reveal no route details", async ({ page }) => {
  let status: "cancelled" | "unavailable" = "cancelled";
  await page.route("**/api/v1/public/plan-share", (route) =>
    route.fulfill({ json: { status, plan: null } }),
  );
  await page.goto("/share#e2e-token");
  await expect(page.getByRole("heading", { name: "行程已取消" })).toBeVisible();
  await expect(page.getByText("海边咖啡")).toHaveCount(0);

  status = "unavailable";
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "这份行程暂时无法查看" }),
  ).toBeVisible();
  await expect(page.getByText(/不会说明具体原因/)).toBeVisible();
});
