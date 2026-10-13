# backend/tests/test_baseline.py
import importlib
import re
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _load() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_market_package_imports():
    mod = importlib.import_module("app.market")
    for name in (
        "stream_router",
        "load_priced_tickers",
        "sync_priced_tickers",
        "PriceCache",
        "create_market_data_source",
    ):
        assert hasattr(mod, name), name


def test_runtime_dependencies_declared():
    deps = _load()["project"]["dependencies"]
    names = {re.split(r"[<>=!~; \[]", d.strip(), maxsplit=1)[0].lower() for d in deps}
    assert {"litellm", "pydantic", "python-dotenv", "tzdata"} <= names


def test_project_is_virtual():
    data = _load()
    assert data["tool"]["uv"]["package"] is False
    assert "build-system" not in data
