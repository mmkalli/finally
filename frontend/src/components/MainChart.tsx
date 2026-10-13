"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatPercent, formatPrice } from "@/lib/format";
import type { PricePoint } from "@/lib/priceHistory";
import { useAppState, useMarket, usePriceHistory } from "@/lib/store";
import { Panel, Placeholder } from "./Panel";

const formatTime = (time: number) => new Date(time).toLocaleTimeString("en-US", { hour12: false });

/** Pads the price axis so a flat line doesn't sit on the chart's edge. */
const priceDomain = ([min, max]: readonly [number, number]): [number, number] => {
  const pad = Math.max((max - min) * 0.1, max * 0.0005);
  return [min - pad, max + pad];
};

function ChartHeader({ ticker }: { ticker: string }) {
  const quote = useMarket().prices[ticker];
  if (!quote) return null;
  const change = quote.change_percent;
  return (
    <span className="tabular flex items-baseline gap-2 text-xs">
      <span data-testid="main-chart-price" className="text-sm text-foreground">
        {formatPrice(quote.price)}
      </span>
      <span className={change > 0 ? "text-up" : change < 0 ? "text-down" : "text-flat"}>
        {formatPercent(change)}
      </span>
    </span>
  );
}

/** Price over time for the selected ticker, from the SSE price-history store. */
export function MainChart({ className }: { className?: string }) {
  const { selectedTicker } = useAppState();
  const points = usePriceHistory(selectedTicker);

  return (
    <Panel
      title={selectedTicker ?? "Chart"}
      className={className}
      data-testid="main-chart"
      bodyClassName="min-h-0 flex-1 p-2"
      actions={selectedTicker && <ChartHeader ticker={selectedTicker} />}
    >
      {!selectedTicker ? (
        <Placeholder>Select a ticker</Placeholder>
      ) : points.length < 2 ? (
        <Placeholder>Waiting for prices…</Placeholder>
      ) : (
        <div className="h-full w-full" data-ticker={selectedTicker} data-points={points.length}>
          <ResponsiveContainer width="100%" height="100%">
            {/* Recharts types `data` as mutable; it only reads it. */}
            <AreaChart
              data={points as PricePoint[]}
              margin={{ top: 4, right: 0, bottom: 0, left: 0 }}
            >
              <defs>
                <linearGradient id="main-chart-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-primary)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--color-primary)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="2 4" vertical={false} />
              <XAxis
                dataKey="time"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={formatTime}
                stroke="var(--color-muted)"
                tick={{ fontSize: 11 }}
                minTickGap={48}
              />
              <YAxis
                dataKey="price"
                orientation="right"
                domain={priceDomain}
                tickFormatter={formatPrice}
                stroke="var(--color-muted)"
                tick={{ fontSize: 11 }}
                width={64}
              />
              <Tooltip
                labelFormatter={(time) => formatTime(Number(time))}
                formatter={(value) => [formatPrice(Number(value)), "Price"]}
                contentStyle={{
                  background: "var(--color-surface-raised)",
                  border: "1px solid var(--color-border)",
                  fontSize: 12,
                }}
                labelStyle={{ color: "var(--color-muted)" }}
                itemStyle={{ color: "var(--color-foreground)" }}
              />
              <Area
                type="linear"
                dataKey="price"
                stroke="var(--color-primary)"
                strokeWidth={1.5}
                fill="url(#main-chart-fill)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}
