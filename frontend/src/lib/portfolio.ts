import type { Portfolio, Position } from "./types";

/** Latest known price per ticker, from the SSE stream. */
export type PriceMap = Record<string, { price: number } | undefined>;

export const round2 = (n: number) => Math.round(n * 100) / 100;

/** Re-values one position at `price` (PLAN §8 field semantics). */
export function revaluePosition(position: Position, price: number): Position {
  const { quantity, avg_cost } = position;
  return {
    ...position,
    current_price: price,
    market_value: round2(quantity * price),
    unrealized_pnl: round2((price - avg_cost) * quantity),
    pnl_percent: avg_cost > 0 ? round2(((price - avg_cost) / avg_cost) * 100) : 0,
  };
}

/**
 * The last `/api/portfolio` response re-valued at live SSE prices (PLAN §10
 * "Live values"). Tickers without a streamed price keep the server's
 * `current_price`. Totals are sums of the rounded per-position values, so
 * they always agree with what the positions table shows.
 */
export function computeLivePortfolio(portfolio: Portfolio, prices: PriceMap): Portfolio {
  const positions = portfolio.positions.map((p) =>
    revaluePosition(p, prices[p.ticker]?.price ?? p.current_price),
  );
  const positionsValue = round2(positions.reduce((sum, p) => sum + p.market_value, 0));
  const unrealizedPnl = round2(positions.reduce((sum, p) => sum + p.unrealized_pnl, 0));
  return {
    cash_balance: portfolio.cash_balance,
    positions_value: positionsValue,
    total_value: round2(portfolio.cash_balance + positionsValue),
    unrealized_pnl: unrealizedPnl,
    positions,
  };
}
