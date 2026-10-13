import type { PriceEvent } from "./types";

export interface PricePoint {
  /** Epoch milliseconds of the update. */
  time: number;
  price: number;
}

/** ~8 minutes of history per ticker at the simulator's 500ms tick. */
export const DEFAULT_MAX_POINTS = 1000;

const EMPTY: readonly PricePoint[] = Object.freeze([]);

/**
 * Per-ticker price history accumulated from the SSE stream since page load
 * (PLAN §10: there is no price-history endpoint). Feeds both the watchlist
 * sparklines and the main chart.
 *
 * Each ticker's array is replaced (never mutated) on append, so `get(ticker)`
 * works as a `useSyncExternalStore` snapshot: components re-render only when
 * their own ticker changes.
 */
export class PriceHistoryStore {
  private series = new Map<string, readonly PricePoint[]>();
  private listeners = new Set<() => void>();

  constructor(private readonly maxPoints = DEFAULT_MAX_POINTS) {}

  get(ticker: string): readonly PricePoint[] {
    return this.series.get(ticker) ?? EMPTY;
  }

  /** Appends every ticker in an SSE event. Repeated timestamps are ignored. */
  append(event: PriceEvent): void {
    let changed = false;
    for (const update of Object.values(event)) {
      const time = Date.parse(update.timestamp);
      if (!Number.isFinite(time) || !Number.isFinite(update.price)) continue;
      const prev = this.get(update.ticker);
      if (prev.length > 0 && prev[prev.length - 1].time >= time) continue;
      const next = [...prev, { time, price: update.price }];
      this.series.set(
        update.ticker,
        next.length > this.maxPoints ? next.slice(-this.maxPoints) : next,
      );
      changed = true;
    }
    if (changed) this.emit();
  }

  clear(): void {
    this.series.clear();
    this.emit();
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private emit(): void {
    for (const listener of this.listeners) listener();
  }
}
