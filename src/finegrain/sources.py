from __future__ import annotations

import json
import re
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

from .models import Memory

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024


def jsonl(path: Path) -> list[dict]:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"Source file too large: {path.name}")
    rows = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON in {path.name} at line {n}") from None
        if not isinstance(row, dict):
            raise ValueError(f"Expected object in {path.name} at line {n}")
        rows.append(row)
    return rows


def files(path: Path, suffix: str) -> list[Path]:
    if not path.exists():
        raise ValueError(f"Source path does not exist: {path}")
    root = path.resolve() if path.is_dir() else path.resolve().parent
    result = sorted(path.rglob(f"*{suffix}")) if path.is_dir() else [path]
    # Explicitly selected roots only; never follow a link out of the source directory.
    return [
        p
        for p in result
        if p.is_file()
        and not p.is_symlink()
        and p.resolve().is_relative_to(root)
        and not any(x.startswith(".") for x in p.relative_to(root).parts)
    ]


def make_memory(source: dict, tenant: str, key: str, title: str, content: str) -> Memory:
    return Memory(
        id=f"{source['name']}:{key}",
        tenant=tenant,
        employee=source.get("employee", "shared"),
        source=source["name"],
        title=title,
        content=content,
        group=f"{source['name']}:{key}",
        scope=source.get("scope", "private"),
        training_allowed=source.get("training_allowed", False),
    )


def text_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            b["text"]
            for b in content
            if isinstance(b, dict)
            and b.get("type") in {"text", "input_text", "output_text"}
            and isinstance(b.get("text"), str)
        )
    return ""


def conversation(rows: list[dict], kind: str) -> str:
    messages = []
    for row in rows:
        msg = None
        if kind == "claude" and row.get("type") in {"user", "assistant"}:
            msg = row.get("message", {})
        elif kind == "codex":
            if (
                row.get("type") == "response_item"
                and row.get("payload", {}).get("type") == "message"
            ):
                if row["payload"].get("channel") not in {"analysis", "commentary"}:
                    msg = row["payload"]
            elif (
                row.get("type") == "item.completed"
                and row.get("item", {}).get("type") == "agent_message"
            ):
                msg = {"role": "assistant", "content": row["item"].get("text", "")}
            elif row.get("type") == "finegrain.user_prompt":
                msg = {"role": "user", "content": row.get("text", "")}
        if isinstance(msg, dict) and msg.get("role") in {"user", "assistant"}:
            content = text_content(msg.get("content"))
            if content.strip():
                messages.append(f"{msg['role']}: {content.strip()}")
    return "\n\n".join(messages)


def read_archive(archive, source: dict, tenant: str) -> list[Memory]:
    total = 0
    with tempfile.TemporaryDirectory(prefix="finegrain-export-") as directory:
        root = Path(directory)
        with tarfile.open(fileobj=archive, mode="r|gz") as tar:
            for entry in tar:
                p = PurePosixPath(entry.name)
                if p.is_absolute() or ".." in p.parts or entry.issym() or entry.islnk():
                    raise ValueError("Unsafe Gbrain archive member")
                if (
                    not entry.isfile()
                    or p.suffix != ".md"
                    or any(x.startswith(".") for x in p.parts)
                ):
                    continue
                total += entry.size
                if entry.size > MAX_FILE_BYTES or total > MAX_ARCHIVE_BYTES:
                    raise ValueError("Gbrain export exceeds size limit")
                parts = p.parts[1:] if p.parts and p.parts[0] == "brain" else p.parts
                target = root.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = tar.extractfile(entry)
                assert stream is not None
                target.write_bytes(stream.read())
        # Apply the same visibility and path policy as a local Markdown source.
        return collect({**source, "kind": "gbrain", "path": str(root)}, tenant)


def collect(source: dict, tenant: str) -> list[Memory]:
    kind = source["kind"]
    if kind == "gbrain_cli":
        from .gbrain import Gbrain, shared_memory

        brain = Gbrain(
            source.get("command", ["gbrain"]),
            source.get("home", ""),
            source["source_id"],
            remote=source.get("remote", False),
        )
        return [
            memory
            for page in brain.pages(source.get("tag", "finegrain-share"), source.get("limit", 1000))
            if (memory := shared_memory(page, tenant)) is not None
        ]
    if kind == "gbrain_ssh":
        host = source.get("host", "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9.-]*", host):
            raise ValueError("gbrain_ssh host must be user@hostname")
        # Documented Gbrain export command. No remote command comes from a memory or model.
        with tempfile.TemporaryFile() as archive:
            subprocess.run(
                ["ssh", "-oBatchMode=yes", "-oConnectTimeout=15", host, "tar czf - -C /data brain"],
                stdout=archive,
                stderr=subprocess.PIPE,
                check=True,
                timeout=120,
            )
            if archive.tell() > MAX_ARCHIVE_BYTES:
                raise ValueError("Gbrain archive exceeds size limit")
            archive.seek(0)
            return read_archive(archive, source, tenant)
    path = Path(source["path"]).resolve()
    if kind == "jsonl":
        result = []
        for file in files(path, ".jsonl"):
            for row in jsonl(file):
                memory = Memory.from_dict(row)
                # Namespace import IDs so multiple employee bundles cannot overwrite each other.
                from dataclasses import replace

                result.append(
                    replace(memory, id=f"{source['name']}:{memory.id}", source=source["name"])
                )
        return result
    if kind not in {"gbrain", "codex", "claude"}:
        raise ValueError(f"Unknown source kind: {kind}")
    result = []
    for file in files(path, ".md" if kind == "gbrain" else ".jsonl"):
        key = str(file.relative_to(path)) if path.is_dir() else file.name
        if any(
            fnmatch(key, pattern)
            for pattern in source.get("exclude_paths", ["personal/**", "hr/**", "compensation/**"])
        ):
            from dataclasses import replace

            result.append(
                replace(
                    make_memory(source, tenant, key, file.stem, "Excluded by path policy"),
                    training_allowed=False,
                )
            )
            continue
        if file.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"Source file too large: {file.name}")
        content = file.read_text() if kind == "gbrain" else conversation(jsonl(file), kind)
        if content.strip():
            memory = make_memory(source, tenant, key, file.stem, content)
            if kind == "gbrain":
                from dataclasses import replace

                # Gbrain export permissions are configured per shared workspace. Optional per-page
                # front matter can narrow that permission, never widen a restricted source.
                header = {}
                if content.startswith("---\n"):
                    head, separator, body = content[4:].partition("\n---\n")
                    if not separator:
                        raise ValueError("Unclosed Markdown metadata header")
                    for line in head.splitlines():
                        field, sep, value = line.partition(":")
                        if sep:
                            header[field.strip()] = value.strip().strip('"').strip("'")
                    content = body
                visibility = header.get(
                    "visibility", "brain-wide" if memory.scope == "company" else "private"
                )
                allowed = visibility in source.get("include_visibility", ["brain-wide"])
                previous = ""
                if source.get("previous_path") and allowed:
                    previous_file = Path(source["previous_path"]) / key
                    if previous_file.is_file() and not previous_file.is_symlink():
                        if previous_file.stat().st_size > MAX_FILE_BYTES:
                            raise ValueError("Previous page exceeds size limit")
                        previous = previous_file.read_text()
                memory = replace(
                    memory,
                    title=header.get("title", memory.title),
                    content=content,
                    scope=memory.scope if allowed else "private",
                    metadata={
                        "path": key,
                        "visibility": visibility,
                        "previous_content": previous,
                        "updated_at": datetime.fromtimestamp(file.stat().st_mtime, UTC).isoformat(),
                    },
                )
            result.append(memory)
    return result
