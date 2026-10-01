# The contract

Four files connect the ML side (Arav) and the product side (Rithvik).
Each file has one writer. The other person only reads it.

| # | File | Writer → Reader | What it is |
|---|---|---|---|
| 1 | `.env` (shape in `.env.example`) | Arav → Rithvik | Where GM lives: an OpenAI-compatible endpoint |
| 2 | `results/results.json` | Arav → Rithvik | Benchmark scores for the Scoreboard |
| 3 | `results/night-run.json` | Arav → Rithvik | Status of one nightly retrain, for the Night view |
| 4 | Approved company Gbrain page | Rithvik → GM Nightly Loop | Fixes users approve with the "Correct this" button |

## `"mock": true`

The committed `results.json` and `night-run.json` are mock data with zeros.
Real runs write `"mock": false`.
**The UI must show a big "MOCK DATA" label when `mock` is true**, so no mock number ends up in a screenshot or the video.

## 1. GM endpoint

```
GM_BASE_URL=https://...   # from River
GM_MODEL=gm-v1
GM_API_KEY=               # real value only in .env
GM_BASE_MODEL=Qwen/Qwen3.5-9B
GM_CHECKPOINT=river://...  # Part 1 training checkpoint; consumed by GM Nightly Loop
GM_LORA_RANK=16            # adapter rank; must match Part 1
RIVER_API_KEY=             # used only by the company training host
```

Call it like any OpenAI chat endpoint: `POST {GM_BASE_URL}/chat/completions` with `model = GM_MODEL`.
Until GM is trained, these point at the untrained base model (hand-off at `0:50`).

`GM_BASE_MODEL`, `GM_CHECKPOINT`, and `GM_LORA_RANK` are the weight-training handoff between the two parts. The first company run evaluates and trains from that checkpoint. Later runs resume from the last promoted company checkpoint. `GM_MODEL` remains the serving name used by the Arena and QM.

## 2. `results/results.json`

- `tasks`: the task ids used as keys in `scores`.
- `models[]`: one entry per model. Names: `Claude`, `GPT`, `Base`, `GM`.
  - `prompt_tokens`: measured tokens of resolver/skill text in the prompt. GM gets none.
  - `scores[task]`: `accuracy` (0–1), `p50_latency_ms` (median), `cost_per_task_usd`.
- `garry_baselines`: Garry's own Opus / Sonnet / Haiku accuracy from `baseline-runs/`.

## 3. `results/night-run.json`

- `steps[]` always in this order: `collect`, `examples`, `train`, `gate`, `promote`.
- `status` is one of: `pending`, `running`, `done`, `failed`, `rolled_back`.
- `detail`: one short line of text for the UI.
- `before_after`: the corrected prompt, yesterday's GM answer, today's GM answer.

## 4. Approved correction page

The Arena writes the request pattern and approved behavior through its scoped
Gbrain connection. The page must use `visibility: brain-wide`, the
`finegrain-share` tag, and `finegrain_training: true`. Do not copy the rejected
model answer into the page.

```markdown
---
title: Approved correction
visibility: brain-wide
tags: ["finegrain-share"]
finegrain_training: true
---

Request pattern: ...
Approved company behavior: ...
```

`data/corrections.jsonl` may remain as an append-only UI audit receipt, but it is
not a training source. The company Gbrain page is authoritative.
