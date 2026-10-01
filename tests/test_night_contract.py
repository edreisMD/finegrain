import importlib.util
import json
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "night/run.py"
SPEC = importlib.util.spec_from_file_location("gm_night", MODULE)
gm_night = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gm_night)


def test_night_status_matches_contract(tmp_path, monkeypatch):
    status = tmp_path / "night-run.json"
    monkeypatch.setattr(gm_night, "STATUS", status)
    gm_night.write_status(1, {"collect": ("done", "Two approved pages")})
    result = json.loads(status.read_text())
    assert result["mock"] is False and result["night"] == 1
    assert [step["id"] for step in result["steps"]] == list(gm_night.STEPS)
    assert result["steps"][0] == {
        "id": "collect",
        "status": "done",
        "detail": "Two approved pages",
    }
    assert result["steps"][1]["status"] == "pending"
    assert gm_night.next_night() == 2


def test_failure_stage_uses_real_progress_markers():
    assert gm_night.failed_step("GM Nightly Loop: reinforcement learning") == "train"
    assert gm_night.failed_step("GM Nightly Loop: generating curriculum 2/3") == "examples"
    assert gm_night.failed_step("connection refused") == "collect"


def test_before_after_prefers_a_real_improvement():
    result = {
        "before": {
            "cases": [
                {
                    "id": "correction-1",
                    "suite": "recall",
                    "prompt": "How do we ship a hotfix?",
                    "response": '{"answer":"Push directly"}',
                    "score": 0,
                }
            ]
        },
        "after": {
            "cases": [
                {
                    "id": "correction-1",
                    "suite": "recall",
                    "prompt": "How do we ship a hotfix?",
                    "response": '{"answer":"Use a reviewed PR"}',
                    "score": 1,
                }
            ]
        },
    }
    assert gm_night.comparison(result) == {
        "prompt": "How do we ship a hotfix?",
        "before": '{"answer":"Push directly"}',
        "after": '{"answer":"Use a reviewed PR"}',
    }
