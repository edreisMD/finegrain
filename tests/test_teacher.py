import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))
from teacher import Teacher, TeacherError, extract_json  # noqa: E402


@pytest.mark.parametrize("model, url", [
    ("claude-sonnet-5", "https://openrouter.ai/api/v1"),
    ("openai/gpt-5", "https://openrouter.ai/api/v1"),
    ("qwen3-35b", "https://api.openai.com/v1"),
])
def test_teacher_refuses_closed_models(model, url):
    with pytest.raises(TeacherError, match="open model"):
        Teacher(url, model, "key")


def test_teacher_allows_open_models():
    Teacher("https://openrouter.ai/api/v1", "qwen/qwen3-235b-a22b", "key")


def test_extract_json_finds_array_inside_prose():
    assert extract_json('Sure!\n```json\n["a", "b"]\n```') == ["a", "b"]
    with pytest.raises(TeacherError):
        extract_json("no json here")


def test_chat_raises_on_empty_reply(monkeypatch):
    teacher = Teacher("https://openrouter.ai/api/v1", "deepseek/deepseek-v4-pro", "key")
    empty = {"choices": [{"message": {"content": None}, "finish_reason": "stop"}]}
    monkeypatch.setattr(teacher, "_post", lambda request: empty)
    with pytest.raises(TeacherError, match="empty reply"):
        teacher.chat("system", "user")
