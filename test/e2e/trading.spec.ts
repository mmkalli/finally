import { test, expect, Locator } from "@playwright/test";
import { getPortfolio, moneyOf, openFreshApp, placeTrade } from "./helpers";

// Positions table columns: ticker, quantity, avg cost, current price, unrealized P&L, % change.
const quantityCell = (row: Locator) => row.locator("td").nth(1);

test.describe("Trading", () => {
  test.beforeEach(async ({ page }) => {
    await openFreshApp(page);
    await expect.poll(() => moneyOf(page.getByTestId("header-cash"))).toBe(10000);
  });

  test("buy shares: cash decreases and a position appears", async ({ page }) => {
    await placeTrade(page, "AAPL", 5, "buy");

    const row = page.getByTestId("position-row-AAPL");
    await expect(row).toBeVisible();
    await expect(row).toContainText("AAPL");
    await expect(quantityCell(row)).toHaveText(/^\s*5(\.0+)?\s*$/);
    await expect(page.getByTestId("trade-error")).toBeHidden();

    const p = await getPortfolio(page.request);
    expect(p.positions).toHaveLength(1);
    expect(p.positions[0]).toMatchObject({ ticker: "AAPL", quantity: 5 });
    expect(p.cash_balance).toBeLessThan(10000);

    await expect.poll(() => moneyOf(page.getByTestId("header-cash"))).toBeCloseTo(p.cash_balance, 2);
    // Total stays near $10k (cash + live market value).
    const total = await moneyOf(page.getByTestId("header-total-value"));
    expect(total).toBeGreaterThan(9900);
    expect(total).toBeLessThan(10100);
  });

  test("sell shares: cash increases, position updates then disappears", async ({ page }) => {
    await placeTrade(page, "MSFT", 4, "buy");
    const row = page.getByTestId("position-row-MSFT");
    await expect(row).toBeVisible();
    const cashAfterBuy = (await getPortfolio(page.request)).cash_balance;
    await expect.poll(() => moneyOf(page.getByTestId("header-cash"))).toBeCloseTo(cashAfterBuy, 2);

    await placeTrade(page, "MSFT", 1, "sell");
    await expect.poll(async () => (await getPortfolio(page.request)).positions[0]?.quantity).toBe(3);
    await expect(quantityCell(row)).toHaveText(/^\s*3(\.0+)?\s*$/);
    const cashAfterSell = (await getPortfolio(page.request)).cash_balance;
    expect(cashAfterSell).toBeGreaterThan(cashAfterBuy);
    await expect.poll(() => moneyOf(page.getByTestId("header-cash"))).toBeCloseTo(cashAfterSell, 2);

    await placeTrade(page, "MSFT", 3, "sell");
    await expect(row).toHaveCount(0);
    expect((await getPortfolio(page.request)).positions).toEqual([]);
  });

  test("rejected trade shows an error next to the trade bar and changes nothing", async ({ page }) => {
    await placeTrade(page, "AAPL", 1000000, "buy");
    const err = page.getByTestId("trade-error");
    await expect(err).toBeVisible();
    await expect(err).toContainText(/insufficient cash/i);
    await expect(page.getByTestId("position-row-AAPL")).toHaveCount(0);
    expect((await getPortfolio(page.request)).cash_balance).toBe(10000);

    await placeTrade(page, "TSLA", 1, "sell");
    await expect(err).toContainText(/insufficient shares/i);
  });
});
