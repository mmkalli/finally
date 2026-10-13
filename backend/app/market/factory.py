import logging
import os

from .cache import PriceCache
from .interface import MarketDataSource
from .massive import MassiveDataSource
from .simulator import SimulatorDataSource

log = logging.getLogger(__name__)

MIN_POLL_INTERVAL = 2.0


def create_market_data_source(cache: PriceCache) -> MarketDataSource:
    """MASSIVE_API_KEY set and non-empty -> Massive; otherwise the simulator (PLAN.md §5)."""
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()
    if not api_key:
        log.info("Market data: built-in simulator")
        return SimulatorDataSource(cache)
    try:
        interval = float(os.getenv("MASSIVE_POLL_INTERVAL", "15"))
    except ValueError:
        interval = 15.0
    interval = max(interval, MIN_POLL_INTERVAL)
    log.info("Market data: Massive API (snapshot poll every %.0fs on paid plans)", interval)
    return MassiveDataSource(cache, api_key=api_key, poll_interval=interval)
