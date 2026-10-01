"""D1: score each model on held-out routing intents and write results/results.json.

Tasks:
  resolver-heldout      Garry's 5 held-out resolver fixtures.
  routing-eval-heldout  every GBrain routing-eval.jsonl intent whose answer is
                        one of our skills (all were kept out of training).

Models (skipped when their endpoint is not set in .env):
  Base + resolver  untrained base, full RESOLVER.md in the system prompt
  Base             untrained base, short routing stub only
  GM               trained model, short routing stub only

Per-case outputs go to results/bench-cases.jsonl so a human can read them.
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))
from leak_filter import LeakFilter, load_eval_intents, normalize  # noqa: E402
from make_routing import ROUTE_STUB  # noqa: E402

RESOLVER_DIR = "evals/functional-area-resolver"
BASELINE_RUNS = {  # Garry's receipts, scored on the variant his SKILL.md ships
    "opus": "2026-05-11-opus-4-7.jsonl",
    "sonnet": "2026-05-11-sonnet-4-6.jsonl",
    "haiku": "2026-05-11-haiku-4-5.jsonl",
}
BASELINE_VARIANT = "functional-areas"
MAX_TOKENS = 256  # reasoning is off, so a skill name fits easily
RETRIES = 3
RIVER_URL = "https://api.river.ai"
_river = None  # River client, created on first use
THINK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL | re.IGNORECASE)
SKILL_PATH = re.compile(r"^skills/([a-z0-9-]+)/skill\.md$")  # RESOLVER.md names skills by path


class BenchError(Exception):
    pass


def parse_answer(text: str, skill_names: set[str]) -> str:
    """Return the skill name the model answered, or the cleaned reply if it is not one."""
    text = THINK.sub("", text or "")
    line = next((l for l in text.splitlines() if l.strip()), "")
    cleaned = line.strip().strip("`*\"'.,:;!?()[]{} \t").lower()
    path = SKILL_PATH.match(cleaned)
    if path:
        cleaned = path.group(1)
    return cleaned if cleaned in skill_names else cleaned[:80]


def score(cases: list[dict]) -> dict:
    """cases have correct, latency_ms and cost_usd (None when the provider did not report it)."""
    costs = [c["cost_usd"] for c in cases]
    return {
        "accuracy": round(sum(c["correct"] for c in cases) / len(cases), 4),
        "p50_latency_ms": round(statistics.median(c["latency_ms"] for c in cases)),
        "cost_per_task_usd": None if None in costs else round(sum(costs) / len(costs), 6),
        "n": len(cases),
    }


def load_tasks(gbrain: Path, skill_names: set[str]) -> dict[str, list[dict]]:
    heldout = []
    for line in (gbrain / RESOLVER_DIR / "fixtures-held-out.jsonl").read_text().splitlines():
        if line.strip().startswith("{"):
            heldout.append(json.loads(line))

    answers = {}  # normalized intent -> set of expected skills, to drop contradictions
    first = {}
    for path in sorted(gbrain.rglob("routing-eval.jsonl")):
        if "examples" in path.relative_to(gbrain).parts:
            continue
        for line in path.read_text().splitlines():
            if not line.strip().startswith("{"):
                continue
            case = json.loads(line)
            key = normalize(case["intent"])
            answers.setdefault(key, set()).add(case["expected_skill"])
            first.setdefault(key, case)
    routing = [first[k] for k, skills in answers.items()
               if len(skills) == 1 and next(iter(skills)) in skill_names]
    return {"resolver-heldout": heldout, "routing-eval-heldout": routing}


def garry_baselines(gbrain: Path) -> dict:
    """Strict held-out accuracy from Garry's own receipts (exact slug, all seeds)."""
    out = {}
    for name, file in BASELINE_RUNS.items():
        rows = [json.loads(l) for l in (gbrain / RESOLVER_DIR / "baseline-runs" / file).read_text().splitlines()]
        runs = [r for r in rows if r.get("kind") == "run"
                and r["corpus"] == "held_out" and r["variant"] == BASELINE_VARIANT]
        out[name] = round(sum(r["correct"] for r in runs) / len(runs), 4)
    return out


def leak_count(training: Path, gbrain: Path) -> dict:
    texts = [next(m["content"] for m in json.loads(l)["messages"] if m["role"] == "user")
             for l in training.read_text().splitlines() if l.strip()]
    leak = LeakFilter(load_eval_intents(gbrain))
    return {"training_pairs": len(texts), "leaked": sum(leak.leaks(t) for t in texts)}


def endpoint(prefix: str) -> tuple[str, str, str] | None:
    checkpoint = os.environ.get(f"{prefix}_CHECKPOINT", "")
    if checkpoint:  # a River checkpoint, served from River's sampler
        return RIVER_URL, checkpoint, os.environ.get(f"{prefix}_BASE_MODEL", "Qwen/Qwen3.5-9B")
    url, model = os.environ.get(f"{prefix}_BASE_URL", ""), os.environ.get(f"{prefix}_MODEL", "")
    if not url.startswith("http") or "..." in url or not model:
        return None
    return url.rstrip("/") + "/chat/completions", model, os.environ.get(f"{prefix}_API_KEY", "")


def river_chat(ep: tuple[str, str, str], system: str, user: str) -> dict:
    global _river
    import river_client as river

    if _river is None:
        _river = river.Client(api_key=os.environ["RIVER_API_KEY"], timeout=120)
    _, checkpoint, base_model = ep
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(RETRIES):
        if attempt:
            time.sleep(2 ** attempt)
        start = time.perf_counter()
        result = _river.chat_complete_from_checkpoint(
            messages, checkpoint_path=checkpoint, base_model=base_model,
            max_tokens=MAX_TOKENS, temperature=0.0,
            # River's sampler thinks by default; GM is trained to answer directly
            chat_template_kwargs={"enable_thinking": False})
        latency = (time.perf_counter() - start) * 1000
        if result.status_code == 200:
            data = json.loads(result.response_json)
            usage = data.get("usage") or {}
            return {"text": data["choices"][0]["message"].get("content") or "",
                    "latency_ms": latency, "prompt_tokens": usage.get("prompt_tokens"),
                    "cost_usd": None, "provider": "river"}
        error = f"River HTTP {result.status_code}"
    raise BenchError(error)


def chat(ep: tuple[str, str, str], system: str, user: str) -> dict:
    if ep[0] == RIVER_URL:
        return river_chat(ep, system, user)
    url, model, key = ep
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": MAX_TOKENS,
        "usage": {"include": True},  # OpenRouter adds usage.cost; other providers ignore it
        # Qwen3.5 thinks by default and spends the whole budget on it. GM is trained to
        # answer directly, so every model answers directly.
        "reasoning": {"enabled": False},
    }).encode()
    request = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    for attempt in range(RETRIES):
        if attempt:
            time.sleep(2 ** attempt)
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.load(response)
            latency = (time.perf_counter() - start) * 1000
            usage = data.get("usage") or {}
            return {"text": data["choices"][0]["message"].get("content") or "",
                    "latency_ms": latency,
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "cost_usd": usage.get("cost"),
                    "provider": data.get("provider")}
        except urllib.error.HTTPError as exc:
            error = f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}"
            if exc.code != 429 and exc.code < 500:
                break
        except OSError as exc:
            error = f"cannot reach {url}: {exc}"
    raise BenchError(error)


def run_model(name: str, ep, system: str, tasks: dict, skill_names: set[str], workers: int):
    cases, scores = [], {}
    for task, fixtures in tasks.items():
        def one(fixture):
            reply = chat(ep, system, fixture["intent"])
            predicted = parse_answer(reply["text"], skill_names)
            return {"model": name, "task": task, "intent": fixture["intent"],
                    "expected": fixture["expected_skill"], "predicted": predicted,
                    "correct": predicted == fixture["expected_skill"], "raw": reply["text"],
                    "latency_ms": round(reply["latency_ms"]), "prompt_tokens": reply["prompt_tokens"],
                    "cost_usd": reply["cost_usd"], "provider": reply["provider"]}
        with ThreadPoolExecutor(workers) as pool:
            done = list(pool.map(one, fixtures))
        scores[task] = score(done)
        cases += done
        print(f"  {name} / {task}: {scores[task]['accuracy']:.1%} of {len(done)}")
    tokens = [c["prompt_tokens"] for c in cases if c["prompt_tokens"] is not None]
    providers = sorted({c["provider"] for c in cases if c["provider"]})
    entry = {"name": name, "model_id": ep[1], "served_via": urlparse(ep[0]).hostname,
             "providers": providers, "reasoning": "off",
             "prompt_tokens": round(statistics.median(tokens)) if tokens else None,
             "scores": scores}
    return entry, cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skills", type=Path, default=Path("data/skills.json"))
    parser.add_argument("--training", type=Path, default=Path("data/routing.jsonl"))
    parser.add_argument("--gbrain", type=Path, default=Path(os.environ.get("GBRAIN_DIR", "vendor/gbrain")))
    parser.add_argument("--out", type=Path, default=Path("results/results.json"))
    parser.add_argument("--cases", type=Path, default=Path("results/bench-cases.jsonl"))
    parser.add_argument("--models", default="Base + resolver,Base,GM",
                        help="comma list of model names to run")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    skills = json.loads(args.skills.read_text())
    skill_names = {s["name"] for s in skills["skills"]}
    configs = {
        "Base + resolver": ("BASE", skills["rules"]["resolver"] + "\n\n" + ROUTE_STUB),
        "Base": ("BASE", ROUTE_STUB),
        "GM": ("GM", ROUTE_STUB),
    }
    tasks = load_tasks(args.gbrain, skill_names)
    leaks = leak_count(args.training, args.gbrain)
    print(f"leak check: {leaks['leaked']} of {leaks['training_pairs']} training pairs match an eval intent")
    if leaks["leaked"]:
        print("error: eval intents leaked into training data, refusing to score", file=sys.stderr)
        return 1

    previous = json.loads(args.out.read_text()) if args.out.exists() else {}
    models = {m["name"]: m for m in previous.get("models", [])} if previous.get("mock") is False else {}
    old_cases = [json.loads(l) for l in args.cases.read_text().splitlines()] if args.cases.exists() else []
    all_cases = []
    for name in [n.strip() for n in args.models.split(",")]:
        prefix, system = configs[name]
        ep = endpoint(prefix)
        if ep is None:
            print(f"skip {name}: set {prefix}_CHECKPOINT, or {prefix}_BASE_URL and {prefix}_MODEL, in .env")
            continue
        try:
            models[name], cases = run_model(name, ep, system, tasks, skill_names, args.workers)
        except BenchError as exc:
            print(f"error: {name}: {exc}", file=sys.stderr)
            return 1
        all_cases += cases
    if not all_cases:
        print("error: no model was run, results unchanged", file=sys.stderr)
        return 1

    ran = {c["model"] for c in all_cases}
    all_cases = [c for c in old_cases if c["model"] not in ran and c["model"] in models] + all_cases
    order = list(configs)
    results = {
        "mock": False,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tasks": list(tasks),
        "task_sizes": {t: len(f) for t, f in tasks.items()},
        # share of cases whose answer is one of our skills; the rest no model here can hit
        "task_max_accuracy": {t: round(sum(c["expected_skill"] in skill_names for c in f) / len(f), 4)
                              for t, f in tasks.items()},
        "models": sorted(models.values(), key=lambda m: order.index(m["name"])),
        "garry_baselines": garry_baselines(args.gbrain),
        "garry_baselines_scoring": f"strict, held-out, {BASELINE_VARIANT} variant, 3 seeds",
        "leak_check": leaks,
    }
    args.out.write_text(json.dumps(results, indent=2) + "\n")
    args.cases.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in all_cases))
    print(f"wrote {args.out} and {args.cases}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
