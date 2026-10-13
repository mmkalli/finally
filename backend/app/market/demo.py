<<<<<<< HEAD
"""Watch live prices in the terminal:  cd backend && uv run python -m app.market.demo [seconds]

Simulator by default; set MASSIVE_API_KEY to watch real prices instead. Ctrl+C to stop.
"""
import asyncio
import logging
import os
import sys
from collections import defaultdict, deque
=======
# backend/app/market/demo.py
"""Watch live prices in the terminal:  cd backend && uv run python -m app.market.demo"""
import asyncio
import logging
>>>>>>> 15bd778770aae61628b6b76861fd1f59cb38fd06

from . import PriceCache, create_market_data_source
from .seed_data import DEFAULT_TICKERS

<<<<<<< HEAD
SPARK = "▁▂▃▄▅▆▇█"
HISTORY = 40
GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def sparkline(values: deque[float]) -> str:
    lo, hi = min(values), max(values)
    if hi == lo:
        return SPARK[3] * len(values)
    return "".join(SPARK[round((v - lo) / (hi - lo) * (len(SPARK) - 1))] for v in values)


def render(cache: PriceCache, history: dict[str, deque[float]], tick: int, source_name: str) -> list[str]:
    lines = [f"{BOLD}FinAlly market demo{RESET}  source={source_name}  tick={tick}",
             f"{DIM}{'TICKER':<7}{'PRICE':>10}{'OPEN':>10}{'CHG %':>8}   SPARKLINE (last {HISTORY} ticks){RESET}"]
    for ticker, u in cache.snapshot().items():
        colour = GREEN if u.direction == "up" else RED if u.direction == "down" else ""
        arrow = "▲" if u.direction == "up" else "▼" if u.direction == "down" else " "
        chg_colour = GREEN if u.change_percent > 0 else RED if u.change_percent < 0 else ""
        lines.append(
            f"{ticker:<7}{colour}{u.price:>10.2f} {arrow}{RESET}{u.open_price:>8.2f}"
            f"{chg_colour}{u.change_percent + 0.0:>+8.2f}{RESET}   {sparkline(history[ticker])}"
        )
    return lines


async def main(seconds: float | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    if os.name == "nt":
        os.system("")  # enable ANSI escape codes in the Windows console
        sys.stdout.reconfigure(encoding="utf-8")  # sparkline and arrow glyphs
    cache = PriceCache()
    source = create_market_data_source(cache)  # simulator unless MASSIVE_API_KEY is set
    await source.start(DEFAULT_TICKERS)
    history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=HISTORY))
    live = sys.stdout.isatty()
    drawn = 0
    tick = 0
    try:
        while seconds is None or tick < seconds * 2:
            await asyncio.sleep(0.5)
            tick += 1
            for ticker, u in cache.snapshot().items():
                history[ticker].append(u.price)
            lines = render(cache, history, tick, source.name)
            if live and drawn:
                sys.stdout.write(f"\033[{drawn}F")  # move back up and redraw in place
            sys.stdout.write("\n".join(f"{line}\033[K" for line in lines) + "\n")
            sys.stdout.flush()
            drawn = len(lines)
=======

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
>>>>>>> 15bd778770aae61628b6b76861fd1f59cb38fd06
    finally:
        await source.stop()


if __name__ == "__main__":
<<<<<<< HEAD
    try:
        asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else None))
    except KeyboardInterrupt:
        pass
=======
    asyncio.run(main())
>>>>>>> 15bd778770aae61628b6b76861fd1f59cb38fd06
