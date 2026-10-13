"use client";

import { Line, LineChart, YAxis } from "recharts";
import type { PricePoint } from "@/lib/priceHistory";
import { usePriceHistory } from "@/lib/store";

const UP = "var(--color-up)";
const DOWN = "var(--color-down)";
const FLAT = "var(--color-flat)";

/** Mini price chart for one ticker, filled in from the SSE stream since page load. */
export function Sparkline({
  ticker,
  width = 80,
  height = 24,
}: {
  ticker: string;
  width?: number;
  height?: number;
}) {
  const points = usePriceHistory(ticker);

  if (points.length < 2) {
    return <div style={{ width, height }} data-testid="sparkline" data-points={points.length} />;
  }

  const first = points[0].price;
  const last = points[points.length - 1].price;
  const stroke = last > first ? UP : last < first ? DOWN : FLAT;

  return (
    <div data-testid="sparkline" data-points={points.length}>
      {/* Recharts types `data` as mutable; it only reads it. */}
      <LineChart width={width} height={height} data={points as PricePoint[]}>
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Line
          type="linear"
          dataKey="price"
          stroke={stroke}
          strokeWidth={1.25}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </div>
  );
}
