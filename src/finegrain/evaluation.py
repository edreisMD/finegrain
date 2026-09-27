from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from .models import Task, normalize


def equal(actual, expected) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, str):
        return normalize(actual) == normalize(expected)
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(equal(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            equal(actual[k], expected[k]) for k in expected
        )
    return actual == expected


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def strict_json(text):
    def invalid(_):
        raise ValueError("Nonfinite value")

    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=invalid)


def reward(text: str, answer) -> float:
    try:
        value = strict_json(text)
        return float(
            isinstance(value, dict) and set(value) == {"answer"} and equal(value["answer"], answer)
        )
    except (ValueError, TypeError, RecursionError):
        return 0.0


@dataclass
class Prediction:
    text: str
    looked_up: bool = False


def task_reward(task: Task, prediction: Prediction) -> float:
    try:
        value = strict_json(prediction.text)
        if task.lookup_required and not prediction.looked_up:
            return 0.0
        return float(equal(value, task.expected()))
    except (ValueError, TypeError, RecursionError):
        return 0.0


def lookup_requested(task: Task, text: str) -> bool:
    try:
        return equal(strict_json(text), task.lookup_action())
    except (ValueError, TypeError, RecursionError):
        return False


def run_episode(task: Task, respond: Callable[[list[dict]], str]) -> Prediction:
    messages = task.messages()
    first = respond(messages)
    if task.lookup_required and lookup_requested(task, first):
        messages += [{"role": "assistant", "content": first}, task.observation()]
        return Prediction(respond(messages), looked_up=True)
    return Prediction(first)


def confident_wrong(text: str, expected) -> bool:
    try:
        value = strict_json(text)
        if not isinstance(value, dict) or "answer" not in value:
            # Invalid free text is not treated as a safe abstention.
            return bool(text.strip())
        return value["answer"] is not None and not equal(value["answer"], expected)
    except (ValueError, TypeError, RecursionError):
        return bool(text.strip())


def evaluate(tasks: list[Task], predict: Callable[[Task], str | Prediction]) -> dict:
    cases, scores, kinds = [], defaultdict(list), defaultdict(list)
    for task in tasks:
        if task.split == "train":
            continue
        output = predict(task)
        prediction = output if isinstance(output, Prediction) else Prediction(output)
        score = task_reward(task, prediction)
        wrong = confident_wrong(prediction.text, task.answer)
        scores[task.split].append(score)
        kinds[task.kind].append(score)
        cases.append(
            {
                "id": task.id,
                "suite": task.split,
                "kind": task.kind,
                "score": score,
                "confident_wrong": wrong,
                "looked_up": prediction.looked_up,
                "response": prediction.text,
            }
        )
    company = [c for c in cases if c["suite"] != "regression"]
    return {
        "count": len(cases),
        "score": sum(c["score"] for c in cases) / len(cases) if cases else None,
        "confident_wrong_rate": sum(c["confident_wrong"] for c in company) / len(company)
        if company
        else None,
        "suites": {s: {"count": len(v), "score": sum(v) / len(v)} for s, v in scores.items()},
        "kinds": {s: {"count": len(v), "score": sum(v) / len(v)} for s, v in kinds.items()},
        "cases": cases,
    }


def promotion_gate(
    before: dict,
    after: dict,
    min_score: float,
    max_regression: float,
    min_count: int,
    min_recall_gain: float = 0.05,
    max_confident_wrong_increase: float = 0.0,
    max_general_regression: float = 0.03,
) -> dict:
    reasons = []
    if [(c["id"], c["suite"]) for c in before.get("cases", [])] != [
        (c["id"], c["suite"]) for c in after.get("cases", [])
    ]:
        reasons.append("evaluation_cases_changed")
    count = sum(s["count"] for name, s in after.get("suites", {}).items() if name != "regression")
    if count < min_count:
        reasons.append("insufficient_company_evaluations")
    for name, current in after.get("suites", {}).items():
        prior = before.get("suites", {}).get(name)
        score = current.get("score")
        if not isinstance(score, (int, float)) or not math.isfinite(score) or score < min_score:
            reasons.append(f"{name}:below_threshold")
        tolerance = max_general_regression if name == "regression" else max_regression
        if prior is None or score + tolerance < prior["score"]:
            reasons.append(f"{name}:regression")
    old_recall = before.get("kinds", {}).get("recall", {}).get("score")
    new_recall = after.get("kinds", {}).get("recall", {}).get("score")
    if (
        old_recall is None
        or new_recall is None
        or new_recall - old_recall + 1e-12 < min_recall_gain
    ):
        reasons.append("insufficient_recall_gain")
    old_wrong, new_wrong = before.get("confident_wrong_rate"), after.get("confident_wrong_rate")
    if (
        old_wrong is None
        or new_wrong is None
        or new_wrong > old_wrong + max_confident_wrong_increase + 1e-12
    ):
        reasons.append("confident_wrong_increased_or_missing")
    if "regression" not in after.get("suites", {}):
        reasons.append("general_evaluation_missing")
    return {"passed": not reasons, "reasons": reasons}
