"use client";

import { useAppState } from "@/lib/store";
import { Panel, Placeholder } from "./Panel";

// Stub — fi-ucn builds the Recharts line chart of total_value over time from
// useAppState().snapshots (refetched after every trade).
export function PnlChart({ className }: { className?: string }) {
  const { snapshots } = useAppState();

  return (
    <Panel title="Portfolio Value" className={className} data-testid="pnl-chart">
      <Placeholder>{snapshots.length} snapshots</Placeholder>
    </Panel>
  );
}
