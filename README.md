# Finegrain

**"GBrain gets better the more it's used. Every correction your team makes becomes training data, and Finegrain improves overnight."**

Finegrain is an open-weight model compiled from [GBrain](https://github.com/garrytan/gbrain)'s skills. It has two parts: Part 1 teaches the model how to use a brain; **Finegrain Nightly Loop** teaches it how your company works.

Facts stay in GBrain. Finegrain's weights hold skills, company procedures, and the judgment to look facts up instead of guessing.

## Finegrain vs. the base model vs. Claude

**Task:** read a request and pick the right GBrain skill. **Test:** 283 held-out intents from GBrain's own `routing-eval.jsonl` files, none of them in training.

| Model | What is in the prompt | Prompt tokens | Accuracy |
|---|---|---:|---:|
| Base `Qwen3.5-9B` | a one-line instruction | 45 | **1.8%** |
| Base `Qwen3.5-9B` + GBrain | all of `RESOLVER.md` | 5,109 | **88.0%** |
| **Finegrain v1** (GBrain in the weights) | **the same one-line instruction** | **45** | **84.5%** |
| Claude + GBrain | GBrain's resolver | — | not run on this test¹ |

**Finegrain matches 96% of the base model's accuracy with GBrain's rules, from a prompt 113× smaller.**

¹ We had no Claude key at the hackathon. Garry's own receipts on his 5-case held-out set (`evals/functional-area-resolver`) put Claude Opus at 86.7% and Sonnet and Haiku at 100%. That is a different, smaller test. On it, Finegrain scores 40% and the base model with GBrain scores 60%, the most any model can score with GBrain's 75 skills.

## Part 1 results

Finegrain v1 is `Qwen/Qwen3.5-9B` with a rank-16 LoRA, trained on River for 118 steps (2 epochs, 1,872 routing pairs, 591 s). The task: read a request and name the one GBrain skill that should handle it. The test is 283 held-out intents from GBrain's own `skills/*/routing-eval.jsonl` files. None of them are in the training data (leak check: 0 of 2,079 pairs).

Training took the same model from 1.8% to 84.5% on the table at the top.

Notes:
- Every model answers directly (thinking off). The base runs on OpenRouter and Finegrain on River's checkpoint sampler, so their latencies are not comparable and are left out here. `results/results.json` has the raw values.
- Garry's own 5-case held-out set (`evals/functional-area-resolver`) has 2 answers that are not among GBrain's 75 skills, so no model here can score above 60% on it. Finegrain scores 40%, and the base model with the rules scores 60%. For reference, Garry's receipts put Opus at 86.7% and Sonnet and Haiku at 100% on that set.
- Reproduce: `make train` trains Finegrain and writes `train/gm-checkpoint.json`; `make bench` scores every model and writes `results/results.json` and `results/bench-cases.jsonl` (one line per answer).

## How the two parts connect

1. **Finegrain Foundation** compiles GBrain's routing, filing, formatting, and citation skills into a model once.
2. **Finegrain Nightly Loop** turns approved company knowledge and corrections into SFT data, RL tasks, and held-out evaluations. It trains from the Finegrain Foundation checkpoint through River and promotes the candidate only when it passes the quality gate.

```text
GBrain skills ──train once──▶ Finegrain Foundation
                                  │
Approved company GBrain pages ───┴──▶ SFT + RL + evals
                                              │
                                           River
                                              │
                                     promotion gate
                                              │
                                  Company Finegrain
```

Company facts remain in GBrain, where they can be updated, deleted, cited, and permissioned. The nightly loop trains durable procedures and conventions while teaching the model when to consult GBrain or admit that the answer is unknown.

## Try it in one command

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), and Git.

```bash
git clone https://github.com/edreisMD/finegrain.git
cd finegrain
make quickstart
```

This command:

- compiles GBrain's skills for Finegrain Foundation;
- runs both test suites;
- generates a complete SFT, RL, and evaluation dataset from fictional company pages;
- uses no credentials and submits nothing for training.

The generated demo includes four task families:

| Task | What it tests |
|---|---|
| Recall | Answer a question grounded in a current GBrain page |
| Abstention | Decline when company knowledge does not support an answer |
| Staleness | Use the newest value after a company fact changes |
| Procedure | Follow a company-specific convention or workflow |

Useful commands:

```bash
make data         # compile GBrain skills for Part 1
make pairs        # write routing + behavior training pairs (needs the teacher keys in .env)
make train        # train Finegrain on River, write train/gm-checkpoint.json (needs RIVER_API_KEY)
make bench        # score Base, Base + resolver and Finegrain on held-out routing tests
make test         # test the root Finegrain contracts
make part2-demo   # build the credential-free company dataset
make part2-test   # test Finegrain Nightly Loop
make night        # run one real company adaptation cycle
```

## Run one real company night

Finegrain Nightly Loop requires the checkpoint created by Part 1. The base model and LoRA rank must match on both sides of the handoff.

```bash
export RIVER_API_KEY=...
export GM_BASE_MODEL=Qwen/Qwen3.5-9B
export GM_CHECKPOINT=river://...   # produced by Finegrain Foundation
export GM_LORA_RANK=16             # must match Part 1

make night
```

The first run evaluates and trains from `GM_CHECKPOINT`. Later runs resume from the last promoted company checkpoint and include replay data. The committed result files contain mock data until a real run writes `"mock": false`.

The default teacher is `nvidia/Kimi-K2.6-NVFP4`, the independent critic is `nvidia/GLM-5.2-NVFP4`, and the student is `Qwen/Qwen3.5-9B`. Change these in `night/gm-nightly-loop/examples/gm-part2.toml` and use `gm-nightly models` to verify the models available in your River account.

## Install it for a company

Finegrain uses GBrain's existing personal and company-brain installations. The framework adds local session capture, approved-page relay, dataset generation, River training, and evaluation.

```text
Claude / Codex / Pi / JSONL agents
                 │
          employee's Mac
                 │
       personal GBrain compiles
       approved notes locally
                 │
      approved compiled pages only
                 │
         company GBrain
                 │
   Finegrain Nightly Loop + River
```

Raw session traces stay on the employee's Mac. Only compiled pages that satisfy the sharing policy reach the company GBrain. River credentials stay on the company training host.

### 1. Install the company server

Requirements: Docker with Compose, Python 3, and a River account.

```bash
cd night/gm-nightly-loop
./scripts/install-server.sh
```

The guided installer creates private settings under `.gm/deployment/` and starts:

- the official GBrain company dashboard at `http://localhost:3131/admin/`;
- the Finegrain Nightly Loop console at `http://localhost:8787`;
- Postgres with pgvector on the internal Docker network.

The default schedule is nightly at 02:00 UTC. `nightly`, `weekly`, `monthly`, `manual`, and `once` are supported. Configure cadence and time zone in `.gm/deployment/.env` before the first startup, or edit the generated training profile afterward.

Already have a company GBrain? Keep it and point Finegrain Nightly Loop at its existing profile:

```bash
cd night/gm-nightly-loop
uv tool install --python 3.12 '.[river]'
gm-nightly server install \
  --company acme \
  --gbrain-home /srv/company-profile \
  --company-url https://brain.acme.example \
  --source shared \
  --output gm-nightly.server.toml
gm-nightly --config gm-nightly.server.toml server serve
```

### 2. Invite employees

Create one scoped GBrain credential per employee:

```bash
cd night/gm-nightly-loop
./scripts/invite.sh alice
./scripts/invite.sh bob
./scripts/invite.sh carol
```

The private handoffs appear in `.gm/invites/`. Send each employee only their own file through a private channel.

### 3. Install the Mac companion

Requirements: macOS 13+, Bun, uv, and Xcode Command Line Tools.

```bash
cd night/gm-nightly-loop
./scripts/install-employee.sh \
  --company acme \
  --employee-id alice \
  --company-url https://brain.acme.example \
  --credentials ~/Downloads/alice.json \
  --share-project ~/work/acme
```

Run the command without arguments for guided onboarding. It reuses the employee's personal GBrain, creates a separate company connection, verifies OAuth, installs the `gm-nightly` command, and opens the native menu-bar app.

No River key is installed on employee Macs. Only selected project paths are eligible for sharing; an empty selection shares nothing automatically. The companion supports Claude, Codex, Pi, and a documented generic JSONL format.

## What happens during a cycle

1. Read new or changed approved pages from the company GBrain.
2. Split source groups before generation so evaluation questions cannot leak into training.
3. Ask the River teacher to create grounded SFT examples and verifiable RL tasks.
4. Ask an independent critic to check evidence, answerability, and leakage.
5. Build held-out recall, abstention, staleness, procedure, and regression suites.
6. Train the student with SFT and the bounded GBrain lookup RL environment.
7. Compare the candidate with the current model.
8. Promote only when recall improves without more confident errors or unacceptable regressions.

Each run preserves its inputs, splits, generated records, critic decisions, checkpoints, scores, rejection reasons, and inspection report. A failed gate keeps the current company model in service.

## Repository map

```text
data/                         Part 1 GBrain skill compiler
results/                      Shared product/ML result contracts
night/run.py                  Root wrapper for one real cycle
night/gm-nightly-loop/
  apps/macos/                 Native menu-bar companion
  deploy/                     GBrain, Postgres, and trainer stack
  scripts/                    Employee and server installers
  src/gm_nightly/             Capture, relay, generation, training, and gates
  tests/                      Nightly-loop verification suite
```

Read [CONTRACT.md](CONTRACT.md) for the files shared by the product and model sides. The deeper [Finegrain Nightly Loop guide](night/gm-nightly-loop/README.md) documents capture rules, provider configuration, dataset artifacts, scheduling, and operational limits.

MIT License.
