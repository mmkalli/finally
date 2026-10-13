import type { Portfolio, Position } from "./types";

const round = (n: number, dp: number) => {
  const f = 10 ** dp;
  return Math.round(n * f) / f;
};

/**
 * Re-values the last portfolio response with live SSE prices (PLAN.md §10 "Live values").
 * Tickers without a live price keep the server's current_price.
 */
export function computeLivePortfolio(
  portfolio: Portfolio,
  livePrices: Record<string, number | undefined>,
): Portfolio {
  const positions: Position[] = portfolio.positions.map((p) => {
    const current_price = livePrices[p.ticker] ?? p.current_price;
    const market_value = round(p.quantity * current_price, 2);
    const unrealized_pnl = round((current_price - p.avg_cost) * p.quantity, 2);
    const pnl_percent = p.avg_cost > 0 ? round(((current_price - p.avg_cost) / p.avg_cost) * 100, 2) : 0;
    return { ...p, current_price, market_value, unrealized_pnl, pnl_percent };
  });
  const positions_value = round(
    positions.reduce((s, p) => s + p.market_value, 0),
    2,
  );
  return {
    cash_balance: portfolio.cash_balance,
    positions_value,
    total_value: round(portfolio.cash_balance + positions_value, 2),
    unrealized_pnl: round(
      positions.reduce((s, p) => s + p.unrealized_pnl, 0),
      2,
    ),
    positions,
  };
}
