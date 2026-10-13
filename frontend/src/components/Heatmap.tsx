"use client";

import { ResponsiveContainer, Treemap } from "recharts";
import { fmtPct, fmtUsd } from "@/utils/format";
import { heatmapColor } from "@/utils/heatmap";
import type { Position } from "@/utils/types";
import { EmptyState, Panel } from "./Panel";

type Cell = {
  name: string;
  size: number;
  pnl: number;
  value: number;
  weight: number;
};

interface NodeProps {
  x: number;
  y: number;
  width: number;
  height: number;
  depth: number;
  name: string;
  pnl: number;
  value: number;
  weight: number;
}

function HeatCell(props: Partial<NodeProps>) {
  const { x = 0, y = 0, width = 0, height = 0, depth, name, pnl = 0, value = 0, weight = 0 } = props;
  if (depth !== 1 || width <= 0 || height <= 0) return null;
  const showName = width > 34 && height > 18;
  const showPct = width > 46 && height > 34;
  const big = width > 90 && height > 56;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={2}
        fill={heatmapColor(pnl)}
        stroke="var(--color-panel)"
        strokeWidth={2}
        data-pnl={pnl}
        data-ticker={name}
      >
        <title>{`${name}: ${fmtPct(pnl)} · ${fmtUsd(value)} · ${weight.toFixed(1)}% of holdings`}</title>
      </rect>
      {showName && (
        <text
          x={x + 6}
          y={y + (big ? 18 : 14)}
          fill="#f2f5f8"
          fontSize={big ? 13 : 11}
          fontWeight={600}
          pointerEvents="none"
        >
          {name}
        </text>
      )}
      {showPct && (
        <text
          x={x + 6}
          y={y + (big ? 34 : 28)}
          fill="#f2f5f8"
          fillOpacity={0.85}
          fontSize={11}
          fontFamily="var(--font-mono)"
          pointerEvents="none"
        >
          {fmtPct(pnl)}
        </text>
      )}
    </g>
  );
}

export function Heatmap({ positions }: { positions: Position[] }) {
  const total = positions.reduce((s, p) => s + Math.max(p.market_value, 0), 0);
  const data: Cell[] = positions
    .filter((p) => p.market_value > 0)
    .map((p) => ({
      name: p.ticker,
      size: p.market_value,
      pnl: p.pnl_percent,
      value: p.market_value,
      weight: total ? (p.market_value / total) * 100 : 0,
    }));

  return (
    <Panel
      title="Holdings heatmap"
      aside={
        <span className="flex items-center gap-1.5" aria-label="Colour scale: −10% red, 0% gray, +10% green">
          <span className="num">−10%</span>
          <span
            className="h-2 w-16 rounded-sm"
            style={{ background: `linear-gradient(90deg, ${heatmapColor(-10)}, ${heatmapColor(0)}, ${heatmapColor(10)})` }}
          />
          <span className="num">+10%</span>
        </span>
      }
      className="h-full"
    >
      <div data-testid="heatmap" className="h-full w-full p-1">
        {data.length === 0 ? (
          <EmptyState>No positions yet. Buy a symbol to see it here, sized by weight.</EmptyState>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <Treemap
              data={data}
              dataKey="size"
              nameKey="name"
              isAnimationActive={false}
              content={<HeatCell />}
            />
          </ResponsiveContainer>
        )}
      </div>
    </Panel>
  );
}
