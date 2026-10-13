"use client";

import { useLiveWatchlist } from "@/lib/store";
import { Panel, Placeholder } from "./Panel";

// Stub — fi-x5z builds the watchlist grid (price flash, change %, sparklines,
// add/remove, click to select via useAppState().selectTicker).
export function Watchlist({ className }: { className?: string }) {
  const watchlist = useLiveWatchlist();

  return (
    <Panel title="Watchlist" className={className} data-testid="watchlist">
      <Placeholder>{watchlist.length} tickers watched</Placeholder>
    </Panel>
  );
}
