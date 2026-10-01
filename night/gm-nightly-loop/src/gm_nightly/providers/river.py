from __future__ import annotations

import json
import os
import random
import uuid
from itertools import cycle

from ..config import Config
from ..evaluation import Prediction, lookup_requested, task_reward
from ..generation import CRITIC_INSTRUCTIONS, TEACHER_INSTRUCTIONS, source_payload
from ..models import Memory, Task, canonical, parse_json
from ..sources import jsonl
from .base import ModelRef, RewardFn, TrainingProvider, TrainResult


def river_client():
    try:
        import river_client as river
    except ImportError:
        raise RuntimeError("Install River support with: pip install -e '.[river]'") from None
    key = os.environ.get("RIVER_API_KEY")
    if not key:
        raise RuntimeError("Set RIVER_API_KEY in the environment before using River")
    return river.Client(api_key=key, timeout=600)


def ensure_models(client, names: list[str]) -> None:
    missing = sorted(set(names) - set(client.get_capabilities()))
    if missing:
        raise ValueError(
            "River account cannot access configured models: "
            + ", ".join(missing)
            + ". Run gm-nightly models and update your configuration."
        )


def completion_text(result) -> str:
    if result.status_code != 200:
        raise RuntimeError(f"River completion failed with status {result.status_code}")
    choice = json.loads(result.response_json)["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("River response was truncated or did not finish normally")
    content = choice["message"].get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("River returned no final text")
    return content


class RiverTeacher:
    def __init__(self, client, config: Config):
        self.provider, self.config = RiverProvider(client, config), config
        self.identity = f"river:{config.teacher_model}:critic={config.critic_model}:v2"
        self.usage = self.provider.usage
        ensure_models(client, [config.teacher_model, config.critic_model])

    def ask(self, model: str, instructions: str, content: str) -> dict:
        output = self.provider.sample(
            ModelRef("river", model),
            [[{"role": "system", "content": instructions}, {"role": "user", "content": content}]],
            max_tokens=self.config.max_generation_tokens,
            temperature=0.3,
        )
        return parse_json(output[0])

    def generate(self, memory: Memory) -> dict:
        return self.ask(self.config.teacher_model, TEACHER_INSTRUCTIONS, source_payload(memory))

    def critique(self, memory: Memory, bundle: dict) -> dict:
        return self.ask(
            self.config.critic_model,
            CRITIC_INSTRUCTIONS,
            canonical({"source": json.loads(source_payload(memory)), "curriculum": bundle}),
        )


def make_environment(reward_fn: RewardFn | None = None):
    from river_client import rl
    from river_client.renderers import get_text_content

    class CompanyMemoryEnv(rl.Env):
        recovery = "stateless"

        async def reset(self, row):
            self.task, self.looked_up = Task(**row), False
            return self.task.messages()

        async def on_turn(self, traj):
            text = get_text_content(traj.messages[-1])
            if (
                self.task.lookup_required
                and not self.looked_up
                and lookup_requested(self.task, text)
            ):
                self.looked_up = True
                return [self.task.observation()]
            return None

        async def reward(self, traj, row):
            if not traj.messages or traj.messages[-1].get("role") != "assistant":
                return 0.0
            text = get_text_content(traj.messages[-1])
            score = task_reward(self.task, Prediction(text, self.looked_up))
            # Custom grader can tighten the reward, never bypass required lookup/citation.
            return min(score, max(0.0, min(1.0, reward_fn(row, text)))) if reward_fn else score

    return CompanyMemoryEnv


def training_example(renderer, task: Task, max_context_tokens: int) -> dict:
    return message_example(renderer, task.sft()["messages"], max_context_tokens)


def message_example(renderer, messages, max_context_tokens):
    from river_client.renderers import TrainOnWhat

    example = renderer.build_training_example(messages, train_on=TrainOnWhat.ALL_ASSISTANT)
    if len(example.input_ids) > max_context_tokens:
        raise ValueError("SFT example exceeds context budget; split its source memory")
    if not example.num_loss_tokens:
        raise ValueError("SFT example has no assistant loss tokens")
    return example.to_dict()


class RiverProvider(TrainingProvider):
    name = "river"

    def __init__(self, client, config: Config):
        self.client, self.config = client, config
        self.usage = []

    def list_base_models(self):
        return list(self.client.get_capabilities())

    def sample(self, model, prompts, max_tokens=512, temperature=0.0):
        if model.provider != self.name:
            raise ValueError("Model provider mismatch")
        result = []
        for messages in prompts:
            kwargs = dict(max_tokens=max_tokens, temperature=temperature)
            if model.checkpoint:
                response = self.client.chat_complete_from_checkpoint(
                    messages,
                    checkpoint_path=model.checkpoint,
                    base_model=model.base_model,
                    **kwargs,
                )
            else:
                response = self.client.chat_complete(
                    messages, base_model=model.base_model, **kwargs
                )
            body = json.loads(response.response_json)
            self.usage.append(
                {
                    "model": model.base_model,
                    "checkpoint": model.checkpoint,
                    "tokens": body.get("usage"),
                    "cost_usd": None,
                }
            )
            result.append(completion_text(response))
        return result

    def train_sft(self, base, examples_path, lora_rank, epochs, learning_rate):
        from pathlib import Path

        import river_client as river
        from river_client.renderers import get_renderer

        ensure_models(self.client, [base.base_model])
        renderer = get_renderer(base.base_model)
        batch = [
            message_example(renderer, row["messages"], self.config.max_context_tokens)
            for row in jsonl(Path(examples_path))
        ]
        if not batch:
            raise ValueError("No SFT examples")
        metrics, rng = [], random.Random(0)
        with self.client.session(
            project=f"gm-nightly-{self.config.tenant}", phase="sft"
        ) as session:
            model = session.create_model(
                base_model=base.base_model,
                tokenizer=renderer.tokenizer,
                lora=river.LoraConfig(rank=lora_rank, seed=0),
                checkpoint=base.checkpoint,
            )
            for epoch in range(epochs):
                rng.shuffle(batch)
                for i in range(0, len(batch), self.config.batch_size):
                    # Sequential primitives intentionally avoid an optimizer step after a failed backward.
                    forward = model.forward_backward(
                        batch[i : i + self.config.batch_size], loss_fn="cross_entropy"
                    )
                    optimizer = model.optim_step(lr=learning_rate, grad_clip_norm=1.0)
                    metrics.append(
                        {
                            "epoch": epoch,
                            "forward": forward.metrics,
                            "optimizer": getattr(optimizer, "metrics", {}),
                        }
                    )
            saved = model.save_weights("sft-" + uuid.uuid4().hex[:16], mode="training")
        return TrainResult(
            ModelRef(self.name, base.base_model, saved.path),
            {"steps": metrics, "examples": len(batch), "cost_usd": None},
        )

    def train_rl(self, start, tasks_path, reward_fn, steps, group_size, learning_rate):
        from pathlib import Path

        import river_client as river
        from river_client import rl
        from river_client.renderers import get_renderer

        rows = jsonl(Path(tasks_path))
        if not rows or any(row["split"] != "train" for row in rows):
            raise ValueError("RL accepts only a nonempty training partition")
        renderer = get_renderer(start.base_model)
        metrics = []
        with self.client.session(project=f"gm-nightly-{self.config.tenant}", phase="rl") as session:
            model = session.create_model(
                base_model=start.base_model,
                tokenizer=renderer.tokenizer,
                lora=river.LoraConfig(rank=self.config.lora_rank, seed=0),
                checkpoint=start.checkpoint,
            )
            engine = rl.RolloutEngine(
                model,
                env=make_environment(reward_fn),
                renderer=renderer,
                budget=rl.Budget(
                    max_turns=2,
                    max_generated_tokens=self.config.max_tokens,
                    max_context_tokens=self.config.max_context_tokens,
                ),
                schedule=rl.Schedule(concurrency=self.config.batch_size * group_size),
                temperature=1.0,
                seed=0,
            )
            trainer = rl.AsyncTrainer(
                engine=engine,
                optimizer=rl.Adam(lr=learning_rate),
                advantage=rl.GroupCentered(),
                completion=rl.GroupCompletion(mode="wait"),
                normalize="token",
                loss="cispo",
                groups_per_step=self.config.batch_size,
                group_size=group_size,
                max_staleness=0,
            )
            rl.run(
                trainer, cycle(rows), steps=steps, on_step=lambda step: metrics.append(step.metrics)
            )
            saved = model.save_weights("rl-" + uuid.uuid4().hex[:16], mode="training")
        return TrainResult(
            ModelRef(self.name, start.base_model, saved.path), {"steps": metrics, "cost_usd": None}
        )


class RiverTrainer:
    """Compatibility facade; orchestration is provider-independent."""

    def __init__(self, client):
        self.client = client

    def train(self, tasks, config, checkpoint=None, baseline=None):
        from ..training import run_experiment

        return run_experiment(
            RiverProvider(self.client, config), tasks, config, checkpoint, baseline
        )
