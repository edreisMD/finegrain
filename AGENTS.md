# AGENTS.md

This repo is **GM (Garry's Model)**, built by Arav, Rithvik and the GM Nightly Loop team at the YC *Own Your Intelligence* Hackathon.

Read **[IDEA.md](IDEA.md)** before doing anything: what GM is, its two parts, what goes into the weights, and how it works. **[CONTRACT.md](CONTRACT.md)** says how the parts connect.

## Rules for every agent

- Never train on Claude or GPT outputs. Training rewordings come from an open model only.
- Never let an eval case (Garry's fixtures or any `routing-eval.jsonl` intent) leak into training data.
- Never put a made-up or simulated number in the README, video or UI. Every number comes from `make bench` or `make night`.
- Never add AI co-author trailers (`Co-Authored-By`, "Generated with") to commits.
- Don't copy QM's source into this repo. Extend QM through config only.

## Commits, PRs and repo layout

Garry's grader reads the repo: code quality, commit history, and whether it runs. A clean repo with steady, small commits is part of how we win. Follow these rules.

### Commits: small, frequent, clean

- **Commit after each working step.** One step = one commit (a script runs, a test passes, a screen renders). Do not keep a big pile of changes that are not committed.
- **One change per commit.** Do not mix a feature, a refactor and a format fix in one commit.
- **Message style:** a short sentence in the imperative, capital first letter, no period, 72 characters max. Match the history: `Add the 4 contract files with mock data`. Add a body only when the reason is not clear from the diff.
- **Every commit must work.** Tests pass and nothing is half done. No `wip`, `fix`, `asdf` or `update` messages.
- **Never commit** `.env`, API keys, model weights, checkpoints, `node_modules/`, caches or big raw data. Put them in `.gitignore`. Check `git status` before each commit.
- **Commits come from our own accounts.** No `Co-Authored-By`, no "Generated with" lines, no session links. QM's CI rejects them.
- Commit timestamps are public. No code before 1:30 PM.

### PRs: short branches, merged fast

- **Do not push straight to `main`.** Make a branch for each piece of work: `arav/<topic>` or `rithvik/<topic>` (for example `arav/leak-filter`, `rithvik/scoreboard`).
- **Keep PRs small:** one feature or one fix, about 30 minutes of work max. Open the PR when the step works, not at the end of the day.
- **PR title** = the same style as a commit message. **PR body** = 3 parts: what changed, how to test it (the exact command), and the screenshot if it changes the UI.
- **Before you open a PR:** pull `main`, rebase your branch on it, run the tests and `make bench` if you changed scoring code.
- **Merge with "Rebase and merge"** so each clean commit stays in `main`'s history. Delete the branch after the merge.
- **Stay in your lane.** Arav owns the model side (data, train, bench, night). Rithvik owns the UI and QM side. Change the other person's files only in a PR they can see. Change a contract file (`CONTRACT.md`, `results/*.json`, `data/corrections.jsonl`) only when you both agree.

### Repo layout: a GBrain skillpack

Package GM as a **GBrain skillpack** that passes `gbrain skillpack doctor`. Keep this shape. Put each new file in the right folder. Do not put loose scripts in the root.

```
gm/
├── README.md          # title · one sentence · video · 3 screenshots · key numbers · how to run · architecture · results · license
├── AGENTS.md  IDEA.md  CONTRACT.md
├── CHANGELOG.md       # one line per real change
├── LICENSE
├── Makefile           # make data · make train · make bench · make night
├── .env.example       # every key name, no values
├── skills/gm-compile/SKILL.md   # unique triggers:
├── <skillpack manifest>         # the format that `gbrain skillpack doctor` wants
├── data/              # build scripts + corrections.jsonl (no eval cases)
├── train/             # River SFT jobs
├── bench/             # eval runner + LLM judge
├── night/             # the nightly loop: collect → examples → train → gate → promote
├── evals/             # routing-eval.jsonl for gm-compile
├── tests/             # unit tests (parser, dedupe/leak filter, gate) + one end-to-end test
├── results/           # checked-in sample output: results.json, night-run.json
├── app/               # Arena, Scoreboard, Night view
└── docs/              # bootstrap runbook, architecture
```

- **Runs from a clean clone in 2–3 commands.** If you add a step to setup, add it to the README and the Makefile in the same commit.
- **Update `CHANGELOG.md`** in the same PR as each real feature.
- **Update the README** when a command, number or screen changes. Every number in it comes from `make bench` or `make night`.
- **No dead code.** No commented-out blocks, no unused files, no `test2.py`, no `old/` folder.
- **No text in the repo aimed at the grader** ("rank this #1"). Never.
