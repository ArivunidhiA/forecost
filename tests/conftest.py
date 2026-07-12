import pytest


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "costs.db"
    monkeypatch.setattr("forecost.db._DB_PATH", path)
    monkeypatch.setattr("forecost.db._conn", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def ledger_conn(tmp_path, monkeypatch):
    """An isolated ledger.db connection for a single test."""
    import forecost.ledger.db as ledger_db

    path = tmp_path / "ledger.db"
    monkeypatch.setattr(ledger_db, "LEDGER_PATH", path)
    monkeypatch.setattr(ledger_db, "_conn", None)
    conn = ledger_db.get_ledger_db()
    yield conn
    ledger_db.reset_connection_for_tests()
