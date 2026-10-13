"use client";

import { useLivePortfolio } from "@/lib/store";
import { Panel, Placeholder } from "./Panel";

// Stub — fi-ucn builds the Recharts treemap: cells sized by market_value,
// filled with pnlColor(pnl_percent) from @/lib/heatmap, each with data-pnl.
export function PortfolioHeatmap({ className }: { className?: string }) {
  const portfolio = useLivePortfolio();
  const count = portfolio?.positions.length ?? 0;

  return (
    <Panel title="Heatmap" className={className} data-testid="portfolio-heatmap">
      <Placeholder>{count ? `${count} positions` : "No positions"}</Placeholder>
    </Panel>
  );
}
