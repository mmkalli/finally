import { APIRequestContext, Locator, Page, expect } from "@playwright/test";

export const DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"];

export type Position = {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  pnl_percent: number;
};

export type Portfolio = {
  cash_balance: number;
  positions_value: number;
  total_value: number;
  unrealized_pnl: number;
  positions: Position[];
};

/** POST /api/reset and return the fresh portfolio. Every test calls this first. */
export async function resetApp(request: APIRequestContext): Promise<Portfolio> {
  const res = await request.post("/api/reset");
  expect(res.status(), `POST /api/reset -> ${await res.text()}`).toBe(200);
  return res.json();
}

export async function getPortfolio(request: APIRequestContext): Promise<Portfolio> {
  const res = await request.get("/api/portfolio");
  expect(res.status()).toBe(200);
  return res.json();
}

export async function getWatchlistTickers(request: APIRequestContext): Promise<string[]> {
  const res = await request.get("/api/watchlist");
  expect(res.status()).toBe(200);
  const body = await res.json();
  return body.tickers.map((t: { ticker: string }) => t.ticker);
}

/** "$10,000.00" / "-$1,234.5" / "10000" -> number */
export function parseMoney(text: string | null): number {
  if (text == null) return NaN;
  const cleaned = text.replace(/[^0-9.\-]/g, "");
  return parseFloat(cleaned);
}

export async function moneyOf(locator: Locator): Promise<number> {
  return parseMoney(await locator.textContent());
}

/** Reset state, open the app and wait for the SSE connection to be open. */
export async function openFreshApp(page: Page): Promise<void> {
  await resetApp(page.request);
  await page.goto("/");
  await expect(page.getByTestId("connection-status")).toHaveAttribute("data-status", "open", { timeout: 15_000 });
}

/** Wait until at least one of the given tickers' displayed price differs from its current value. */
export async function expectPricesToChange(page: Page, tickers: string[], timeout = 10_000): Promise<void> {
  const read = () => Promise.all(tickers.map((t) => page.getByTestId(`price-${t}`).textContent()));
  // Wait for real prices first (not placeholders).
  await expect.poll(async () => (await read()).every((txt) => !isNaN(parseMoney(txt))), { timeout }).toBe(true);
  const before = await read();
  await expect
    .poll(async () => (await read()).some((txt, i) => txt !== before[i]), {
      timeout,
      message: `expected one of ${tickers.join(",")} to update; initial ${JSON.stringify(before)}`,
    })
    .toBe(true);
}

export async function placeTrade(page: Page, ticker: string, quantity: number | string, side: "buy" | "sell") {
  await page.getByTestId("trade-ticker").fill(ticker);
  await page.getByTestId("trade-quantity").fill(String(quantity));
  await page.getByTestId(side === "buy" ? "trade-buy" : "trade-sell").click();
}

export async function sendChat(page: Page, message: string) {
  await page.getByTestId("chat-input").fill(message);
  await page.getByTestId("chat-send").click();
}

/** Parse any CSS colour the browser hands us (rgb()/rgba()/#hex) into [r,g,b]. */
export function parseColor(c: string): [number, number, number] | null {
  c = c.trim();
  let m = c.match(/^#([0-9a-f]{3})$/i);
  if (m) return m[1].split("").map((h) => parseInt(h + h, 16)) as [number, number, number];
  m = c.match(/^#([0-9a-f]{6})([0-9a-f]{2})?$/i);
  if (m) return [0, 2, 4].map((i) => parseInt(m![1].slice(i, i + 2), 16)) as [number, number, number];
  m = c.match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i);
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3])];
  m = c.match(/hsla?\(\s*([\d.]+)(?:deg)?[,\s]+([\d.]+)%[,\s]+([\d.]+)%/i);
  if (m) {
    const h = Number(m[1]) / 360, s = Number(m[2]) / 100, l = Number(m[3]) / 100;
    const f = (n: number) => {
      const k = (n + h * 12) % 12;
      return Math.round(255 * (l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(k - 3, 9 - k, 1))));
    };
    return [f(0), f(8), f(4)];
  }
  return null;
}
