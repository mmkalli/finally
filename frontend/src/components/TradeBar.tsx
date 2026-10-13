"use client";

import { Panel, Placeholder } from "./Panel";

// Stub — fi-x5z builds ticker/quantity inputs, buy/sell buttons and inline
// API errors, via useAppState().trade (throws ApiError on rejection).
export function TradeBar({ className }: { className?: string }) {
  return (
    <Panel title="Trade" className={className} data-testid="trade-bar">
      <Placeholder>Trade bar</Placeholder>
    </Panel>
  );
}
