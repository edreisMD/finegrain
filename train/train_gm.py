"""C4: fine-tune GM on River with LoRA SFT and record the checkpoint.

The base model and LoRA rank match Finegrain's student model, so its nightly
loop can continue training from GM's checkpoint.
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_MODEL = "Qwen/Qwen3.5-9B"
LORA_RANK = 16


def load_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        rows += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows


def split(rows: list[dict], val_fraction: float, seed: int) -> tuple[list[dict], list[dict]]:
    rows = rows[:]
    random.Random(seed).shuffle(rows)
    n_val = max(1, int(len(rows) * val_fraction))
    return rows[n_val:], rows[:n_val]


def answer_text(result) -> str:
    if result.status_code != 200:
        raise RuntimeError(f"River completion failed with status {result.status_code}")
    content = json.loads(result.response_json)["choices"][0]["message"].get("content") or ""
    return content.split("</think>")[-1].strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, nargs="+", default=[Path("data/routing.jsonl")])
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--val-checks", type=int, default=20)
    parser.add_argument("--out", type=Path, default=Path("train/gm-checkpoint.json"))
    args = parser.parse_args()

    import river_client as river
    from river_client.renderers import TrainOnWhat, get_renderer

    if not os.environ.get("RIVER_API_KEY"):
        print("error: set RIVER_API_KEY in .env", file=sys.stderr)
        return 1
    client = river.Client(api_key=os.environ["RIVER_API_KEY"], timeout=600)
    available = set(client.get_capabilities())
    if BASE_MODEL not in available:
        qwen = sorted(m for m in available if "qwen" in m.lower())
        print(f"error: {BASE_MODEL} not available. Qwen models on this account: {qwen}", file=sys.stderr)
        return 1

    train_rows, val_rows = split(load_rows(args.data), args.val_fraction, seed=0)
    renderer = get_renderer(BASE_MODEL, thinking=False)
    data = [
        renderer.build_training_example(r["messages"], train_on=TrainOnWhat.LAST_ASSISTANT).to_dict()
        for r in train_rows
    ]
    print(f"train {len(data)} examples, validation {len(val_rows)}, base {BASE_MODEL}, rank {LORA_RANK}")

    started, losses = time.time(), []
    rng = random.Random(0)
    with client.session(project="gm", phase="sft") as session:
        model = session.create_model(
            base_model=BASE_MODEL, tokenizer=renderer.tokenizer, lora=river.LoraConfig(rank=LORA_RANK, seed=0)
        )
        for epoch in range(args.epochs):
            rng.shuffle(data)
            for i in range(0, len(data), args.batch_size):
                fb, _ = model.train_step(
                    data[i : i + args.batch_size], lr=args.lr, loss_fn="cross_entropy", grad_clip_norm=1.0
                )
                losses.append(fb.metrics["loss_mean"])
                print(f"epoch {epoch} step {model.step} loss_mean {losses[-1]:.4f} ({time.time() - started:.0f}s)", flush=True)
        tag = datetime.now(timezone.utc).strftime("gm-v1-%Y%m%d-%H%M%S")
        train_ckpt = model.save_weights(tag, mode="training")
        infer_ckpt = model.save_weights(tag + "-infer", mode="inference")

    checks = val_rows[: args.val_checks]
    correct = 0
    for row in checks:
        prompt = row["messages"][:-1]
        reply = client.chat_complete_from_checkpoint(
            prompt, checkpoint_path=train_ckpt.path, base_model=BASE_MODEL, max_tokens=64, temperature=0.0,
            chat_template_kwargs={"enable_thinking": False},  # trained without thinking, so sample without it
        )
        correct += answer_text(reply) == row["messages"][-1]["content"]

    record = {
        "model": "GM",
        "base_model": BASE_MODEL,
        "lora_rank": LORA_RANK,
        "checkpoint": train_ckpt.path,
        "inference_checkpoint": infer_ckpt.path,
        "train_examples": len(data),
        "validation_examples": len(val_rows),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.lr,
        "steps": model.step,
        "first_loss_mean": losses[0],
        "last_loss_mean": losses[-1],
        "train_seconds": round(time.time() - started),
        "validation_check": {"correct": correct, "total": len(checks)},
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    args.out.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
