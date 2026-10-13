"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtClock, fmtUsd } from "@/utils/format";
import type { Snapshot } from "@/utils/types";
import { EmptyState, Panel } from "./Panel";

const AXIS = { fill: "var(--color-muted)", fontSize: 10, fontFamily: "var(--font-mono)" };
const STARTING_VALUE = 10000;

/**
 * Round-number ticks covering the series and the $10k starting line, with a minimum span so a
 * near-flat portfolio doesn't turn cents of drift into a steep-looking chart.
 */
function valueTicks(values: number[]): number[] {
  const lo = Math.min(...values, STARTING_VALUE);
  const hi = Math.max(...values, STARTING_VALUE);
  const span = Math.max(hi - lo, hi * 0.002);
  const raw = span / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const mid = (lo + hi) / 2;
  const start = Math.floor((mid - span / 2) / step) * step;
  const end = Math.ceil((mid + span / 2) / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Math.round(v * 100) / 100);
  return ticks;
}

export function PnlChart({ snapshots }: { snapshots: Snapshot[] }) {
  const data = snapshots.map((s) => ({ t: Date.parse(s.recorded_at), v: s.total_value }));
  const ticks = data.length ? valueTicks(data.map((d) => d.v)) : [0, 1];
  const domain: [number, number] = [ticks[0], ticks[ticks.length - 1]];
  const cents = ticks.some((t) => !Number.isInteger(t));
  const tickUsd = (v: number) =>
    "$" + v.toLocaleString("en-US", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 });

  return (
    <Panel title="Portfolio value" aside={<span className="truncate">every 30s and after trades</span>} className="h-full">
      <div data-testid="pnl-chart" data-points={data.length} className="h-full w-full px-1 pb-1 pt-2">
        {data.length === 0 ? (
          <EmptyState>The first snapshot is recorded within 30 seconds.</EmptyState>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--color-line)" vertical={false} />
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
                domain={domain}
                tickFormatter={tickUsd}
                ticks={ticks}
                interval={0}
                tick={AXIS}
                tickLine={false}
                axisLine={false}
                width={76}
              />
              <ReferenceLine y={STARTING_VALUE} stroke="var(--color-faint)" strokeDasharray="3 3" ifOverflow="hidden" />
              <Tooltip
                cursor={{ stroke: "var(--color-line-strong)" }}
                isAnimationActive={false}
                content={({ active, payload }) => {
                  const p = active && payload?.[0]?.payload;
                  if (!p) return null;
                  return (
                    <div className="num rounded-sm border border-line-strong bg-raised px-2 py-1 text-[11px]">
                      <div className="text-muted">{fmtClock(p.t)}</div>
                      <div className="text-ink">{fmtUsd(p.v)}</div>
                    </div>
                  );
                }}
              />
              <Line
                type="linear"
                dataKey="v"
                stroke="var(--color-accent)"
                strokeWidth={2}
                dot={data.length < 3 ? { r: 3, fill: "var(--color-accent)", strokeWidth: 0 } : false}
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
