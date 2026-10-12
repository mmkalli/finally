# backend/app/market/demo.py
"""Watch live prices in the terminal:  cd backend && uv run python -m app.market.demo"""
import asyncio
import logging

from . import PriceCache, create_market_data_source
from .seed_data import DEFAULT_TICKERS


async def main(seconds: float = 10.0) -> None:
    logging.basicConfig(level=logging.INFO)
    cache = PriceCache()
    source = create_market_data_source(cache)  # simulator unless MASSIVE_API_KEY is set
    await source.start(DEFAULT_TICKERS)
    try:
        for _ in range(int(seconds * 2)):
            await asyncio.sleep(0.5)
            print("  ".join(
                f"{u.ticker:<5}{u.price:>8.2f} {u.change_percent:+5.2f}%{'▲' if u.direction == 'up' else '▼' if u.direction == 'down' else ' '}"
                for u in list(cache.snapshot().values())[:5]
            ))
    finally:
        await source.stop()


if __name__ == "__main__":
    asyncio.run(main())
