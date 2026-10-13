import { describe, expect, it } from "vitest";
import type { Position } from "@/lib/types";
import { pnlSeries, seriesChange } from "./PnlChart";
import { heatmapCells } from "./PortfolioHeatmap";

const position = (ticker: string, market_value: number, pnl_percent: number): Position => ({
  ticker,
  quantity: 1,
  avg_cost: market_value,
  current_price: market_value,
  market_value,
  unrealized_pnl: 0,
  pnl_percent,
});

describe("heatmapCells", () => {
  it("sizes cells by market value with weights summing to 100%, largest first", () => {
    const cells = heatmapCells([position("AAPL", 250, 2.5), position("TSLA", 750, -4)]);
    expect(cells.map((c) => c.name)).toEqual(["TSLA", "AAPL"]);
    expect(cells.map((c) => c.value)).toEqual([750, 250]);
    expect(cells.map((c) => c.weight)).toEqual([75, 25]);
    expect(cells.map((c) => c.pnl)).toEqual([-4, 2.5]);
  });

  it("drops positions with no market value", () => {
    expect(heatmapCells([position("AAPL", 0, 0), position("MSFT", 100, 1)])).toHaveLength(1);
    expect(heatmapCells([])).toEqual([]);
  });
});

describe("pnlSeries", () => {
  it("orders points by time and drops bad timestamps", () => {
    const points = pnlSeries([
      { total_value: 10_050, recorded_at: "2026-10-12T14:00:30Z" },
      { total_value: 10_000, recorded_at: "2026-10-12T14:00:00Z" },
      { total_value: 1, recorded_at: "not a date" },
    ]);
    expect(points).toEqual([
      { time: Date.parse("2026-10-12T14:00:00Z"), value: 10_000 },
      { time: Date.parse("2026-10-12T14:00:30Z"), value: 10_050 },
    ]);
  });
});

describe("seriesChange", () => {
  it("is null with fewer than two points", () => {
    expect(seriesChange([])).toBeNull();
    expect(seriesChange([{ time: 0, value: 10_000 }])).toBeNull();
  });

  it("measures first-to-last change in dollars and percent", () => {
    expect(
      seriesChange([
        { time: 0, value: 10_000 },
        { time: 1, value: 9_000 },
        { time: 2, value: 10_500 },
      ]),
    ).toEqual({ change: 500, percent: 5 });
  });
});
