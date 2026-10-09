import os
import sqlite3
import stat

import pytest

from forecost.core.local_identity import (
    INSTALLATION_KEY_ID_NAME,
    INSTALLATION_KEY_NAME,
    LocalIdentityKeyError,
    installation_key,
    keyed_fingerprint,
)


def test_installation_fingerprint_is_stable_locally_and_scoped_between_homes(tmp_path, monkeypatch):
    first_home = tmp_path / "first"
    monkeypatch.setenv("FORECOST_HOME", str(first_home))
    first = keyed_fingerprint("cursor", "/workspace/session.jsonl")
    assert keyed_fingerprint("cursor", "/workspace/session.jsonl") == first

    second_home = tmp_path / "second"
    monkeypatch.setenv("FORECOST_HOME", str(second_home))
    second = keyed_fingerprint("cursor", "/workspace/session.jsonl")

    assert first != second
    assert "/workspace" not in first
    assert len(first) == 64


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_installation_key_is_owner_only(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("FORECOST_HOME", str(home))

    assert len(installation_key()) == 32

    key_path = home / INSTALLATION_KEY_NAME
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600


def test_malformed_key_is_not_silently_rotated(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("FORECOST_HOME", str(home))
    home.mkdir()
    key_path = home / INSTALLATION_KEY_NAME
    key_path.write_bytes(b"short")

    with pytest.raises(LocalIdentityKeyError, match="invalid length"):
        installation_key()

    assert key_path.read_bytes() == b"short"


def test_missing_key_with_existing_keyed_cursor_fails_instead_of_reingesting(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("FORECOST_HOME", str(home))
    original = installation_key()
    ledger = home / "ledger.db"
    conn = sqlite3.connect(ledger)
    conn.execute(
        "CREATE TABLE ingest_state(source TEXT, cursor_key TEXT, cursor_val TEXT, "
        "updated_at TEXT, PRIMARY KEY(source,cursor_key))"
    )
    conn.execute(
        "INSERT INTO ingest_state VALUES(?,?,?,?)",
        ("claude_code", "cursor-hmac:v1:" + "0" * 64, '{"offset":1}', "now"),
    )
    conn.commit()
    conn.close()
    (home / INSTALLATION_KEY_NAME).unlink()

    with pytest.raises(LocalIdentityKeyError, match="missing while keyed state exists"):
        installation_key()

    assert not (home / INSTALLATION_KEY_NAME).exists()
    assert (home / INSTALLATION_KEY_ID_NAME).exists()
    assert len(original) == 32


def test_replaced_key_is_detected_by_registered_id(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("FORECOST_HOME", str(home))
    installation_key()
    key_path = home / INSTALLATION_KEY_NAME
    key_path.write_bytes(os.urandom(32))

    with pytest.raises(LocalIdentityKeyError, match="does not match"):
        installation_key()


def test_missing_key_id_with_existing_keyed_cursor_fails_closed(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("FORECOST_HOME", str(home))
    installation_key()
    ledger = home / "ledger.db"
    conn = sqlite3.connect(ledger)
    conn.execute(
        "CREATE TABLE ingest_state(source TEXT, cursor_key TEXT, cursor_val TEXT, "
        "updated_at TEXT, PRIMARY KEY(source,cursor_key))"
    )
    conn.execute(
        "INSERT INTO ingest_state VALUES(?,?,?,?)",
        ("claude_code", "cursor-hmac:v1:" + "0" * 64, '{"offset":1}', "now"),
    )
    conn.commit()
    conn.close()
    (home / INSTALLATION_KEY_ID_NAME).unlink()

    with pytest.raises(LocalIdentityKeyError, match="key id is missing"):
        installation_key()

    assert not (home / INSTALLATION_KEY_ID_NAME).exists()
