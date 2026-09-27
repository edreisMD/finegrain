"""Adapter to the official garrytan/gbrain CLI, pinned/tested at 0.59.0.0.

Gbrain owns storage, revisions, OAuth, scoping, raw traces, and the admin UI.
Finegrain never connects directly to its database or copies its auth system.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from pathlib import Path

from .models import Memory, canonical, digest
from .privacy import has_secret

UPSTREAM_REVISION = "e78f1c38b947b053f3a46881340f74f316be855a"


class GbrainError(RuntimeError):
    pass


class Gbrain:
    def __init__(
        self, command: list[str], home: str = "", source: str = "default", *, remote=False
    ):
        self.command, self.home, self.source, self.remote = command, home, source, remote
        if not source or source == "__all__":
            raise ValueError("Finegrain requires one explicit Gbrain source")

    def env(self):
        env = dict(os.environ)
        env["PATH"] = (
            str(Path(self.command[0]).parent)
            + os.pathsep
            + str(Path.home() / ".bun/bin")
            + os.pathsep
            + env.get("PATH", "/usr/bin:/bin")
        )
        if self.home:
            env["GBRAIN_HOME"] = str(Path(self.home).expanduser().resolve())
        # A company's machine credential must never replace the local brain's connection.
        if not self.remote:
            for key in ("GBRAIN_REMOTE_CLIENT_SECRET", "GBRAIN_REMOTE_TOKEN"):
                env.pop(key, None)
        env["GBRAIN_SOURCE"] = self.source
        return env

    def run(self, args: list[str], content: str | None = None, timeout=120):
        try:
            result = subprocess.run(
                [*self.command, *args],
                input=content or "",
                text=True,
                capture_output=True,
                timeout=timeout,
                env=self.env(),
            )
        except FileNotFoundError:
            raise GbrainError("Gbrain is not installed; run scripts/install-gbrain.sh") from None
        except subprocess.TimeoutExpired:
            raise GbrainError(
                "Gbrain timed out; the next cycle will retry the same request ID"
            ) from None
        if result.returncode:
            # Never forward credentials, source text, or database URLs in upstream errors.
            reason = "Gbrain command failed; check its doctor and intended profile"
            try:
                error = json.loads(result.stdout)
                code = error.get("reason", error.get("error", ""))
                if isinstance(code, str) and re.fullmatch(r"[a-z_]{1,60}", code):
                    reason += ": " + code
            except (ValueError, AttributeError):
                pass
            raise GbrainError(reason)
        return result.stdout

    def call(self, operation: str, params: dict):
        output = self.run(["call", "--source", self.source, operation, canonical(params)])
        try:
            value = json.loads(output)
        except ValueError:
            raise GbrainError(
                "Gbrain returned an incompatible response; use the pinned version"
            ) from None
        if isinstance(value, dict) and (value.get("error") or value.get("status") == "error"):
            raise GbrainError("Gbrain rejected the operation")
        return value

    def pages(self, tag: str, limit: int = 1000):
        pages, offset = [], 0
        while True:
            rows = self.call(
                "list_pages",
                {
                    "source_id": self.source,
                    "tag": tag,
                    "sort": "slug",
                    "limit": 100,
                    "offset": offset,
                },
            )
            if not isinstance(rows, list):
                raise GbrainError("Unexpected page listing")
            pages.extend(rows)
            if len(pages) > limit:
                raise GbrainError("Gbrain page budget exceeded; narrow the training source")
            if len(rows) < 100:
                return [
                    self.call("get_page", {"source_id": self.source, "slug": p["slug"]})
                    for p in pages
                ]
            offset += len(rows)

    def put(
        self, slug: str, markdown: str, revision: str | None = None, request_id: str | None = None
    ):
        args = [
            "put",
            slug,
            "--source-id",
            self.source,
            "--request-id",
            request_id or str(uuid.uuid4()),
            "--json",
        ]
        if revision:
            args += ["--expected-revision", revision]
        result = json.loads(self.run(args, content=markdown))
        if result.get("state") != "committed" or not result.get("revision"):
            raise GbrainError("Gbrain has not committed this write; preserve and retry the request")
        return result

    def delete(self, slug: str, revision: str, request_id: str):
        return self.call(
            "delete_page",
            {
                "slug": slug,
                "source_id": self.source,
                "expected_revision": revision,
                "request_id": request_id,
            },
        )

    def ingest(self, path: str, kind: str):
        formats = {"claude": "claude-code", "codex": "codex"}
        if kind in formats:
            self.run(
                [
                    "transcripts",
                    "ingest",
                    path,
                    "--format",
                    formats[kind],
                    "--source-id",
                    self.source,
                    "--since",
                    "last",
                    "--json",
                ],
                timeout=300,
            )


def shared_memory(page: dict, tenant: str, employee="company") -> Memory | None:
    """Only explicitly approved compiled pages cross the training/relay boundary."""
    fm = page.get("frontmatter") or {}
    if (
        page.get("deleted_at")
        or page.get("type") in {"conversation", "transcript", "session"}
        or fm.get("visibility") != "brain-wide"
        or fm.get("finegrain_training") is not True
    ):
        return None
    content = page.get("compiled_truth", "")
    if (
        not isinstance(content, str)
        or not content.strip()
        or has_secret(canonical([content, page.get("title", "")]))
    ):
        return None
    # Local trusted Gbrain reads can contain protected sections. Do not attempt to
    # reinterpret their visibility: reject that page. Remote Gbrain reads sanitize them.
    if re.search(r"gbrain:(?:facts|takes):", content, re.I):
        return None
    source, slug = page.get("source_id"), page.get("slug")
    if not isinstance(source, str) or not isinstance(slug, str):
        return None
    return Memory(
        id=f"{source}:{slug}",
        tenant=tenant,
        employee=employee,
        source="gbrain",
        title=page["title"],
        content=content,
        group=f"{source}:{slug}",
        scope="company",
        training_allowed=True,
        metadata={
            "gbrain_source": source,
            "slug": slug,
            "revision": page.get("revision"),
            "content_hash": digest(content),
        },
    )


def note_markdown(
    title: str, content: str, shared: bool, tag="finegrain-share", extra: dict | None = None
):
    # JSON strings/values are YAML-compatible, so model text never becomes a YAML key.
    header = {
        "title": title,
        "type": "note",
        "visibility": "brain-wide" if shared else "private",
        "tags": [tag] if shared else [],
        "finegrain_training": shared,
        **(extra or {}),
    }
    return (
        "---\n"
        + "\n".join(f"{k}: {canonical(v)}" for k, v in header.items())
        + "\n---\n\n"
        + content
        + "\n"
    )
