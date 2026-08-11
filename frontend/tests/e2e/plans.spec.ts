import { expect, type Page, test } from "@playwright/test";

const plan = {
  id: "pln_0123456789abcdef0123456789abcdef",
  root_plan_id: "pln_0123456789abcdef0123456789abcdef",
  parent_plan_id: null,
  version: 1,
  status: "draft",
  constraints: {
    start_at: "2026-07-29T02:00:00Z",
    end_at: "2026-07-29T10:00:00Z",
    area_districts: ["南山区"],
    area_labels: ["海上世界"],
    has_exact_origin: true,
    budget: null,
    pace: "balanced",
    transport_modes: ["transit"],
    include: [],
    exclude: [],
    collection_only: false,
  },
  adjustment_text: null,
  draft: {
    exclusions: [],
    options: [
      {
        role: "main",
        total_cost_amount: null,
        total_cost_currency: null,
        risk_codes: ["PRICE_UNKNOWN"],
        risks: ["价格待确认"],
        items: [
          {
            title: "海边咖啡",
            start_at: "2026-07-29T02:15:00Z",
            end_at: "2026-07-29T03:15:00Z",
            visit_duration_seconds: 3600,
            inbound_route: {
              duration_seconds: 900,
              distance_meters: 3200,
              transport_mode: "transit",
            },
            price_amount: null,
            price_currency: null,
            source: { kind: "collection_derived", source_label: null },
            selection_reason_code: "PRIMARY_STABLE_RANK",
            selection_reason: "收藏稳定排序优先。",
            risk_codes: ["PRICE_UNKNOWN"],
            risks: ["价格待确认"],
          },
        ],
      },
    ],
  },
  trace_id: "trc_0123456789abcdef0123456789abcdef",
  events_url: "/api/v1/agent-runs/example/events",
  result_url: "/api/v1/plans/pln_0123456789abcdef0123456789abcdef",
  error_code: null,
  is_current_version: true,
  versions: [
    {
      id: "pln_0123456789abcdef0123456789abcdef",
      version: 1,
      status: "draft",
      adjustment_text: null,
    },
  ],
  approval: null,
};

async function mockPlans(page: Page, items: object[]) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/demo/sessions") {
      await route.fulfill({ json: { csrf_token: "e2e-csrf" } });
      return;
    }
    if (path === "/api/v1/plans") {
      await route.fulfill({ json: { items } });
      return;
    }
    await route.fulfill({ json: plan });
  });
}

test("mobile user can review conditions before generation", async ({ page }) => {
  await mockPlans(page, []);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/plans");

  await expect(page.getByRole("heading", { name: "时间与范围" })).toBeVisible();
  await page.getByRole("button", { name: "检查生成条件" }).click();
  const card = page.getByLabel("生成前条件确认");
  await expect(card.getByText("确认这次出发")).toBeVisible();
  await expect(card.getByText(/费用未知会明确标记/)).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    ),
  ).toBeLessThanOrEqual(0);
});

test("refreshed plan shows authoritative rail and explicit confirmation", async ({
  page,
}) => {
  await mockPlans(page, [plan]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/plans");

  await expect(page.getByText("来自收藏").first()).toBeVisible();
  await expect(page.getByText(/公共交通 · 15 分钟 · 3.2 km/)).toBeVisible();
  await expect(page.getByText("未知", { exact: true })).toBeVisible();
  const confirm = page.getByRole("button", { name: "确认 V1 · 主方案" });
  await expect(confirm).toBeVisible();
  await confirm.focus();
  await expect(confirm).toBeFocused();
});

test("real offline stack creates, adjusts, confirms, restarts, and recovers a plan", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/plans");

  await page.getByLabel("起点纬度（确认前必填）").fill("22.4798");
  await page.getByLabel("起点经度（确认前必填）").fill("113.9158");

  await page.getByRole("button", { name: "检查生成条件" }).click();
  await page.getByRole("button", { name: "确认并生成" }).click();
  await expect(page.getByRole("heading", { level: 3, name: "海上世界散步公园" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText("来自收藏").first()).toBeVisible();

  await page
    .getByLabel("基于主方案怎么调整？")
    .fill("不要咖啡店，换成适合散步的地方，其他不变。");
  await page.getByRole("button", { name: "生成新版本" }).click();
  await expect(page.getByRole("button", { name: "V2", exact: true })).toHaveAttribute(
    "aria-current",
    "page",
    { timeout: 20_000 },
  );
  await page.getByRole("button", { name: "V1", exact: true }).click();
  await expect(page.getByRole("button", { name: "V1", exact: true })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await page.getByRole("button", { name: "V2", exact: true }).click();
  await page.getByRole("button", { name: "确认 V2 · 主方案" }).click();
  await expect(page.getByText("这一版已确认")).toBeVisible();

  await page.getByRole("button", { name: "查看路线、日历与完成反馈" }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: /下载日历/ }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^shiguang-.*\.ics$/);

  const navigation = page.getByRole("link", { name: /打开地点/ }).first();
  await expect(navigation).toHaveAttribute("href", /^geo:/);
  await navigation.click();

  await page.getByRole("radio", { name: /部分完成/ }).click();
  const visits = page.locator('input[name="visited_plan_items"]');
  await expect(visits).toHaveCount(2);
  await visits.first().check();
  await page.getByRole("button", { name: "保存完成反馈" }).click();
  await expect(page.getByText("完成反馈已保存。")).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "查看路线、日历与完成反馈" }).click();
  await expect(page.getByText("第 1 次记录")).toBeVisible();
  await expect(page.getByRole("checkbox").first()).toBeChecked();
  await expect(page.getByRole("checkbox").nth(1)).not.toBeChecked();

  await page.getByRole("radio", { name: /未完成/ }).click();
  await page.getByLabel("未完成原因（选填）").fill("临时改变安排");
  await page.getByRole("button", { name: "保存更正" }).click();
  await expect(page.getByText(/反馈已更正/)).toBeVisible();
  await expect(page.getByText("第 2 次记录")).toBeVisible();

  await page.getByRole("button", { name: "新建计划" }).click();
  await page.getByLabel("起点纬度（确认前必填）").fill("22.4798");
  await page.getByLabel("起点经度（确认前必填）").fill("113.9158");
  await page.getByRole("button", { name: "检查生成条件" }).click();
  await page.getByRole("button", { name: "确认并生成" }).click();
  await expect(page.getByRole("button", { name: "V1", exact: true })).toHaveAttribute(
    "aria-current",
    "page",
    { timeout: 20_000 },
  );

  await page.getByLabel("基于主方案怎么调整？").fill("把地点换成广州塔");
  await page.getByRole("button", { name: "生成新版本" }).click();
  await expect(
    page.getByText("没有理解这次调整，请换一种更明确的说法。"),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "V2", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "V1", exact: true })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(
    page.getByRole("heading", { level: 3, name: "海上世界散步公园" }),
  ).toBeVisible();
});
