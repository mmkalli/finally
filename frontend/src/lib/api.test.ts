import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

const mockFetch = (status: number, body?: unknown, statusText = "") => {
  const fn = vi.fn(async () =>
    body === undefined
      ? new Response(null, { status, statusText })
      : new Response(typeof body === "string" ? body : JSON.stringify(body), {
          status,
          statusText,
        }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
};

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("POSTs JSON to the trade endpoint", async () => {
    const fetch = mockFetch(200, { trade: {}, portfolio: {} });
    await api.trade({ ticker: "AAPL", quantity: 10, side: "buy" });

    const [path, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/portfolio/trade");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body as string)).toEqual({ ticker: "AAPL", quantity: 10, side: "buy" });
  });

  it("returns parsed JSON", async () => {
    mockFetch(200, { snapshots: [{ total_value: 10000, recorded_at: "t" }] });
    expect((await api.getPortfolioHistory()).snapshots).toHaveLength(1);
  });

  it("returns undefined for 204 and URL-encodes the ticker", async () => {
    const fetch = mockFetch(204);
    await expect(api.removeFromWatchlist("BRK.B")).resolves.toBeUndefined();
    const [path, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/watchlist/BRK.B");
    expect(init.method).toBe("DELETE");
  });

  it("throws ApiError carrying the API's error and code", async () => {
    mockFetch(400, { error: "Insufficient cash: need $1,950.30", code: "INSUFFICIENT_CASH" });
    const err = await api.trade({ ticker: "AAPL", quantity: 10, side: "buy" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      message: "Insufficient cash: need $1,950.30",
      code: "INSUFFICIENT_CASH",
      status: 400,
    });
  });

  it("falls back to HTTP_<status> when the error body isn't JSON", async () => {
    mockFetch(502, "<html>Bad Gateway</html>", "Bad Gateway");
    const err = await api.getPortfolio().catch((e) => e);
    expect(err).toMatchObject({ code: "HTTP_502", status: 502 });
    expect(err.message).toContain("502");
  });
});
