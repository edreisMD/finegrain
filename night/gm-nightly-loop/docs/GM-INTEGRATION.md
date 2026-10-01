# GM Part 2 integration

GM has two weight-training stages with one required invariant: both use the same River base model.

1. Part 1 trains Gbrain's general routing, filing, formatting, and citation behavior. It publishes `GM_BASE_MODEL`, `GM_CHECKPOINT`, and `GM_LORA_RANK` privately to the runtime environment.
2. Part 2 reads approved company Gbrain pages. Arena corrections become pages in that same source; rejected model answers are excluded. It generates procedure, abstention, staleness, and limited recall tasks, then starts its first SFT job from `GM_CHECKPOINT`.
3. Later Part 2 runs resume from the last promoted company checkpoint. A candidate is promoted only after the held-out gate passes.

GM includes the nightly loop as a self-contained subtree at `night/gm-nightly-loop`. This preserves a clean ownership boundary and avoids collisions with Part 1's `data/`, `train/`, `bench/`, and product UI.

```bash
git fetch origin gm/nightly-loop
git switch gm/nightly-loop
```

Future work stays inside `night/gm-nightly-loop`, so the two parts can evolve in one GM repository without overlapping files.

From the GM repository root, the integration exposes these commands:

```bash
make part2-setup
make part2-demo
make part2-test
make night
```

The offline demo is credential-free and produces inspectable synthetic artifacts. `make night` is the real River path and requires `RIVER_API_KEY`, `GM_BASE_MODEL`, `GM_CHECKPOINT`, and `GM_LORA_RANK`. Results must be presented as live only after River returns a real checkpoint and evaluation report.
