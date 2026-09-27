from dataclasses import asdict
from pathlib import Path

import pytest

from finegrain.generation import DemoTeacher
from finegrain.models import Memory
from finegrain.pipeline import compile_dataset, load_dataset, write_jsonl
from finegrain.providers.base import ModelRef, TrainResult
from finegrain.training import run_experiment, train_dataset


class FakeProvider:
    def __init__(self, passed=True, fail=False):
        self.calls = []
        self.baselines = []
        self.passed, self.fail = passed, fail

    def train(self, tasks, config, checkpoint=None, baseline=None):
        self.calls.append(checkpoint)
        self.baselines.append(baseline)
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


def test_first_company_run_starts_from_gm_foundation(config, store):
    config.foundation_checkpoint = "river://gm/foundation-v1"
    config.foundation_name = "gm-v1"
    path = real_manifest(config, store)
    provider = FakeProvider()

    result = train_dataset(config, path, provider, store)

    assert provider.calls == ["river://gm/foundation-v1"]
    assert provider.baselines == [
        {
            "student_model": "Qwen/Qwen3.5-9B",
            "checkpoint": "river://gm/foundation-v1",
        }
    ]
    assert result["resume_strategy"] == "foundation_checkpoint"
    assert result["started_from_checkpoint"] == "river://gm/foundation-v1"
    assert result["foundation"] == {
        "name": "gm-v1",
        "checkpoint": "river://gm/foundation-v1",
        "base_model": "Qwen/Qwen3.5-9B",
    }


def test_experiment_evaluates_gm_as_current_before_training(config, store):
    config.teacher = "river"
    config.rl_steps = 0
    path = compile_dataset(config, DemoTeacher(), store)
    _, tasks = load_dataset(path, config.tenant)

    class Provider:
        name = "river"

        def __init__(self):
            self.sampled = []

        def sample(self, model, prompts, **kwargs):
            self.sampled.extend([model.checkpoint] * len(prompts))
            return ['{"answer":null}'] * len(prompts)

        def train_sft(self, base, *args):
            assert base.checkpoint == "river://gm/foundation-v1"
            return TrainResult(ModelRef("river", config.student_model, "river://company/sft"), {})

    provider = Provider()
    result = run_experiment(
        provider,
        tasks,
        config,
        checkpoint="river://gm/foundation-v1",
        baseline={
            "student_model": config.student_model,
            "checkpoint": "river://gm/foundation-v1",
        },
    )

    assert None in provider.sampled
    assert "river://gm/foundation-v1" in provider.sampled
    assert "river://company/sft" in provider.sampled
    assert result["parent_checkpoint"] == "river://gm/foundation-v1"


def test_rebuild_after_withdrawal_returns_to_gm_foundation(config, store):
    config.foundation_checkpoint = "river://gm/foundation-v1"
    path = real_manifest(config, store)
    first_provider = FakeProvider()
    previous = train_dataset(config, path, first_provider, store)

    import json

    source = Path(config.sources[0]["path"])
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    changed_id = next(iter(previous["training_lineage"])).split(":", 1)[1]
    write_jsonl(source, [row for row in rows if row["id"] != changed_id])
    updated = compile_dataset(config, DemoTeacher(), store)
    provider = FakeProvider(passed=False)

    result = train_dataset(config, updated, provider, store)

    assert provider.calls == ["river://gm/foundation-v1"]
    assert result["resume_strategy"] == "source_revised_or_removed"
    assert store.get("promoted") is None


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
