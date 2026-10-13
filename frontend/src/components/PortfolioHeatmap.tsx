"use client";

import { ResponsiveContainer, Treemap, type TreemapNode } from "recharts";
import { formatCurrency, formatPercent } from "@/lib/format";
import { pnlColor } from "@/lib/heatmap";
import { useAppState, useLivePortfolio } from "@/lib/store";
import type { Position } from "@/lib/types";
import { Panel, Placeholder } from "./Panel";

/** One treemap rectangle. `value` (market value) sizes it; `pnl` colours it. */
export interface HeatmapCell {
  name: string;
  value: number;
  /** `pnl_percent` of the position. */
  pnl: number;
  /** Share of total positions value, in percent. */
  weight: number;
  [key: string]: unknown;
}

/** Positions → treemap cells, largest first. Zero-value positions have no area and are dropped. */
export function heatmapCells(positions: readonly Position[]): HeatmapCell[] {
  const sized = positions.filter((p) => p.market_value > 0);
  const total = sized.reduce((sum, p) => sum + p.market_value, 0);
  return sized
    .map((p) => ({
      name: p.ticker,
      value: p.market_value,
      pnl: p.pnl_percent,
      weight: (p.market_value / total) * 100,
    }))
    .sort((a, b) => b.value - a.value);
}

function HeatmapCellShape(node: TreemapNode) {
  // The root node (depth 0) spans the whole chart; only leaves are drawn.
  if (node.depth === 0) return <g />;
  const { x, y, width, height, name } = node;
  const { pnl, weight, value } = node as unknown as HeatmapCell;
  const showTicker = width > 36 && height > 18;
  const showPnl = width > 48 && height > 36;
  const cx = x + width / 2;
  const cy = y + height / 2;

  return (
    <g className="cursor-pointer">
      <rect
        data-testid="heatmap-cell"
        data-ticker={name}
        data-pnl={pnl}
        x={x}
        y={y}
        width={width}
        height={height}
        fill={pnlColor(pnl)}
        stroke="var(--color-surface)"
        strokeWidth={2}
      />
      <title>{`${name} · ${formatCurrency(value)} · ${weight.toFixed(1)}% of positions · ${formatPercent(pnl)}`}</title>
      {showTicker && (
        <text
          x={cx}
          y={showPnl ? cy - 7 : cy}
          textAnchor="middle"
          dominantBaseline="central"
          fill="#f3f4f6"
          fontSize={12}
          fontWeight={600}
          pointerEvents="none"
        >
          {name}
        </text>
      )}
      {showPnl && (
        <text
          x={cx}
          y={cy + 9}
          textAnchor="middle"
          dominantBaseline="central"
          fill="#f3f4f6"
          fillOpacity={0.85}
          fontSize={11}
          className="tabular"
          pointerEvents="none"
        >
          {formatPercent(pnl)}
        </text>
      )}
    </g>
  );
}

/**
 * Treemap of open positions (PLAN §10): area by portfolio weight, colour by
 * unrealized P&L %. Re-sized and re-coloured live from SSE prices. Clicking a
 * cell charts that ticker.
 */
export function PortfolioHeatmap({ className }: { className?: string }) {
  const portfolio = useLivePortfolio();
  const { selectTicker } = useAppState();
  const cells = heatmapCells(portfolio?.positions ?? []);

  return (
    <Panel
      title="Heatmap"
      className={className}
      bodyClassName="min-h-0 flex-1 p-1"
      data-testid="portfolio-heatmap"
    >
      {cells.length === 0 ? (
        <Placeholder>No positions</Placeholder>
      ) : (
        <ResponsiveContainer width="100%" height="100%" minHeight={120}>
          <Treemap
            data={cells}
            dataKey="value"
            nameKey="name"
            isAnimationActive={false}
            content={HeatmapCellShape}
            onClick={(node: TreemapNode) => selectTicker(node.name)}
          />
        </ResponsiveContainer>
      )}
    </Panel>
  );
}
