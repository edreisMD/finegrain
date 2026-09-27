# First-version demo

**One sentence:** GM Nightly Loop turns approved company Gbrain knowledge into training data and a company model that is tested before it is promoted.

## A reproducible two-minute walkthrough

1. Start with the running company Gbrain dashboard and GM Nightly Loop console. Explain: personal memory stays in the normal Gbrain; selected compiled knowledge goes into the real company brain.
2. Show three separately scoped teammate connections. Open one compiled page in Gbrain. The synthetic sandbox proves each teammate can write their own folder and cannot overwrite another teammate's folder.
3. Run `make demo`. Open the reported `report.html`: inspect a recall task, an abstention task, a changed-fact task, and a procedure. Expand the evidence and show the held-out/source split. This is explicitly the **offline fixture demo**, not a trained-model benchmark.
4. Show `results/sample.json` and its reproduction command. For a live River run, show the actual `generation_log.json`, accepted/rejected curricula, and checkpoint/metrics files if training has completed. Never substitute offline demo scores for live model scores.
5. Show the promotion gate and explain the failure case: a worse candidate does not replace the company model. Gbrain remains the authority for mutable facts.

## What this adds to upstream

Gbrain already supplies the dream cycle, memory synthesis, skills, routing evaluations, and company access controls. GM Nightly Loop adds a provider-based path from approved company pages to supervised examples, small RL environments, withheld evaluation, and River weight updates. Its Mac app is a companion, not a replacement brain.

## Evidence available in v0.1

- A source-built native Mac menu-bar app.
- Official Gbrain 0.59.0.0 and Postgres running in Docker.
- A real OAuth relay smoke test with three fictional teammates.
- Automated tests for capture, relay, privacy boundaries, leakage, rewards, scheduling, and provider contracts.
- Reproducible offline curriculum and a separate live River generation path.
- No claim yet of a live trained model outperforming a baseline. Record a completed River experiment before making that claim or presenting this as a completed River-trained model submission.

## Submission preparation

The attached judging dossier distinguishes published observations from its inferred rubric. We use it as product guidance, not as a source of official numeric scoring weights. The first version prioritizes a clean-clone run, visible artifacts, truthful measurements, and substantial Gbrain/River integration.

Before submission, add the actual team handles, a public demo video, and any completed training receipt. Keep the same one-sentence claim in the form and video. No judge-directed instructions, invented performance numbers, or claims that existing Gbrain features are missing.
