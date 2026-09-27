import asyncio
import inspect
from contextlib import contextmanager
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from finegrain.generation import DemoTeacher, materialize
from finegrain.models import canonical
from finegrain.providers.river import (
    RiverProvider,
    completion_text,
    ensure_models,
    make_environment,
    training_example,
)

river = pytest.importorskip("river_client")
from river_client.renderers import TrainingExample  # noqa: E402
from river_client.types import ChatCompleteResult  # noqa: E402


def response(content, finish="stop"):
    return ChatCompleteResult(
        status_code=200,
        response_json=canonical(
            {"choices": [{"message": {"content": content}, "finish_reason": finish}]}
        ),
    )


def test_sdk_signatures_match_adapter():
    from river_client.client import Model, Session

    assert {"base_model", "lora", "tokenizer", "checkpoint"} <= set(
        inspect.signature(Session.create_model).parameters
    )
    assert {"messages", "base_model"} <= set(
        inspect.signature(river.Client.chat_complete).parameters
    )
    assert "mode" in inspect.signature(Model.save_weights).parameters


def test_renderer_masks_first_completion_token():
    # Test the real River 0.11 renderer contract without downloading a tokenizer.
    example = TrainingExample(input_ids=[10, 11, 20, 21], weights=[0, 0, 1, 1])
    datum = example.to_dict()
    assert datum["weights"] == [0, 0.5, 0.5, 0]


@pytest.mark.parametrize("finish", ["length", "tool_calls", None])
def test_truncated_teacher_output_rejected(finish):
    with pytest.raises(ValueError):
        completion_text(response('{"train":[]}', finish))


def test_model_access_fails_without_silent_downgrade():
    with pytest.raises(ValueError, match="cannot access"):
        ensure_models(SimpleNamespace(get_capabilities=lambda: ["small"]), ["large"])


def test_environment_hides_answer_and_scores_order(memory):
    task = materialize(memory, DemoTeacher().generate(memory), False)[0]
    env = make_environment()()
    messages = asyncio.run(env.reset(asdict(task)))
    assert task.answer not in canonical(messages)
    traj = SimpleNamespace(
        messages=[
            {
                "role": "assistant",
                "content": [{"type": "text", "text": canonical({"answer": task.answer})}],
            }
        ]
    )
    assert asyncio.run(env.reward(traj, asdict(task))) == 1
    traj.messages[-1]["content"][0]["text"] = '{"answer":"incorrect"}'
    assert asyncio.run(env.reward(traj, asdict(task))) == 0


class FakeRenderer:
    tokenizer = SimpleNamespace(encode=lambda *args, **kwargs: [1, 2, 3])

    def build_training_example(self, messages, **kwargs):
        return TrainingExample(input_ids=[1, 2, 3, 4], weights=[0, 0, 1, 1])

    def build_prompt_str(self, messages):
        return canonical(messages)


def test_training_adapter_runs_sft_and_saves(memory, config, monkeypatch, tmp_path):
    import river_client.renderers

    from finegrain.pipeline import write_jsonl
    from finegrain.providers.base import ModelRef

    tasks = materialize(memory, DemoTeacher().generate(memory), False)
    examples = tmp_path / "sft.jsonl"
    write_jsonl(examples, [t.sft() for t in tasks if t.split == "train"])
    events = []

    class Model:
        def forward_backward(self, data, **kwargs):
            events.append("forward")
            assert all(d["weights"] == [0, 0.5, 0.5, 0] for d in data)
            return SimpleNamespace(metrics={"loss": 0.1})

        def optim_step(self, **kwargs):
            events.append("optim")
            return SimpleNamespace(metrics={})

        def save_weights(self, name, mode):
            assert mode == "training"
            events.append("save")
            return SimpleNamespace(path="river://test/checkpoint")

    class Client:
        def get_capabilities(self):
            return [config.student_model]

        @contextmanager
        def session(self, **kwargs):
            yield SimpleNamespace(create_model=lambda **kwargs: Model())

    monkeypatch.setattr(river_client.renderers, "get_renderer", lambda _: FakeRenderer())
    result = RiverProvider(Client(), config).train_sft(
        ModelRef("river", config.student_model), str(examples), 16, 1, 1e-4
    )
    assert result.model.checkpoint == "river://test/checkpoint"
    assert events == ["forward", "optim", "save"]


def test_sft_context_overflow_rejected(memory):
    task = materialize(memory, DemoTeacher().generate(memory), False)[0]
    with pytest.raises(ValueError, match="context"):
        training_example(FakeRenderer(), task, 2)
