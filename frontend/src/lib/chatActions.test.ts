import { describe, expect, it } from "vitest";
import { describeAction } from "./chatActions";

describe("describeAction", () => {
  it("summarises a filled buy with its price", () => {
    expect(
      describeAction({
        type: "trade",
        ticker: "AAPL",
        side: "buy",
        quantity: 10,
        price: 195.03,
        status: "ok",
      }),
    ).toBe("Bought 10 AAPL @ $195.03");
  });

  it("summarises a filled sell with fractional quantity", () => {
    expect(
      describeAction({
        type: "trade",
        ticker: "MSFT",
        side: "sell",
        quantity: 0.5,
        price: 1234.5,
        status: "ok",
      }),
    ).toBe("Sold 0.5 MSFT @ $1,234.50");
  });

  it("omits the price when an ok trade has none", () => {
    expect(
      describeAction({ type: "trade", ticker: "V", side: "buy", quantity: 1, status: "ok" }),
    ).toBe("Bought 1 V");
  });

  it("includes the API error for a failed trade", () => {
    expect(
      describeAction({
        type: "trade",
        ticker: "TSLA",
        side: "sell",
        quantity: 5,
        status: "error",
        error: "Insufficient shares: you hold 0 TSLA",
        code: "INSUFFICIENT_SHARES",
      }),
    ).toBe("Sell 5 TSLA failed: Insufficient shares: you hold 0 TSLA");
  });

  it("summarises watchlist adds and removes", () => {
    expect(describeAction({ type: "watchlist", ticker: "PYPL", action: "add", status: "ok" })).toBe(
      "Added PYPL to watchlist",
    );
    expect(
      describeAction({ type: "watchlist", ticker: "NFLX", action: "remove", status: "ok" }),
    ).toBe("Removed NFLX from watchlist");
  });

  it("includes the API error for a failed watchlist change", () => {
    expect(
      describeAction({
        type: "watchlist",
        ticker: "ZZZ",
        action: "remove",
        status: "error",
        error: "ZZZ is not on the watchlist",
        code: "NOT_FOUND",
      }),
    ).toBe("Remove ZZZ from watchlist failed: ZZZ is not on the watchlist");
  });

  it("falls back when an error action has no message", () => {
    expect(describeAction({ type: "watchlist", ticker: "X", action: "add", status: "error" })).toBe(
      "Add X to watchlist failed: unknown error",
    );
  });
});
