import { DEFAULT_TICKERS, expect, test } from "./fixtures";

test("shows the default watchlist, $10k balance and streaming prices", async ({ app: page }) => {
  const rows = page.locator('[data-testid^="watchlist-row-"]');
  await expect(rows).toHaveCount(DEFAULT_TICKERS.length);
  for (const ticker of DEFAULT_TICKERS) {
    await expect(page.getByTestId(`watchlist-row-${ticker}`)).toBeVisible();
  }

  await expect(page.getByTestId("header-cash")).toHaveText("$10,000.00");
  await expect(page.getByTestId("header-total-value")).toHaveText("$10,000.00");
  await expect(page.getByTestId("positions-table")).toContainText("No positions");

  // Prices fill in from the first SSE event, then keep moving (~500ms ticks).
  const price = page.getByTestId("watchlist-row-AAPL").getByTestId("watchlist-price");
  await expect(price).toHaveText(/^\d[\d,]*\.\d{2}$/);
  const first = await price.innerText();
  await expect.poll(() => price.innerText(), { timeout: 15_000 }).not.toBe(first);

  // Sparklines accumulate points from the stream.
  const sparkline = page.getByTestId("watchlist-row-AAPL").getByTestId("sparkline");
  await expect
    .poll(async () => Number(await sparkline.getAttribute("data-points")))
    .toBeGreaterThan(1);
});

test("clicking a ticker charts it in the main chart", async ({ app: page }) => {
  await page.getByTestId("watchlist-row-NVDA").click();

  const chart = page.getByTestId("main-chart");
  await expect(chart.getByRole("heading", { name: "NVDA" })).toBeVisible();
  await expect(chart.locator("[data-ticker=NVDA]")).toBeVisible();
  await expect(chart.locator(".recharts-area-area")).toBeVisible();
  await expect(page.getByTestId("trade-ticker")).toHaveValue("NVDA");
});
