# backend/tests/market/fake_massive.py
"""In-memory stand-in for the Massive REST API, served through httpx.MockTransport."""
from __future__ import annotations

import httpx

from app.market.massive import BASE_URL


class FakeMassive:
    def __init__(self, *, plan: str = "paid") -> None:
        self.plan = plan  # "paid" -> snapshots allowed, "free" -> snapshot 403
        self.snapshot: dict[str, dict] = {}       # ticker -> snapshot item
        self.grouped: dict[str, list[dict]] = {}  # "YYYY-MM-DD" -> grouped-daily results
        self.calls: list[str] = []
        self.status_override: int | None = None

    def set_quote(self, ticker: str, price: float, prev_close: float, updated: int) -> None:
        self.snapshot[ticker] = {
            "ticker": ticker,
            "updated": updated,
            "day": {"o": prev_close, "c": price},
            "prevDay": {"c": prev_close},
            "min": {"c": price, "t": updated // 1_000_000},
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.path)
        if self.status_override:
            return httpx.Response(self.status_override, json={"status": "ERROR"})
        path = request.url.path
        if path == "/v2/snapshot/locale/us/markets/stocks/tickers":
            if self.plan == "free":
                return httpx.Response(403, json={"status": "NOT_AUTHORIZED"})
            wanted = request.url.params["tickers"].split(",")
            items = [self.snapshot[t] for t in wanted if t in self.snapshot]
            return httpx.Response(200, json={"status": "OK", "count": len(items), "tickers": items})
        if path.startswith("/v2/aggs/grouped/locale/us/market/stocks/"):
            day = path.rsplit("/", 1)[1]
            results = self.grouped.get(day, [])
            return httpx.Response(200, json={"status": "OK", "resultsCount": len(results), "results": results})
        return httpx.Response(404)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(self.handler))
