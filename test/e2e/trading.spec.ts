import { expect, formatCurrency, headerCash, parseMoney, test, type Page } from "./fixtures";

/** Places a trade through the trade bar and returns the fill price shown in the status line. */
async function trade(page: Page, side: "buy" | "sell", ticker: string, quantity: number) {
  await page.getByTestId("trade-ticker").fill(ticker);
  await page.getByTestId("trade-quantity").fill(String(quantity));
  await page.getByTestId(`trade-${side}`).click();

  const verb = side === "buy" ? "Bought" : "Sold";
  const status = page.getByTestId("trade-status");
  await expect(status).toHaveText(
    new RegExp(`^${verb} ${quantity} ${ticker} @ \\$[\\d,]+\\.\\d{2}$`),
  );
  return parseMoney((await status.innerText()).split("@")[1]);
}

const cents = (n: number) => Math.round(n * 100) / 100;

test("buying shares spends cash and opens a position", async ({ app: page }) => {
  const price = await trade(page, "buy", "AAPL", 5);

  await expect(page.getByTestId("header-cash")).toHaveText(
    formatCurrency(cents(10_000 - 5 * price)),
  );
  const row = page.locator('[data-testid="position-row"][data-ticker="AAPL"]');
  await expect(row).toBeVisible();
  await expect(row.getByTestId("position-quantity")).toHaveText("5");

  // Total value is cash plus live market value, so it stays near $10k right after the buy.
  const total = parseMoney(await page.getByTestId("header-total-value").innerText());
  expect(total).toBeGreaterThan(9_500);
  expect(total).toBeLessThan(10_500);
});

test("selling shares returns cash and shrinks, then closes, the position", async ({
  app: page,
}) => {
  await trade(page, "buy", "MSFT", 4);
  const row = page.locator('[data-testid="position-row"][data-ticker="MSFT"]');
  await expect(row.getByTestId("position-quantity")).toHaveText("4");

  const cashBefore = await headerCash(page);
  const price = await trade(page, "sell", "MSFT", 1);
  await expect(page.getByTestId("header-cash")).toHaveText(
    formatCurrency(cents(cashBefore + price)),
  );
  await expect(row.getByTestId("position-quantity")).toHaveText("3");

  await trade(page, "sell", "MSFT", 3);
  await expect(row).toHaveCount(0);
  await expect(page.getByTestId("positions-table")).toContainText("No positions");
});

test("shows API errors next to the trade bar", async ({ app: page }) => {
  await page.getByTestId("trade-ticker").fill("AAPL");
  await page.getByTestId("trade-quantity").fill("1000000");
  await page.getByTestId("trade-buy").click();
  await expect(page.getByTestId("trade-error")).toContainText(/insufficient cash/i);

  await page.getByTestId("trade-quantity").fill("1");
  await page.getByTestId("trade-sell").click();
  await expect(page.getByTestId("trade-error")).toContainText(/insufficient shares/i);

  await expect(page.getByTestId("header-cash")).toHaveText("$10,000.00");
});
