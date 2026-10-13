import asyncio

import pytest

from app.database import connect, init_db, utc_now
from app.market import PriceCache
from app.snapshots import compute_total_value, record_snapshot, run_snapshot_loop


@pytest.fixture
def conn(db_path):
    conn = connect()
    init_db(conn)
    with conn:
        conn.execute("UPDATE users_profile SET cash_balance = 1000.0")
        conn.executemany(
            "INSERT INTO positions (id, ticker, quantity, avg_cost, updated_at) VALUES (?, ?, ?, ?, ?)",
            [("1", "AAPL", 10, 150.0, utc_now()), ("2", "PYPL", 2.5, 60.0, utc_now())],
        )
    yield conn
    conn.close()


def snapshots(conn):
    return [r[0] for r in conn.execute("SELECT total_value FROM portfolio_snapshots ORDER BY recorded_at")]


def test_total_value_uses_cached_price_else_avg_cost(conn):
    cache = PriceCache()
    cache.update("AAPL", 200.0)  # PYPL unpriced -> avg_cost
    assert compute_total_value(conn, cache) == 1000.0 + 10 * 200.0 + 2.5 * 60.0


def test_record_snapshot_inserts(conn):
    cache = PriceCache()
    with conn:
        total = record_snapshot(conn, cache)
    assert snapshots(conn) == [total] == [1000.0 + 1500.0 + 150.0]


async def test_loop_records_immediately_then_every_interval(conn):
    task = asyncio.create_task(run_snapshot_loop(conn, PriceCache(), asyncio.Lock(), interval=0.01))
    for _ in range(200):
        await asyncio.sleep(0.01)
        if len(snapshots(conn)) >= 3:
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(snapshots(conn)) >= 3


async def test_loop_waits_for_the_lock(conn):
    lock = asyncio.Lock()
    await lock.acquire()
    task = asyncio.create_task(run_snapshot_loop(conn, PriceCache(), lock, interval=0.01))
    await asyncio.sleep(0.05)
    assert snapshots(conn) == []
    lock.release()
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert snapshots(conn)
