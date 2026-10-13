import { fmtSignedUsd, fmtUsd, signClass } from "@/utils/format";
import type { ConnectionStatus, Portfolio } from "@/utils/types";

const STATUS_STYLE: Record<ConnectionStatus, { dot: string; label: string }> = {
  open: { dot: "bg-up", label: "Live" },
  connecting: { dot: "bg-accent", label: "Reconnecting" },
  closed: { dot: "bg-down", label: "Disconnected" },
};

export function Header({
  portfolio,
  status,
  onReset,
}: {
  portfolio: Portfolio | null;
  status: ConnectionStatus;
  onReset: () => void;
}) {
  const s = STATUS_STYLE[status];
  return (
    <header className="flex h-14 shrink-0 items-center gap-6 border-b border-line bg-panel px-4">
      <div className="flex items-baseline gap-2">
        <span className="text-[18px] font-semibold tracking-tight text-ink">
          Fin<span className="text-accent">Ally</span>
        </span>
        <span className="hidden text-[11px] text-faint md:inline">AI trading workstation</span>
      </div>

      <div className="ml-auto flex items-center gap-6">
        <Stat label="Portfolio value">
          <span data-testid="header-total-value" className="num text-[20px] font-semibold text-ink">
            {portfolio ? fmtUsd(portfolio.total_value) : "—"}
          </span>
        </Stat>
        <Stat label="Unrealized P&L" className="hidden sm:flex">
          <span className={`num text-[14px] font-medium ${signClass(portfolio?.unrealized_pnl)}`}>
            {portfolio ? fmtSignedUsd(portfolio.unrealized_pnl) : "—"}
          </span>
        </Stat>
        <Stat label="Cash">
          <span data-testid="header-cash" className="num text-[14px] font-medium text-ink">
            {portfolio ? fmtUsd(portfolio.cash_balance) : "—"}
          </span>
        </Stat>

        <div
          data-testid="connection-status"
          data-status={status}
          className="flex items-center gap-2 border-l border-line pl-5 text-[11px] text-muted"
          title={`Price stream: ${s.label.toLowerCase()}`}
          role="status"
        >
          <span className={`h-2 w-2 rounded-full ${s.dot}`} />
          <span className="hidden lg:inline">{s.label}</span>
        </div>

        <button
          type="button"
          onClick={onReset}
          className="rounded-sm border border-line px-2 py-1 text-[11px] text-muted hover:border-line-strong hover:text-ink"
        >
          Reset
        </button>
      </div>
    </header>
  );
}

function Stat({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`flex flex-col items-end leading-tight ${className}`}>
      <span className="text-[10px] text-muted">{label}</span>
      {children}
    </div>
  );
}
