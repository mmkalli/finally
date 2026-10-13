"use client";

import { formatCurrency } from "@/lib/format";
import { useLivePortfolio, useMarket } from "@/lib/store";
import type { ConnectionStatus } from "@/lib/usePriceStream";

const DOT: Record<ConnectionStatus, string> = {
  open: "bg-up",
  connecting: "bg-accent",
  closed: "bg-down",
};

// Stub — fi-x5z builds the full header (live total, cash, status dot).
export function Header() {
  const portfolio = useLivePortfolio();
  const { connection } = useMarket();

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-surface px-4">
      <h1 className="text-lg font-bold tracking-tight">
        Fin<span className="text-accent">Ally</span>
      </h1>
      <div className="flex items-center gap-6 text-sm">
        <span className="text-muted">
          Total{" "}
          <span className="tabular text-foreground">
            {portfolio ? formatCurrency(portfolio.total_value) : "—"}
          </span>
        </span>
        <span className="text-muted">
          Cash{" "}
          <span className="tabular text-foreground">
            {portfolio ? formatCurrency(portfolio.cash_balance) : "—"}
          </span>
        </span>
        <span
          data-testid="connection-status"
          data-status={connection}
          title={`Price stream: ${connection}`}
          className={`h-2.5 w-2.5 rounded-full ${DOT[connection]}`}
        />
      </div>
    </header>
  );
}
