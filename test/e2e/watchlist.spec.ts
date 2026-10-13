import { test, expect } from "@playwright/test";
import { getWatchlistTickers, openFreshApp, parseMoney } from "./helpers";

test.describe("Watchlist", () => {
  test.beforeEach(async ({ page }) => {
    await openFreshApp(page);
  });

  test("add a ticker, see it priced, then remove it", async ({ page }) => {
    await page.getByTestId("watchlist-add-input").fill("pypl");
    await page.getByTestId("watchlist-add-button").click();

    const row = page.getByTestId("watchlist-row-PYPL");
    await expect(row).toBeVisible();
    await expect.poll(async () => parseMoney(await page.getByTestId("price-PYPL").textContent())).toBeGreaterThan(0);
    await expect.poll(() => getWatchlistTickers(page.request)).toContain("PYPL");

    await row.hover();
    await page.getByTestId("watchlist-remove-PYPL").click();
    await expect(row).toHaveCount(0);
    await expect.poll(() => getWatchlistTickers(page.request)).not.toContain("PYPL");
  });

  test("remove a default ticker", async ({ page }) => {
    const row = page.getByTestId("watchlist-row-NFLX");
    await expect(row).toBeVisible();
    await row.hover();
    await page.getByTestId("watchlist-remove-NFLX").click();
    await expect(row).toHaveCount(0);
    await expect(page.locator('[data-testid^="watchlist-row-"]')).toHaveCount(9);

    // Survives a reload (persisted server-side).
    await page.reload();
    await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();
    await expect(page.getByTestId("watchlist-row-NFLX")).toHaveCount(0);
  });
});
