import { expect, test } from "./fixtures";

test("adds and removes a ticker", async ({ app: page }) => {
  await page.getByTestId("watchlist-add-input").fill("pypl");
  await page.getByTestId("watchlist-add-button").click();

  // Unknown tickers get a simulator seed price and start streaming.
  const row = page.getByTestId("watchlist-row-PYPL");
  await expect(row).toBeVisible();
  await expect(row.getByTestId("watchlist-price")).toHaveText(/^\d[\d,]*\.\d{2}$/);
  await expect(page.getByTestId("watchlist-add-input")).toHaveValue("");

  // Persisted server-side: still there after a reload.
  await page.reload();
  await expect(page.getByTestId("watchlist-row-PYPL")).toBeVisible();

  await page.getByTestId("watchlist-row-PYPL").hover();
  await page.getByTestId("watchlist-remove-PYPL").click();
  await expect(page.getByTestId("watchlist-row-PYPL")).toHaveCount(0);

  await page.reload();
  await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();
  await expect(page.getByTestId("watchlist-row-PYPL")).toHaveCount(0);
});

test("removes a default ticker", async ({ app: page }) => {
  await page.getByTestId("watchlist-row-NFLX").hover();
  await page.getByTestId("watchlist-remove-NFLX").click();
  await expect(page.getByTestId("watchlist-row-NFLX")).toHaveCount(0);
  await expect(page.locator('[data-testid^="watchlist-row-"]')).toHaveCount(9);
});

test("rejects an invalid ticker", async ({ app: page }) => {
  await page.getByTestId("watchlist-add-input").fill("123");
  await page.getByTestId("watchlist-add-button").click();
  await expect(page.getByTestId("watchlist-error")).toBeVisible();
  await expect(page.locator('[data-testid^="watchlist-row-"]')).toHaveCount(10);
});
