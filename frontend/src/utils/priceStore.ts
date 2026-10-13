import type { PriceMap } from "./types";

export interface PricePoint {
  t: number; // epoch ms
  p: number;
}

export const MAX_POINTS = 1200; // ~10 minutes at 2 ticks/s

/**
 * Client-side price store fed by the SSE stream (PLAN.md §10 "Price history").
 * Holds the latest update per ticker plus a capped history that feeds sparklines and the main chart.
 * Each tick replaces only the arrays of tickers that changed, so memoised consumers stay cheap.
 */
export class PriceStore {
  latest: PriceMap = {};
  history: Record<string, PricePoint[]> = {};
  private listeners = new Set<() => void>();
  private version = 0;

  apply(updates: PriceMap) {
    const entries = Object.entries(updates).filter(([, u]) => u && typeof u.price === "number");
    if (!entries.length) return;
    const latest = { ...this.latest };
    const history = { ...this.history };
    for (const [ticker, u] of entries) {
      latest[ticker] = u;
      const t = Date.parse(u.timestamp) || Date.now();
      const prev = history[ticker] ?? [];
      if (prev.length && prev[prev.length - 1].t >= t) continue;
      const next = prev.length >= MAX_POINTS ? prev.slice(prev.length - MAX_POINTS + 1) : prev.slice();
      next.push({ t, p: u.price });
      history[ticker] = next;
    }
    this.latest = latest;
    this.history = history;
    this.version++;
    this.listeners.forEach((l) => l());
  }

  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };

  getVersion = () => this.version;
}
