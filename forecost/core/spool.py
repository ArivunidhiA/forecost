"""Crash-resistant immutable JSONL spools shared by current and legacy writers."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from collections.abc import Iterable, Mapping
from contextlib import suppress
from pathlib import Path

from forecost.core.paths import chmod_private, ensure_private_dir


def write_immutable_spool(base_path: Path, rows: Iterable[Mapping[str, object]]) -> Path:
    """Fsync rows to a unique file and atomically make the complete spool visible.

    A recovery command can safely archive another immutable spool while writers
    publish new batches under distinct names. This avoids the append-versus-
    rewrite race inherent in one shared ``recovery.jsonl`` file.
    """
    ensure_private_dir(base_path.parent)
    final_path = base_path.with_name(
        f"{base_path.stem}.{time.time_ns()}.{os.getpid()}.{uuid.uuid4().hex}.jsonl"
    )
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=base_path.parent,
            prefix=f".{base_path.stem}-spill-",
            suffix=".tmp",
            delete=False,
        ) as temp:
            temp_name = temp.name
            for row in rows:
                temp.write(json.dumps(row, default=str, separators=(",", ":")) + "\n")
            temp.flush()
            os.fsync(temp.fileno())
        temp_path = Path(temp_name)
        chmod_private(temp_path)
        os.replace(temp_path, final_path)
        chmod_private(final_path)
        return final_path
    except BaseException:
        if temp_name is not None:
            with suppress(OSError):
                Path(temp_name).unlink(missing_ok=True)
        raise
