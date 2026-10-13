import { describe, expect, it } from "vitest";
import { flashClassFor } from "./flash";
import { HEATMAP_GAIN, HEATMAP_LOSS, HEATMAP_NEUTRAL, heatmapColor, pnlIntensity } from "./heatmap";
import { computeLivePortfolio } from "./portfolio";
import { PriceStore } from "./priceStore";
import type { Portfolio, PriceUpdate } from "./types";

const base: Portfolio = {
  cash_balance: 8100,
  positions_value: 1900,
  total_value: 10000,
  unrealized_pnl: 0,
  positions: [
    { ticker: "AAPL", quantity: 10, avg_cost: 190, current_price: 190, market_value: 1900, unrealized_pnl: 0, pnl_percent: 0 },
  ],
};

describe("computeLivePortfolio", () => {
  it("revalues positions with live prices", () => {
    const live = computeLivePortfolio(base, { AAPL: 195.03 });
    const p = live.positions[0];
    expect(p.current_price).toBe(195.03);
    expect(p.market_value).toBe(1950.3);
    expect(p.unrealized_pnl).toBe(50.3);
    expect(p.pnl_percent).toBe(2.65);
    expect(live.positions_value).toBe(1950.3);
    expect(live.total_value).toBe(10050.3);
    expect(live.unrealized_pnl).toBe(50.3);
    expect(live.cash_balance).toBe(8100);
  });

  it("falls back to the server price when no live price exists", () => {
    const live = computeLivePortfolio(base, {});
    expect(live.positions[0].current_price).toBe(190);
    expect(live.total_value).toBe(10000);
  });

  it("handles losses and multiple positions", () => {
    const p: Portfolio = {
      ...base,
      positions: [
        ...base.positions,
        { ticker: "TSLA", quantity: 2.5, avg_cost: 200, current_price: 200, market_value: 500, unrealized_pnl: 0, pnl_percent: 0 },
      ],
    };
    const live = computeLivePortfolio(p, { AAPL: 180, TSLA: 210 });
    expect(live.positions[0].unrealized_pnl).toBe(-100);
    expect(live.positions[0].pnl_percent).toBe(-5.26);
    expect(live.positions[1].unrealized_pnl).toBe(25);
    expect(live.unrealized_pnl).toBe(-75);
    expect(live.positions_value).toBe(2325);
    expect(live.total_value).toBe(10425);
  });

  it("is cash-only when there are no positions", () => {
    const live = computeLivePortfolio({ ...base, positions: [] }, { AAPL: 500 });
    expect(live.total_value).toBe(8100);
    expect(live.positions_value).toBe(0);
  });
});

describe("heatmap colour scale", () => {
  it("is neutral gray at 0%", () => {
    expect(heatmapColor(0)).toBe(HEATMAP_NEUTRAL);
  });
  it("reaches full saturation at ±10%", () => {
    expect(heatmapColor(10)).toBe(HEATMAP_GAIN);
    expect(heatmapColor(-10)).toBe(HEATMAP_LOSS);
  });
  it("clamps beyond ±10%", () => {
    expect(heatmapColor(37)).toBe(HEATMAP_GAIN);
    expect(heatmapColor(-80)).toBe(HEATMAP_LOSS);
    expect(pnlIntensity(25)).toBe(1);
    expect(pnlIntensity(-25)).toBe(-1);
  });
  it("interpolates in between", () => {
    const half = heatmapColor(5);
    expect(half).not.toBe(HEATMAP_NEUTRAL);
    expect(half).not.toBe(HEATMAP_GAIN);
    expect(pnlIntensity(5)).toBe(0.5);
    expect(pnlIntensity(-2.5)).toBe(-0.25);
  });
  it("treats non-finite input as neutral", () => {
    expect(heatmapColor(Number.NaN)).toBe(HEATMAP_NEUTRAL);
  });
});

describe("price flash", () => {
  it("flashes up on an uptick and down on a downtick", () => {
    expect(flashClassFor(100, 100.01)).toBe("flash-up");
    expect(flashClassFor(100, 99.99)).toBe("flash-down");
  });
  it("does not flash on an unchanged or first price", () => {
    expect(flashClassFor(100, 100)).toBeNull();
    expect(flashClassFor(undefined, 100)).toBeNull();
    expect(flashClassFor(null, 100)).toBeNull();
  });
});

describe("PriceStore", () => {
  const u = (ticker: string, price: number, ts: string): PriceUpdate => ({
    ticker,
    price,
    previous_price: price,
    open_price: price,
    change_percent: 0,
    direction: "flat",
    timestamp: ts,
  });

  it("accumulates history per ticker and notifies listeners", () => {
    const s = new PriceStore();
    let calls = 0;
    s.subscribe(() => calls++);
    s.apply({ AAPL: u("AAPL", 1, "2026-10-12T14:00:00.000Z"), MSFT: u("MSFT", 2, "2026-10-12T14:00:00.000Z") });
    const msftBefore = s.history.MSFT;
    s.apply({ AAPL: u("AAPL", 1.5, "2026-10-12T14:00:00.500Z") });
    expect(s.history.AAPL.map((p) => p.p)).toEqual([1, 1.5]);
    expect(s.history.MSFT).toBe(msftBefore); // untouched ticker keeps identity
    expect(s.latest.AAPL.price).toBe(1.5);
    expect(calls).toBe(2);
  });

  it("ignores duplicate timestamps (e.g. the full snapshot after a reconnect)", () => {
    const s = new PriceStore();
    s.apply({ AAPL: u("AAPL", 1, "2026-10-12T14:00:00.000Z") });
    s.apply({ AAPL: u("AAPL", 1, "2026-10-12T14:00:00.000Z") });
    expect(s.history.AAPL).toHaveLength(1);
  });
});
