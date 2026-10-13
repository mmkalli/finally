import { test, expect, APIRequestContext, APIResponse } from "@playwright/test";
import { DEFAULT_TICKERS, getPortfolio, getWatchlistTickers, resetApp } from "./helpers";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:8000";

async function expectError(res: APIResponse, status: number, code: string) {
  const text = await res.text();
  expect(res.status(), `body: ${text}`).toBe(status);
  const body = JSON.parse(text);
  expect(body).toEqual({ error: expect.any(String), code });
  expect(body.error.length).toBeGreaterThan(0);
}

async function trade(request: APIRequestContext, ticker: string, quantity: number, side: "buy" | "sell") {
  return request.post("/api/portfolio/trade", { data: { ticker, quantity, side } });
}

/** Read the first `count` SSE `data:` events from /api/stream/prices. */
async function firstSseEvents(count: number): Promise<Record<string, any>[]> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15_000);
  try {
    const res = await fetch(`${BASE_URL}/api/stream/prices`, {
      signal: ctrl.signal,
      headers: { Accept: "text/event-stream" },
    });
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type") ?? "").toContain("text/event-stream");
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    const events: Record<string, any>[] = [];
    while (events.length < count) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const data = block
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trimStart())
          .join("\n");
        if (data) events.push(JSON.parse(data));
      }
    }
    return events;
  } finally {
    clearTimeout(timer);
    ctrl.abort();
  }
}

/** Reset clears snapshots and records one $10k baseline (a 30s background tick may add a second). */
async function expectFreshHistory(request: APIRequestContext) {
  const { snapshots } = await (await request.get("/api/portfolio/history")).json();
  expect(snapshots.length).toBeGreaterThanOrEqual(1);
  expect(snapshots.length).toBeLessThanOrEqual(2);
  expect(snapshots[0].total_value).toBe(10000);
  for (const s of snapshots) expect(s.total_value).toBe(10000);
}

const close = (actual: number, expected: number, tol = 0.011) =>
  expect(Math.abs(actual - expected), `${actual} vs ${expected}`).toBeLessThanOrEqual(tol);

test.describe("API", () => {
  test.beforeEach(async ({ request }) => {
    await resetApp(request);
  });

  test("GET /api/health", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.status()).toBe(200);
    expect(await res.json()).toEqual({ status: "ok" });
  });

  test("GET / serves the static frontend", async ({ request }) => {
    const res = await request.get("/");
    expect(res.status()).toBe(200);
    expect(res.headers()["content-type"]).toContain("text/html");
    expect(await res.text()).toMatch(/<html/i);
  });

  test("POST /api/reset returns the seed portfolio", async ({ request }) => {
    const p = await resetApp(request);
    expect(p).toEqual({ cash_balance: 10000, positions_value: 0, total_value: 10000, unrealized_pnl: 0, positions: [] });
    expect((await getWatchlistTickers(request)).sort()).toEqual([...DEFAULT_TICKERS].sort());
    await expectFreshHistory(request);
  });

  test("GET /api/watchlist shape", async ({ request }) => {
    const res = await request.get("/api/watchlist");
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.tickers).toHaveLength(10);
    for (const t of body.tickers) {
      expect(Object.keys(t).sort()).toEqual(
        ["change_percent", "direction", "open_price", "previous_price", "price", "ticker", "timestamp"].sort(),
      );
    }
    // The simulator prices every watched ticker almost immediately.
    await expect
      .poll(async () =>
        (await (await request.get("/api/watchlist")).json()).tickers.every((t: any) => typeof t.price === "number"),
      )
      .toBe(true);
    const aapl = (await (await request.get("/api/watchlist")).json()).tickers.find((t: any) => t.ticker === "AAPL");
    expect(["up", "down", "flat"]).toContain(aapl.direction);
    expect(aapl.price).toBeGreaterThan(0);
    close(aapl.change_percent, ((aapl.price - aapl.open_price) / aapl.open_price) * 100, 0.02);
    expect(aapl.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
  });

  test("watchlist add is normalised and idempotent; remove returns 204 then 404", async ({ request }) => {
    const add = await request.post("/api/watchlist", { data: { ticker: " pypl " } });
    expect(add.status(), await add.text()).toBe(200);
    const entry = await add.json();
    expect(entry.ticker).toBe("PYPL");
    expect(entry).toHaveProperty("price");
    expect(entry).toHaveProperty("change_percent");

    const again = await request.post("/api/watchlist", { data: { ticker: "PYPL" } });
    expect(again.status()).toBe(200);
    expect((await again.json()).ticker).toBe("PYPL");
    expect((await getWatchlistTickers(request)).filter((t) => t === "PYPL")).toHaveLength(1);

    // Unknown tickers get a simulator seed price.
    await expect
      .poll(
        async () =>
          (await (await request.get("/api/watchlist")).json()).tickers.find((t: any) => t.ticker === "PYPL").price,
      )
      .toEqual(expect.any(Number));

    const del = await request.delete("/api/watchlist/PYPL");
    expect(del.status()).toBe(204);
    expect(await getWatchlistTickers(request)).not.toContain("PYPL");

    await expectError(await request.delete("/api/watchlist/PYPL"), 404, "NOT_FOUND");
  });

  test("watchlist add rejects invalid tickers", async ({ request }) => {
    for (const bad of ["123", "TOOLONGX", "AB-C", ""]) {
      await expectError(await request.post("/api/watchlist", { data: { ticker: bad } }), 400, "INVALID_TICKER");
    }
  });

  test("buy, buy again (weighted avg cost), partial sell, full sell", async ({ request }) => {
    const r1 = await trade(request, " aapl ", 2, "buy");
    expect(r1.status(), await r1.text()).toBe(200);
    const b1 = await r1.json();
    expect(b1.trade).toMatchObject({ ticker: "AAPL", side: "buy", quantity: 2, price: expect.any(Number) });
    expect(b1.trade.id).toEqual(expect.any(String));
    expect(b1.trade.executed_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    const p1 = b1.trade.price;
    close(b1.portfolio.cash_balance, 10000 - 2 * p1);
    expect(b1.portfolio.positions).toHaveLength(1);

    const b2 = await (await trade(request, "AAPL", 3, "buy")).json();
    const p2 = b2.trade.price;
    const pos = b2.portfolio.positions.find((p: any) => p.ticker === "AAPL");
    expect(pos.quantity).toBe(5);
    close(pos.avg_cost, (2 * p1 + 3 * p2) / 5);
    close(b2.portfolio.cash_balance, 10000 - 2 * p1 - 3 * p2, 0.02);

    // Portfolio math consistency.
    const port = await getPortfolio(request);
    const ap = port.positions[0];
    close(ap.market_value, ap.quantity * ap.current_price);
    close(ap.unrealized_pnl, (ap.current_price - ap.avg_cost) * ap.quantity, 0.02);
    close(ap.pnl_percent, ((ap.current_price - ap.avg_cost) / ap.avg_cost) * 100, 0.02);
    close(port.total_value, port.cash_balance + port.positions_value);
    close(port.unrealized_pnl, ap.unrealized_pnl);

    // Partial sell: avg_cost unchanged, cash goes up.
    const cashBefore = b2.portfolio.cash_balance;
    const s1 = await (await trade(request, "AAPL", 1.5, "sell")).json();
    const posAfter = s1.portfolio.positions.find((p: any) => p.ticker === "AAPL");
    expect(posAfter.quantity).toBe(3.5);
    close(posAfter.avg_cost, pos.avg_cost);
    close(s1.portfolio.cash_balance, cashBefore + 1.5 * s1.trade.price);

    // Full sell removes the position row.
    const s2 = await (await trade(request, "AAPL", 3.5, "sell")).json();
    expect(s2.portfolio.positions).toEqual([]);
  });

  test("fractional quantities are rounded to 4 dp", async ({ request }) => {
    const res = await trade(request, "MSFT", 0.123456, "buy");
    expect(res.status(), await res.text()).toBe(200);
    expect((await res.json()).trade.quantity).toBe(0.1235);
  });

  test("trade error codes", async ({ request }) => {
    await expectError(await trade(request, "AAPL", 0, "buy"), 400, "INVALID_QUANTITY");
    await expectError(await trade(request, "AAPL", -1, "buy"), 400, "INVALID_QUANTITY");
    await expectError(await trade(request, "AAPL", 0.00001, "buy"), 400, "INVALID_QUANTITY");
    await expectError(await trade(request, "AAPL", 1_000_000, "buy"), 400, "INSUFFICIENT_CASH");
    await expectError(await trade(request, "TSLA", 1, "sell"), 400, "INSUFFICIENT_SHARES");
    await expectError(await trade(request, "12$", 1, "buy"), 400, "INVALID_TICKER");
    await expectError(
      await request.post("/api/portfolio/trade", { data: { ticker: "AAPL", quantity: 1, side: "hold" } }),
      400,
      "INVALID_SIDE",
    );
    expect(await trade(request, "AAPL", 1, "buy")).toBeOK();
    await expectError(await trade(request, "AAPL", 2, "sell"), 400, "INSUFFICIENT_SHARES");
    // Failed trades must not change state.
    const p = await getPortfolio(request);
    expect(p.positions).toHaveLength(1);
    expect(p.positions[0].quantity).toBe(1);
  });

  test("buying an unwatched ticker holds it without watching it", async ({ request }) => {
    const res = await trade(request, "PYPL", 1, "buy");
    // A ticker that has never been priced is allowed to fail with NO_PRICE (backend never waits).
    if (res.status() === 400) {
      expect((await res.json()).code).toBe("NO_PRICE");
      return;
    }
    expect(res.status()).toBe(200);
    expect(await getWatchlistTickers(request)).not.toContain("PYPL");
    const p = await getPortfolio(request);
    expect(p.positions.map((x) => x.ticker)).toContain("PYPL");
  });

  test("held ticker stays priced after removal from watchlist", async ({ request }) => {
    expect(await trade(request, "NFLX", 1, "buy")).toBeOK();
    expect((await request.delete("/api/watchlist/NFLX")).status()).toBe(204);
    // Still sellable at a live price.
    const res = await trade(request, "NFLX", 1, "sell");
    expect(res.status(), await res.text()).toBe(200);
  });

  test("GET /api/portfolio/history records a snapshot per trade", async ({ request }) => {
    await trade(request, "AAPL", 1, "buy");
    await trade(request, "NVDA", 1, "buy");
    const res = await request.get("/api/portfolio/history");
    expect(res.status()).toBe(200);
    const { snapshots } = await res.json();
    expect(snapshots.length).toBeGreaterThanOrEqual(2);
    for (const s of snapshots) {
      expect(s).toEqual({ total_value: expect.any(Number), recorded_at: expect.any(String) });
    }
    const times = snapshots.map((s: any) => Date.parse(s.recorded_at));
    expect([...times].sort((a, b) => a - b)).toEqual(times);
  });

  test("reset clears positions, trades, snapshots and watchlist changes", async ({ request }) => {
    await trade(request, "AAPL", 1, "buy");
    await request.post("/api/watchlist", { data: { ticker: "PYPL" } });
    await request.delete("/api/watchlist/NFLX");
    const p = await resetApp(request);
    expect(p.cash_balance).toBe(10000);
    expect(p.positions).toEqual([]);
    expect((await getWatchlistTickers(request)).sort()).toEqual([...DEFAULT_TICKERS].sort());
    await expectFreshHistory(request);
  });

  test.describe("chat (LLM_MOCK=true)", () => {
    async function chat(request: APIRequestContext, message: string) {
      const res = await request.post("/api/chat", { data: { message } });
      expect(res.status(), await res.text()).toBe(200);
      return res.json();
    }

    test("buy pattern executes a trade", async ({ request }) => {
      const body = await chat(request, "Please BUY 2 aapl now");
      expect(body.message).toMatch(/^Mock: buying 2(\.0+)? AAPL\.$/);
      expect(body.actions).toHaveLength(1);
      expect(body.actions[0]).toMatchObject({ type: "trade", ticker: "AAPL", side: "buy", quantity: 2, status: "ok" });
      expect(body.actions[0].price).toEqual(expect.any(Number));
      expect((await getPortfolio(request)).positions[0]).toMatchObject({ ticker: "AAPL", quantity: 2 });
    });

    test("failing sell is reported as an action error, not an HTTP error", async ({ request }) => {
      const body = await chat(request, "sell 1000 TSLA");
      expect(body.message).toMatch(/^Mock: selling 1000(\.0+)? TSLA\.$/);
      expect(body.actions[0]).toMatchObject({
        type: "trade",
        ticker: "TSLA",
        side: "sell",
        status: "error",
        code: "INSUFFICIENT_SHARES",
        error: expect.any(String),
      });
    });

    test("add / watch / remove patterns", async ({ request }) => {
      let body = await chat(request, "add PYPL");
      expect(body.message).toBe("Mock: adding PYPL to your watchlist.");
      expect(body.actions[0]).toMatchObject({ type: "watchlist", ticker: "PYPL", action: "add", status: "ok" });
      expect(await getWatchlistTickers(request)).toContain("PYPL");

      body = await chat(request, "watch uber");
      expect(body.actions[0]).toMatchObject({ type: "watchlist", ticker: "UBER", action: "add", status: "ok" });

      body = await chat(request, "remove PYPL");
      expect(body.message).toBe("Mock: removing PYPL from your watchlist.");
      expect(body.actions[0]).toMatchObject({ type: "watchlist", ticker: "PYPL", action: "remove", status: "ok" });
      expect(await getWatchlistTickers(request)).not.toContain("PYPL");

      body = await chat(request, "remove PYPL");
      expect(body.actions[0]).toMatchObject({ status: "error", code: "NOT_FOUND" });
    });

    test("fallback message has no actions", async ({ request }) => {
      const body = await chat(request, "how is my portfolio doing?");
      expect(body).toEqual({ message: "Mock: I'm FinAlly, your AI trading assistant.", actions: [] });
    });
  });

  test("SSE: first event has every priced ticker, later events stream", async () => {
    const [first, second] = await firstSseEvents(2);
    expect(Object.keys(first).sort()).toEqual([...DEFAULT_TICKERS].sort());
    for (const [ticker, u] of Object.entries(first)) {
      expect(u).toMatchObject({
        ticker,
        price: expect.any(Number),
        previous_price: expect.any(Number),
        open_price: expect.any(Number),
        change_percent: expect.any(Number),
        timestamp: expect.any(String),
      });
      expect(["up", "down", "flat"]).toContain(u.direction);
    }
    expect(second).toBeDefined();
    expect(Object.keys(second).length).toBeGreaterThan(0);
  });
});
