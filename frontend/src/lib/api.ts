import type {
  ApiErrorBody,
  ChatResponse,
  Health,
  Portfolio,
  PortfolioHistory,
  TradeRequest,
  TradeResponse,
  Watchlist,
  WatchlistEntry,
} from "./types";

/** SSE endpoint, for `new EventSource(...)`. */
export const PRICE_STREAM_URL = "/api/stream/prices";

/** A non-2xx response. `code` is the API's error code, or "HTTP_<status>" if the body wasn't JSON. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = init?.body ? { "Content-Type": "application/json" } : undefined;
  const res = await fetch(path, { ...init, headers: { ...headers, ...init?.headers } });

  if (!res.ok) {
    let body: Partial<ApiErrorBody> = {};
    try {
      body = await res.json();
    } catch {
      // Not our JSON error shape (e.g. a proxy error page); fall through.
    }
    throw new ApiError(
      body.error ?? `Request failed: ${res.status} ${res.statusText}`,
      body.code ?? `HTTP_${res.status}`,
      res.status,
    );
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/api/health"),

  getPortfolio: () => request<Portfolio>("/api/portfolio"),
  trade: (req: TradeRequest) => request<TradeResponse>("/api/portfolio/trade", post(req)),
  getPortfolioHistory: () => request<PortfolioHistory>("/api/portfolio/history"),
  reset: () => request<Portfolio>("/api/reset", { method: "POST" }),

  getWatchlist: () => request<Watchlist>("/api/watchlist"),
  addToWatchlist: (ticker: string) => request<WatchlistEntry>("/api/watchlist", post({ ticker })),
  removeFromWatchlist: (ticker: string) =>
    request<void>(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" }),

  chat: (message: string) => request<ChatResponse>("/api/chat", post({ message })),
};
