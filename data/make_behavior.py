"""C3: build behavior pairs (raw note -> filed GBrain page) in data/behavior.jsonl.

The teacher sees GBrain's filing, output and page-format rules in its own
prompt. The training pair does not: GM gets only the raw note and a short
stub, so it has to learn the rules into its weights. Only pages that pass
page_checker are kept.
"""

import argparse
import json
import os
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from page_checker import check_page
from teacher import Teacher, TeacherError

FILE_STUB = "File this into the brain. Reply with the page path and the page."
NOTE_KINDS = [
    "meeting notes typed fast during a call", "a forwarded email thread", "a tweet thread",
    "a voice memo transcript", "notes from reading an article", "notes from a book chapter",
    "a founder's pitch call notes", "a one-line idea jotted on a phone",
]
GIVE_UP_AFTER = 40
SUBJECTS = [
    "a person the user just met", "an early-stage startup", "a public company",
    "a reusable mental model or framework", "a policy issue", "a book",
    "an investment deal in progress", "the user's own original idea",
]
NOTE_SYSTEM = "You write realistic raw notes. Reply with the note text only, no preamble."
PAGE_FORMAT = """Reply in exactly this shape and nothing else:

File: <folder>/<slug>.md
---
<YAML frontmatter with at least type and title>
---
<compiled truth: ## sections, current synthesis>

<!-- timeline -->

## Timeline

- **YYYY-MM-DD** | <what happened> [Source: ...]

Rules you must follow:
- Write exactly one page: the page for the note's primary subject.
- Every paragraph and list item carries an inline [Source: ...] citation,
  including the Executive Summary. A list item that is only links needs none.
- Link every person, company and concept you mention as [Title](folder/slug.md).
- Use real dates from the note. Never write a placeholder.
"""


def note_prompt(rng: random.Random) -> str:
    return (
        f"Write {rng.choice(NOTE_KINDS)} whose main subject is {rng.choice(SUBJECTS)}. "
        f"Date it 2026-{rng.randint(1, 9):02d}-{rng.randint(1, 28):02d}. Invent specific names, "
        "numbers and quotes. Mention at least one other person or company. 80 to 250 words. "
        "Keep it messy the way real notes are."
    )


def page_system(gbrain_dir: Path, rules: dict) -> str:
    guide = (gbrain_dir / "docs/guides/compiled-truth.md").read_text()
    return (
        "You file raw notes into a GBrain knowledge base. Follow these rules exactly.\n\n"
        f"{rules['filing_rules']}\n\n{rules['output_rules']}\n\n{guide}\n\n{PAGE_FORMAT}"
    )


def pair(note: str, page: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": FILE_STUB},
            {"role": "user", "content": note},
            {"role": "assistant", "content": page},
        ],
        "task": "behavior",
    }


def attempt(teacher: Teacher, system: str, seed: int) -> tuple[dict | None, str]:
    """One try: write a note, file it, check it. Returns (pair or None, reason)."""
    try:
        note = teacher.chat(NOTE_SYSTEM, note_prompt(random.Random(seed))).strip()
        page = teacher.chat(system, note, temperature=0.3).strip()
    except TeacherError as exc:
        return None, f"teacher error: {exc}"
    page = page.removeprefix("```markdown").removeprefix("```").removesuffix("```").strip()
    problems = check_page(page)
    if problems:
        return None, problems[0]
    return pair(note, page), "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skills", type=Path, default=Path("data/skills.json"))
    parser.add_argument("--gbrain", type=Path, default=Path(os.environ.get("GBRAIN_DIR", "vendor/gbrain")))
    parser.add_argument("--out", type=Path, default=Path("data/behavior.jsonl"))
    parser.add_argument("--target", type=int, default=200)
    parser.add_argument("--max-attempts", type=int, default=400)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    try:
        teacher = Teacher.from_env()
    except TeacherError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    system = page_system(args.gbrain, json.loads(args.skills.read_text())["rules"])

    kept, rejected = [], {}
    seed = 0
    with ThreadPoolExecutor(args.workers) as pool:
        while len(kept) < args.target and seed < args.max_attempts:
            batch = range(seed, min(seed + args.workers, args.max_attempts))
            seed = batch.stop
            for result, reason in pool.map(lambda s: attempt(teacher, system, s), batch):
                if result:
                    kept.append(result)
                else:
                    key = re.sub(r"\d+", "N", reason.split(",")[0])
                    rejected[key] = rejected.get(key, 0) + 1
            print(f"  {len(kept)} kept / {seed} tried", file=sys.stderr)
            if not kept and seed >= GIVE_UP_AFTER:
                print(f"error: 0 of {seed} pages passed the checker; stopping to save credits",
                      file=sys.stderr)
                break

    kept = kept[:args.target]
    args.out.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in kept))
    print(f"wrote {args.out}: {len(kept)} pairs from {seed} tries")
    for reason, count in sorted(rejected.items(), key=lambda r: -r[1]):
        print(f"  rejected {count}: {reason}")
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())
