import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))
from leak_filter import LeakFilter, load_eval_intents  # noqa: E402
from make_routing import build_pairs  # noqa: E402


def test_load_eval_intents_skips_comments_examples_and_dupes(tmp_path):
    fixtures = tmp_path / "evals/functional-area-resolver"
    fixtures.mkdir(parents=True)
    (fixtures / "fixtures.jsonl").write_text(
        '// comment\n{"intent":"What do we know about Stripe","expected_skill":"gbrain"}\n')
    (fixtures / "fixtures-held-out.jsonl").write_text(
        '{"intent":"what do we know about stripe?","expected_skill":"gbrain"}\n')
    skill = tmp_path / "skills/enrich"
    skill.mkdir(parents=True)
    (skill / "routing-eval.jsonl").write_text('{"intent":"enrich Jane Doe","expected_skill":"enrich"}\n')
    example = tmp_path / "examples/pack/skills/x"
    example.mkdir(parents=True)
    (example / "routing-eval.jsonl").write_text('{"intent":"example phrase 1","expected_skill":"x"}\n')

    assert load_eval_intents(tmp_path) == ["What do we know about Stripe", "enrich Jane Doe"]


@pytest.mark.parametrize("text, leaks", [
    ("What do we know about Stripe", True),       # exact
    ("what do we know about STRIPE??", True),     # same after normalizing
    ("What do we know about Stripes", True),      # near duplicate
    ("Pull up everything on Stripe's founders", False),
])
def test_leak_filter(text, leaks):
    assert LeakFilter(["What do we know about Stripe"]).leaks(text) is leaks


def test_build_pairs_drops_leaks_ambiguous_and_duplicates():
    leak = LeakFilter(["What do we know about Stripe"])
    candidates = [
        ("enrich Jane Doe from LinkedIn", "enrich", "teacher"),
        ("Enrich jane doe from linkedin!", "enrich", "teacher"),   # duplicate
        ("What do we know about Stripe", "gbrain", "teacher"),     # eval leak
        ("look this up", "gbrain", "teacher"),                     # ambiguous
        ("look this up", "enrich", "teacher"),
    ]
    pairs, stats = build_pairs(candidates, leak)

    assert [p["messages"][1]["content"] for p in pairs] == ["enrich Jane Doe from LinkedIn"]
    assert pairs[0]["messages"][2]["content"] == "enrich"
    assert stats == {"candidates": 5, "leaked": 1, "ambiguous": 2, "duplicate": 1, "kept": 1}
