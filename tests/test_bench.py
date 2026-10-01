import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
from run_bench import garry_baselines, load_tasks, parse_answer, score  # noqa: E402

SKILLS = {"skillify", "skill-creator", "enrich"}


def test_parse_answer_strips_formatting_and_case():
    assert parse_answer("  `Skillify`.\n", SKILLS) == "skillify"
    assert parse_answer('"skill-creator"', SKILLS) == "skill-creator"
    assert parse_answer("**enrich**\nbecause it enriches", SKILLS) == "enrich"


def test_parse_answer_reads_resolver_style_skill_path():
    assert parse_answer("`skills/skill-creator/SKILL.md`", SKILLS) == "skill-creator"


def test_parse_answer_drops_think_block():
    assert parse_answer("<think>maybe enrich?</think>\nskillify", SKILLS) == "skillify"
    assert parse_answer("<think>never closed enrich", SKILLS) == ""


def test_parse_answer_keeps_non_skill_reply_so_it_scores_wrong():
    assert parse_answer("I would use skillify here", SKILLS) == "i would use skillify here"


def test_score_counts_accuracy_median_and_cost():
    cases = [{"correct": True, "latency_ms": 100, "cost_usd": 0.001},
             {"correct": False, "latency_ms": 300, "cost_usd": 0.003},
             {"correct": True, "latency_ms": 200, "cost_usd": 0.002}]
    assert score(cases) == {"accuracy": 0.6667, "p50_latency_ms": 200,
                            "cost_per_task_usd": 0.002, "n": 3}


def test_score_cost_is_null_when_any_call_has_no_cost():
    cases = [{"correct": True, "latency_ms": 1, "cost_usd": 0.001},
             {"correct": True, "latency_ms": 1, "cost_usd": None}]
    assert score(cases)["cost_per_task_usd"] is None


def _gbrain(tmp_path):
    evals = tmp_path / "evals/functional-area-resolver"
    (evals / "baseline-runs").mkdir(parents=True)
    (evals / "fixtures-held-out.jsonl").write_text(
        '// comment\n{"intent":"Skillify this","expected_skill":"skillify"}\n')
    for name, skill in [("enrich", "enrich"), ("other", "skill-creator")]:
        d = tmp_path / "skills" / name
        d.mkdir(parents=True)
        (d / "routing-eval.jsonl").write_text(
            f'{{"intent":"Enrich Jane","expected_skill":"{skill}"}}\n'
            f'{{"intent":"only {name}","expected_skill":"{skill}"}}\n'
            '{"intent":"nothing","expected_skill":null}\n')
    return tmp_path


def test_load_tasks_drops_contradictions_negatives_and_unknown_skills(tmp_path):
    tasks = load_tasks(_gbrain(tmp_path), SKILLS)
    assert [c["intent"] for c in tasks["resolver-heldout"]] == ["Skillify this"]
    assert sorted(c["intent"] for c in tasks["routing-eval-heldout"]) == ["only enrich", "only other"]


def test_garry_baselines_use_strict_held_out_functional_areas(tmp_path):
    gbrain = _gbrain(tmp_path)
    rows = [{"kind": "receipt"},
            {"kind": "run", "corpus": "held_out", "variant": "functional-areas", "correct": 1},
            {"kind": "run", "corpus": "held_out", "variant": "functional-areas", "correct": 0},
            {"kind": "run", "corpus": "training", "variant": "functional-areas", "correct": 0},
            {"kind": "run", "corpus": "held_out", "variant": "baseline", "correct": 0}]
    text = "".join(json.dumps(r) + "\n" for r in rows)
    for file in ["2026-05-11-opus-4-7.jsonl", "2026-05-11-sonnet-4-6.jsonl", "2026-05-11-haiku-4-5.jsonl"]:
        (gbrain / "evals/functional-area-resolver/baseline-runs" / file).write_text(text)
    assert garry_baselines(gbrain) == {"opus": 0.5, "sonnet": 0.5, "haiku": 0.5}
