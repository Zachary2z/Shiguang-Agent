import { expect, test } from "@playwright/test";

const routes = [
  ["/agent", "Agent"],
  ["/collections", "收藏"],
  ["/plans", "计划"],
  ["/me", "我的"],
] as const;

for (const [path, label] of routes) {
  test(`${path} supports direct access and accurate navigation state`, async ({
    page,
  }) => {
    await page.goto(path);
    await expect(page.locator("h1")).toBeVisible();
    const current = page.getByRole("link", { name: label, exact: true });
    await expect(current.first()).toHaveAttribute("aria-current", "page");
    await page.reload();
    await expect(page).toHaveURL(new RegExp(`${path}$`));
  });
}

test("root redirects to Agent", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/agent$/);
});

for (const width of [320, 390, 768, 1024, 1440]) {
  test(`${width}px has no horizontal overflow and preserves touch targets`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const consoleErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    await page.goto("/agent");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);

    const visibleNav = width < 768 ? page.locator(".mobile-nav") : page.locator(".desktop-sidebar nav");
    await expect(visibleNav).toBeVisible();
    const boxes = await page.locator(".app-shell a, .app-shell button").evaluateAll(
      (targets) =>
        targets.flatMap((target) => {
          const rect = target.getBoundingClientRect();
          const style = getComputedStyle(target);
          const visible =
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            rect.width > 0 &&
            rect.height > 0;
          return visible
            ? [{ width: rect.width, height: rect.height }]
            : [];
        }),
    );
    expect(boxes.length).toBeGreaterThan(0);
    for (const box of boxes) {
      expect(box.width).toBeGreaterThanOrEqual(44);
      expect(box.height).toBeGreaterThanOrEqual(44);
    }
    expect(consoleErrors).toEqual([]);
  });
}

test("keyboard navigation exposes skip link and visible focus", async ({ page }) => {
  await page.goto("/agent");
  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", { name: "跳到主要内容" });
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
});

test("browser back and forward follows real links", async ({ page }) => {
  await page.goto("/agent");
  await page.getByRole("link", { name: "收藏", exact: true }).first().click();
  await expect(page).toHaveURL(/\/collections$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/agent$/);
  await page.goForward();
  await expect(page).toHaveURL(/\/collections$/);
});

test("prefers-reduced-motion removes meaningful animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/agent");
  const duration = await page.locator(".nav-link").first().evaluate(
    (element) => getComputedStyle(element).transitionDuration,
  );
  expect(Number.parseFloat(duration)).toBeLessThanOrEqual(0.00001);
});
