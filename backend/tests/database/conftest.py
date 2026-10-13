import pytest

from app import database as db


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "sub" / "finally.db"


@pytest.fixture
def conn(db_path):
    db.init_db(db_path)
    yield db.get_connection()
    db.close_db()
