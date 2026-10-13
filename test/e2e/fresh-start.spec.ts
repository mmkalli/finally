import { test, expect, Locator } from "@playwright/test";
import { DEFAULT_TICKERS, expectPricesToChange, moneyOf, openFreshApp } from "./helpers";

/** The main chart exposes its selected ticker as `data-ticker`. */
async function expectChartTicker(chart: Locator, ticker: string) {
  await expect(chart).toHaveAttribute("data-ticker", ticker);
}

test.describe("Fresh start", () => {
  test.beforeEach(async ({ page }) => {
    await openFreshApp(page);
  });

  test("shows the default watchlist, $10,000 cash and streaming prices", async ({ page }) => {
    for (const t of DEFAULT_TICKERS) {
      await expect(page.getByTestId(`watchlist-row-${t}`)).toBeVisible();
    }
    await expect(page.locator('[data-testid^="watchlist-row-"]')).toHaveCount(DEFAULT_TICKERS.length);

    await expect.poll(() => moneyOf(page.getByTestId("header-cash"))).toBe(10000);
    await expect.poll(() => moneyOf(page.getByTestId("header-total-value"))).toBe(10000);

    await expect(page.getByTestId("connection-status")).toHaveAttribute("data-status", "open");
    await expectPricesToChange(page, DEFAULT_TICKERS);

    // No positions yet.
    await expect(page.locator('[data-testid^="position-row-"]')).toHaveCount(0);
  });

  test("clicking a watchlist ticker selects it in the main chart", async ({ page }) => {
    const chart = page.getByTestId("main-chart");
    await expect(chart).toBeVisible();
    await page.getByTestId("watchlist-row-NVDA").click();
    await expectChartTicker(chart, "NVDA");
    // Chart is drawn from the client-side SSE price history.
    await expect(chart.locator("svg").first()).toBeVisible();
    await expect
      .poll(async () => (await chart.locator("path.recharts-curve, .recharts-line path").first().getAttribute("d")) ?? "", {
        timeout: 15_000,
      })
      .toMatch(/L/);

    await page.getByTestId("watchlist-row-MSFT").click();
    await expectChartTicker(chart, "MSFT");
  });

  test("watchlist rows render sparklines that fill in", async ({ page }) => {
    const row = page.getByTestId("watchlist-row-AAPL");
    await expect(row.locator("svg").first()).toBeVisible({ timeout: 15_000 });
  });
});
