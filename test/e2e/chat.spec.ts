import { test, expect } from "@playwright/test";
import { getPortfolio, getWatchlistTickers, moneyOf, openFreshApp, sendChat } from "./helpers";

test.describe("AI chat (mocked LLM)", () => {
  test.beforeEach(async ({ page }) => {
    await openFreshApp(page);
  });

  test("'buy 1 AAPL' shows the mock reply and an inline ok trade action", async ({ page }) => {
    await sendChat(page, "buy 1 AAPL");

    const messages = page.getByTestId("chat-message");
    await expect(messages.filter({ hasText: "buy 1 AAPL" }).first()).toBeVisible();
    await expect(messages.filter({ hasText: /Mock: buying 1(\.0+)? AAPL\./ })).toHaveCount(1);

    const action = page.getByTestId("chat-action");
    await expect(action).toHaveCount(1);
    await expect(action).toHaveAttribute("data-status", "ok");
    await expect(action).toContainText("AAPL");

    // Portfolio refreshes after an ok action.
    await expect(page.getByTestId("position-row-AAPL")).toBeVisible();
    const p = await getPortfolio(page.request);
    expect(p.positions[0]).toMatchObject({ ticker: "AAPL", quantity: 1 });
    await expect.poll(() => moneyOf(page.getByTestId("header-cash"))).toBeCloseTo(p.cash_balance, 2);
  });

  test("a failing action is shown inline as an error", async ({ page }) => {
    await sendChat(page, "sell 1000 TSLA");
    await expect(page.getByTestId("chat-message").filter({ hasText: /Mock: selling 1000(\.0+)? TSLA\./ })).toHaveCount(1);
    const action = page.getByTestId("chat-action");
    await expect(action).toHaveCount(1);
    await expect(action).toHaveAttribute("data-status", "error");
    await expect(action).toContainText(/insufficient shares/i);
    await expect(page.locator('[data-testid^="position-row-"]')).toHaveCount(0);
  });

  test("watchlist changes via chat update the watchlist panel", async ({ page }) => {
    await sendChat(page, "add PYPL");
    await expect(page.getByTestId("chat-action")).toHaveAttribute("data-status", "ok");
    await expect(page.getByTestId("watchlist-row-PYPL")).toBeVisible();
    expect(await getWatchlistTickers(page.request)).toContain("PYPL");

    await sendChat(page, "remove PYPL");
    await expect(page.getByTestId("chat-action")).toHaveCount(2);
    await expect(page.getByTestId("chat-action").nth(1)).toHaveAttribute("data-status", "ok");
    await expect(page.getByTestId("watchlist-row-PYPL")).toHaveCount(0);
  });

  test("plain question gets the fallback reply with no actions", async ({ page }) => {
    await sendChat(page, "hello there");
    await expect(page.getByTestId("chat-message").filter({ hasText: "Mock: I'm FinAlly, your AI trading assistant." })).toHaveCount(1);
    await expect(page.getByTestId("chat-action")).toHaveCount(0);
  });
});
