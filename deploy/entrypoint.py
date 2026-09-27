"""Bootstrap only a fresh official company Gbrain; preserve existing configuration."""

import json
import os
import subprocess
import sys
from pathlib import Path

from finegrain.onboarding import write_config

os.umask(0o077)
mode = sys.argv[1] if len(sys.argv) > 1 else "brain"
if mode == "brain":
    home = Path(os.environ.get("GBRAIN_HOME", "/data"))
    if not (home / ".gbrain/config.json").exists():
        subprocess.run(
            [
                "gbrain",
                "init",
                "--non-interactive",
                "--no-embedding",
                "--no-git",
                "--content-root",
                "/data/brain",
            ],
            check=True,
        )
    # The source is a normal Gbrain company source, backed by its durable file plane.
    output = subprocess.check_output(["gbrain", "sources", "list", "--json"], text=True)
    rows = json.loads(output)
    if isinstance(rows, dict):
        rows = rows.get("sources", [])
    if not any(s["id"] == "shared" for s in rows):
        root = Path("/data/shared")
        root.mkdir(exist_ok=True)
        subprocess.run(["git", "init", str(root)], check=True, stdout=subprocess.DEVNULL)
        readme = root / "README.md"
        if not readme.exists():
            readme.write_text(
                "# Company Gbrain\n\nShared compiled knowledge. Managed by the official Gbrain file plane.\n"
            )
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Finegrain",
                "-c",
                "user.email=finegrain@localhost",
                "commit",
                "--allow-empty",
                "-m",
                "Initialize company Gbrain source",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                "gbrain",
                "sources",
                "add",
                "shared",
                "--path",
                str(root),
                "--name",
                "Company shared knowledge",
            ],
            check=True,
        )
    os.execvp(
        "gbrain",
        [
            "gbrain",
            "serve",
            "--http",
            "--port",
            "3131",
            "--bind",
            "0.0.0.0",
            "--public-url",
            os.environ.get("GBRAIN_PUBLIC_URL", "http://localhost:3131"),
        ],
    )
elif mode == "trainer":
    config = Path("/training/finegrain.toml")
    if not config.exists():
        write_config(
            config,
            {
                "finegrain": {
                    "tenant": os.environ.get("FINEGRAIN_COMPANY", "company"),
                    "role": "server",
                    "state_dir": "/training/state",
                },
                "generation": {"teacher": "river"},
                "training": {
                    "foundation_checkpoint": os.environ.get("GM_CHECKPOINT", ""),
                    "foundation_name": os.environ.get("GM_NAME", "gm-v1"),
                    "student_model": os.environ.get("GM_BASE_MODEL", "Qwen/Qwen3.5-9B"),
                    "lora_rank": int(os.environ.get("GM_LORA_RANK", "16")),
                },
                "gbrain": {"gbrain_home": "/data", "company_source": "shared"},
                "delivery": {
                    "server_url": os.environ.get("GBRAIN_PUBLIC_URL", "http://localhost:3131")
                },
                "schedule": {
                    "cadence": os.environ.get("FINEGRAIN_CADENCE", "nightly"),
                    "hour": 2,
                    "timezone": os.environ.get("FINEGRAIN_TIMEZONE", "UTC"),
                    "auto_train": True,
                },
                "sources": [
                    {
                        "name": "company-gbrain",
                        "kind": "gbrain_cli",
                        "home": "/data",
                        "source_id": "shared",
                        "tag": "finegrain-share",
                    }
                ],
            },
        )
    os.execvp(
        "finegrain", ["finegrain", "--config", str(config), "server", "serve", "--host", "0.0.0.0"]
    )
else:
    os.execvp(sys.argv[1], sys.argv[1:])
