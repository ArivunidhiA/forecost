import pytest


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "costs.db"
    monkeypatch.setattr("llmcast.db._DB_PATH", path)
    monkeypatch.setattr("llmcast.db._conn", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
