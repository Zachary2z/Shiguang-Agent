import { expect, type Page, test } from "@playwright/test";

const itemId = "col_0123456789abcdef0123456789abcdef";
const baseItem = {
  id: itemId,
  kind: "place",
  title: "<img src=x onerror=alert(1)> 一尺花园",
  city_hint: "深圳",
  city_pending: false,
  formal_city_code: "shenzhen",
  city_group: "shenzhen",
  district: "南山区",
  address: "太子路118号",
  business_district: "海上世界",
  landmark: "海上世界文化艺术中心",
  metro_station: "海上世界站",
  event_start_date: null,
  event_end_date: null,
  event_start_at: null,
  event_end_at: null,
  event_start_clue: null,
  event_end_clue: null,
  price_amount: "48.00",
  price_currency: "CNY",
  tags: ["咖啡"],
  missing_fields: [],
  uncertainties: [],
  status: "pending_selection",
  version: 1,
  planning_eligible: false,
  planning_exclusion_reason: "location_unconfirmed",
};

const eventItem = {
  ...baseItem,
  kind: "event",
  title: "深圳周末音乐节",
  event_start_date: "2026-08-02",
  event_end_date: "2026-08-04",
  event_start_at: "2026-08-02T07:30:00Z",
  event_end_at: "2026-08-04T12:00:00Z",
  uncertainties: [
    { field: "event_start_at", reason: "模型建议需要确认" },
    { field: "event_end_at", reason: "模型建议需要确认" },
  ],
  status: "pending_details",
  planning_exclusion_reason: "event_time_unconfirmed",
};

async function mockCollections(page: Page) {
  let item = { ...baseItem };
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/demo/sessions") {
      await route.fulfill({ json: { csrf_token: "e2e-csrf" } });
      return;
    }
    if (path.endsWith("/poi-candidates")) {
      await route.fulfill({
        json: {
          collection_item_id: itemId,
          expected_version: item.version,
          snapshot_fingerprint: "a".repeat(64),
          queried_at: "2026-07-27T00:00:00Z",
          candidates: [
            {
              provider: "amap",
              poi_id: "poi-seaworld",
              name: "一尺花园",
              branch_name: "海上世界店",
              city_code: "shenzhen",
              district: "南山区",
              business_area: "海上世界",
              address: "太子路118号，近海上世界文化艺术中心",
              poi_type: "cafe",
              matching_clues: ["district", "business_area"],
            },
          ],
        },
      });
      return;
    }
    if (path.endsWith("/poi-selection")) {
      item = { ...item, status: "pending_details", version: item.version + 1 };
      await route.fulfill({ json: { items: [item], replayed: false } });
      return;
    }
    if (path.endsWith("/restore")) {
      item = { ...item, status: "pending_details", version: item.version + 1 };
      await route.fulfill({ json: item });
      return;
    }
    if (path === `/api/v1/collections/${itemId}`) {
      if (request.method() === "DELETE") {
        item = { ...item, status: "deleted", version: item.version + 1 };
        await route.fulfill({ json: item });
      } else {
        await route.fulfill({ json: { item, sources: [] } });
      }
      return;
    }
    await route.fulfill({
      json: { items: item.status === "deleted" ? [] : [item], page: 1, page_size: 8, total: item.status === "deleted" ? 0 : 1 },
    });
  });
}

async function mockEventCollections(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/demo/sessions") {
      await route.fulfill({ json: { csrf_token: "e2e-csrf" } });
      return;
    }
    if (path === `/api/v1/collections/${itemId}`) {
      await route.fulfill({ json: { item: eventItem, sources: [] } });
      return;
    }
    await route.fulfill({
      json: {
        items: [eventItem],
        page: 1,
        page_size: 8,
        total: 1,
      },
    });
  });
}

test("collection URL state survives refresh and browser history", async ({ page }) => {
  await mockCollections(page);
  await page.goto("/collections");
  const search = page.getByRole("textbox", { name: "搜索收藏" });
  await search.fill("花园");
  await page.getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page).toHaveURL(/search=%E8%8A%B1%E5%9B%AD/);
  await page.getByRole("combobox", { name: "城市" }).selectOption("pending");
  await expect(page).toHaveURL(/city_group=pending/);
  await page.reload();
  await expect(search).toHaveValue("花园");
  await page.goBack();
  await expect(page).not.toHaveURL(/city_group=pending/);
  await page.goForward();
  await expect(page).toHaveURL(/city_group=pending/);
});

for (const width of [320, 390, 768, 1024, 1440]) {
  test(`collection library has no horizontal overflow at ${width}px`, async ({
    page,
  }) => {
    await mockCollections(page);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/collections");
    await expect(page.getByText(baseItem.title)).toBeVisible();
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      ),
    ).toBeLessThanOrEqual(0);
    const controls = await page
      .locator(".collections-page button, .collections-page input, .collections-page select")
      .evaluateAll((elements) =>
        elements
          .filter((element) => {
            const rect = element.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          })
          .map((element) => {
            const rect = element.getBoundingClientRect();
            return { width: rect.width, height: rect.height };
          }),
      );
    for (const control of controls) {
      expect(control.width).toBeGreaterThanOrEqual(44);
      expect(control.height).toBeGreaterThanOrEqual(44);
    }
  });
}

for (const width of [320, 390, 768, 1024, 1440]) {
  test(`Event date and time form is accessible without horizontal overflow at ${width}px`, async ({
    page,
  }) => {
    await mockEventCollections(page);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/collections");
    await page.getByRole("button", { name: new RegExp(eventItem.title) }).click();
    const dialog = page.getByRole("dialog");
    const startDate = dialog.getByLabel("活动有效开始日期");
    const endDate = dialog.getByLabel("活动有效结束日期");
    const startTime = dialog.getByLabel("具体开始时间");
    const endTime = dialog.getByLabel("具体结束时间");
    await expect(startDate).toHaveAttribute("type", "date");
    await expect(endDate).toHaveAttribute("type", "date");
    await expect(startTime).toHaveAttribute("type", "time");
    await expect(endTime).toHaveAttribute("type", "time");
    await expect(startTime).toHaveValue("15:30");
    await expect(endTime).toHaveValue("20:00");
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      ),
    ).toBeLessThanOrEqual(0);
    await expect(
      dialog.getByRole("button", { name: "关闭收藏详情" }),
    ).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(startDate).toBeFocused();
  });
}

test("candidate recovery, deletion, restore, safe text, and keyboard close work", async ({
  page,
}) => {
  await mockCollections(page);
  await page.goto("/collections");
  await expect(page.locator(".collection-card img")).toHaveCount(0);
  await page.getByRole("button", { name: new RegExp("一尺花园") }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "关闭收藏详情" })).toBeFocused();
  await expect(dialog.getByText(/海上世界店/)).toBeVisible();
  await expect(dialog.getByText(/南山区 · 海上世界 · 太子路118号/)).toBeVisible();
  await dialog.getByRole("button", { name: /以上都不是/ }).click();
  await expect(page.getByText(/原收藏已保留为待补充/)).toBeVisible();
  await dialog.getByRole("button", { name: "删除收藏" }).click();
  await dialog.getByRole("button", { name: "恢复收藏" }).click();
  await expect(page.getByText(/收藏已恢复到删除前的准确状态/)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("reduced motion remains disabled in collection interactions", async ({ page }) => {
  await mockCollections(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/collections");
  const duration = await page.locator(".collection-card").evaluate(
    (element) => getComputedStyle(element).transitionDuration,
  );
  expect(Number.parseFloat(duration)).toBeLessThanOrEqual(0.00001);
});
