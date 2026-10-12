# Massive API (formerly Polygon.io) — Stock Price Reference

Reference for the parts of the Massive REST API that FinAlly needs: **current prices for many tickers at once** and **end-of-day (EOD) prices**. It is the source document for `MARKET_INTERFACE.md`.

Researched 2026-10-12 against `massive.com/docs`, `massive.com/pricing` and the source of the official Python client (`massive` on PyPI, v2.8.0). Things that could not be confirmed from official sources are marked **(unverified)**.

---

## 1. Overview

- Polygon.io rebranded as **Massive** in late 2025. The API and data are the same; paths are unchanged (`/v2/...`, `/v3/...`).
- **Base URL:** `https://api.massive.com`
- **Format:** JSON over HTTPS, `GET` only for market data.
- **Tickers are case-sensitive** in paths and query strings: always send uppercase (`AAPL`, `BRK.B`).
- **Official Python client:** `pip install massive` (Python ≥ 3.9), `from massive import RESTClient`. It is synchronous (urllib3).

### Authentication

Either works:

```
GET https://api.massive.com/v2/aggs/ticker/AAPL/prev?apiKey=YOUR_KEY
```
```
GET https://api.massive.com/v2/aggs/ticker/AAPL/prev
Authorization: Bearer YOUR_KEY
```

Prefer the header: query-string keys end up in access logs. The official client uses the header, and reads the key from the `MASSIVE_API_KEY` environment variable by default — the same variable FinAlly uses.

---

## 2. Plans — what you get matters more than which endpoint you call

Stocks plans (individual), from `massive.com/pricing`:

| Plan | Price | Rate limit | Recency | Snapshots | Last trade | Quotes |
|---|---|---|---|---|---|---|
| **Basic** (free) | $0 | **5 calls/min** | **End of day** | ❌ | ❌ | ❌ |
| Starter | $29/mo | Unlimited | 15-min delayed | ✅ | ❌ | ❌ |
| Developer | $79/mo | Unlimited | 15-min delayed | ✅ | ✅ | ❌ |
| Advanced | $199/mo | Unlimited | Real-time | ✅ | ✅ | ✅ |

Endpoint access per plan:

| Endpoint | Basic | Starter | Developer | Advanced |
|---|---|---|---|---|
| Full market snapshot `/v2/snapshot/.../tickers` | ❌ | ✅ delayed | ✅ delayed | ✅ real-time |
| Single ticker snapshot `/v2/snapshot/.../tickers/{T}` | ❌ | ✅ | ✅ | ✅ |
| Unified snapshot `/v3/snapshot` | ❌ | ✅ | ✅ | ✅ |
| Last trade `/v2/last/trade/{T}` | ❌ | ❌ | ✅ | ✅ |
| Previous day bar `/v2/aggs/ticker/{T}/prev` | ✅ EOD | ✅ | ✅ | ✅ |
| Grouped daily (whole market) `/v2/aggs/grouped/...` | ✅ EOD | ✅ | ✅ | ✅ |
| Custom bars `/v2/aggs/ticker/{T}/range/...` | ✅ EOD | ✅ | ✅ | ✅ |

**Consequences for FinAlly**

1. The **free tier cannot get intraday prices at all**. A free key gives the last closing prices, which change once per trading day. Polling it every 15 s just re-reads the same numbers. (`PLAN.md` §6 assumes free-tier polling every 15 s; see `MARKET_INTERFACE.md` §6 for how we handle this.)
2. **Starter and above** get the snapshot endpoint. One call returns every ticker we care about, and there's no per-minute limit, so polling every 2–15 s is fine. Data is 15 minutes delayed below Advanced.
3. The snapshot response has `lastTrade` only on Developer+ and `lastQuote` only on Advanced. Code must not assume either is there.

---

## 3. Endpoints for current prices (paid plans)

### 3.1 Full market snapshot — multiple tickers in one call ⭐ primary

```
GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT,NVDA
```

| Query param | Type | Notes |
|---|---|---|
| `tickers` | string | Comma-separated, case-sensitive. **Omit to get the entire market** (10,000+ tickers, a large payload). |
| `include_otc` | bool | Default `false`. |

Response (one ticker shown):

```json
{
  "status": "OK",
  "count": 1,
  "tickers": [
    {
      "ticker": "AAPL",
      "todaysChange": 1.62,
      "todaysChangePerc": 0.85,
      "updated": 1760278401512000000,
      "day":     {"o": 189.9, "h": 191.2, "l": 189.1, "c": 190.12, "v": 41234567, "vw": 190.4},
      "prevDay": {"o": 188.0, "h": 189.9, "l": 187.6, "c": 188.50, "v": 52345678, "vw": 188.9},
      "min":     {"o": 190.0, "h": 190.2, "l": 190.0, "c": 190.12, "v": 120345, "vw": 190.1,
                  "av": 41234567, "n": 812, "t": 1760278380000},
      "lastTrade": {"p": 190.12, "s": 100, "t": 1760278401512000000, "x": 4, "i": "71675577320245", "c": [14, 41]},
      "lastQuote": {"p": 190.11, "s": 3, "P": 190.13, "S": 2, "t": 1760278401498000000}
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `ticker` | Symbol |
| `updated` | Last update time, **nanoseconds** since epoch |
| `todaysChange` / `todaysChangePerc` | Change vs previous close ($ / %) |
| `day` | Today's bar so far: `o h l c v vw` |
| `prevDay` | Previous trading day's bar. **`prevDay.c` = previous close** |
| `min` | Latest minute bar (`t` in **milliseconds**, `av` = accumulated day volume, `n` = trades) |
| `lastTrade` | Developer+ only. `p` price, `s` size, `t` SIP time (**ns**), `x` exchange id |
| `lastQuote` | Advanced only. `p`/`s` bid price/size, `P`/`S` ask price/size, `t` (**ns**) |
| `fmv` | Fair market value, Business plans only |

**Gotchas**

- Snapshot data is **cleared at ~3:30 AM ET** and fills in again from ~4:00 AM ET. In that window `day` values (and sometimes `min`) are `0`. Never treat `0` as a price.
- Use the most specific price available: `lastTrade.p` → `min.c` → `day.c` → `prevDay.c`, skipping missing or zero values.
- Unknown tickers are **left out** of `tickers[]`. They don't cause an error. Compare what you asked for with what came back.
- Some volume fields (`dv`, `dav`, `ds`) are **strings**, e.g. `"37216.0"`.
- Timestamps mix units: `updated`, `lastTrade.t`, `lastQuote.t` are ns; `min.t` is ms.

Python client:

```python
from massive import RESTClient

client = RESTClient()  # reads MASSIVE_API_KEY from the environment

snapshots = client.get_snapshot_all("stocks", tickers=["AAPL", "MSFT", "NVDA"])
for s in snapshots:  # list[TickerSnapshot]
    price = (
        (s.last_trade.price if s.last_trade else None)
        or (s.min.close if s.min else None)
        or (s.day.close if s.day else None)
        or (s.prev_day.close if s.prev_day else None)
    )
    prev_close = s.prev_day.close if s.prev_day else None
    print(s.ticker, price, prev_close, s.todays_change_percent, s.updated)
```

`TickerSnapshot` attributes: `ticker, day, prev_day, min, last_trade, last_quote, todays_change, todays_change_percent, updated, fair_market_value`. `day`/`prev_day` are `Agg(open, high, low, close, volume, vwap, timestamp, …)`, and `last_trade` is `LastTrade(price, size, sip_timestamp, exchange, …)`.

Raw async (httpx), which is what FinAlly uses (see §6):

```python
import httpx

async def fetch_snapshot(client: httpx.AsyncClient, tickers: list[str]) -> list[dict]:
    resp = await client.get(
        "/v2/snapshot/locale/us/markets/stocks/tickers",
        params={"tickers": ",".join(tickers)},
    )
    resp.raise_for_status()
    return resp.json().get("tickers", [])

client = httpx.AsyncClient(
    base_url="https://api.massive.com",
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=10.0,
)
```

### 3.2 Single ticker snapshot

```
GET /v2/snapshot/locale/us/markets/stocks/tickers/{TICKER}
```

Same object as one element of §3.1, under the key `ticker` (singular) instead of `tickers`. Use it only for one-off lookups. For more than one ticker, §3.1 does it in one call.

```python
snap = client.get_snapshot_ticker("stocks", "AAPL")
```

### 3.3 Unified snapshot (v3) — alternative

```
GET /v3/snapshot?ticker.any_of=AAPL,MSFT&limit=250
```

- Up to 250 tickers per page (`limit` max 250, default **10** — always set it). Paginated via `next_url`.
- Normalized, readable field names: `session.close`, `session.previous_close`, `session.change_percent`, `last_trade.price`, `last_minute.close`, `market_status` (`open`/`closed`/`early_trading`/`late_trading`).
- Unknown tickers come back as entries with `"error": "NOT_FOUND"` instead of being dropped, which is handy for validation.
- Same plan gating as §3.1 (not available on Basic).

```python
for s in client.list_universal_snapshots(ticker_any_of=["AAPL", "MSFT"], limit=250):
    print(s.ticker, s.session.close if s.session else None)
```

FinAlly uses §3.1 because the v2 format is what the rest of the ecosystem documents. v3 is a drop-in alternative if `market_status` becomes useful.

### 3.4 Last trade (Developer+)

```
GET /v2/last/trade/{TICKER}
```
```json
{"status": "OK", "request_id": "…",
 "results": {"T": "AAPL", "p": 190.12, "s": 100, "t": 1760278401512000000, "x": 4, "q": 1234567, "z": 3}}
```
```python
trade = client.get_last_trade("AAPL")
print(trade.price, trade.sip_timestamp)
```
This takes one call per ticker. The snapshot already contains `lastTrade` on plans that allow this endpoint, so FinAlly doesn't use it.

---

## 4. Endpoints for end-of-day prices (all plans, including free)

### 4.1 Grouped daily — every US stock for one date in one call ⭐ free-tier primary

```
GET /v2/aggs/grouped/locale/us/market/stocks/{YYYY-MM-DD}?adjusted=true
```
```json
{
  "status": "OK", "adjusted": true, "queryCount": 11042, "resultsCount": 11042,
  "results": [
    {"T": "AAPL", "o": 189.9, "h": 191.2, "l": 189.1, "c": 190.12, "v": 41234567, "vw": 190.4, "n": 512345, "t": 1760126400000}
  ]
}
```

| Field | Meaning |
|---|---|
| `T` | Ticker |
| `o h l c` | Open, high, low, close |
| `v`, `vw`, `n` | Volume, VWAP, number of trades |
| `t` | Unix **ms**, end of the window |

- A weekend, holiday or not-yet-published date returns `resultsCount: 0` and no `results`. It isn't an error. Step back one day and retry.
- One call covers the whole market, so a free key can price any number of tickers using only **2 calls per trading day** (latest close plus the close before it). It can also validate new tickers without extra calls.

```python
from datetime import date, timedelta

def latest_two_closes(client, today: date) -> tuple[dict[str, float], dict[str, float]]:
    """Return ({ticker: last_close}, {ticker: prior_close}) for the two most recent trading days."""
    days: list[dict[str, float]] = []
    d = today
    while len(days) < 2:
        bars = client.get_grouped_daily_aggs(d.isoformat(), adjusted=True)
        if bars:
            days.append({b.ticker: b.close for b in bars})
        d -= timedelta(days=1)
    return days[0], days[1]
```

Each empty day (weekend/holiday) costs one call. With 5 calls/min, walking back across a long weekend uses most of a minute's budget, so cache the result and only refresh it after the next close.

### 4.2 Previous day bar — one ticker

```
GET /v2/aggs/ticker/{TICKER}/prev?adjusted=true
```
```json
{"ticker": "AAPL", "status": "OK", "adjusted": true, "queryCount": 1, "resultsCount": 1,
 "results": [{"T": "AAPL", "o": 115.55, "h": 117.59, "l": 114.13, "c": 115.97, "v": 131704427, "vw": 116.3058, "t": 1605042000000}]}
```
```python
prev = client.get_previous_close_agg("AAPL")   # list[PreviousCloseAgg]
print(prev[0].close if prev else None)
```
An unknown ticker returns `resultsCount: 0` / no `results`, which makes this a cheap existence check. It only gives one day, so you can't get "change since prior close" from it alone.

### 4.3 Custom bars — history for one ticker

```
GET /v2/aggs/ticker/{TICKER}/range/{multiplier}/{timespan}/{from}/{to}?adjusted=true&sort=asc&limit=50000
```
`timespan` ∈ `minute, hour, day, week, month, quarter, year`; `from`/`to` are `YYYY-MM-DD` or ms timestamps.

```python
from datetime import date, timedelta

# Last ~10 calendar days of daily bars → the last two closes, in one call per ticker
bars = list(client.list_aggs("AAPL", 1, "day",
                             (date.today() - timedelta(days=10)).isoformat(),
                             date.today().isoformat(),
                             adjusted=True, sort="asc", limit=50))
last_close, prior_close = bars[-1].close, bars[-2].close
```
`list_aggs` follows `next_url` pagination automatically; `get_aggs` returns one page. FinAlly has no price-history endpoint (`PLAN.md` §10), so this is only documented for completeness.

### 4.4 Daily open/close — one ticker, one date

```
GET /v1/open-close/{TICKER}/{YYYY-MM-DD}?adjusted=true
```
Returns `open, high, low, close, volume, preMarket, afterHours`. `client.get_daily_open_close_agg("AAPL", "2026-10-09")`.

---

## 5. Errors and rate limits

| Situation | HTTP | Body (typical) |
|---|---|---|
| Missing / bad key | 401 | `{"status": "ERROR", "error": "Unknown API Key", …}` **(unverified wording)** |
| Endpoint not in your plan (e.g. snapshot on Basic) | 403 | `{"status": "NOT_AUTHORIZED", "message": "You are not entitled to this data. Please upgrade your plan…"}` **(unverified wording)** |
| Rate limit exceeded (Basic: >5/min) | 429 | `{"status": "ERROR", "error": "You've exceeded the maximum requests per minute…"}` **(unverified wording)** |
| No data (holiday, unknown ticker on aggs) | 200 | `resultsCount: 0`, no `results` |

Branch on the **HTTP status code**, not on the message text.

**Official client behaviour** (from source):
- `RESTClient()` raises `massive.exceptions.AuthError` if no key is available.
- Any non-200 raises `massive.exceptions.BadResponse(body_text)`. The status code isn't kept separately, so you'd have to parse the text.
- It retries `413, 429, 499, 500, 502, 503, 504` up to `retries=3` times, with backoff starting at 0.1 s. On the free tier that turns one call into up to four and drains the 5/min budget. When retries run out, the error can come out of urllib3 (`MaxRetryError`) rather than `BadResponse`.
- Timeouts default to 10 s connect / 10 s read.

---

## 6. Recommendations for FinAlly

1. **Use `httpx.AsyncClient` directly, not the official client.** We only need two endpoints (§3.1, §4.1). Going direct gives us native async with no `to_thread`, the real HTTP status for 403/429 handling, and no hidden retries spending the free-tier budget. (`httpx` is already a FastAPI/LiteLLM dependency.) The official client is still handy for exploring in a REPL.
2. **Find out the plan at startup** with one snapshot call. A 200 means snapshot mode (poll every `MASSIVE_POLL_INTERVAL`, default 15 s). A 403 means EOD mode (grouped daily, refreshed every few minutes and cached per trading date).
3. **Price selection:** `lastTrade.p` → `min.c` → `day.c` → `prevDay.c`, skipping missing/zero values. `open_price` = `prevDay.c` (`PLAN.md` §6).
4. **Change detection:** only write to the price cache when a ticker's `updated` (snapshot) or trading date (EOD) has changed. That way most SSE ticks are empty, as `PLAN.md` §6 expects.
5. **Ticker validation:** snapshot mode — request the ticker, and if it isn't in `tickers[]`, return `UNKNOWN_TICKER`. EOD mode — look it up in the cached grouped-daily result (no extra call).
6. Always uppercase tickers before sending them.

---

## Sources

- [Full Market Snapshot](https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot)
- [Unified Snapshot](https://massive.com/docs/rest/stocks/snapshots/unified-snapshot)
- [Daily Market Summary (grouped daily)](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary)
- [Previous Day Bar](https://massive.com/docs/rest/stocks/aggregates/previous-day-bar)
- [Last Trade](https://massive.com/docs/rest/stocks/trades-quotes/last-trade)
- [REST Quickstart (auth)](https://massive.com/docs/rest/quickstart)
- [Pricing](https://massive.com/pricing)
- [massive-com/client-python](https://github.com/massive-com/client-python) — `massive/rest/{snapshot,aggs,trades,base}.py`, `massive/exceptions.py`
