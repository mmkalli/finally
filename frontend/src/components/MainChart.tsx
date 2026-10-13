"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtClock, fmtPct, fmtPrice, signClass } from "@/utils/format";
import type { PricePoint } from "@/utils/priceStore";
import type { PriceUpdate } from "@/utils/types";
import { EmptyState, Panel } from "./Panel";

const AXIS = { fill: "var(--color-muted)", fontSize: 10, fontFamily: "var(--font-mono)" };

export function MainChart({
  ticker,
  points,
  latest,
}: {
  ticker: string | null;
  points: PricePoint[] | undefined;
  latest: PriceUpdate | undefined;
}) {
  const data = points ?? [];
  const title = ticker ? (
    <span className="flex items-baseline gap-3">
      <span className="text-[13px] text-accent">{ticker}</span>
      <span className="num text-[14px] text-ink">{fmtPrice(latest?.price)}</span>
      <span className={`num text-[12px] ${signClass(latest?.change_percent)}`}>{fmtPct(latest?.change_percent)}</span>
    </span>
  ) : (
    "Chart"
  );

  return (
    <Panel
      title={title}
      aside={latest && <span className="num">open {fmtPrice(latest.open_price)} · since page load</span>}
      className="h-full"
    >
      <div data-testid="main-chart" data-ticker={ticker ?? ""} className="h-full w-full px-1 pb-1 pt-2">
        {!ticker ? (
          <EmptyState>Select a symbol in the watchlist to chart it.</EmptyState>
        ) : data.length < 2 ? (
          <EmptyState>Collecting prices for {ticker}…</EmptyState>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--color-line)" strokeDasharray="0" vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={fmtClock}
                tick={AXIS}
                tickLine={false}
                axisLine={{ stroke: "var(--color-line-strong)" }}
                minTickGap={60}
              />
              <YAxis
                orientation="right"
                domain={["auto", "auto"]}
                tickFormatter={(v: number) => fmtPrice(v)}
                tick={AXIS}
                tickLine={false}
                axisLine={false}
                width={64}
              />
              {latest && (
                <ReferenceLine
                  y={latest.open_price}
                  stroke="var(--color-faint)"
                  strokeDasharray="3 3"
                  ifOverflow="hidden"
                />
              )}
              <Tooltip
                cursor={{ stroke: "var(--color-line-strong)" }}
                isAnimationActive={false}
                content={({ active, payload }) => {
                  const p = active && payload?.[0]?.payload;
                  if (!p) return null;
                  return (
                    <div className="num rounded-sm border border-line-strong bg-raised px-2 py-1 text-[11px]">
                      <div className="text-muted">{fmtClock(p.t)}</div>
                      <div className="text-ink">{fmtPrice(p.p)}</div>
                    </div>
                  );
                }}
              />
              <Line
                type="linear"
                dataKey="p"
                stroke="var(--color-primary)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: "var(--color-panel)", strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </Panel>
  );
}
