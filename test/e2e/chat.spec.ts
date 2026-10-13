import { expect, test, type Page } from "./fixtures";

async function send(page: Page, message: string) {
  await page.getByTestId("chat-input").fill(message);
  await page.getByTestId("chat-send").click();
  const reply = page.locator('[data-testid="chat-message"][data-role="assistant"]').last();
  await expect(page.getByTestId("chat-loading")).toHaveCount(0);
  return reply;
}

test("mock AI buys shares and shows the trade inline", async ({ app: page }) => {
  const reply = await send(page, "buy 1 AAPL");

  await expect(page.locator('[data-testid="chat-message"][data-role="user"]')).toHaveText(
    /buy 1 AAPL/,
  );
  await expect(reply).toContainText("Mock: buying 1 AAPL.");
  const action = reply.getByTestId("chat-action");
  await expect(action).toHaveCount(1);
  await expect(action).toHaveAttribute("data-type", "trade");
  await expect(action).toHaveAttribute("data-status", "ok");
  await expect(action).toHaveAttribute("data-ticker", "AAPL");

  // The portfolio refreshes after an ok action.
  const row = page.locator('[data-testid="position-row"][data-ticker="AAPL"]');
  await expect(row.getByTestId("position-quantity")).toHaveText("1");
  await expect(page.getByTestId("header-cash")).not.toHaveText("$10,000.00");
});

test("mock AI adds and removes watchlist tickers", async ({ app: page }) => {
  let reply = await send(page, "add PYPL");
  await expect(reply).toContainText("Mock: adding PYPL to your watchlist.");
  await expect(reply.getByTestId("chat-action")).toHaveAttribute("data-status", "ok");
  await expect(page.getByTestId("watchlist-row-PYPL")).toBeVisible();

  reply = await send(page, "remove PYPL");
  await expect(reply).toContainText("Mock: removing PYPL from your watchlist.");
  await expect(page.getByTestId("watchlist-row-PYPL")).toHaveCount(0);
});

test("failed AI actions are shown as inline errors", async ({ app: page }) => {
  const reply = await send(page, "sell 5 TSLA");
  await expect(reply).toContainText("Mock: selling 5 TSLA.");
  const action = reply.getByTestId("chat-action");
  await expect(action).toHaveAttribute("data-status", "error");
  await expect(action).toContainText(/insufficient shares/i);
  await expect(page.getByTestId("header-cash")).toHaveText("$10,000.00");
});

test("plain messages get the default mock reply", async ({ app: page }) => {
  const reply = await send(page, "How diversified am I?");
  await expect(reply).toContainText("Mock: I'm FinAlly, your AI trading assistant.");
  await expect(reply.getByTestId("chat-action")).toHaveCount(0);
});
