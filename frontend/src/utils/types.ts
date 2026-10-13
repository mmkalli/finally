// Wire shapes from PLAN.md §6 (SSE) and §8 (REST).

export type Direction = "up" | "down" | "flat";

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  open_price: number;
  change_percent: number;
  direction: Direction;
  timestamp: string;
}

export type PriceMap = Record<string, PriceUpdate>;

export interface WatchlistEntry {
  ticker: string;
  price: number | null;
  previous_price: number | null;
  open_price: number | null;
  change_percent: number | null;
  direction: Direction | null;
  timestamp: string | null;
}

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

export interface Trade {
  id: string;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  executed_at: string;
}

export interface Snapshot {
  total_value: number;
  recorded_at: string;
}

export interface ChatAction {
  type: "trade" | "watchlist";
  ticker: string;
  side?: "buy" | "sell";
  quantity?: number;
  price?: number;
  action?: "add" | "remove";
  status: "ok" | "error";
  error?: string;
  code?: string;
}

export interface ChatResponse {
  message: string;
  actions: ChatAction[];
}

export type ConnectionStatus = "open" | "connecting" | "closed";
