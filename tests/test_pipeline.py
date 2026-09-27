import json
from dataclasses import asdict
from pathlib import Path

import pytest

from gm_nightly.generation import DemoTeacher
from gm_nightly.pipeline import compile_dataset, load_dataset, write_jsonl
from gm_nightly.report import render_report
from gm_nightly.storage import workspace_lock


class CountingTeacher(DemoTeacher):
    def __init__(self):
        self.calls = 0

    def generate(self, memory):
        self.calls += 1
        return super().generate(memory)


def test_end_to_end_and_idempotent_compile(config, store):
    teacher = CountingTeacher()
    path = compile_dataset(config, teacher, store)
    manifest, tasks = load_dataset(path, config.tenant)
    assert teacher.calls == 8
    assert manifest["counts"]["train"] > 0
    assert manifest["counts"]["recall"] > 0
    assert manifest["counts"]["generalization"] > 0
    assert {t.group for t in tasks if t.split == "train"}.isdisjoint(
        {t.group for t in tasks if t.split == "generalization"}
    )
    again = compile_dataset(config, teacher, store)
    assert again == path and teacher.calls == 8
    assert store.get("last_compile")["generated"] == 0
    for name in ("sft.jsonl", "rl.jsonl", "eval.jsonl"):
        assert (path / name).exists()


def test_incremental_change_and_removal(config, store):
    teacher = CountingTeacher()
    first = compile_dataset(config, teacher, store)
    source = Path(config.sources[0]["path"])
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    rows[0]["content"] = rows[0]["content"].replace("Platform Engineering", "Infrastructure Team")
    rows.pop()
    write_jsonl(source, rows)
    second = compile_dataset(config, teacher, store)
    assert teacher.calls == 9 and first != second
    manifest, tasks = load_dataset(second, config.tenant)
    assert manifest["memories"] == 7
    assert all(t.memory_id != "approved:m7" for t in tasks)
    assert "Platform Engineering" not in (second / "sft.jsonl").read_text()


def test_policy_before_teacher(config, store, memory):
    from dataclasses import replace

    source = Path(config.sources[0]["path"])
    write_jsonl(
        source,
        [
            asdict(replace(memory, training_allowed=False)),
            asdict(replace(memory, id="private", scope="private")),
        ],
    )
    teacher = CountingTeacher()
    path = compile_dataset(config, teacher, store)
    assert teacher.calls == 0
    manifest, _ = load_dataset(path, config.tenant)
    assert manifest["rejected_memories"] == 2 and manifest["memories"] == 0
    assert "Platform Engineering" not in (path / "memories.jsonl").read_text()


def test_duplicate_content_only_compiled_once(config, store, memory):
    from dataclasses import replace

    write_jsonl(
        Path(config.sources[0]["path"]),
        [asdict(memory), asdict(replace(memory, id="copy", group="another-group"))],
    )
    teacher = CountingTeacher()
    path = compile_dataset(config, teacher, store)
    assert teacher.calls == 1
    assert json.loads((path / "rejections.json").read_text())[0]["reason"] == "duplicate_content"


def test_failed_generation_not_cached(config, store):
    class BadTeacher(DemoTeacher):
        def generate(self, memory):
            return {"train": [], "eval": []}

    bad = compile_dataset(config, BadTeacher(), store)
    assert load_dataset(bad, config.tenant)[0]["memories"] == 0
    good = compile_dataset(config, DemoTeacher(), store)
    assert load_dataset(good, config.tenant)[0]["memories"] == 8


def test_integrity_and_company_validation(config, store):
    path = compile_dataset(config, DemoTeacher(), store)
    with pytest.raises(ValueError, match="company"):
        load_dataset(path, "other")
    (path / "sft.jsonl").write_text("tampered")
    with pytest.raises(ValueError, match="integrity"):
        load_dataset(path, config.tenant)


def test_lock_prevents_overlapping_workers(tmp_path):
    with workspace_lock(tmp_path):
        with pytest.raises(RuntimeError, match="Another"):
            with workspace_lock(tmp_path):
                pass


def test_html_report_escapes_source_data(config, store):
    path = compile_dataset(config, DemoTeacher(), store)
    report = render_report(path, config.tenant)
    assert "Offline fixture" in report.read_text()
    assert "<details" in report.read_text()


def test_source_failure_does_not_change_latest(config, store):
    first = compile_dataset(config, DemoTeacher(), store)
    Path(config.sources[0]["path"]).write_text("invalid json")
    with pytest.raises(ValueError):
        compile_dataset(config, DemoTeacher(), store)
    assert store.get("latest_dataset") == str(first)
