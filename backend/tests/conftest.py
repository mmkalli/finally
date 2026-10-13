import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "db" / "finally.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(path))
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)  # always the simulator, never the network
    return path


@pytest.fixture
def client(db_path):
    with TestClient(create_app(static_dir=None)) as c:
        yield c
