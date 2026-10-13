import re

TICKER_RE = re.compile(r"^[A-Z.]{1,6}$")


class MarketDataError(ValueError):
    """Base for market-data errors that map to the API error shape {"error", "code"} (PLAN.md §8)."""

    code = "MARKET_ERROR"
    http_status = 400


class InvalidTickerError(MarketDataError):
    code = "INVALID_TICKER"


class UnknownTickerError(MarketDataError):
    """The data source knows this ticker doesn't exist. Raised by Massive only."""

    code = "UNKNOWN_TICKER"


def normalize_ticker(raw: object) -> str:
    """Trim + uppercase, then validate (PLAN.md §6 'Ticker Validation')."""
    ticker = raw.strip().upper() if isinstance(raw, str) else ""
    if not TICKER_RE.fullmatch(ticker):
        raise InvalidTickerError(f"Invalid ticker: {raw!r}")
    return ticker
