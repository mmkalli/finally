import { describe, expect, it, vi } from "vitest";
import { PriceHistoryStore } from "./priceHistory";
import type { PriceEvent, PriceUpdate } from "./types";

const update = (ticker: string, price: number, timestamp: string): PriceUpdate => ({
  ticker,
  price,
  previous_price: price,
  open_price: price,
  change_percent: 0,
  direction: "flat",
  timestamp,
});

const event = (...updates: PriceUpdate[]): PriceEvent =>
  Object.fromEntries(updates.map((u) => [u.ticker, u]));

const T0 = "2026-10-12T14:03:21.000Z";
const T1 = "2026-10-12T14:03:21.500Z";
const T2 = "2026-10-12T14:03:22.000Z";

describe("PriceHistoryStore", () => {
  it("accumulates points per ticker", () => {
    const store = new PriceHistoryStore();
    store.append(event(update("AAPL", 190, T0), update("MSFT", 410, T0)));
    store.append(event(update("AAPL", 190.5, T1)));

    expect(store.get("AAPL")).toEqual([
      { time: Date.parse(T0), price: 190 },
      { time: Date.parse(T1), price: 190.5 },
    ]);
    expect(store.get("MSFT")).toHaveLength(1);
    expect(store.get("NFLX")).toEqual([]);
  });

  it("ignores repeated or older timestamps", () => {
    const store = new PriceHistoryStore();
    store.append(event(update("AAPL", 190, T1)));
    store.append(event(update("AAPL", 191, T1)));
    store.append(event(update("AAPL", 189, T0)));
    expect(store.get("AAPL")).toEqual([{ time: Date.parse(T1), price: 190 }]);
  });

  it("skips malformed updates", () => {
    const store = new PriceHistoryStore();
    store.append(event(update("AAPL", NaN, T0), update("MSFT", 410, "not a date")));
    expect(store.get("AAPL")).toEqual([]);
    expect(store.get("MSFT")).toEqual([]);
  });

  it("caps each series at maxPoints, keeping the newest", () => {
    const store = new PriceHistoryStore(2);
    for (const [i, t] of [T0, T1, T2].entries()) store.append(event(update("AAPL", 100 + i, t)));
    expect(store.get("AAPL").map((p) => p.price)).toEqual([101, 102]);
  });

  it("replaces only the changed ticker's array (stable snapshots)", () => {
    const store = new PriceHistoryStore();
    store.append(event(update("AAPL", 190, T0), update("MSFT", 410, T0)));
    const aapl = store.get("AAPL");
    const msft = store.get("MSFT");

    store.append(event(update("AAPL", 191, T1)));
    expect(store.get("AAPL")).not.toBe(aapl);
    expect(store.get("MSFT")).toBe(msft);
    expect(aapl).toHaveLength(1);
  });

  it("notifies subscribers only when something was appended", () => {
    const store = new PriceHistoryStore();
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);

    store.append(event(update("AAPL", 190, T0)));
    store.append(event(update("AAPL", 190, T0)));
    store.append({});
    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();
    store.append(event(update("AAPL", 191, T1)));
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("clear() empties every series", () => {
    const store = new PriceHistoryStore();
    store.append(event(update("AAPL", 190, T0)));
    store.clear();
    expect(store.get("AAPL")).toEqual([]);
  });
});
