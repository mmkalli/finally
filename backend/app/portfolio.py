"""Portfolio valuation and trade execution (PLAN.md §7 Trade Execution Rules, §8 Portfolio).

Manual trades (POST /api/portfolio/trade) and chat trades both go through `execute_trade`.
"""
import math
import sqlite3
import uuid

from app.database import DEFAULT_USER, reset_to_seed, utc_now
from app.errors import AppError
from app.market import MarketDataError, MarketDataSource, PriceCache, normalize_ticker, sync_priced_tickers
from app.snapshots import record_snapshot

QUANTITY_DP = 4
MONEY_DP = 2
MIN_POSITION = 1e-6  # a sell leaving less than this deletes the position row
SIDES = ("buy", "sell")


# ----------------------------------------------------------------------------- reads

def get_portfolio(conn: sqlite3.Connection, cache: PriceCache, user_id: str = DEFAULT_USER) -> dict:
    """GET /api/portfolio shape. An unpriced position is valued at its avg_cost (PLAN.md §8)."""
    row = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    cash = row[0] if row else 0.0
    rows = conn.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker", (user_id,)
    ).fetchall()

    positions = []
    positions_value = unrealized_pnl = 0.0
    for ticker, quantity, avg_cost in rows:
        cached = cache.get_price(ticker)
        price = cached if cached is not None else avg_cost
        market_value = quantity * price
        pnl = (price - avg_cost) * quantity
        positions_value += market_value
        unrealized_pnl += pnl
        positions.append({
            "ticker": ticker,
            "quantity": round(quantity, QUANTITY_DP),
            "avg_cost": round(avg_cost, MONEY_DP),
            "current_price": round(price, MONEY_DP),
            "market_value": round(market_value, MONEY_DP),
            "unrealized_pnl": round(pnl, MONEY_DP),
            "pnl_percent": round((price - avg_cost) / avg_cost * 100, 2) if avg_cost else 0.0,
        })

    cash, positions_value = round(cash, MONEY_DP), round(positions_value, MONEY_DP)
    return {
        "cash_balance": cash,
        "positions_value": positions_value,
        "total_value": round(cash + positions_value, MONEY_DP),  # adds up exactly as displayed
        "unrealized_pnl": round(unrealized_pnl, MONEY_DP),
        "positions": positions,
    }


def get_history(conn: sqlite3.Connection, user_id: str = DEFAULT_USER) -> list[dict]:
    """Portfolio value snapshots, oldest first (GET /api/portfolio/history)."""
    rows = conn.execute(
        "SELECT total_value, recorded_at FROM portfolio_snapshots WHERE user_id = ? ORDER BY recorded_at, rowid",
        (user_id,),
    ).fetchall()
    return [{"total_value": round(v, MONEY_DP), "recorded_at": t} for v, t in rows]


# ----------------------------------------------------------------------------- trades

async def execute_trade(
    conn: sqlite3.Connection,
    cache: PriceCache,
    market: MarketDataSource,
    ticker: object,
    side: object,
    quantity: object,
    user_id: str = DEFAULT_USER,
) -> dict:
    """Validate and execute one market order; return the trade record ({id, ticker, side, quantity, price, executed_at}).

    The caller holds app.state.lock. Raises AppError with a PLAN.md §8 code on any rejection, after which
    nothing has been written. The priced-ticker set is re-synced whatever happens (MARKET_DATA_DESIGN.md §10.3).
    """
    try:
        ticker = normalize_ticker(ticker)
    except MarketDataError as e:
        raise AppError(e.code, str(e)) from e
    side = _validate_side(side)
    quantity = _validate_quantity(quantity)

    try:
        try:
            await market.add_ticker(ticker)  # an unwatched, unheld ticker gets a price so it can fill
        except MarketDataError as e:
            raise AppError(e.code, str(e)) from e
        price = cache.get_price(ticker)
        if price is None:
            raise AppError("NO_PRICE", f"No price yet for {ticker}")
        return apply_trade(conn, cache, ticker, side, quantity, price, user_id)
    finally:
        await sync_priced_tickers(conn, market, user_id)  # drops the ticker again unless watched or held


def apply_trade(
    conn: sqlite3.Connection,
    cache: PriceCache,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    user_id: str = DEFAULT_USER,
) -> dict:
    """Fill a validated order at `price`: cash, position, trade log and a snapshot in one transaction.

    `ticker` is normalized, `side` is "buy"/"sell" and `quantity` is already rounded and positive.
    Raises AppError (INSUFFICIENT_CASH / INSUFFICIENT_SHARES) before writing anything.
    """
    now = utc_now()
    with conn:
        cash = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)).fetchone()[0]
        held = conn.execute(
            "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker)
        ).fetchone()
        held_qty, avg_cost = (held[0], held[1]) if held else (0.0, 0.0)
        amount = round(quantity * price, MONEY_DP)

        if side == "buy":
            if amount > cash:
                raise AppError("INSUFFICIENT_CASH", f"Insufficient cash: need ${amount:,.2f}, have ${cash:,.2f}")
            new_qty = round(held_qty + quantity, QUANTITY_DP)
            new_avg = (held_qty * avg_cost + quantity * price) / new_qty
            new_cash = round(cash - amount, MONEY_DP) + 0.0  # + 0.0 turns a -0.0 into 0.0
            conn.execute(
                "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (user_id, ticker) DO UPDATE SET "
                "quantity = excluded.quantity, avg_cost = excluded.avg_cost, updated_at = excluded.updated_at",
                (str(uuid.uuid4()), user_id, ticker, new_qty, new_avg, now),
            )
        else:
            if quantity > round(held_qty, QUANTITY_DP):
                raise AppError("INSUFFICIENT_SHARES", f"Insufficient shares: you hold {_fmt_qty(held_qty)} {ticker}")
            new_qty = round(held_qty - quantity, QUANTITY_DP)
            new_cash = round(cash + amount, MONEY_DP)
            if new_qty < MIN_POSITION:
                conn.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker))
            else:  # avg_cost is unchanged by a sell
                conn.execute(
                    "UPDATE positions SET quantity = ?, updated_at = ? WHERE user_id = ? AND ticker = ?",
                    (new_qty, now, user_id, ticker),
                )

        conn.execute("UPDATE users_profile SET cash_balance = ? WHERE id = ?", (new_cash, user_id))
        trade = {
            "id": str(uuid.uuid4()), "ticker": ticker, "side": side,
            "quantity": quantity, "price": price, "executed_at": now,
        }
        conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (trade["id"], user_id, ticker, side, quantity, price, now),
        )
        record_snapshot(conn, cache, user_id)
    return trade


async def reset_portfolio(
    conn: sqlite3.Connection, cache: PriceCache, market: MarketDataSource, user_id: str = DEFAULT_USER
) -> None:
    """POST /api/reset: back to the seed state, priced set back to the defaults. The caller holds app.state.lock.

    Records one fresh snapshot so the P&L chart starts from $10,000, as it does on a fresh start.
    """
    reset_to_seed(conn, user_id)
    await sync_priced_tickers(conn, market, user_id)
    with conn:
        record_snapshot(conn, cache, user_id)


def _validate_side(side: object) -> str:
    normalized = side.strip().lower() if isinstance(side, str) else ""
    if normalized not in SIDES:
        raise AppError("INVALID_REQUEST", f"Invalid side: {side!r} (expected 'buy' or 'sell')")
    return normalized


def _validate_quantity(quantity: object) -> float:
    """Must be > 0; rounded to 4 dp, and anything that rounds to 0 is rejected (PLAN.md §7)."""
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or not math.isfinite(quantity):
        raise AppError("INVALID_QUANTITY", f"Invalid quantity: {quantity!r}")
    rounded = round(float(quantity), QUANTITY_DP)
    if rounded <= 0:
        raise AppError("INVALID_QUANTITY", f"Quantity must be greater than 0 (got {quantity!r})")
    return rounded


def _fmt_qty(quantity: float) -> str:
    return f"{quantity:,.{QUANTITY_DP}f}".rstrip("0").rstrip(".")
