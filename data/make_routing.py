"""C2: build routing pairs (request -> skill name) in data/routing.jsonl.

For each skill, the open teacher writes new wordings of its triggers. The
real triggers are kept too. Every wording that matches an eval intent is
dropped, and the drop count is saved so the README can show it.
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from leak_filter import LeakFilter, load_eval_intents, normalize
from teacher import Teacher, TeacherError, extract_json

ROUTE_STUB = "Route this request to one GBrain skill. Reply with the skill name only."
TEACHER_SYSTEM = (
    "You write realistic requests that a busy founder types to their AI assistant. "
    "Reply with a JSON array of strings and nothing else."
)


def teacher_prompt(skill: dict, count: int) -> str:
    triggers = "\n".join(f"- {t}" for t in skill["triggers"])
    return (
        f"Skill: {skill['name']}\n"
        f"What it does: {skill['description']}\n"
        f"Trigger phrases:\n{triggers}\n\n"
        f"Write {count} different requests a user might type that should run this skill. "
        "Vary length, tone and detail: some terse, some with a concrete person, company "
        "or document named, some casual. Do not copy the trigger phrases word for word."
    )


def ask_wordings(teacher: Teacher, skill: dict, count: int) -> list[str]:
    for _ in range(3):
        try:
            reply = extract_json(teacher.chat(TEACHER_SYSTEM, teacher_prompt(skill, count)))
        except TeacherError as exc:
            print(f"  {skill['name']}: {exc}", file=sys.stderr)
            continue
        if isinstance(reply, list):
            return [w.strip() for w in reply if isinstance(w, str) and w.strip()]
    print(f"  {skill['name']}: no usable wordings after 3 tries, keeping its triggers only",
          file=sys.stderr)
    return []


def pair(text: str, skill: str, source: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": ROUTE_STUB},
            {"role": "user", "content": text},
            {"role": "assistant", "content": skill},
        ],
        "task": "routing",
        "source": source,
    }


def build_pairs(candidates: list[tuple[str, str, str]], leak: LeakFilter) -> tuple[list[dict], dict]:
    """candidates = (text, skill, source). Returns kept pairs and counts.

    A wording listed under two different skills is ambiguous, so it is dropped
    instead of teaching the model two answers for one input.
    """
    skills_for = {}
    for text, skill, _ in candidates:
        skills_for.setdefault(normalize(text), set()).add(skill)

    kept, seen = [], set()
    stats = {"candidates": len(candidates), "leaked": 0, "ambiguous": 0, "duplicate": 0}
    for text, skill, source in candidates:
        key = normalize(text)
        if not key:
            continue
        if len(skills_for[key]) > 1:
            stats["ambiguous"] += 1
        elif key in seen:
            stats["duplicate"] += 1
        elif leak.leaks(text):
            stats["leaked"] += 1
        else:
            seen.add(key)
            kept.append(pair(text, skill, source))
    stats["kept"] = len(kept)
    return kept, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skills", type=Path, default=Path("data/skills.json"))
    parser.add_argument("--gbrain", type=Path, default=Path(os.environ.get("GBRAIN_DIR", "vendor/gbrain")))
    parser.add_argument("--out", type=Path, default=Path("data/routing.jsonl"))
    parser.add_argument("--stats", type=Path, default=Path("data/routing-stats.json"))
    parser.add_argument("--per-skill", type=int, default=20)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    try:
        teacher = Teacher.from_env()
    except TeacherError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    skills = json.loads(args.skills.read_text())["skills"]
    eval_intents = load_eval_intents(args.gbrain)

    with ThreadPoolExecutor(args.workers) as pool:
        wordings = list(pool.map(lambda s: ask_wordings(teacher, s, args.per_skill), skills))

    candidates = []
    for skill, generated in zip(skills, wordings):
        candidates += [(t, skill["name"], "trigger") for t in skill["triggers"]]
        candidates += [(w, skill["name"], "teacher") for w in generated]

    pairs, stats = build_pairs(candidates, LeakFilter(eval_intents))
    stats.update(eval_intents=len(eval_intents), skills=len(skills), teacher_model=teacher.model,
                 skills_without_wordings=[s["name"] for s, w in zip(skills, wordings) if not w])

    args.out.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs))
    args.stats.write_text(json.dumps(stats, indent=2) + "\n")
    print(f"wrote {args.out}: {stats['kept']} pairs "
          f"({stats['leaked']} removed as eval leaks, {stats['ambiguous']} ambiguous, "
          f"{stats['duplicate']} duplicates)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
