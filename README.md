# Finegrain

**Finegrain turns approved company knowledge into training data and a continuously improving company model.**

Finegrain reads new and changed pages from [GBrain](https://github.com/garrytan/gbrain), generates grounded supervised fine-tuning examples, reinforcement-learning tasks, and held-out evaluations, then trains the model through River. A candidate becomes current only when it passes the quality gate.

Facts stay in GBrain, where they can be updated, deleted, cited, and permissioned. Finegrain trains durable company procedures, conventions, lookup behavior, and the judgment to admit when the answer is unknown.

```text
Approved company GBrain pages
                │
                ▼
   SFT data · RL tasks · held-out tests
                │
                ▼
          River fine-tuning
                │
                ▼
          promotion gate
                │
                ▼
     current company model
```

## Early benchmark: a specialized model beats the general model on the company task

We tested the core premise on GBrain skill routing: read a request and choose the correct GBrain skill. The evaluation contains 283 held-out intents from GBrain's own `routing-eval.jsonl` files; none appeared in training.

| Model | What is in the prompt | Prompt tokens | Accuracy |
|---|---|---:|---:|
| General `Qwen3.5-9B` | A one-line instruction | 45 | **1.8%** |
| General `Qwen3.5-9B` + GBrain rules | All of `RESOLVER.md` | 5,109 | **88.0%** |
| **Finegrain v1** | **The same one-line instruction** | **45** | **84.5%** |

Fine-tuning raised accuracy on this specialized task from **1.8% to 84.5%**. Finegrain reached 96% of the rule-loaded model's accuracy while using a prompt **113× smaller**. This is the value of a company model: it can internalize recurring company behavior instead of making every request carry the entire rulebook.

Finegrain v1 is `Qwen/Qwen3.5-9B` with a rank-16 LoRA, trained on River for 118 steps over 1,872 routing pairs in 591 seconds. The leak check found 0 of 2,079 total pairs in the held-out set. These results demonstrate specialization on the measured routing task; they do not claim broader general capability.

Reproduce the benchmark with `make bench`. Raw aggregate results are in `results/results.json`, and `results/bench-cases.jsonl` records every evaluated answer.

## Try it in one command

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), and Git.

```bash
git clone https://github.com/edreisMD/finegrain.git
cd finegrain
make quickstart
```

This command:

- prepares the sample inputs and runs the test suites;
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
make quickstart   # build a credential-free dataset and run the tests
make night        # run one real dataset and fine-tuning cycle
```

## Run one real company night

Finegrain requires a starting River checkpoint. Its base model and LoRA rank must match the values used to create that checkpoint.

```bash
export RIVER_API_KEY=...
export GM_BASE_MODEL=Qwen/Qwen3.5-9B
export GM_CHECKPOINT=river://...   # starting company-model checkpoint
export GM_LORA_RANK=16             # must match the checkpoint

make night
```

The first run evaluates and trains from `GM_CHECKPOINT`. Later runs resume from the last promoted company checkpoint and include replay data. The committed result files contain mock data until a real run writes `"mock": false`.

The default teacher is `nvidia/Kimi-K2.6-NVFP4`, the independent critic is `nvidia/GLM-5.2-NVFP4`, and the student is `Qwen/Qwen3.5-9B`. Change these in the company training profile and use `gm-nightly models` to verify the models available in your River account.

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
       Finegrain + River
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
- the Finegrain training console at `http://localhost:8787`;
- Postgres with pgvector on the internal Docker network.

The default schedule is nightly at 02:00 UTC. `nightly`, `weekly`, `monthly`, `manual`, and `once` are supported. Configure cadence and time zone in `.gm/deployment/.env` before the first startup, or edit the generated training profile afterward.

Already have a company GBrain? Keep it and point Finegrain at its existing profile:

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
data/                         Dataset preparation and validation
results/                      Shared product/ML result contracts
night/run.py                  Root wrapper for one real cycle
night/gm-nightly-loop/
  apps/macos/                 Native menu-bar companion
  deploy/                     GBrain, Postgres, and trainer stack
  scripts/                    Employee and server installers
  src/gm_nightly/             Capture, relay, generation, training, and gates
  tests/                      Nightly-loop verification suite
```

Read [CONTRACT.md](CONTRACT.md) for the files shared by the product and model sides. The deeper [Finegrain operations guide](night/gm-nightly-loop/README.md) documents capture rules, provider configuration, dataset artifacts, scheduling, and operational limits.

MIT License.
