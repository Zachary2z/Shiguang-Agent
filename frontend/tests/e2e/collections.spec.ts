import { expect, type Locator, type Page, test } from "@playwright/test";

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
  event_start_at: null,
  event_end_at: null,
  missing_fields: [],
  uncertainties: [],
  status: "active",
  planning_eligible: true,
  planning_exclusion_reason: null,
};

const mobileViewports = [
  { width: 320, height: 568 },
  { width: 320, height: 740 },
  { width: 390, height: 667 },
  { width: 390, height: 844 },
  { width: 729, height: 837 },
] as const;

const desktopViewports = [
  { width: 768, height: 900 },
  { width: 1024, height: 900 },
  { width: 1440, height: 900 },
] as const;

async function mockCollections(page: Page) {
  let item = { ...baseItem };
  const selectionBodies: Array<Record<string, unknown>> = [];
  let deleteRequests = 0;
  let restoreRequests = 0;
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
      const body = request.postDataJSON() as Record<string, unknown>;
      selectionBodies.push(body);
      item = {
        ...item,
        status:
          body.choice === "candidate" || body.choice === "any_branch"
            ? "active"
            : "pending_details",
        version: item.version + 1,
      };
      await route.fulfill({ json: { items: [item], replayed: false } });
      return;
    }
    if (path.endsWith("/restore")) {
      restoreRequests += 1;
      item = { ...item, status: "pending_details", version: item.version + 1 };
      await route.fulfill({ json: item });
      return;
    }
    if (path === `/api/v1/collections/${itemId}`) {
      if (request.method() === "DELETE") {
        deleteRequests += 1;
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
  return {
    deleteRequests: () => deleteRequests,
    restoreRequests: () => restoreRequests,
    selectionBodies,
  };
}

async function mockEventCollections(page: Page) {
  let patchRequests = 0;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/demo/sessions") {
      await route.fulfill({ json: { csrf_token: "e2e-csrf" } });
      return;
    }
    if (path === `/api/v1/collections/${itemId}`) {
      if (request.method() === "PATCH") {
        patchRequests += 1;
        await route.fulfill({ json: eventItem });
      } else {
        await route.fulfill({ json: { item: eventItem, sources: [] } });
      }
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
  return { patchRequests: () => patchRequests };
}

async function mockLongEventCollections(page: Page) {
  let item = {
    ...eventItem,
    title: "深圳周末音乐节 · 长 Event 移动端操作可达性验证",
    tags: ["音乐节", "户外", "朋友", "周末"],
  };
  let eventConfirmRequests = 0;
  let detailSaveRequests = 0;
  let deleteRequests = 0;
  let restoreRequests = 0;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/demo/sessions") {
      await route.fulfill({ json: { csrf_token: "e2e-csrf" } });
      return;
    }
    if (path.endsWith("/restore")) {
      restoreRequests += 1;
      item = {
        ...item,
        status: "active",
        version: item.version + 1,
      };
      await route.fulfill({ json: item });
      return;
    }
    if (path === `/api/v1/collections/${itemId}`) {
      if (request.method() === "PATCH") {
        const body = request.postDataJSON() as {
          changes: Record<string, unknown>;
        };
        if ("event_start_date" in body.changes) {
          eventConfirmRequests += 1;
        } else {
          detailSaveRequests += 1;
        }
        item = {
          ...item,
          ...body.changes,
          version: item.version + 1,
        };
        await route.fulfill({ json: item });
        return;
      }
      if (request.method() === "DELETE") {
        deleteRequests += 1;
        item = { ...item, status: "deleted", version: item.version + 1 };
        await route.fulfill({ json: item });
        return;
      }
      await route.fulfill({ json: { item, sources: [] } });
      return;
    }
    await route.fulfill({
      json: {
        items: item.status === "deleted" ? [] : [item],
        page: 1,
        page_size: 8,
        total: item.status === "deleted" ? 0 : 1,
      },
    });
  });
  return {
    deleteRequests: () => deleteRequests,
    detailSaveRequests: () => detailSaveRequests,
    eventConfirmRequests: () => eventConfirmRequests,
    restoreRequests: () => restoreRequests,
  };
}

async function expectReachable(page: Page, target: Locator) {
  await target.scrollIntoViewIfNeeded();
  await expect(target).toBeVisible();
  const box = await target.boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  if (!box || !viewport) return;
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
  expect(box.width).toBeGreaterThanOrEqual(44);
  expect(box.height).toBeGreaterThanOrEqual(44);
  expect(
    await target.evaluate((element, point) => {
      const hit = document.elementFromPoint(point.x, point.y);
      return hit === element || (hit !== null && element.contains(hit));
    }, {
      x: box.x + box.width / 2,
      y: box.y + box.height / 2,
    }),
  ).toBe(true);
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

for (const viewport of [...mobileViewports, ...desktopViewports]) {
  test(`collection library has no horizontal overflow at ${viewport.width}x${viewport.height}`, async ({
    page,
  }) => {
    await mockCollections(page);
    await page.setViewportSize(viewport);
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

for (const viewport of mobileViewports) {
  test(`long Event detail actions stay reachable at ${viewport.width}x${viewport.height}`, async ({
    page,
  }) => {
    const requests = await mockLongEventCollections(page);
    await page.setViewportSize(viewport);
    await page.goto("/collections");
    await page.getByRole("button", { name: new RegExp(eventItem.title) }).click();
    const dialog = page.getByRole("dialog");
    const close = dialog.getByRole("button", { name: "关闭收藏详情" });
    await expect(close).toBeFocused();
    await expect(page.locator(".mobile-nav-wrap")).toBeHidden();
    await expect(page.locator(".desktop-sidebar")).toBeHidden();

    const save = dialog.getByRole("button", { name: "保存修改" });
    save.focus();
    await expect(save).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(close).toBeFocused();
    await expect(
      page.locator(".mobile-nav-wrap .nav-link:focus"),
    ).toHaveCount(0);

    const startDate = dialog.getByLabel("活动有效开始日期");
    const endDate = dialog.getByLabel("活动有效结束日期");
    await expect(startDate).toHaveValue("2026-08-02");
    await expect(endDate).toHaveValue("2026-08-04");
    await expect(dialog.getByLabel("具体场次日期")).toHaveCount(0);
    await expect(dialog.getByLabel("具体开始时间")).toHaveCount(0);
    await expect(dialog.getByLabel("具体结束时间")).toHaveCount(0);
    const confirm = dialog.getByRole("button", { name: "确认并保存" });
    await expectReachable(page, confirm);
    await confirm.click();
    await expect.poll(requests.eventConfirmRequests).toBe(1);

    const title = dialog.getByRole("textbox", { name: "名称" });
    await title.fill("深圳周末音乐节 · 已核对");
    await expectReachable(page, save);
    await save.click();
    await expect.poll(requests.detailSaveRequests).toBe(1);

    const remove = dialog.getByRole("button", { name: "删除收藏" });
    await expectReachable(page, remove);
    await remove.click();
    await expect.poll(requests.deleteRequests).toBe(1);

    const restore = dialog.getByRole("button", { name: "恢复收藏" });
    await expectReachable(page, restore);
    await restore.click();
    await expect.poll(requests.restoreRequests).toBe(1);
    await expect(
      page.getByText("收藏已恢复到删除前的准确状态。"),
    ).toBeVisible();

    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      ),
    ).toBeLessThanOrEqual(0);

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    const mobileNavigation = page.locator(".mobile-nav-wrap");
    await expect(mobileNavigation).toBeVisible();
    await expect(
      page.locator(`.collection-card[data-collection-id="${itemId}"]`),
    ).toBeFocused();
    const meNavigation = mobileNavigation.getByRole("link", { name: "我的" });
    await expectReachable(page, meNavigation);
    await meNavigation.click();
    await expect(page).toHaveURL(/\/me$/);
  });
}

for (const viewport of desktopViewports) {
  test(`desktop collection drawer remains reachable at ${viewport.width}x${viewport.height}`, async ({
    page,
  }) => {
    await mockLongEventCollections(page);
    await page.setViewportSize(viewport);
    await page.goto("/collections");
    await page.getByRole("button", { name: new RegExp(eventItem.title) }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(page.locator(".desktop-sidebar")).toBeVisible();
    await expect(page.locator(".mobile-nav-wrap")).toBeHidden();
    await expectReachable(
      page,
      dialog.getByRole("button", { name: "确认并保存" }),
    );
    await expectReachable(
      page,
      dialog.getByRole("button", { name: "保存修改" }),
    );
    await expectReachable(
      page,
      dialog.getByRole("button", { name: "删除收藏" }),
    );
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      ),
    ).toBeLessThanOrEqual(0);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });
}

test("reversed Event date range reaches product validation without PATCH", async ({
  page,
}) => {
  const requests = await mockEventCollections(page);
  await page.goto("/collections");
  await page.getByRole("button", { name: new RegExp(eventItem.title) }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("活动有效结束日期").fill("2026-08-01");
  await dialog.getByRole("button", { name: "确认并保存" }).click();

  await expect(
    page.getByText("活动有效结束日期不能早于开始日期。"),
  ).toBeVisible();
  expect(requests.patchRequests()).toBe(0);
});

test("candidate recovery, deletion, restore, safe text, and keyboard close work", async ({
  page,
}) => {
  const requests = await mockCollections(page);
  await page.goto("/collections");
  await expect(page.locator(".collection-card img")).toHaveCount(0);
  await page.getByRole("button", { name: new RegExp("一尺花园") }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "关闭收藏详情" })).toBeFocused();
  await expect(dialog.getByText(/海上世界店/)).toBeVisible();
  await expect(dialog.getByText(/南山区 · 海上世界 · 太子路118号/)).toBeVisible();
  const none = dialog.getByRole("button", { name: /以上都不是/ });
  await expectReachable(page, none);
  await none.click();
  expect(requests.selectionBodies).toHaveLength(1);
  expect(requests.selectionBodies[0].choice).toBe("none_of_above");
  await expect(page.getByText(/原收藏已保留为待补充/)).toBeVisible();
  const remove = dialog.getByRole("button", { name: "删除收藏" });
  await expectReachable(page, remove);
  await remove.click();
  expect(requests.deleteRequests()).toBe(1);
  const restore = dialog.getByRole("button", { name: "恢复收藏" });
  await expectReachable(page, restore);
  await restore.click();
  expect(requests.restoreRequests()).toBe(1);
  await expect(page.getByText(/收藏已恢复到删除前的准确状态/)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("a concrete pending-selection candidate is reachable and sends one request", async ({
  page,
}) => {
  const requests = await mockCollections(page);
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/collections");
  await page.getByRole("button", { name: new RegExp("一尺花园") }).click();
  const dialog = page.getByRole("dialog");
  const candidate = dialog.getByRole("button", {
    name: /一尺花园 · 海上世界店/,
  });
  await expectReachable(page, candidate);
  await candidate.click();
  await expect(page.getByText("准确地点已保存。")).toBeVisible();
  expect(requests.selectionBodies).toHaveLength(1);
  expect(requests.selectionBodies[0]).toMatchObject({
    choice: "candidate",
    provider: "amap",
    poi_id: "poi-seaworld",
  });
});

test("mobile any-branch confirmation uses the existing selection request", async ({ page }) => {
  const requests = await mockCollections(page);
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/collections");
  await page.getByRole("button", { name: new RegExp("一尺花园") }).click();
  const anyBranch = page.getByRole("dialog").getByRole("button", {
    name: /保存为任意分店/,
  });
  await expectReachable(page, anyBranch);
  await anyBranch.click();

  expect(requests.selectionBodies).toHaveLength(1);
  expect(requests.selectionBodies[0]).toMatchObject({ choice: "any_branch" });
  expect(requests.selectionBodies[0]).not.toHaveProperty("stable_id");
});

test("mobile collection selection opens the existing plan page", async ({ page }) => {
  await mockEventCollections(page);
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/collections");
  await page.getByRole("checkbox", { name: new RegExp(eventItem.title) }).check();
  await page.getByRole("button", { name: "用这些收藏规划" }).click();

  await expect(page).toHaveURL(new RegExp(`/plans\\?collection=${itemId}`));
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
