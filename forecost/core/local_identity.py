"""Installation-scoped keyed identities for content-minimizing local state.

The key is deliberately local and owner-readable. It makes transcript cursor
keys and diagnostic fingerprints harder to dictionary-recover after export;
other legacy/canonical SHA-256 pseudonyms retain their separately documented
linkability. This is not a boundary against code running as the same OS user.
Accidental loss, corruption, or mismatch of one key/ID file is not rotated
silently when dependent keyed cursors are visible in the canonical home,
because that would orphan cursors and can cause duplicate ingestion. Coordinated
same-UID replacement of both matching files is outside this local boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import stat
import tempfile
import time
from contextlib import suppress
from pathlib import Path

from forecost.core.paths import (
    UnsafeDataPathError,
    chmod_private,
    ensure_private_dir,
    forecost_home,
    validate_private_file,
)

INSTALLATION_KEY_NAME = "installation-hmac.key"
INSTALLATION_KEY_ID_NAME = "installation-hmac.key.id"
_KEY_BYTES = 32
_KEY_ID_BYTES = 64
_CREATE_RETRIES = 10


class LocalIdentityKeyError(RuntimeError):
    """The installation identity key is missing, unsafe, or malformed."""


def _read_exact_key(path: Path) -> bytes:
    validate_private_file(path, may_not_exist=False)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LocalIdentityKeyError("installation identity key is not a regular file")
        value = os.read(descriptor, _KEY_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(value) != _KEY_BYTES:
        raise LocalIdentityKeyError("installation identity key has an invalid length")
    chmod_private(path)
    return value


def _publish_exact(path: Path, value: bytes) -> None:
    """Publish complete bytes atomically without replacing an existing file."""
    descriptor, temporary_raw = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_raw)
    try:
        written = 0
        while written < len(value):
            count = os.write(descriptor, value[written:])
            if count <= 0:  # pragma: no cover - OS write contract
                raise OSError("installation identity file write made no progress")
            written += count
        os.fsync(descriptor)
        with suppress(OSError, AttributeError):
            os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    try:
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)
    with suppress(OSError):
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def _create_key(path: Path) -> bytes:
    value = os.urandom(_KEY_BYTES)
    _publish_exact(path, value)
    return value


def _key_id(value: bytes) -> bytes:
    return hashlib.sha256(b"forecost-installation-key-v1\0" + value).hexdigest().encode("ascii")


def _read_key_id(path: Path) -> bytes:
    validate_private_file(path, may_not_exist=False)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        value = os.read(descriptor, _KEY_ID_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(value) != _KEY_ID_BYTES:
        raise LocalIdentityKeyError("installation identity key id has an invalid length")
    return value


def _validate_or_create_key_id(home: Path, value: bytes) -> None:
    path = home / INSTALLATION_KEY_ID_NAME
    expected = _key_id(value)
    try:
        actual = _read_key_id(path)
    except (FileNotFoundError, UnsafeDataPathError):
        if path.exists() or path.is_symlink():
            raise
        if _ledger_has_keyed_cursors(home):
            raise LocalIdentityKeyError(
                "installation identity key id is missing while keyed state exists; "
                "restore both identity files or purge the complete Forecost data root"
            ) from None
        with suppress(FileExistsError):
            _publish_exact(path, expected)
        actual = _read_key_id(path)
    if not hmac.compare_digest(actual, expected):
        raise LocalIdentityKeyError(
            "installation identity key does not match its registered id; "
            "restore both identity files or purge the complete Forecost data root"
        )


def _ledger_has_keyed_cursors(home: Path) -> bool:
    ledger = home / "ledger.db"
    if not ledger.is_file() or ledger.is_symlink():
        return False
    try:
        conn = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
        try:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ingest_state'"
            ).fetchone()
            if table is None:
                return False
            return (
                conn.execute(
                    "SELECT 1 FROM ingest_state WHERE cursor_key LIKE 'cursor-hmac:v1:%' LIMIT 1"
                ).fetchone()
                is not None
            )
        finally:
            conn.close()
    except sqlite3.Error as error:
        raise LocalIdentityKeyError(
            "cannot verify installation identity key state in the existing ledger"
        ) from error


def _load_validated_key(home: Path, path: Path) -> bytes:
    value = _read_exact_key(path)
    _validate_or_create_key_id(home, value)
    return value


def _keyed_state_exists(home: Path, id_path: Path) -> bool:
    return id_path.exists() or id_path.is_symlink() or _ledger_has_keyed_cursors(home)


def _create_validated_key(home: Path, path: Path, id_path: Path) -> bytes | None:
    if _keyed_state_exists(home, id_path):
        raise LocalIdentityKeyError(
            "installation identity key is missing while keyed state exists; "
            "restore the identity files or purge the complete Forecost data root"
        ) from None
    try:
        value = _create_key(path)
    except FileExistsError:
        return None
    _validate_or_create_key_id(home, value)
    return value


def _installation_key_attempt(home: Path, path: Path, id_path: Path) -> bytes | None:
    try:
        return _load_validated_key(home, path)
    except (FileNotFoundError, UnsafeDataPathError):
        if path.exists() or path.is_symlink():
            raise
        return _create_validated_key(home, path, id_path)
    except LocalIdentityKeyError:
        # A just-created file may not have received its 32 bytes yet.  An
        # established malformed file remains a hard error after retries.
        return None


def _wait_for_key_publish(attempt: int) -> None:
    if attempt + 1 < _CREATE_RETRIES:
        time.sleep(0.005)


def installation_key() -> bytes:
    """Return the stable 256-bit key for this ``FORECOST_HOME``.

    Creation fsyncs a private temporary file, then atomically publishes it
    without replacement. A public key-id sidecar detects accidental replacement.
    If keyed cursors exist, deleting both files is a hard error.
    """
    home = ensure_private_dir(forecost_home())
    path = home / INSTALLATION_KEY_NAME
    id_path = home / INSTALLATION_KEY_ID_NAME
    for attempt in range(_CREATE_RETRIES):
        value = _installation_key_attempt(home, path, id_path)
        if value is not None:
            return value
        _wait_for_key_publish(attempt)
    return _load_validated_key(home, path)


def keyed_fingerprint(namespace: str, *parts: str, key: bytes | None = None) -> str:
    """HMAC a length-delimited tuple without retaining any input text."""
    secret = key if key is not None else installation_key()
    digest = hmac.new(secret, digestmod=hashlib.sha256)
    for value in (namespace, *parts):
        encoded = value.encode("utf-8", errors="replace")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()
