import pytest


@pytest.fixture(autouse=True)
def _block_external_network(monkeypatch):
    """Unit and fixture tests may use loopback, never the public network."""
    import socket

    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def guarded_connect(sock, address):
        if sock.family == getattr(socket, "AF_UNIX", None):
            return original_connect(sock, address)
        host = address[0] if isinstance(address, tuple) and address else None
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise RuntimeError(f"external network disabled in tests: {host}")
        return original_connect(sock, address)

    def guarded_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) and address else None
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise RuntimeError(f"external network disabled in tests: {host}")
        return original_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)


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
