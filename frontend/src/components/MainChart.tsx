"use client";

import { useAppState, usePriceHistory } from "@/lib/store";
import { Panel, Placeholder } from "./Panel";

// Stub — fi-x5z builds the selected ticker's price chart (Recharts) from usePriceHistory.
export function MainChart({ className }: { className?: string }) {
  const { selectedTicker } = useAppState();
  const points = usePriceHistory(selectedTicker);

  return (
    <Panel title={selectedTicker ?? "Chart"} className={className} data-testid="main-chart">
      <Placeholder>
        {selectedTicker ? `${points.length} price points` : "Select a ticker"}
      </Placeholder>
    </Panel>
  );
}
