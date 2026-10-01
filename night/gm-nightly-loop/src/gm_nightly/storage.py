from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .models import canonical


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(canonical(data) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def workspace_lock(path: Path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (path / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "Another GM Nightly Loop process owns this company workspace"
            ) from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class Store:
    def __init__(self, path: Path):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path / "state.sqlite3")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

    def get(self, key: str, *, cache=False):
        table = "cache" if cache else "state"
        row = self.db.execute(f"SELECT value FROM {table} WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value, *, cache=False):
        table = "cache" if cache else "state"
        with self.db:
            self.db.execute(
                f"INSERT OR REPLACE INTO {table} VALUES (?, ?)", (key, canonical(value))
            )

    def close(self):
        self.db.close()
