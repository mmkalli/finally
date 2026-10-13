# Coding Conventions

**Analysis Date:** 2026-10-13

Scope: Python backend only (`backend/app/market/`). No frontend code, linter, or formatter config exists yet (no ruff/black/flake8/mypy in `backend/pyproject.toml`). Conventions below are inferred from existing code; follow them.

## Naming Patterns

**Files:**
- `snake_case.py`, one concern per module: `backend/app/market/cache.py`, `seed_data.py`, `massive.py`.
- Test files: `test_<topic>.py` in `backend/tests/market/`; non-test helpers there use plain names (`fake_massive.py`).

**Functions:**
- `snake_case`. Private helpers prefixed `_` (`_positive` in `backend/app/market/massive.py`). Pure helpers that tests call directly are public (`pick_price`, `latest_published_day`, `normalize_ticker`).

**Variables / constants:**
- `snake_case` locals; module constants `UPPER_SNAKE` (`BASE_URL`, `TICKER_RE`, `TRADING_SECONDS_PER_YEAR`, `EMPTY_PRICE_FIELDS`).
- Private instance attrs use a leading underscore (`self._cache`, `self._prices`) exposed via `@property`.

**Types / classes:**
- `PascalCase`. Exceptions end in `Error` (`MarketDataError`, `InvalidTickerError`, `UnknownTickerError`). ABCs are named by role (`MarketDataSource`); implementations `<Impl>DataSource` (`MassiveDataSource`, `SimulatorDataSource`). Type aliases via `Literal` (`Direction`, `Mode`).

## Code Style

**Formatting:**
- No tool configured. Observed: 4-space indent, double quotes, line length up to ~120 chars, trailing commas in multi-line literals, aligned inline comments, section dividers like `# ---- writes (data source only) ----`.
- Every module starts with `from __future__ import annotations`; use modern typing (`X | None`, `dict[str, float]`, `collections.abc.Iterable`).
- Use `@dataclass(frozen=True, slots=True)` for value objects (`PriceUpdate` in `backend/app/market/models.py`), `@dataclass(slots=True)` for mutable state.
- Keyword-only args (`*,`) for tuning/optional parameters (`PriceCache.update`, `GBMSimulator.__init__`).

**Linting:**
- None configured. Dependencies: `backend/pyproject.toml` (requires Python >=3.12).

## Import Organization

**Order (isort-style, observed):**
1. `from __future__ import annotations`
2. Standard library (`asyncio`, `logging`, `dataclasses`, ...)
3. Third party (`httpx`, `fastapi`)
4. Relative intra-package imports (`from .cache import PriceCache`)

**Path Aliases:** none. Inside `app/market/` use relative imports; tests use absolute (`from app.market import ...`, `from tests.market.fake_massive import FakeMassive`). Public API is re-exported in `backend/app/market/__init__.py` with an explicit `__all__`; import from `app.market` in other packages/tests.

## Error Handling

- Domain errors subclass `MarketDataError(ValueError)` in `backend/app/market/tickers.py`, carrying class attrs `code` (matches PLAN.md API error codes e.g. `INVALID_TICKER`) and `http_status`. Routes should translate them to `{"error": msg, "code": code}`.
- Validate input at the boundary with `normalize_ticker()` (trim, uppercase, `^[A-Z.]{1,6}$`); all source methods assume already-normalized tickers.
- Best-effort background work logs and continues rather than raising (`MarketDataSource.sync` catches `UnknownTickerError` and logs a warning).

## Logging

**Framework:** stdlib `logging`; module-level `log = logging.getLogger(__name__)`. Use `%s` lazy formatting (`log.warning("Not pricing unknown ticker %s", ticker)`), never f-strings in log calls.

## Comments

- Docstrings on public classes/methods explain contract and invariants (lifecycle, idempotence, what raises), short and prose-style, not Sphinx/Google param lists.
- Inline comments explain why (e.g. rounding only in cache, ET reset window behaviour). Reference spec sections like `(PLAN.md §6)`.
- Tests tag contract cases with comments (`# C1`, `# C2`) mapped to the design doc.
- Many files begin with a path comment `# backend/app/market/<file>.py`.

## Function Design

- Small functions; pure/sync logic separated from async I/O (`GBMSimulator` is pure and deterministic with an injected `random.Random`; `SimulatorDataSource` wraps it in a task).
- Inject dependencies for testability: `client=` (httpx.AsyncClient), `now=` (clock callable), `rng=`, `tick_seconds=`/`poll_interval=`.
- Methods intended to be safely repeatable are idempotent (`add_ticker`, `remove_ticker`, `stop`).
- Return `None` for "no data" (`get`, `get_price`, `pick_price`) rather than raising.

## Module Design

- Single in-memory source of truth: `PriceCache` (no locks; event-loop only, no awaits inside methods).
- Abstract interface `MarketDataSource` in `backend/app/market/interface.py`; new sources must implement `start/stop/add_ticker/remove_ticker/tickers` and call `cache.update`.
- Barrel file: `backend/app/market/__init__.py` (keep `__all__` sorted and updated).

## Known Repository Hazard

Unresolved git merge-conflict markers (`<<<<<<< HEAD` / `=======` / `>>>>>>>`) are present in `backend/pyproject.toml` and most files under `backend/app/market/` (see CONCERNS.md). Resolve before running anything; the intended content is the code between `=======` / `>>>>>>>` of each hunk where HEAD side is empty, and for `pyproject.toml`/`__init__.py` a union of both sides.

---

*Convention analysis: 2026-10-13*
