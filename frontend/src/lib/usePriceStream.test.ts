import { describe, expect, it } from "vitest";
import { connectionStatusFromReadyState, parsePriceEvent } from "./usePriceStream";

describe("connectionStatusFromReadyState", () => {
  it("maps EventSource readyState to the status dot (PLAN §10)", () => {
    expect(connectionStatusFromReadyState(0)).toBe("connecting");
    expect(connectionStatusFromReadyState(1)).toBe("open");
    expect(connectionStatusFromReadyState(2)).toBe("closed");
  });
});

describe("parsePriceEvent", () => {
  it("parses an event keyed by ticker", () => {
    const data = JSON.stringify({
      AAPL: {
        ticker: "AAPL",
        price: 190.12,
        previous_price: 190.05,
        open_price: 189.5,
        change_percent: 0.33,
        direction: "up",
        timestamp: "2026-10-12T14:03:21.512Z",
      },
    });
    expect(parsePriceEvent(data)?.AAPL.price).toBe(190.12);
  });

  it("returns null for non-object or invalid payloads", () => {
    expect(parsePriceEvent("not json")).toBeNull();
    expect(parsePriceEvent("[1,2]")).toBeNull();
    expect(parsePriceEvent("null")).toBeNull();
    expect(parsePriceEvent("42")).toBeNull();
  });
});
