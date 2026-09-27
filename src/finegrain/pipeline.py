from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .generation import (
    COMPILER_VERSION,
    dedupe_tasks,
    holdout,
    materialize,
    regression_tasks,
    validate_bundle,
    validate_critique,
)
from .models import Task, Teacher, canonical, digest, normalize
from .privacy import rejection_reason
from .sources import collect, jsonl
from .storage import Store, atomic_json


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(canonical(row) + "\n" for row in rows))
    path.chmod(0o600)


def compile_dataset(config: Config, teacher: Teacher, store: Store) -> Path:
    if not config.experimental_sessions and any(
        s["kind"] in {"codex", "claude"} for s in config.sources
    ):
        raise ValueError(
            "Employee sessions are outside the hackathon scope; enable experimental_sessions explicitly"
        )
    collected = [m for source in config.sources for m in collect(source, config.tenant)]
    if len({m.id for m in collected}) != len(collected):
        raise ValueError("Duplicate memory IDs; each source must provide stable unique IDs")
    rejected, accepted, content_seen = [], [], set()
    for memory in sorted(collected, key=lambda m: m.id):
        reason = rejection_reason(memory, config.tenant, config.max_source_chars)
        fingerprint = digest(normalize(memory.content))
        if not reason and fingerprint in content_seen:
            reason = "duplicate_content"
        if reason:
            rejected.append({"memory_id": memory.id, "reason": reason})
        else:
            content_seen.add(fingerprint)
            accepted.append(memory)
    if len(accepted) > config.max_memories:
        raise ValueError("Memory budget exceeded; narrow sources or raise max_memories explicitly")
    tasks, generated, reviews, resolved_memories, curricula = [], 0, [], [], []
    for memory in accepted:
        history_key = f"history:{memory.id}"
        history = store.get(history_key)
        raw_fingerprint = memory.fingerprint
        if history and history["fingerprint"] != raw_fingerprint:
            previous = history["current"]
        else:
            previous = (
                history["previous"] if history else memory.metadata.get("previous_content", "")
            )
        store.put(
            history_key,
            {"fingerprint": raw_fingerprint, "current": memory.content, "previous": previous},
        )
        memory = replace(memory, metadata={**memory.metadata, "previous_content": previous})
        resolved_memories.append(memory)
        key = digest([COMPILER_VERSION, teacher.identity, memory.fingerprint])
        cached = store.get(key, cache=True)
        if cached is None:
            print(
                f"Finegrain: generating curriculum {len(resolved_memories)}/{len(accepted)}",
                file=sys.stderr,
                flush=True,
            )
            # Completed sources remain cached after an interrupted compile; malformed output never does.
            error = None
            for _ in range(2):
                try:
                    bundle = validate_bundle(memory, teacher.generate(memory))
                    critique = teacher.critique(memory, bundle)
                    validate_critique(critique)
                    cached = {"bundle": bundle, "critique": critique}
                    break
                except (ValueError, TypeError, KeyError) as exc:
                    error = exc
            if cached is None:
                rejected.append(
                    {
                        "memory_id": memory.id,
                        "reason": "curriculum_rejected",
                        "detail": type(error).__name__,
                    }
                )
                continue
            store.put(key, cached, cache=True)
            generated += 1
        # Revalidate cache at the trust boundary as well.
        validate_bundle(memory, cached["bundle"])
        validate_critique(cached["critique"])
        reviews.append({"memory_id": memory.id, "review": cached["critique"]})
        curricula.append(
            {"memory": asdict(memory), "bundle": cached["bundle"], "review": cached["critique"]}
        )
        tasks.extend(
            materialize(memory, cached["bundle"], holdout(memory.group, config.holdout_fraction))
        )
    tasks, duplicates_removed = dedupe_tasks(tasks)
    tasks.extend(regression_tasks())
    used = {t.memory_id for t in tasks}
    lineage = {m.id: m.fingerprint for m in accepted if m.id in used}
    dataset_id = digest(
        [COMPILER_VERSION, teacher.identity, lineage, [asdict(t) for t in tasks], rejected]
    )[:20]
    root = config.workspace / "runs"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    latest = store.get("latest_dataset")
    latest_id = None
    if latest and Path(latest).exists():
        try:
            latest_id = load_dataset(Path(latest), config.tenant)[0]["id"]
        except ValueError:
            # Older artifact layouts are rebuilt from revalidated curriculum cache.
            # Training still refuses the invalid/obsolete artifact itself.
            pass
    if latest and Path(latest).exists() and latest_id == dataset_id:
        target = Path(latest)
    else:
        target = root / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + dataset_id)
    if not target.exists():
        stage = Path(tempfile.mkdtemp(prefix=".compile-", dir=root))
        try:
            write_jsonl(stage / "tasks.jsonl", [asdict(t) for t in tasks])
            write_jsonl(stage / "sft.jsonl", [t.sft() for t in tasks if t.split == "train"])
            write_jsonl(stage / "rl.jsonl", [asdict(t) for t in tasks if t.split == "train"])
            write_jsonl(stage / "eval.jsonl", [asdict(t) for t in tasks if t.split != "train"])
            write_jsonl(
                stage / "memories.jsonl", [asdict(m) for m in resolved_memories if m.id in used]
            )
            atomic_json(stage / "reviews.json", reviews)
            write_jsonl(stage / "curricula.jsonl", curricula)
            atomic_json(
                stage / "generation_log.json",
                {
                    "teacher": teacher.identity,
                    "generated_pages": generated,
                    "cached_pages": len(reviews) - generated,
                    "duplicates_removed": duplicates_removed,
                    "usage": getattr(teacher, "usage", []),
                    "cost_usd": None,
                    "cost_note": "Cost is unavailable unless reported by the provider; null is not zero.",
                },
            )
            atomic_json(stage / "rejections.json", rejected)
            manifest = {
                "schema": 1,
                "compiler": COMPILER_VERSION,
                "id": dataset_id,
                "tenant": config.tenant,
                "teacher": teacher.identity,
                "demo": config.teacher == "demo",
                "created_at": datetime.now(UTC).isoformat(),
                "counts": dict(Counter(t.split for t in tasks)),
                "kinds": dict(Counter(t.kind for t in tasks if t.split != "regression")),
                "duplicates_removed": duplicates_removed,
                "memories": len(lineage),
                "generated_memories": generated,
                "rejected_memories": len(rejected),
                "lineage": lineage,
                "training_lineage": {
                    m.id: m.fingerprint
                    for m in accepted
                    if any(t.memory_id == m.id and t.split == "train" for t in tasks)
                },
                "files": {p.name: digest(p.read_text()) for p in stage.iterdir()},
            }
            atomic_json(stage / "manifest.json", manifest)
            os.replace(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    load_dataset(target, config.tenant)
    store.put("latest_dataset", str(target))
    store.put(
        "last_compile",
        {"at": datetime.now(UTC).isoformat(), "generated": generated, "dataset": dataset_id},
    )
    return target


def load_dataset(path: Path, tenant: str) -> tuple[dict, list[Task]]:
    manifest = json.loads((path / "manifest.json").read_text())
    if manifest.get("schema") != 1 or manifest.get("tenant") != tenant:
        raise ValueError("Dataset schema or company does not match")
    required = {
        "tasks.jsonl",
        "sft.jsonl",
        "rl.jsonl",
        "eval.jsonl",
        "memories.jsonl",
        "reviews.json",
        "rejections.json",
        "generation_log.json",
        "curricula.jsonl",
    }
    if set(manifest.get("files", {})) != required:
        raise ValueError("Dataset file manifest is incomplete")
    for name, expected in manifest["files"].items():
        if digest((path / name).read_text()) != expected:
            raise ValueError(f"Dataset integrity check failed: {name}")
    tasks = [Task(**row) for row in jsonl(path / "tasks.jsonl")]
    return manifest, tasks
