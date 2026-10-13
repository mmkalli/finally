"""API routers. main.py includes each module's `router` before the static mount.

Shared state on request.app.state, set up by the lifespan hook in app/main.py:
  db           sqlite3.Connection    single shared connection (see app.database.connect)
  price_cache  app.market.PriceCache latest price per ticker
  market       MarketDataSource      the active price source
  lock         asyncio.Lock          process-wide lock: hold it for trades, watchlist add/remove,
                                     chat actions and reset (PLAN.md §7, MARKET_DATA_DESIGN.md §10.2)

After anything that changes the watchlist or positions, call
`await app.market.sync_priced_tickers(state.db, state.market)` while still holding the lock.
"""
