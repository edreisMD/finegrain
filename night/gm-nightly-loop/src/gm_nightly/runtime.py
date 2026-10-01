from __future__ import annotations

import json
import time
import uuid
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from .brain import compile_session
from .capture import TraceJournal, default_sources
from .config import Config
from .employee import relay
from .gbrain import Gbrain, note_markdown
from .models import digest
from .storage import Store, atomic_json, workspace_lock


def employee_cycle(config: Config, store: Store, *, force=False, brain=None, company=None):
    local = brain or Gbrain(config.gbrain_command, config.gbrain_home, config.gbrain_source)
    sources = config.capture_sources or default_sources()
    journal = TraceJournal(config.workspace / "capture.sqlite3")
    try:
        scanned = journal.scan(sources)
        changed = 0
        for session in journal.sessions():
            if (config.workspace / "paused").exists():
                break
            path = Path(session["path"])
            # A removed source or file is no longer eligible for publication.
            enabled = path.exists() and any(
                path.is_relative_to(Path(s["path"]).expanduser().resolve())
                if Path(s["path"]).expanduser().is_dir()
                else path == Path(s["path"]).expanduser().resolve()
                for s in sources
            )
            if enabled and (
                session["offset"] < path.stat().st_size
                or (not force and time.time() - session["touched"] < config.quiet_seconds)
            ):
                continue
            signature = digest(
                [
                    session["messages"] if enabled else [],
                    config.shared_projects,
                    config.memory_compiler,
                    config.local_model,
                ]
            )
            key = "capture:" + session["id"]
            previous = store.get(key) or {}
            if previous.get("signature") == signature:
                continue
            slug = "gm-nightly/compiled/" + session["id"]
            # Reuse Gbrain's native import, parsers, redaction and checkpoints for these harnesses.
            if enabled and config.gbrain_ingest and session["kind"] in {"claude", "codex"}:
                local.ingest(str(path), session["kind"])
            page = compile_session(session, config) if enabled else None
            revision = previous.get("revision")
            intent_key = "capture_pending:" + session["id"]
            intent = store.get(intent_key)
            content = (
                note_markdown(
                    page["title"],
                    page["content"],
                    page["shared"],
                    config.share_tag,
                    {
                        "gm_compiler": page["compiler"],
                        "gm_provenance": page["provenance"],
                    },
                )
                if page
                else None
            )
            if intent and intent["content"] != content:
                raise RuntimeError(
                    "A local Gbrain write needs recovery before this session can advance"
                )
            intent = intent or {
                "content": content,
                "revision": revision,
                "request_id": str(uuid.uuid4()),
            }
            store.put(intent_key, intent)
            if content:
                result = local.put(slug, content, intent["revision"], intent["request_id"])
                revision = result["revision"]
            elif revision:
                result = local.delete(slug, revision, intent["request_id"])
                if result.get("state") != "committed":
                    raise RuntimeError("Local Gbrain withdrawal has not committed")
                revision = None
            store.put(key, {"signature": signature, "revision": revision})
            store.put(intent_key, None)
            changed += 1
        result = {"capture": scanned, "compiled_sessions": changed}
        if config.company_home and not (config.workspace / "paused").exists():
            company = company or Gbrain(
                config.gbrain_command, config.company_home, config.company_source, remote=True
            )
            result["relay"] = relay(config, local, company, store)
        return result
    finally:
        journal.close()


def run_worker(config: Config, *, once=False, force=False):
    if config.role not in {"employee", "server"}:
        raise ValueError("Install an employee or server profile first")
    while True:
        status = {
            "role": config.role,
            "company": config.tenant,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        try:
            with workspace_lock(config.workspace), ExitStack() as stack:
                store = Store(config.workspace)
                stack.callback(store.close)
                paused = (config.workspace / "paused").exists()
                if paused:
                    status.update(state="paused")
                else:
                    atomic_json(config.workspace / "status.json", {**status, "state": "working"})
                    if config.role == "employee":
                        status.update(employee_cycle(config, store, force=force))
                    else:
                        from .cli import tick

                        status.update(tick(config, store, stack))
                    status.update(state="ready")
                status["latest_dataset"] = store.get("latest_dataset")
                status["promoted"] = store.get("promoted")
                status["last_delivery"] = store.get("last_delivery")
        except Exception as error:
            # Content-free status file; details remain in upstream's own diagnostics.
            status.update(
                state="error",
                error=type(error).__name__,
                message="Check GM Nightly Loop status and gbrain doctor; work will retry.",
            )
            if once:
                atomic_json(config.workspace / "status.json", status)
                raise
        atomic_json(config.workspace / "status.json", status)
        if once:
            return status
        time.sleep(config.poll_seconds if config.role == "employee" else 30)


def read_status(config: Config):
    path = config.workspace / "status.json"
    return (
        json.loads(path.read_text())
        if path.exists()
        else {"state": "not_started", "company": config.tenant}
    )
