"""Keep every eval intent out of the training data.

The test set is Garry's resolver fixtures plus every routing-eval.jsonl in
GBrain. If a training wording matches one of them (exactly or nearly), the
model has seen the test answer and the benchmark is fake.
"""

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

FIXTURES = (
    "evals/functional-area-resolver/fixtures.jsonl",
    "evals/functional-area-resolver/fixtures-held-out.jsonl",
)
NEAR_DUPLICATE = 0.85


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def read_intents(path: Path) -> list[str]:
    intents = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        intents.append(json.loads(line)["intent"])
    return intents


def load_eval_intents(gbrain_dir: Path) -> list[str]:
    paths = [gbrain_dir / f for f in FIXTURES]
    paths += [p for p in sorted(gbrain_dir.rglob("routing-eval.jsonl"))
              if "examples" not in p.relative_to(gbrain_dir).parts]
    seen, intents = set(), []
    for path in paths:
        for intent in read_intents(path):
            key = normalize(intent)
            if key not in seen:
                seen.add(key)
                intents.append(intent)
    return intents


class LeakFilter:
    def __init__(self, eval_intents: list[str], threshold: float = NEAR_DUPLICATE):
        self.eval = [normalize(i) for i in eval_intents]
        self.exact = set(self.eval)
        self.threshold = threshold

    def leaks(self, text: str) -> bool:
        candidate = normalize(text)
        if candidate in self.exact:
            return True
        matcher = SequenceMatcher(a=candidate, autojunk=False)
        for intent in self.eval:
            matcher.set_seq2(intent)
            # quick_ratio is a cheap upper bound, so most pairs skip the full ratio
            if matcher.quick_ratio() >= self.threshold and matcher.ratio() >= self.threshold:
                return True
        return False
