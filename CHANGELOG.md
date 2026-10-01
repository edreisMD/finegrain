# Changelog

- Train GM v1 on River (Qwen3.5-9B, LoRA rank 16) and score it: 84.5% on 283 held-out routing intents with a 45-token prompt, vs 88.0% for the base model reading the full 5,109-token resolver
- Add `make bench`: held-out routing benchmark for Base, Base + resolver and GM, with a leak check that refuses to score if any eval intent is in training
- Add `make train`: River LoRA SFT on the base model Part 2 uses, so the nightly loop can continue from GM's checkpoint
- Make the nightly handoff idempotent, require the Part 1 adapter rank, route approved corrections through GBrain, and compare reset runs against GM.
- Add GM Nightly Loop as Part 2 with a checkpoint handoff and one-command demo.
- Add the skill parser: `make data` reads GBrain's 75 skills and 3 rule files into `data/skills.json`
- Add `make routing`: teacher rewordings of each skill's triggers, with every eval intent filtered out
- Add `make behavior`: raw notes filed into GBrain pages, kept only if they pass the page checker
