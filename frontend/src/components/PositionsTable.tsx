import { fmtPct, fmtPrice, fmtQty, fmtSignedUsd, fmtUsd, signClass } from "@/utils/format";
import type { Position } from "@/utils/types";
import { Panel } from "./Panel";

export function PositionsTable({
  positions,
  onSelect,
}: {
  positions: Position[];
  onSelect: (ticker: string) => void;
}) {
  return (
    <Panel title="Positions" aside={<span className="num">{positions.length}</span>} bodyClassName="overflow-auto">
      <table className="w-full border-collapse text-[12px]">
        <thead className="sticky top-0 bg-panel text-[10px] text-faint">
          <tr className="border-b border-line">
            <th className="px-3 py-1 text-left font-normal">Symbol</th>
            <th className="px-3 py-1 text-right font-normal">Qty</th>
            <th className="px-3 py-1 text-right font-normal">Avg cost</th>
            <th className="px-3 py-1 text-right font-normal">Last</th>
            <th className="px-3 py-1 text-right font-normal">Market value</th>
            <th className="px-3 py-1 text-right font-normal">Unrealized P&amp;L</th>
            <th className="px-3 py-1 text-right font-normal">% chg</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr
              key={p.ticker}
              data-testid={`position-row-${p.ticker}`}
              onClick={() => onSelect(p.ticker)}
              className="cursor-pointer border-b border-line/60 hover:bg-raised"
            >
              <td className="px-3 py-1 font-semibold">{p.ticker}</td>
              <td className="num px-3 py-1 text-right">{fmtQty(p.quantity)}</td>
              <td className="num px-3 py-1 text-right text-muted">{fmtPrice(p.avg_cost)}</td>
              <td className="num px-3 py-1 text-right">{fmtPrice(p.current_price)}</td>
              <td className="num px-3 py-1 text-right">{fmtUsd(p.market_value)}</td>
              <td className={`num px-3 py-1 text-right ${signClass(p.unrealized_pnl)}`}>
                {fmtSignedUsd(p.unrealized_pnl)}
              </td>
              <td className={`num px-3 py-1 text-right ${signClass(p.pnl_percent)}`}>{fmtPct(p.pnl_percent)}</td>
            </tr>
          ))}
          {positions.length === 0 && (
            <tr>
              <td colSpan={7} className="px-3 py-4 text-center text-muted">
                No open positions. Use the trade bar or ask FinAlly to buy something.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Panel>
  );
}
