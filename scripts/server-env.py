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
owner = secrets.token_urlsafe(32)
lines = {
    "POSTGRES_PASSWORD": secrets.token_hex(24),
    "GBRAIN_ADMIN_BOOTSTRAP_TOKEN": owner,
    "RIVER_API_KEY": river_key,
    "GBRAIN_PUBLIC_URL": url,
    "FINEGRAIN_COMPANY": company,
    "FINEGRAIN_CADENCE": "nightly",
    "FINEGRAIN_TIMEZONE": "UTC",
}
with path.open("x") as f:
    f.write("\n".join(f"{k}={v}" for k, v in lines.items()) + "\n")
(path.parent / "owner-token").write_text(owner + "\n")
print("Private deployment settings saved. Starting the official Gbrain company stack…")
