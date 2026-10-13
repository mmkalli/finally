// API shapes from planning/PLAN.md §6 and §8. Money is dollars (2 dp),
// quantities 4 dp, timestamps ISO 8601 UTC strings.

export type Direction = "up" | "down" | "flat";
export type TradeSide = "buy" | "sell";

/** One ticker in an SSE event (and a priced watchlist entry). */
export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  open_price: number;
  change_percent: number;
  direction: Direction;
  timestamp: string;
}

/** One SSE `data:` event: only the tickers that changed, keyed by ticker. */
export type PriceEvent = Record<string, PriceUpdate>;

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  pnl_percent: number;
}

export interface Portfolio {
  cash_balance: number;
  positions_value: number;
  total_value: number;
  unrealized_pnl: number;
  positions: Position[];
}

export interface TradeRequest {
  ticker: string;
  quantity: number;
  side: TradeSide;
}

export interface Trade {
  id: string;
  ticker: string;
  side: TradeSide;
  quantity: number;
  price: number;
  executed_at: string;
}

export interface TradeResponse {
  trade: Trade;
  portfolio: Portfolio;
}

export interface PortfolioSnapshot {
  total_value: number;
  recorded_at: string;
}

export interface PortfolioHistory {
  snapshots: PortfolioSnapshot[];
}

/** A watched ticker. Price fields are null until the ticker has been priced. */
export interface WatchlistEntry {
  ticker: string;
  price: number | null;
  previous_price: number | null;
  open_price: number | null;
  change_percent: number | null;
  direction: Direction | null;
  timestamp: string | null;
}

export interface Watchlist {
  tickers: WatchlistEntry[];
}

export type ErrorCode =
  | "INVALID_TICKER"
  | "UNKNOWN_TICKER"
  | "INVALID_QUANTITY"
  | "INSUFFICIENT_CASH"
  | "INSUFFICIENT_SHARES"
  | "NO_PRICE"
  | "NOT_FOUND";

/** The single error shape every endpoint uses. */
export interface ApiErrorBody {
  error: string;
  code: ErrorCode | string;
}

export type ActionStatus = "ok" | "error";

export interface TradeAction {
  type: "trade";
  ticker: string;
  side: TradeSide;
  quantity: number;
  /** Fill price; present when status is "ok". */
  price?: number;
  status: ActionStatus;
  error?: string;
  code?: string;
}

export interface WatchlistAction {
  type: "watchlist";
  ticker: string;
  action: "add" | "remove";
  status: ActionStatus;
  error?: string;
  code?: string;
}

export type ChatAction = TradeAction | WatchlistAction;

export interface ChatResponse {
  message: string;
  actions: ChatAction[];
}

export interface Health {
  status: "ok";
}
