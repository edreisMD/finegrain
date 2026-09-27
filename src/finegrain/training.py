from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .models import Task, TrainingProvider, digest
from .pipeline import load_dataset
from .storage import Store, atomic_json


def run_experiment(provider, tasks, config, checkpoint=None, baseline=None):
    from .evaluation import Prediction, evaluate, promotion_gate, run_episode, task_reward
    from .pipeline import write_jsonl
    from .providers.base import ModelRef

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    folder = config.workspace / "experiments" / run_id
    data = folder / "data"
    data.mkdir(parents=True, mode=0o700)
    atomic_json(folder / "config.json", {**asdict(config), "state_dir": str(config.state_dir)})
    write_jsonl(data / "sft.jsonl", [t.sft() for t in tasks if t.split == "train"])
    write_jsonl(data / "rl_tasks.jsonl", [asdict(t) for t in tasks if t.split == "train"])
    write_jsonl(data / "eval.jsonl", [asdict(t) for t in tasks if t.split != "train"])

    def assess(model):
        def predict(task):
            def respond(messages):
                try:
                    return provider.sample(model, [messages], max_tokens=config.max_tokens)[0]
                except ValueError as exc:
                    if "truncated" in str(exc) or "no final text" in str(exc):
                        return ""
                    raise

            return run_episode(task, respond)

        return evaluate(tasks, predict)

    base = ModelRef(provider.name, config.student_model)
    print("Finegrain: evaluating base model", file=sys.stderr, flush=True)
    evaluations = {"base": assess(base)}
    atomic_json(folder / "evaluation.json", evaluations)
    current = (
        ModelRef(provider.name, baseline["student_model"], baseline["checkpoint"])
        if baseline
        else base
    )
    evaluations["current"] = assess(current) if baseline else evaluations["base"]
    atomic_json(folder / "evaluation.json", evaluations)
    print("Finegrain: supervised fine-tuning", file=sys.stderr, flush=True)
    sft = provider.train_sft(
        ModelRef(provider.name, config.student_model, checkpoint),
        str(data / "sft.jsonl"),
        config.lora_rank,
        config.sft_epochs,
        config.learning_rate,
    )
    atomic_json(folder / "sft.json", asdict(sft))
    evaluations["sft"] = assess(sft.model)
    atomic_json(folder / "evaluation.json", evaluations)
    candidate = sft
    if config.rl_steps:
        print("Finegrain: reinforcement learning", file=sys.stderr, flush=True)
        candidate = provider.train_rl(
            sft.model,
            str(data / "rl_tasks.jsonl"),
            lambda row, text: task_reward(Task(**row), Prediction(text, True)),
            config.rl_steps,
            config.group_size,
            config.rl_learning_rate,
        )
        atomic_json(folder / "rl.json", asdict(candidate))
        evaluations["candidate"] = assess(candidate.model)
    else:
        evaluations["candidate"] = evaluations["sft"]
    gate = promotion_gate(
        evaluations["current"],
        evaluations["candidate"],
        config.min_score,
        config.max_regression,
        config.min_eval_tasks,
        config.min_recall_gain,
        config.max_confident_wrong_increase,
        config.max_general_regression,
    )
    result = {
        "run_id": run_id,
        "checkpoint": candidate.model.checkpoint,
        "parent_checkpoint": checkpoint,
        "student_model": config.student_model,
        "lora_rank": config.lora_rank,
        "before": evaluations["current"],
        "after": evaluations["candidate"],
        "evaluations": evaluations,
        "gate": gate,
        "metrics": {
            "sft": sft.metrics,
            "candidate": candidate.metrics,
            "sampling_usage": getattr(provider, "usage", []),
            "cost_usd": None,
        },
    }
    atomic_json(folder / "result.json", result)
    from .report import write_evaluation_report

    write_evaluation_report(folder / "report.md", result)
    result["report"] = str(folder / "report.md")
    return result


def training_signature(config: Config) -> str:
    fields = (
        "student_model",
        "lora_rank",
        "sft_epochs",
        "batch_size",
        "rl_steps",
        "group_size",
        "learning_rate",
        "rl_learning_rate",
        "max_tokens",
        "max_context_tokens",
        "min_score",
        "max_regression",
        "min_recall_gain",
        "max_confident_wrong_increase",
        "max_general_regression",
        "min_train_tasks",
        "min_eval_tasks",
    )
    return digest({name: getattr(config, name) for name in fields})


def train_dataset(config: Config, path: Path, provider: TrainingProvider, store: Store) -> dict:
    manifest, tasks = load_dataset(path, config.tenant)
    if manifest["demo"]:
        raise ValueError("Demo datasets are fixtures and cannot be submitted for real training")
    if sum(t.split == "train" for t in tasks) < config.min_train_tasks:
        raise ValueError("Insufficient training tasks")
    if sum(t.split not in {"train", "regression"} for t in tasks) < config.min_eval_tasks:
        raise ValueError("Insufficient company evaluation tasks")
    key = digest([manifest["id"], training_signature(config)])
    existing = store.get(f"training:{key}")
    if existing:
        return existing
    attempt = store.get("active_training")
    if attempt:
        raise RuntimeError(
            "A previous training attempt has an uncertain outcome. Inspect River, then run recover."
        )
    parent = store.get("promoted")
    checkpoint = None
    reset_reason = "first_run"
    if parent:
        old = parent["training_lineage"]
        changed = any(manifest["training_lineage"].get(k) != v for k, v in old.items())
        compatible = (
            parent["student_model"] == config.student_model
            and parent["lora_rank"] == config.lora_rank
        )
        if compatible and not changed:
            checkpoint = parent["checkpoint"]
            reset_reason = "resume_with_replay"
        else:
            reset_reason = "source_revised_or_removed" if changed else "model_configuration_changed"
            # Withdraw the local current-model pointer immediately; old weights cannot be unlearned
            # by removing a dataset row. Remote checkpoint deletion is a separate provider operation.
            store.put("promoted", None)
            atomic_json(
                config.workspace / "model.json",
                {
                    "status": "retired",
                    "reason": reset_reason,
                    "retired_checkpoint": parent["checkpoint"],
                },
            )
    started = datetime.now(UTC).isoformat()
    store.put("active_training", {"key": key, "dataset": manifest["id"], "started_at": started})
    # Never auto-retry a failed remote mutation: its result may have committed on River.
    result = provider.train(tasks, config, checkpoint, baseline=parent)
    result.update(
        {
            "dataset": manifest["id"],
            "tenant": config.tenant,
            "finished_at": datetime.now(UTC).isoformat(),
            "training_lineage": manifest["training_lineage"],
            "resume_strategy": reset_reason,
        }
    )
    artifact = config.workspace / "training" / f"{key}.json"
    atomic_json(artifact, result)
    store.put(f"training:{key}", result)
    store.put("last_training", result)
    if result["gate"]["passed"]:
        store.put("promoted", result)
        atomic_json(config.workspace / "model.json", result)
    store.put("active_training", None)
    return result
