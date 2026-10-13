"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatCurrency, formatPercent } from "@/lib/format";
import { useAppState } from "@/lib/store";
import type { PortfolioSnapshot } from "@/lib/types";
import { Panel, Placeholder } from "./Panel";

export interface PnlPoint {
  /** Epoch ms of `recorded_at`. */
  time: number;
  value: number;
}

/** Snapshots → chart points in time order; unparseable timestamps are dropped. */
export function pnlSeries(snapshots: readonly PortfolioSnapshot[]): PnlPoint[] {
  return snapshots
    .map((s) => ({ time: Date.parse(s.recorded_at), value: s.total_value }))
    .filter((p) => Number.isFinite(p.time))
    .sort((a, b) => a.time - b.time);
}

/** Change from the first to the last point, or null with fewer than two points. */
export function seriesChange(points: readonly PnlPoint[]) {
  if (points.length < 2) return null;
  const first = points[0].value;
  const change = points[points.length - 1].value - first;
  return { change, percent: first > 0 ? (change / first) * 100 : 0 };
}

const TREND = {
  up: { text: "text-up", stroke: "var(--color-up)" },
  down: { text: "text-down", stroke: "var(--color-down)" },
  flat: { text: "text-muted", stroke: "var(--color-primary)" },
} as const;

const formatTime = (ms: number) =>
  new Date(ms).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });

const formatAxisValue = (n: number) =>
  `$${n.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 })}`;

/** Total portfolio value over time from `/api/portfolio/history` (PLAN §10). */
export function PnlChart({ className }: { className?: string }) {
  const { snapshots } = useAppState();
  const points = pnlSeries(snapshots);
  const delta = seriesChange(points);
  const trend = TREND[!delta || delta.change === 0 ? "flat" : delta.change > 0 ? "up" : "down"];

  return (
    <Panel
      title="Portfolio Value"
      className={className}
      bodyClassName="min-h-0 flex-1 p-1"
      data-testid="pnl-chart"
      actions={
        delta && (
          <span data-testid="pnl-change" className={`tabular text-xs ${trend.text}`}>
            {delta.change > 0 ? "+" : ""}
            {formatCurrency(delta.change)} ({formatPercent(delta.percent)})
          </span>
        )
      }
    >
      {points.length === 0 ? (
        <Placeholder>No history yet</Placeholder>
      ) : (
        <div className="h-full w-full" data-testid="pnl-chart-plot" data-points={points.length}>
          <ResponsiveContainer width="100%" height="100%" minHeight={120}>
            <LineChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="time"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={formatTime}
                stroke="var(--color-muted)"
                tick={{ fontSize: 10 }}
                minTickGap={24}
              />
              <YAxis
                domain={["auto", "auto"]}
                tickFormatter={formatAxisValue}
                stroke="var(--color-muted)"
                tick={{ fontSize: 10 }}
                width={52}
              />
              <Tooltip
                labelFormatter={(ms) => new Date(Number(ms)).toLocaleString("en-US")}
                formatter={(v) => [formatCurrency(Number(v)), "Total value"]}
                contentStyle={{
                  background: "var(--color-surface-raised)",
                  border: "1px solid var(--color-border)",
                  fontSize: 12,
                }}
                labelStyle={{ color: "var(--color-muted)" }}
                itemStyle={{ color: "var(--color-foreground)" }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={trend.stroke}
                strokeWidth={2}
                // A single snapshot has no line segment; show it as a dot instead.
                dot={points.length === 1}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}
