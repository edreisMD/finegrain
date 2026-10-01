"""Run GM Nightly Loop and publish the UI's night-run contract."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "results/night-run.json"
PYTHON = ROOT / "night/gm-nightly-loop/.venv/bin/python"
STEPS = ("collect", "examples", "train", "gate", "promote")


def write_status(
    night: int,
    states: dict[str, tuple[str, str]],
    before_after: dict[str, str] | None = None,
) -> None:
    payload = {
        "mock": False,
        "night": night,
        "steps": [
            {
                "id": step,
                "status": states.get(step, ("pending", ""))[0],
                "detail": states.get(step, ("pending", ""))[1],
            }
            for step in STEPS
        ],
        "before_after": before_after or {"prompt": "", "before": "", "after": ""},
    }
    temporary = STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(temporary, STATUS)


def next_night() -> int:
    try:
        previous = json.loads(STATUS.read_text())
    except (OSError, json.JSONDecodeError):
        return 1
    return previous.get("night", 0) + 1 if previous.get("mock") is False else 1


def failed_step(stderr: str) -> str:
    if "supervised fine-tuning" in stderr or "reinforcement learning" in stderr:
        return "train"
    if "generating curriculum" in stderr:
        return "examples"
    return "collect"


def comparison(result: dict) -> dict[str, str]:
    before = {case["id"]: case for case in result.get("before", {}).get("cases", [])}
    after = result.get("after", {}).get("cases", [])
    comparable = [
        (before[case["id"]], case)
        for case in after
        if case.get("id") in before and case.get("suite") != "regression"
    ]
    if not comparable:
        return {"prompt": "", "before": "", "after": ""}
    prior, current = next(
        (
            pair
            for pair in comparable
            if pair[1].get("score", 0) > pair[0].get("score", 0)
        ),
        comparable[0],
    )
    return {
        "prompt": current.get("prompt", prior.get("prompt", "")),
        "before": prior.get("response", ""),
        "after": current.get("response", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    required = ("RIVER_API_KEY", "GM_BASE_MODEL", "GM_CHECKPOINT", "GM_LORA_RANK")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        print("Missing environment variables: " + ", ".join(missing), file=sys.stderr)
        return 2
    night = next_night()
    write_status(
        night,
        {"collect": ("running", "Reading approved company Gbrain pages")},
    )
    command = [str(PYTHON), "-m", "gm_nightly", "--config", str(args.config), "run"]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if completed.returncode:
        step = failed_step(completed.stderr)
        write_status(night, {step: ("failed", "See the GM Nightly Loop run log")})
        sys.stderr.write(completed.stderr)
        return completed.returncode
    result = json.loads(completed.stdout)
    passed = bool(result.get("gate", {}).get("passed"))
    write_status(
        night,
        {
            "collect": ("done", "Approved company sources collected"),
            "examples": ("done", "Grounded training and held-out tasks generated"),
            "train": ("done", "River SFT and configured RL completed"),
            "gate": ("done", "Candidate passed" if passed else "Candidate rejected"),
            "promote": (
                "done" if passed else "rolled_back",
                "Candidate promoted" if passed else "Previous company checkpoint retained",
            ),
        },
        comparison(result),
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
