"""Incremental, read-only adapters for local agent histories.

No tools, reasoning blocks, images, or attachments enter the memory compiler.
Rows are projected into a local SQLite journal, never into a relay request.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from .models import canonical, digest
from .sources import text_content

MAX_LINE = 4 * 1024 * 1024
BATCH_BYTES = 16 * 1024 * 1024


def default_sources(home: Path | None = None) -> list[dict]:
    home = home or Path.home()
    return [
        {"kind": "claude", "path": str(home / ".claude/projects")},
        {
            "kind": "codex",
            "path": str(Path(os.environ.get("CODEX_HOME", str(home / ".codex"))) / "sessions"),
        },
        {"kind": "pi", "path": str(home / ".pi/agent/sessions")},
    ]


def project_row(row: dict, kind: str, offset: int) -> dict:
    """Allowlist fields. Source format extensions never become accidental uploads."""
    result = {
        "id": str(row.get("id") or row.get("uuid") or offset),
        "parent": row.get("parentId", row.get("parentUuid")),
        "role": "",
        "text": "",
    }
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    cwd = row.get("cwd") or (
        payload.get("cwd") if row.get("type") in {"session_meta", "turn_context"} else None
    )
    if isinstance(cwd, str):
        result["cwd"] = cwd
    message = None
    if kind == "claude" and row.get("type") in {"user", "assistant"}:
        message = row.get("message")
        if row.get("isSidechain"):
            return result
    elif kind == "codex":
        if (
            row.get("type") == "response_item"
            and payload.get("type") == "message"
            and payload.get("channel") not in {"analysis", "commentary"}
        ):
            message = payload
        elif (
            row.get("type") == "item.completed"
            and row.get("item", {}).get("type") == "agent_message"
        ):
            message = {"role": "assistant", "content": row["item"].get("text", "")}
        elif row.get("type") == "gm.user_prompt":
            message = {"role": "user", "content": row.get("text", "")}
    elif kind in {"pi", "jsonl"} and row.get("type") == "message":
        message = row.get("message")
    if isinstance(message, dict) and message.get("role") in {"user", "assistant"}:
        result.update(role=message["role"], text=text_content(message.get("content"))[:24000])
    if kind == "pi" and row.get("type") == "context_edit":
        replacement = row.get("replacement")
        if isinstance(replacement, dict):
            replacement = replacement.get("content")
        result["edit"] = {"target": row.get("targetId"), "text": text_content(replacement)}
    return result


def active_messages(rows: list[dict], kind: str) -> list[dict]:
    if kind == "pi" and any(r.get("parent") for r in rows):
        nodes = {r["id"]: r for r in rows}
        selected, seen, node = [], set(), rows[-1] if rows else None
        while node and node["id"] not in seen:
            selected.append(node)
            seen.add(node["id"])
            node = nodes.get(node.get("parent"))
        rows = list(reversed(selected))
    edits = {r["edit"]["target"]: r["edit"]["text"] for r in rows if "edit" in r}
    return [
        {**r, "text": edits.get(r["id"], r["text"])}
        for r in rows
        if r.get("role") and edits.get(r["id"], r.get("text", "")).strip()
    ]


class TraceJournal:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS cursors (path TEXT PRIMARY KEY, kind TEXT, inode TEXT, offset INTEGER, project TEXT, mixed INTEGER, touched REAL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS events (path TEXT, offset INTEGER, body TEXT, PRIMARY KEY(path, offset))"
        )

    def close(self):
        self.db.close()

    def read(self, path: Path, kind: str) -> dict:
        if kind not in {"claude", "codex", "pi", "jsonl"}:
            raise ValueError("Unknown trace adapter")
        if path.is_symlink():
            raise ValueError("Trace symlinks are not followed")
        stat = path.stat()
        key, inode = str(path.resolve()), f"{stat.st_dev}:{stat.st_ino}"
        old = self.db.execute(
            "SELECT inode, offset, project, mixed, touched FROM cursors WHERE path=?", (key,)
        ).fetchone()
        reset = not old or old[0] != inode or stat.st_size < old[1]
        position, project, mixed = (0, "", False) if reset else (old[1], old[2], bool(old[3]))
        processed, malformed = 0, 0
        with self.db:
            if reset:
                self.db.execute("DELETE FROM events WHERE path=?", (key,))
            with path.open("rb") as stream:
                stream.seek(position)
                start = position
                while stream.tell() - start < BATCH_BYTES:
                    offset = stream.tell()
                    line = stream.readline(MAX_LINE + 1)
                    if not line:
                        break
                    if len(line) > MAX_LINE:
                        # Do not advance over a partial oversized row; discard only when complete.
                        while line and not line.endswith(b"\n"):
                            line = stream.readline(MAX_LINE + 1)
                        if not line:
                            break
                        position, malformed = stream.tell(), malformed + 1
                        continue
                    if not line.endswith(b"\n"):
                        break  # Writer is still appending. Retry from the prior durable cursor.
                    position = stream.tell()
                    try:
                        raw = json.loads(line)
                        if not isinstance(raw, dict):
                            raise ValueError()
                        row = project_row(raw, kind, offset)
                    except (ValueError, TypeError, AttributeError):
                        malformed += 1
                        continue
                    cwd = row.pop("cwd", "")
                    if cwd:
                        cwd = str(Path(cwd).expanduser().resolve())
                        if project and cwd != project:
                            mixed = True
                        project = project or cwd
                    self.db.execute(
                        "INSERT OR REPLACE INTO events VALUES (?, ?, ?)",
                        (key, offset, canonical(row)),
                    )
                    processed += 1
            touched = time.time() if reset or position != (old[1] if old else 0) else old[4]
            self.db.execute(
                "INSERT OR REPLACE INTO cursors VALUES (?, ?, ?, ?, ?, ?, ?)",
                (key, kind, inode, position, project, int(mixed), touched),
            )
        return {
            "session": digest([kind, key])[:24],
            "events": processed,
            "malformed": malformed,
            "complete": position == stat.st_size,
        }

    def sessions(self) -> list[dict]:
        result = []
        for path, kind, _, offset, project, mixed, touched in self.db.execute(
            "SELECT * FROM cursors ORDER BY path"
        ):
            rows = [
                json.loads(r[0])
                for r in self.db.execute(
                    "SELECT body FROM events WHERE path=? ORDER BY offset", (path,)
                )
            ]
            result.append(
                {
                    "id": digest([kind, path])[:24],
                    "path": path,
                    "kind": kind,
                    "project": project,
                    "mixed": bool(mixed),
                    "touched": touched,
                    "offset": offset,
                    "messages": active_messages(rows, kind),
                }
            )
        return result

    def scan(self, sources: list[dict]) -> dict:
        result = {"files": 0, "events": 0, "malformed": 0, "errors": 0}
        for source in sources:
            root = Path(source["path"]).expanduser()
            if not root.exists():
                continue
            paths = root.rglob("*.jsonl") if root.is_dir() else [root]
            for path in sorted(paths):
                if path.is_symlink() or not path.resolve().is_relative_to(
                    root.resolve() if root.is_dir() else root.resolve().parent
                ):
                    continue
                try:
                    info = self.read(path, source["kind"])
                    result["files"] += 1
                    result["events"] += info["events"]
                    result["malformed"] += info["malformed"]
                except (OSError, ValueError):
                    result["errors"] += 1
        return result
