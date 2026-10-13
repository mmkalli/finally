import { test as base, expect, type APIRequestContext, type Page } from "@playwright/test";

export const DEFAULT_TICKERS = [
  "AAPL",
  "GOOGL",
  "MSFT",
  "AMZN",
  "TSLA",
  "NVDA",
  "META",
  "JPM",
  "V",
  "NFLX",
];

/**
 * Every test starts from the seed state (PLAN §12): reset the backend, then load
 * the page and wait until the price stream is live.
 */
export const test = base.extend<{ app: Page }>({
  app: async ({ page, request }, use) => {
    await resetBackend(request);
    await page.goto("/");
    await expect(page.getByTestId("connection-status")).toHaveAttribute("data-status", "open");
    await use(page);
  },
});

export { expect };
export type { Page };

export async function resetBackend(request: APIRequestContext) {
  const res = await request.post("/api/reset");
  expect(res.ok(), `POST /api/reset → ${res.status()}`).toBe(true);
}

/** Places a trade through the API, for tests whose subject isn't the trade bar. */
export async function apiTrade(
  request: APIRequestContext,
  trade: { ticker: string; quantity: number; side: "buy" | "sell" },
) {
  const res = await request.post("/api/portfolio/trade", { data: trade });
  expect(res.ok(), `trade ${JSON.stringify(trade)} → ${res.status()} ${await res.text()}`).toBe(
    true,
  );
  return res.json();
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

/** Same formatting as the UI: $1,234.56 */
export const formatCurrency = (n: number) => usd.format(n);

/** Parses "$1,234.56" (or "1,234.56") into a number. */
export const parseMoney = (text: string) => Number(text.replace(/[$,\s]/g, ""));

/** Reads the header cash balance as a number. */
export async function headerCash(page: Page) {
  return parseMoney(await page.getByTestId("header-cash").innerText());
}
