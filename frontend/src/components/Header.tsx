"use client";

import { formatCurrency } from "@/lib/format";
import { useLivePortfolio, useMarket } from "@/lib/store";
import type { ConnectionStatus } from "@/lib/usePriceStream";

const STATUS: Record<ConnectionStatus, { dot: string; label: string }> = {
  open: { dot: "bg-up", label: "Live" },
  connecting: { dot: "bg-accent", label: "Reconnecting" },
  closed: { dot: "bg-down", label: "Disconnected" },
};

function Stat({ label, value, testId }: { label: string; value: string; testId: string }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-[10px] tracking-wider text-muted uppercase">{label}</span>
      <span data-testid={testId} className="tabular text-sm text-foreground">
        {value}
      </span>
    </div>
  );
}

/** Live portfolio total (re-valued at SSE prices), cash, and the price-stream status dot. */
export function Header() {
  const portfolio = useLivePortfolio();
  const { connection } = useMarket();
  const status = STATUS[connection];

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-surface px-4">
      <h1 className="text-lg font-bold tracking-tight">
        Fin<span className="text-accent">Ally</span>
      </h1>
      <div className="flex items-center gap-6">
        <Stat
          label="Portfolio"
          testId="header-total-value"
          value={portfolio ? formatCurrency(portfolio.total_value) : "—"}
        />
        <Stat
          label="Cash"
          testId="header-cash"
          value={portfolio ? formatCurrency(portfolio.cash_balance) : "—"}
        />
        <div className="flex items-center gap-1.5" title={`Price stream: ${status.label}`}>
          <span
            data-testid="connection-status"
            data-status={connection}
            aria-label={`Price stream ${status.label.toLowerCase()}`}
            role="status"
            className={`h-2.5 w-2.5 rounded-full ${status.dot}`}
          />
          <span className="text-xs text-muted">{status.label}</span>
        </div>
      </div>
    </header>
  );
}
