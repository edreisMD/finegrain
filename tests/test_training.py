from dataclasses import asdict
from pathlib import Path

import pytest

from gm_nightly.config import load_config
from gm_nightly.generation import DemoTeacher
from gm_nightly.models import Memory
from gm_nightly.pipeline import compile_dataset, write_jsonl
from gm_nightly.training import train_dataset


class FakeProvider:
    def __init__(self, passed=True, fail=False):
        self.calls = []
        self.passed, self.fail = passed, fail

    def train(self, tasks, config, checkpoint=None, baseline=None):
        self.calls.append(checkpoint)
        if self.fail:
            raise RuntimeError("Remote timeout")
        return {
            "checkpoint": f"river://fake/{len(self.calls)}",
            "student_model": config.student_model,
            "lora_rank": config.lora_rank,
            "gate": {"passed": self.passed, "reasons": []},
        }


def real_manifest(config, store):
    # Inject a fixture teacher behind the live compiler boundary; never calls River.
    config.teacher = "river"
    return compile_dataset(config, DemoTeacher(), store)


def test_demo_cannot_train(config, store):
    path = compile_dataset(config, DemoTeacher(), store)
    provider = FakeProvider()
    with pytest.raises(ValueError, match="Demo"):
        train_dataset(config, path, provider, store)
    assert provider.calls == []


def test_training_idempotence_and_promotion(config, store):
    path = real_manifest(config, store)
    provider = FakeProvider()
    result = train_dataset(config, path, provider, store)
    assert result["gate"]["passed"]
    assert store.get("promoted")["checkpoint"] == result["checkpoint"]
    assert train_dataset(config, path, provider, store) == result
    assert provider.calls == [None]


def test_first_company_run_starts_from_gm(config, store):
    config.foundation_checkpoint = "river://gm/part-1"
    path = real_manifest(config, store)
    provider = FakeProvider()
    result = train_dataset(config, path, provider, store)
    assert provider.calls == ["river://gm/part-1"]
    assert result["resume_strategy"] == "gm_foundation"


def test_gm_checkpoint_environment_contract(tmp_path, monkeypatch):
    profile = tmp_path / "gm.toml"
    profile.write_text("[gm]\ntenant = 'gm-company'\n")
    monkeypatch.setenv("GM_BASE_MODEL", "Qwen/Qwen3.5-9B")
    monkeypatch.setenv("GM_CHECKPOINT", "river://gm/part-1")
    config = load_config(profile)
    assert config.student_model == "Qwen/Qwen3.5-9B"
    assert config.foundation_checkpoint == "river://gm/part-1"


def test_regression_is_not_promoted(config, store):
    path = real_manifest(config, store)
    result = train_dataset(config, path, FakeProvider(passed=False), store)
    assert not result["gate"]["passed"] and store.get("promoted") is None


def test_uncertain_mutation_never_auto_retried(config, store):
    path = real_manifest(config, store)
    failing = FakeProvider(fail=True)
    with pytest.raises(RuntimeError, match="timeout"):
        train_dataset(config, path, failing, store)
    assert store.get("active_training")
    with pytest.raises(RuntimeError, match="uncertain"):
        train_dataset(config, path, failing, store)
    assert len(failing.calls) == 1


def test_new_memories_resume_and_replay(config, store):
    path = real_manifest(config, store)
    provider = FakeProvider()
    previous = train_dataset(config, path, provider, store)
    source = Path(config.sources[0]["path"])
    with source.open("a") as stream:
        import json

        stream.write(
            json.dumps(
                asdict(
                    Memory(
                        id="new",
                        tenant="acme",
                        employee="bob",
                        source="gbrain",
                        title="New project",
                        content="Owner: Special Projects\nDocumentation home: The Wiki",
                        group="new-project",
                        scope="company",
                        training_allowed=True,
                    )
                )
            )
            + "\n"
        )
    updated = compile_dataset(config, DemoTeacher(), store)
    result = train_dataset(config, updated, provider, store)
    assert provider.calls[-1] == previous["checkpoint"]
    assert result["resume_strategy"] == "resume_with_replay"


def test_revoked_sources_retire_parent(config, store):
    path = real_manifest(config, store)
    previous = train_dataset(config, path, FakeProvider(), store)
    import json

    source = Path(config.sources[0]["path"])
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    changed_id = next(iter(previous["training_lineage"])).split(":", 1)[1]
    rows = [r for r in rows if r["id"] != changed_id]
    write_jsonl(source, rows)
    updated = compile_dataset(config, DemoTeacher(), store)
    provider = FakeProvider(passed=False)
    result = train_dataset(config, updated, provider, store)
    assert provider.calls == [None]
    assert result["resume_strategy"] == "source_revised_or_removed"
    assert store.get("promoted") is None
    assert json.loads((config.workspace / "model.json").read_text())["status"] == "retired"
