# nightly-trainer

An open-source framework that turns a company's GBrain into a continuously updated fine-tuned model.

Every night (or week, or month), `nightly-trainer` reads what changed in GBrain, uses a strong teacher model to generate supervised fine-tuning (SFT) examples, reinforcement learning (RL) tasks, and evaluation questions from that material, trains a LoRA adapter on a hosted open-weight model through a training provider, evaluates the result against the previous model, and promotes the new checkpoint only if it measurably improves.

The first supported training provider is River AI. The provider layer is modular so that other services (Thinking Machines Tinker, the OpenAI fine-tuning platform, and others) can be added later without changing the rest of the pipeline.

---

## 1. Design principles

These principles are requirements, not suggestions. Every component must respect them.

1. **GBrain remains the source of truth for facts.** Fine-tuning is not used as a replacement for retrieval. Facts change, need corrections, and need citations; GBrain handles all of that. The model is trained to know *how the company works* and *when and how to consult GBrain*, not to memorize every fact.
2. **Train behavior, calibration, and conventions.** The training data targets: company terminology and conventions, recurring procedures, correct use of GBrain (looking things up, citing pages), and calibration (declining or looking up instead of guessing).
3. **Nothing enters the weights unless it is permitted to.** Only pages whose visibility allows every intended user of the model may be used for training. Private or restricted pages are excluded at collection time. Once information is in shared weights, it cannot be permission-filtered.
4. **No checkpoint is promoted without passing evaluation.** Every run produces a before-and-after report. A new checkpoint replaces the current one only if it passes the promotion gate (Section 8).
5. **Everything is reproducible and inspectable.** Each run writes its inputs, generated data, training configuration, and evaluation results to a dated run directory.
6. **Providers are pluggable.** Pipeline code never imports a provider SDK directly. It uses the `TrainingProvider` interface (Section 6).

---

## 2. Pipeline overview

```
            GBrain (markdown repo + index)
                        │
                        ▼
   ┌──────────────────────────────────────┐
   │ 1. COLLECT                           │
   │ Pages changed since last run,        │
   │ filtered by visibility allowlist     │
   └──────────────────┬───────────────────┘
                      ▼
   ┌──────────────────────────────────────┐
   │ 2. GENERATE (teacher model)          │
   │ SFT examples, RL tasks, eval items   │
   └──────────────────┬───────────────────┘
                      ▼
   ┌──────────────────────────────────────┐
   │ 3. TRAIN (TrainingProvider)          │
   │ LoRA SFT, then short RL phase        │
   └──────────────────┬───────────────────┘
                      ▼
   ┌──────────────────────────────────────┐
   │ 4. EVALUATE                          │
   │ Candidate vs. current vs. base model │
   └──────────────────┬───────────────────┘
                      ▼
   ┌──────────────────────────────────────┐
   │ 5. PROMOTE or REJECT                 │
   │ Promotion gate, report, registry     │
   └──────────────────────────────────────┘
```

Data generation runs locally (on a laptop or server). Training and sampling of the student model run remotely on the training provider.

---

## 3. Repository layout

```
nightly-trainer/
  README.md
  pyproject.toml
  config.example.yaml
  src/nightly_trainer/
    cli.py                    # entry point: `nt run`, `nt eval`, `nt schedule`
    config.py                 # loads and validates config.yaml
    collect/
      gbrain_source.py        # reads changed GBrain pages, applies visibility filter
      session_source.py       # (stretch) reads Claude Code / Codex session logs
    generate/
      teacher.py              # wrapper around the teacher model used for generation
      sft.py                  # builds SFT examples
      rl_tasks.py             # builds RL tasks with reward specifications
      evals.py                # builds held-out evaluation items
      dedupe.py               # removes near-duplicates and leakage between splits
    rewards/
      recall.py               # correctness against a reference answer
      abstention.py           # rewards declining on unanswerable questions
      staleness.py            # rewards current facts over superseded ones
      citation.py             # rewards citing the correct GBrain page
      judge.py                # LLM-judge helper used by the reward functions
    providers/
      base.py                 # TrainingProvider interface and shared types
      river.py                # River AI implementation
    evaluate/
      runner.py               # runs eval items against one or more models
      report.py               # writes the before/after report (markdown + JSON)
    promote.py                # promotion gate and model registry
    schedule.py               # installs cron / launchd entries
  fixtures/
    brain/                    # small sample GBrain (markdown pages) for development and demo
  runs/                       # created at runtime, one directory per run
  tests/
```

Language: Python 3.12 or newer (required by `river-client`).

---

## 4. Collect

### 4.1 GBrain pages

GBrain stores knowledge as markdown files in a git repository, indexed into a database. The simplest reliable way to find what changed is git:

```bash
git -C "$BRAIN_REPO" log --since="$LAST_RUN_ISO" --name-only --pretty=format: -- '*.md' | sort -u
```

For each changed file, `gbrain_source.py` must produce:

```json
{
  "page_id": "concepts/deploy-freeze-policy",
  "path": "concepts/deploy-freeze-policy.md",
  "title": "Deploy freeze policy",
  "type": "concept",
  "content": "...full markdown...",
  "previous_content": "...content at last run, or null if new...",
  "sources": ["meetings/2026-09-20-eng-sync"],
  "visibility": "brain-wide",
  "updated_at": "2026-09-27T01:12:00Z"
}
```

`previous_content` is required: it is how staleness tasks are generated (a fact that changed).

GBrain can also be queried through its CLI (`gbrain search`, `gbrain think`) or its MCP memory verbs (`recall`, `remember`, `entity`, `synthesize`, `forget`, `context_pack`, `delta`). Use these where the git view is insufficient, for example to retrieve linked pages as context. Agents must verify exact command flags against the installed GBrain version (`gbrain --help`) rather than guessing.

### 4.2 Visibility filter

Configured in `config.yaml`:

```yaml
collect:
  brain_repo: ~/brain
  include_visibility: [brain-wide]
  exclude_paths: ["personal/**", "hr/**", "compensation/**"]
```

A page that fails the filter is never passed to generation. Log excluded page counts (not content) in the run report.

### 4.3 Agent sessions (stretch goal)

Claude Code and Codex store local session logs. `session_source.py` extracts user requests and the final successful approach, to generate procedure tasks (Section 5.4). Log locations differ by tool and version; agents must locate and confirm them on the machine rather than hard-coding assumed paths. Sessions pass through the same exclusion rules, plus a secret scrubber (API keys, tokens, emails).

---

## 5. Generate

A strong teacher model generates all training and evaluation data. The teacher may be a large model hosted on River (sampled through the provider interface) or any other configured model. The student is the smaller model being trained.

For every changed page, the generator produces items of the following types. Every item carries `page_id` provenance.

### 5.1 Recall

Questions answerable from the page.

```json
{
  "id": "recall-000123",
  "kind": "recall",
  "prompt": "During a deploy freeze, who can approve an emergency production deploy?",
  "reference": "Only the on-call engineering manager, and the approval must be posted in #deploys.",
  "page_id": "concepts/deploy-freeze-policy"
}
```

### 5.2 Abstention

Plausible questions whose answers are **not** in GBrain. The correct behavior is to state that the information is not known, or to indicate it should be looked up, rather than inventing an answer.

```json
{
  "id": "abstain-000045",
  "kind": "abstention",
  "prompt": "What is the deploy freeze policy for the Singapore office?",
  "reference": null,
  "page_id": "concepts/deploy-freeze-policy",
  "note": "Page covers only the US policy."
}
```

### 5.3 Staleness

Generated only when `previous_content` differs materially from `content`. The question targets the changed fact; the reference is the new value, and the superseded value is recorded so the reward can penalize it.

```json
{
  "id": "stale-000012",
  "kind": "staleness",
  "prompt": "How long does the Friday deploy freeze last?",
  "reference": "From 2pm Friday until 9am Monday.",
  "superseded": "From 5pm Friday until 9am Monday.",
  "page_id": "concepts/deploy-freeze-policy"
}
```

### 5.4 Procedure and conventions

Tasks that test whether the model follows the company's way of doing something (naming conventions, document formats, review steps). Generated from procedure-like pages and, if enabled, from agent sessions.

### 5.5 Output files

```
runs/<run_id>/data/
  sft.jsonl          # chat-format examples for SFT
  rl_tasks.jsonl     # RL tasks with kind, prompt, reference, reward spec
  eval.jsonl         # held-out evaluation items (never used in training)
  generation_log.json
```

SFT format:

```json
{"messages": [
  {"role": "system", "content": "You are the company assistant. ..."},
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."}
], "page_id": "...", "kind": "recall"}
```

### 5.6 Generation rules

1. Every reference answer must be directly supported by the page text. The generator runs a second teacher pass that checks support and discards unsupported items.
2. `eval.jsonl` is split off **before** SFT and RL data are produced, and `dedupe.py` removes eval items that are near-duplicates of any training item. Without this, evaluation results are meaningless.
3. Target mix for the hackathon: roughly 50% recall, 20% abstention, 15% staleness, 15% procedure. Configurable.
4. Paraphrase each question several ways so the model learns the knowledge, not a single phrasing.

---

## 6. Train: provider interface

All training goes through this interface in `providers/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

@dataclass
class ModelRef:
    provider: str
    base_model: str
    checkpoint: str | None   # None means the untrained base model

@dataclass
class TrainResult:
    model: ModelRef
    metrics: dict             # loss curves, reward curves, token counts, cost

RewardFn = Callable[[dict, str], float]   # (task, completion) -> reward in [0, 1]

class TrainingProvider(ABC):
    name: str

    @abstractmethod
    def list_base_models(self) -> list[str]: ...

    @abstractmethod
    def sample(self, model: ModelRef, prompts: list[list[dict]],
               max_tokens: int = 512, temperature: float = 0.0) -> list[str]: ...

    @abstractmethod
    def train_sft(self, base: ModelRef, examples_path: str,
                  lora_rank: int, epochs: int, learning_rate: float) -> TrainResult: ...

    @abstractmethod
    def train_rl(self, start: ModelRef, tasks_path: str, reward_fn: RewardFn,
                 steps: int, group_size: int, learning_rate: float) -> TrainResult: ...
```

### 6.1 River implementation (`providers/river.py`)

Install the client:

```bash
pip install river-client
```

Known facts about the River client (from its public documentation):

- It is a Python client for sampling, LoRA fine-tuning, and RL against River-hosted open-weight models.
- It exposes low-level primitives (forward-backward passes, optimizer steps, sampling, checkpoint save and resume) and an integrated RL library that manages rollouts from your environment and reward function.
- SFT uses the `cross_entropy` loss with per-token weights (set prompt tokens to 0.0, completion tokens to 1.0). RL losses include `importance_sampling`, `ppo`, `cispo`, and `dro`.
- LoRA rank is configurable from 1 to 32.
- Access to base models is granted per API key.

Minimal connectivity check:

```python
import os
import river_client as river

client = river.Client(api_key=os.environ["RIVER_API_KEY"])
print("healthy:", client.health_check())
for name in client.get_capabilities():
    print(name)
```

**Instruction for agents:** the `river-client` package bundles its own agent skill (a `SKILL.md` describing the current training API, data formats, and SFT/RL loop patterns), matched to the installed version. Install and read that skill before writing `providers/river.py`. Do not guess method names or signatures beyond the connectivity check above; use the bundled skill and https://docs.river.ai as the authority.

Model choice for the hackathon: the smallest base model available to the team's API key, to keep training time short. Confirm availability with `get_capabilities()`.

---

## 7. Rewards

Each reward function returns a value in `[0, 1]`.

| Kind | Reward logic |
|---|---|
| recall | 1.0 if the completion is judged equivalent to `reference`; partial credit allowed; bonus if it cites the correct `page_id`. |
| abstention | 1.0 if the completion declines or says it would look this up; 0.0 if it states a specific answer. |
| staleness | 1.0 if it gives the current value; 0.0 if it gives `superseded` (heavily penalized, since that is a confident wrong answer). |
| procedure | Judge score against the page's described procedure or convention. |

`rewards/judge.py` wraps the teacher model as a grader with a fixed rubric prompt and temperature 0. Use exact or normalized string matching first where possible (numbers, names, dates) and fall back to the judge only when needed, to reduce cost and noise.

---

## 8. Evaluate and promote

`evaluate/runner.py` runs `eval.jsonl` against three models:

1. the untrained base model,
2. the currently promoted company model (if any),
3. the new candidate checkpoint.

Metrics per model, reported overall and per kind:

- **Recall accuracy**: fraction of recall items answered correctly.
- **Confident-wrong rate**: fraction of items where the model gave a specific, incorrect answer. This is the most important safety metric.
- **Abstention accuracy**: fraction of unanswerable items correctly declined.
- **Staleness accuracy**: fraction of changed facts answered with the current value.
- **General capability check**: a small fixed set of general questions (reasoning, coding, writing) to detect regression. The set lives in `fixtures/general_eval.jsonl` and never changes between runs.

Promotion gate (defaults, configurable):

```yaml
promote:
  min_recall_gain: 0.05            # candidate must beat current by at least 5 points
  max_confident_wrong_increase: 0.0
  max_general_regression: 0.03
```

If the gate passes, `promote.py` records the checkpoint as current in `runs/registry.json`. If it fails, the run is kept for inspection and the current model is unchanged. Either way, `report.py` writes `runs/<run_id>/report.md`.

---

## 9. Scheduling

```yaml
schedule:
  frequency: nightly      # nightly | weekly | monthly
  time: "02:00"
```

`nt schedule install` writes a cron entry (Linux) or launchd plist (macOS) that runs `nt run`. Each run records `last_run` so the next run collects only new changes. A run with no changed pages exits early without training.

---

## 10. Configuration example

```yaml
provider:
  name: river
  api_key_env: RIVER_API_KEY
  student_model: "<smallest model available to your key>"
  teacher_model: "<largest model available to your key>"
  lora_rank: 16

collect:
  brain_repo: ./fixtures/brain
  include_visibility: [brain-wide]
  exclude_paths: ["personal/**", "hr/**"]

generate:
  questions_per_page: 8
  paraphrases_per_question: 3
  mix: {recall: 0.5, abstention: 0.2, staleness: 0.15, procedure: 0.15}
  eval_fraction: 0.2

train:
  sft: {epochs: 2, learning_rate: 1.0e-4}
  rl:  {enabled: true, steps: 20, group_size: 4, learning_rate: 5.0e-6}

promote:
  min_recall_gain: 0.05
  max_confident_wrong_increase: 0.0
  max_general_regression: 0.03

schedule:
  frequency: nightly
  time: "02:00"
```

---

## 11. Hackathon scope

### 11.1 Minimum viable demo (must work)

1. A fixture brain of 15 to 30 markdown pages about a fictional company, including at least 5 pages with a `previous_content` version (to produce staleness items).
2. Collect, then generate SFT data and eval items with the teacher model.
3. One SFT run on River with the smallest available student model.
4. Evaluation of base vs. candidate, producing `report.md` with the metrics in Section 8.

### 11.2 Strong demo (target)

Everything above, plus a short RL phase using the recall, abstention, and staleness rewards, and a three-way comparison (base, SFT only, SFT plus RL).

### 11.3 Out of scope for the hackathon

Agent session ingestion, additional providers, scheduling installers, and multi-user permission modeling beyond the path-based exclusion list. Keep the interfaces in place so these can be added later.

### 11.4 Suggested parallel work split

| Workstream | Owner | Deliverable |
|---|---|---|
| A. Fixture brain + collect | Agent 1 | `fixtures/brain/`, `collect/gbrain_source.py` |
| B. Generation + dedupe | Agent 2 | `generate/*`, `data/*.jsonl` for the fixture |
| C. River provider | Agent 3 | `providers/river.py`, SFT run working end to end |
| D. Rewards + evaluation + report | Agent 4 | `rewards/*`, `evaluate/*`, `report.md` |

Workstream C should start first, since River access, model availability, and training time are the largest unknowns. Workstreams A and B agree on the page JSON schema (Section 4.1) and item schemas (Section 5) before starting. Workstream D can develop against hand-written eval items and base-model sampling before any training finishes.

### 11.5 Demo script

1. Show the fixture brain and a changed page (the deploy freeze moved from 5pm to 2pm).
2. Ask the base model three questions: one answerable, one unanswerable, one about the changed fact. It guesses or answers incorrectly.
3. Run `nt run` (or show the run that was started earlier, if training takes longer than the presentation slot).
4. Show `report.md`: recall up, confident-wrong rate down, abstention up, general capability unchanged, gate passed.
5. Ask the promoted model the same three questions.

---

## 12. Rules for agents working in this repository

1. Do not invent APIs. For River, use the bundled `river-client` skill and https://docs.river.ai. For GBrain, use `gbrain --help` and the GBrain repository documentation.
2. Never send pages excluded by the visibility filter to any model, including the teacher.
3. Never let eval items leak into training data. `dedupe.py` must run before training.
4. Keep provider-specific code inside `providers/`.
5. Write every intermediate artifact to `runs/<run_id>/` so any result can be traced to its inputs.
6. Log token usage and cost per stage in `runs/<run_id>/generation_log.json` and the training metrics.
7. Prefer small, working end-to-end steps over complete but untested components. The minimum viable demo in Section 11.1 takes priority over everything else.

---

## License

MIT (proposed).
