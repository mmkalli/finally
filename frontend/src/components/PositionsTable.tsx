"use client";

import { useLivePortfolio } from "@/lib/store";
import { Panel, Placeholder } from "./Panel";

// Stub — fi-ucn builds the table: ticker, quantity, avg cost, current price,
// unrealized P&L, % change, from the live-revalued portfolio.
export function PositionsTable({ className }: { className?: string }) {
  const portfolio = useLivePortfolio();
  const count = portfolio?.positions.length ?? 0;

  return (
    <Panel title="Positions" className={className} data-testid="positions-table">
      <Placeholder>{count ? `${count} positions` : "No positions"}</Placeholder>
    </Panel>
  );
}
