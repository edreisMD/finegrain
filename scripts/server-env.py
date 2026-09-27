"""Create a private deployment environment; never print keys."""

import getpass
import os
import re
import secrets
import sys
from pathlib import Path

os.umask(0o077)
path = Path(sys.argv[1])
company = input("Company ID [company]: ").strip() or "company"
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", company):
    raise SystemExit("Use a simple company ID")
url = (
    input("Company Gbrain public URL [http://localhost:3131]: ").strip() or "http://localhost:3131"
)
if "\n" in url or not url.startswith(("https://", "http://localhost:", "http://127.0.0.1:")):
    raise SystemExit("Use HTTPS, or localhost for your sandbox")
river_key = os.environ.get("RIVER_API_KEY") or getpass.getpass(
    "River API key (hidden, blank to configure later): "
)
if not re.fullmatch(r"[A-Za-z0-9_-]*", river_key):
    raise SystemExit("Unexpected key format")
gm_checkpoint = os.environ.get("GM_CHECKPOINT", "")
if "\n" in gm_checkpoint or "\r" in gm_checkpoint:
    raise SystemExit("GM_CHECKPOINT must fit on one line")
gm_name = os.environ.get("GM_NAME", "gm-v1")
gm_base_model = os.environ.get("GM_BASE_MODEL", "Qwen/Qwen3.5-9B")
gm_lora_rank = os.environ.get("GM_LORA_RANK", "16")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", gm_name):
    raise SystemExit("GM_NAME must be a simple model identifier")
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,255}", gm_base_model):
    raise SystemExit("GM_BASE_MODEL has an unexpected format")
if not re.fullmatch(r"[1-9][0-9]*", gm_lora_rank):
    raise SystemExit("GM_LORA_RANK must be a positive integer")
owner = secrets.token_urlsafe(32)
lines = {
    "POSTGRES_PASSWORD": secrets.token_hex(24),
    "GBRAIN_ADMIN_BOOTSTRAP_TOKEN": owner,
    "RIVER_API_KEY": river_key,
    "GBRAIN_PUBLIC_URL": url,
    "FINEGRAIN_COMPANY": company,
    "FINEGRAIN_CADENCE": "nightly",
    "FINEGRAIN_TIMEZONE": "UTC",
    "GM_CHECKPOINT": gm_checkpoint,
    "GM_NAME": gm_name,
    "GM_BASE_MODEL": gm_base_model,
    "GM_LORA_RANK": gm_lora_rank,
}
with path.open("x") as f:
    f.write("\n".join(f"{k}={v}" for k, v in lines.items()) + "\n")
(path.parent / "owner-token").write_text(owner + "\n")
print("Private deployment settings saved. Starting the official Gbrain company stack…")
