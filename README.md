# GM — Part 2

> **“GBrain gets better the more it's used. Every correction your team makes becomes training data, and GM improves overnight.”**

This repository is the company adaptation half of **GM (Garry's Model)**. Part 1 compiles Gbrain's general routing, filing, formatting, and citation skills into GM once. Part 2 turns approved company knowledge and corrections into grounded SFT examples, verifiable RL tasks, and held-out tests, then trains from the Part 1 GM checkpoint through River.

Facts remain in Gbrain. GM's weights learn procedures, calibration, and when to look facts up.

It uses **[Gbrain's normal personal installation](https://github.com/garrytan/gbrain)** on each Mac and **[Gbrain's company-brain setup](https://github.com/garrytan/gbrain/blob/master/docs/tutorials/company-brain.md)** on the server. Gbrain owns memory, permissions, revisions, and the company dashboard. GM Nightly Loop focuses on the learning pipeline.

Built for the [Own Your Intelligence hackathon](https://events.ycombinator.com/gbrain-qm-river-memorable-hackathon). The product is **GM Nightly Loop** and its command is `gm-nightly`.

**Start here:** [two-minute demo](docs/DEMO.md) · [reproducible sample results](results/sample.json) · [implementation plan](docs/PLAN.md).

```bash
git clone https://github.com/arav-rithvik/gm.git
cd gm
make setup && make demo  # requires uv; no API key needed
```

That produces a complete inspectable fixture dataset with all four task families and runs without credentials. For a real company night starting from GM Part 1:

```bash
export RIVER_API_KEY=...                 # keep this outside Git
export GM_BASE_MODEL=Qwen/Qwen3.5-9B    # must match Part 1
export GM_CHECKPOINT=river://...         # checkpoint produced by Part 1
make night
```

`GM_CHECKPOINT` is the critical handoff: the first company run evaluates GM, fine-tunes from GM, evaluates the candidate, and promotes it only if the gate passes. Later runs resume from the last promoted company checkpoint with replay.

```text
Claude / Codex / Pi / other agents
              ↓
     Mac menu-bar companion
              ↓
   Official personal Gbrain
              ↓ compiled, explicitly shared notes
       Gbrain OAuth relay
              ↓
   Official company Gbrain       ← Docker · Postgres · Gbrain /admin/
              ↓
  River teacher + independent critic
              ↓
  SFT examples · RL tasks · held-out tests
              ↓
   River SFT → RL → evaluation → promotion gate
```

One repository, two installation commands. Data generation runs on the company host (your laptop for a sandbox); model training runs on River. The employee companion never trains or sends full traces to River.

## Install the company server

Requirements: Docker with Compose, Python 3, and a River account for live generation/training.

```bash
./scripts/install-server.sh
```

The installer asks for your company ID, Gbrain URL, and River key with hidden input. It creates private settings under `.gm/deployment/`, then starts:

- **Gbrain company dashboard:** http://localhost:3131/admin/
- **GM Nightly Loop training console:** http://localhost:8787
- **Postgres with pgvector:** internal Docker network, persistent volume.

The Gbrain owner credential is saved in `.gm/deployment/owner-token`. Use Gbrain's own dashboard login and access-management flow. Neither API keys nor generated credentials belong in Git.

Default: nightly at 02:00 UTC. Configure cadence/time zone in `.gm/deployment/.env` **before first startup**, or edit `/training/gm-nightly.toml` in the persistent training volume afterward. `nightly`, `weekly`, `monthly`, `manual`, and `once` are supported. No new checkpoint becomes current unless it passes the promotion gate.

For a cloud VM, keep these services behind HTTPS and set `GBRAIN_PUBLIC_URL` to that public origin. A reverse proxy can reach the loopback ports on the same host. The repository does not provision a Google Cloud project or domain.

### Invite three teammates

Create separate official Gbrain OAuth credentials, each fenced to its own folder:

```bash
./scripts/invite.sh alice
./scripts/invite.sh bob
./scripts/invite.sh carol
```

Private handoffs appear in `.gm/invites/`. Give each teammate only their own file through your private sharing channel. Their writes are bounded to `employees/<id>/` in the `shared` company source; all three can read that shared source. Internal/HR sources must not enter this model's training set.

### Already running a company Gbrain?

Keep it. Install GM Nightly Loop's Python package and point it at an existing company host profile, or an upstream thin-client profile with read access to the training source:

```bash
uv tool install --python 3.12 '.[river]'
gm-nightly server install --company acme --gbrain-home /srv/company-profile \
  --company-url https://brain.acme.example --source shared --output gm-nightly.server.toml
gm-nightly --config gm-nightly.server.toml server serve
```

`--gbrain-home` follows upstream's convention: its config is `<home>/.gbrain/config.json`. Add `--remote` for a thin-client profile. Set `RIVER_API_KEY` in the server environment. Existing brains are never reinitialized by this command.

## Install on each employee's Mac

Requirements: macOS 13+, Bun, uv, and Xcode Command Line Tools for the source-built menu app.

```bash
./scripts/install-employee.sh \
  --company acme --employee-id alice \
  --company-url https://brain.acme.example \
  --credentials ~/Downloads/alice.json \
  --share-project ~/work/acme
```

Omit arguments for guided terminal onboarding. It reuses the personal Gbrain, or initializes an official local, keyless PGLite brain if none exists. It creates a **separate** Gbrain thin-client profile for the company connection, verifies OAuth, and opens the native menu-bar app. The Mac retains its personal brain configuration.

The menu shows worker/relay status, pause/resume, settings, personal files, and the existing company Gbrain dashboard. Quit stops the companion. For automatic startup, add `~/Applications/GM Nightly Loop.app` to macOS Login Items.

No River key is required on employee Macs. Their selected project paths are the sharing policy. Sessions outside those paths stay local; unknown or mixed project identity is private. Empty project selection shares nothing automatically.

### What gets captured and compiled

Claude, Codex, and Pi JSONL histories are read locally with incremental cursors, incomplete-line handling, and file-rotation recovery. Gbrain's existing native importer handles Claude/Codex brain ingestion. Pi and generic JSONL adapters fill the missing capture formats. Tool outputs, images, and reasoning blocks are excluded from GM Nightly Loop's compiler input; original session files are never edited.

The initial compiler selects explicit user-stated decisions and conventions, scrubs known secrets, and saves those notes through Gbrain's official page API. It is conservative: it does not claim to understand every trace or infer reliable facts from assistant guesses. Set `memory_compiler = "local-model"`, `local_model`, and a loopback `local_model_url` in `[capture]` to use an installed local model for grounded note selection. Gbrain's existing agent memory and synthesis can continue independently.

GM Nightly Loop relays only Gbrain pages carrying **both** the `gm-nightly-share` tag and `gm_training: true`, with `visibility: brain-wide`. Conversation/transcript/session pages are excluded. The relay sends compiled body/title and minimal provenance; never the trace journal, raw-data sidecars, timeline, credentials, or local paths. Upstream OAuth and revision checks enforce company writes. Removing approval withdraws a previously relayed page on the next successful cycle.

For other agents, add `capture_sources` in `[capture]` using TOML inline tables:

```toml
capture_sources = [{kind = "jsonl", path = "/absolute/agent/sessions"}]
```

The generic format is `{"type":"message","cwd":"/project","message":{"role":"user","content":"We always require review before release."}}`, one object per line. Specifying `capture_sources` replaces default discovery; include Claude/Codex/Pi entries too if desired.

## Generate, inspect, and train

From the Docker installation:

```bash
docker compose --env-file .gm/deployment/.env -f deploy/compose.yaml exec trainer \
  gm-nightly --config /training/gm-nightly.toml compile

docker compose --env-file .gm/deployment/.env -f deploy/compose.yaml exec trainer \
  gm-nightly --config /training/gm-nightly.toml server train
```

The company dataset compiler uses a large River model as teacher and a separate critic. Defaults are `nvidia/Kimi-K2.6-NVFP4` and `nvidia/GLM-5.2-NVFP4`, with `Qwen/Qwen3.5-9B` as student. These were available in the connected account; change them in the profile and use `gm-nightly models` to verify your catalog. GM Nightly Loop does not assume parameter count proves which model is strongest.

Four task families: **recall**, **abstention**, **staleness**, and **procedure**. Changed pages retain prior context for staleness examples. Source groups split before training; exact and near duplicates are removed. The critic must accept grounding, answerability, and leakage checks. Generated examples are schema/evidence validated and cached per page/version/teacher.

Artifacts include `memories.jsonl`, `curricula.jsonl`, `sft.jsonl`, `rl.jsonl`, `eval.jsonl`, `manifest.json`, critic reviews, rejection reasons, usage, and an inspection report. Training experiments preserve base/current/SFT/candidate scores and checkpoints. Costs remain unknown unless the provider reports them.

The initial RL environment is a bounded, two-turn **Gbrain snapshot lookup simulator**: ask for a page, receive its current snapshot, then answer with a citation or abstain. It executes no generated code. Training uses River's real SDK renderers, SFT client, rollout engine, and RL trainer behind a provider interface.

Gbrain stays the factual authority. A model is promoted only after measurable recall improvement without increased confident errors, per-suite regressions, or unacceptable general-ability loss. The bundled general suite is a small smoke check, not a comprehensive capability benchmark. Withdrawn training lineage requires rebuilding from the base; removing a page cannot erase facts from an already distributed model.

## Try the offline dataset demo

```bash
make setup
make demo
make test
```

Eighteen fictional company pages and five previous versions exercise all four task types. Demo datasets cannot be submitted for training. Live River examples use `examples/river.toml` and `RIVER_API_KEY`.

## Repository

`apps/macos/` contains the native menu-bar app; `deploy/` the official Gbrain/Postgres/GM Nightly Loop stack; `src/gm_nightly/` contains the adapters, relay, curriculum compiler, provider, evaluation and scheduling; `tests/` is the verification suite. See the [GM integration contract](docs/GM-INTEGRATION.md), [updated plan](docs/PLAN.md), [upstream contracts](docs/UPSTREAM.md), and [original project brief](docs/original-project-brief.md).

This is an initial working framework. The local extractor is narrow, secret detection is best effort, and source-built Mac apps are not notarized. A failed upstream write retains its request ID for retry; if the source changes while that write is unresolved, the worker stops that publication for reconciliation rather than silently overwriting another revision. Future providers and per-user adapters are extension points, not shipped integrations.

MIT license.
