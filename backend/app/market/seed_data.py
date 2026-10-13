<<<<<<< HEAD
=======
# backend/app/market/seed_data.py
>>>>>>> 15bd778770aae61628b6b76861fd1f59cb38fd06
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TickerProfile:
    seed_price: float
    drift: float        # annualized mu
    volatility: float   # annualized sigma
    sector: str | None  # tickers in the same sector share a sector shock


MARKET_LOADING = 0.5
SECTOR_LOADINGS: dict[str, float] = {"tech": 0.6, "finance": 0.5, "consumer": 0.4}
# Keep MARKET_LOADING**2 + loading**2 <= 1 for every sector.

PROFILES: dict[str, TickerProfile] = {
    "AAPL":  TickerProfile(190.00, 0.08, 0.25, "tech"),
    "GOOGL": TickerProfile(175.00, 0.08, 0.28, "tech"),
    "MSFT":  TickerProfile(420.00, 0.08, 0.24, "tech"),
    "AMZN":  TickerProfile(185.00, 0.09, 0.30, "consumer"),
    "TSLA":  TickerProfile(250.00, 0.05, 0.55, None),
    "NVDA":  TickerProfile(130.00, 0.12, 0.45, "tech"),
    "META":  TickerProfile(500.00, 0.09, 0.35, "tech"),
    "JPM":   TickerProfile(200.00, 0.06, 0.20, "finance"),
    "V":     TickerProfile(280.00, 0.07, 0.18, "finance"),
    "NFLX":  TickerProfile(650.00, 0.08, 0.38, "consumer"),
    # Extras so common watchlist additions start at believable levels
    "AMD":   TickerProfile(160.00, 0.10, 0.45, "tech"),
    "INTC":  TickerProfile(35.00, 0.03, 0.35, "tech"),
    "BAC":   TickerProfile(40.00, 0.06, 0.25, "finance"),
    "GS":    TickerProfile(450.00, 0.06, 0.25, "finance"),
    "DIS":   TickerProfile(100.00, 0.06, 0.28, "consumer"),
}

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
DEFAULT_DRIFT = 0.05
DEFAULT_VOLATILITY = 0.30
UNKNOWN_PRICE_RANGE = (50.0, 300.0)


def profile_for(ticker: str, rng: random.Random) -> TickerProfile:
    """Known ticker -> its profile. Unknown valid ticker -> random $50-$300 seed, default mu/sigma, no sector."""
    known = PROFILES.get(ticker)
    if known:
        return known
    return TickerProfile(
        seed_price=round(rng.uniform(*UNKNOWN_PRICE_RANGE), 2),
        drift=DEFAULT_DRIFT,
        volatility=DEFAULT_VOLATILITY,
        sector=None,
    )
