"use client";

import { formatCurrency, formatPercent, formatPrice, formatQuantity } from "@/lib/format";
import { useAppState, useLivePortfolio } from "@/lib/store";
import { Panel, Placeholder } from "./Panel";

const pnlClass = (n: number) => (n > 0 ? "text-up" : n < 0 ? "text-down" : "text-flat");

const HEADERS = ["Ticker", "Qty", "Avg Cost", "Price", "P&L", "%"];

/** Open positions re-valued at live SSE prices. Clicking a row charts that ticker. */
export function PositionsTable({ className }: { className?: string }) {
  const portfolio = useLivePortfolio();
  const { selectTicker } = useAppState();
  const positions = portfolio?.positions ?? [];

  return (
    <Panel
      title="Positions"
      className={className}
      bodyClassName="min-h-0 flex-1 overflow-auto"
      data-testid="positions-table"
    >
      {positions.length === 0 ? (
        <Placeholder>No positions</Placeholder>
      ) : (
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-surface text-muted">
            <tr>
              {HEADERS.map((h, i) => (
                <th
                  key={h}
                  scope="col"
                  className={`px-2 py-1 font-medium ${i === 0 ? "text-left" : "text-right"}`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="tabular">
            {positions.map((p) => (
              <tr
                key={p.ticker}
                data-testid="position-row"
                data-ticker={p.ticker}
                onClick={() => selectTicker(p.ticker)}
                className="cursor-pointer border-t border-border hover:bg-surface-raised"
              >
                <td className="px-2 py-1 text-left font-sans font-semibold">{p.ticker}</td>
                <td className="px-2 py-1 text-right" data-testid="position-quantity">
                  {formatQuantity(p.quantity)}
                </td>
                <td className="px-2 py-1 text-right">{formatPrice(p.avg_cost)}</td>
                <td className="px-2 py-1 text-right" data-testid="position-price">
                  {formatPrice(p.current_price)}
                </td>
                <td
                  className={`px-2 py-1 text-right ${pnlClass(p.unrealized_pnl)}`}
                  data-testid="position-pnl"
                >
                  {formatCurrency(p.unrealized_pnl)}
                </td>
                <td
                  className={`px-2 py-1 text-right ${pnlClass(p.pnl_percent)}`}
                  data-testid="position-pnl-percent"
                >
                  {formatPercent(p.pnl_percent)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
