import type { ChatResponse, Portfolio, Snapshot, Trade, WatchlistEntry } from "./types";

/** Error carrying the backend's `{error, code}` body (PLAN.md §8). */
export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch {
    throw new ApiError("Can't reach the server. Check that the backend is running.", "NETWORK", 0);
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const message =
      body?.error ?? (typeof body?.detail === "string" ? body.detail : `Request failed (${res.status})`);
    throw new ApiError(message, body?.code ?? "HTTP_ERROR", res.status);
  }
  return body as T;
}

const post = (data: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(data) });

export const api = {
  portfolio: () => request<Portfolio>("/api/portfolio"),
  history: () => request<{ snapshots: Snapshot[] }>("/api/portfolio/history"),
  trade: (ticker: string, quantity: number, side: "buy" | "sell") =>
    request<{ trade: Trade; portfolio: Portfolio }>("/api/portfolio/trade", post({ ticker, quantity, side })),
  reset: () => request<Portfolio>("/api/reset", { method: "POST" }),
  watchlist: () => request<{ tickers: WatchlistEntry[] }>("/api/watchlist"),
  addTicker: (ticker: string) => request<WatchlistEntry>("/api/watchlist", post({ ticker })),
  removeTicker: (ticker: string) =>
    request<void>(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" }),
  chat: (message: string) => request<ChatResponse>("/api/chat", post({ message })),
};
