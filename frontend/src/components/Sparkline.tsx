"use client";

import { memo } from "react";
import { Line, LineChart, YAxis } from "recharts";
import type { PricePoint } from "@/utils/priceStore";

const SPARK_POINTS = 120; // last ~60s

/** Price since page load; colour follows the move across the visible window. */
export const Sparkline = memo(function Sparkline({ points }: { points: PricePoint[] | undefined }) {
  const data = points ? points.slice(-SPARK_POINTS) : [];
  if (data.length < 2) return <div className="h-6 w-[84px]" aria-hidden />;
  const rising = data[data.length - 1].p >= data[0].p;
  return (
    <LineChart width={84} height={24} data={data} margin={{ top: 2, right: 0, bottom: 2, left: 0 }} aria-hidden>
      <YAxis hide domain={["dataMin", "dataMax"]} />
      <Line
        type="linear"
        dataKey="p"
        stroke={rising ? "var(--color-up)" : "var(--color-down)"}
        strokeWidth={1.5}
        dot={false}
        isAnimationActive={false}
      />
    </LineChart>
  );
});
