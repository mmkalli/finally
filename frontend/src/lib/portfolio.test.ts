import { describe, expect, it } from "vitest";
import { computeLivePortfolio, revaluePosition } from "./portfolio";
import type { Portfolio, Position } from "./types";

const position = (over: Partial<Position> = {}): Position => ({
  ticker: "AAPL",
  quantity: 10,
  avg_cost: 190,
  current_price: 190,
  market_value: 1900,
  unrealized_pnl: 0,
  pnl_percent: 0,
  ...over,
});

const portfolio = (positions: Position[], cash = 8100): Portfolio => ({
  cash_balance: cash,
  positions_value: positions.reduce((s, p) => s + p.market_value, 0),
  total_value: cash + positions.reduce((s, p) => s + p.market_value, 0),
  unrealized_pnl: positions.reduce((s, p) => s + p.unrealized_pnl, 0),
  positions,
});

describe("revaluePosition", () => {
  it("matches the PLAN §8 example", () => {
    expect(revaluePosition(position(), 195.03)).toEqual({
      ticker: "AAPL",
      quantity: 10,
      avg_cost: 190,
      current_price: 195.03,
      market_value: 1950.3,
      unrealized_pnl: 50.3,
      pnl_percent: 2.65,
    });
  });

  it("reports losses as negative P&L", () => {
    const p = revaluePosition(position({ quantity: 4, avg_cost: 200 }), 180);
    expect(p.unrealized_pnl).toBe(-80);
    expect(p.pnl_percent).toBe(-10);
  });

  it("handles fractional quantities and rounds money to 2 dp", () => {
    const p = revaluePosition(position({ quantity: 0.3333, avg_cost: 100 }), 123.456);
    expect(p.market_value).toBe(41.15);
    expect(p.unrealized_pnl).toBe(7.82);
  });

  it("avoids dividing by a zero avg_cost", () => {
    expect(revaluePosition(position({ avg_cost: 0 }), 10).pnl_percent).toBe(0);
  });
});

describe("computeLivePortfolio", () => {
  it("re-values positions at live prices and recomputes totals", () => {
    const base = portfolio([
      position(),
      position({
        ticker: "MSFT",
        quantity: 2,
        avg_cost: 400,
        current_price: 400,
        market_value: 800,
      }),
    ]);
    const live = computeLivePortfolio(base, { AAPL: { price: 195.03 }, MSFT: { price: 390 } });

    expect(live.cash_balance).toBe(8100);
    expect(live.positions_value).toBe(2730.3);
    expect(live.total_value).toBe(10830.3);
    expect(live.unrealized_pnl).toBe(30.3);
    expect(live.positions.map((p) => p.current_price)).toEqual([195.03, 390]);
  });

  it("keeps the server's current_price for tickers without a streamed price", () => {
    const base = portfolio([position({ current_price: 192, market_value: 1920 })]);
    const live = computeLivePortfolio(base, { MSFT: { price: 1 } });
    expect(live.positions[0].current_price).toBe(192);
    expect(live.positions_value).toBe(1920);
  });

  it("totals are cash alone with no positions", () => {
    const live = computeLivePortfolio(portfolio([], 10000), { AAPL: { price: 190 } });
    expect(live).toEqual({
      cash_balance: 10000,
      positions_value: 0,
      total_value: 10000,
      unrealized_pnl: 0,
      positions: [],
    });
  });

  it("totals equal the sum of the rounded per-position values", () => {
    const base = portfolio([
      position({ ticker: "A", quantity: 1, avg_cost: 1 }),
      position({ ticker: "B", quantity: 1, avg_cost: 1 }),
      position({ ticker: "C", quantity: 1, avg_cost: 1 }),
    ]);
    const live = computeLivePortfolio(base, {
      A: { price: 0.105 },
      B: { price: 0.105 },
      C: { price: 0.105 },
    });
    const sum = live.positions.reduce((s, p) => s + p.market_value, 0);
    expect(live.positions_value).toBeCloseTo(sum, 10);
  });

  it("does not mutate its input", () => {
    const base = portfolio([position()]);
    const copy = structuredClone(base);
    computeLivePortfolio(base, { AAPL: { price: 250 } });
    expect(base).toEqual(copy);
  });
});
