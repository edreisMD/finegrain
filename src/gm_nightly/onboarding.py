from __future__ import annotations

import getpass
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

from .config import Config
from .employee import validate_server_url
from .gbrain import Gbrain
from .storage import atomic_json


def identifier(value):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", value):
        raise ValueError("Company and employee IDs use letters, numbers, underscores or dashes")
    return value


def write_config(path: Path, sections: dict):
    if path.exists():
        raise ValueError("Profile already exists; edit it or choose another --output path")
    lines = []
    for section, values in sections.items():
        if section == "sources":
            for source in values:
                lines.append("[[sources]]")
                lines.extend(f"{k} = {json.dumps(v)}" for k, v in source.items())
        else:
            lines.append(f"[{section}]")
            lines.extend(f"{k} = {json.dumps(v)}" for k, v in values.items())
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("x") as f:
        f.write("\n".join(lines))
    path.chmod(0o600)


def employee_install(args):
    print(
        "\n  ◒  GM Nightly Loop\n  Personal Gbrain → company Gbrain → a model that learns\n",
        file=sys.stderr,
    )
    tenant = identifier(args.company or input("Company ID: ").strip())
    employee = identifier(args.employee_id or input("Your teammate ID: ").strip())
    url = validate_server_url(args.company_url or input("Company Gbrain URL: ").strip())
    output = (
        (args.output or Path.home() / ".config/gm-nightly/employee.toml").expanduser().resolve()
    )
    if output.exists():
        raise ValueError("Employee profile already exists; it has not been changed")
    projects = [str(Path(p).expanduser().resolve()) for p in args.share_project]
    if not projects and sys.stdin.isatty():
        project = input("Company project folder to share (blank keeps everything local): ").strip()
        if project:
            projects = [str(Path(project).expanduser().resolve())]
    root = output.parent / "state"
    company_home = output.parent / "company-connection"
    executable = shutil.which(args.gbrain_binary)
    if not executable:
        raise ValueError("Install Gbrain first with scripts/install-gbrain.sh")
    command = [str(Path(executable).absolute())]
    local = Gbrain(command, args.gbrain_home)
    config_file = (
        Path(args.gbrain_home).expanduser() if args.gbrain_home else Path.home()
    ) / ".gbrain/config.json"
    if not config_file.exists():
        print("  1/3  Initializing the official personal Gbrain (local, keyless)…", file=sys.stderr)
        local.run(
            ["init", "--pglite", "--no-embedding", "--non-interactive", "--no-git"], timeout=300
        )
    else:
        print("  1/3  Reusing your existing personal Gbrain.", file=sys.stderr)
    if args.credentials:
        handoff = json.loads(args.credentials.read_text())
        if (
            handoff.get("company") != tenant
            or handoff.get("employee_id") != employee
            or handoff.get("url") != url
        ):
            raise ValueError("Credential handoff does not match this company, employee and URL")
        client_id, client_secret = handoff["client_id"], handoff["client_secret"]
        source = handoff["source"]
    else:
        client_id = input("Gbrain OAuth client ID: ").strip()
        client_secret = getpass.getpass("Gbrain OAuth client secret (hidden): ")
        source = args.source
    credential_path = output.parent / (employee + "-credentials.json")
    if credential_path.exists():
        raise ValueError("Credential file already exists; refusing to overwrite it")
    atomic_json(credential_path, {"GBRAIN_REMOTE_CLIENT_SECRET": client_secret})
    old_secret = os.environ.get("GBRAIN_REMOTE_CLIENT_SECRET")
    os.environ["GBRAIN_REMOTE_CLIENT_SECRET"] = client_secret
    try:
        print("  2/3  Verifying your scoped company Gbrain connection…", file=sys.stderr)
        company = Gbrain(command, str(company_home), source, remote=True)
        company.run(
            [
                "init",
                "--mcp-only",
                "--issuer-url",
                url,
                "--mcp-url",
                url + "/mcp",
                "--oauth-client-id",
                client_id,
                "--non-interactive",
                "--json",
            ]
        )
    finally:
        if old_secret is None:
            os.environ.pop("GBRAIN_REMOTE_CLIENT_SECRET", None)
        else:
            os.environ["GBRAIN_REMOTE_CLIENT_SECRET"] = old_secret
    write_config(
        output,
        {
            "gm": {
                "tenant": tenant,
                "role": "employee",
                "employee_id": employee,
                "state_dir": str(root),
                "credentials_file": str(credential_path),
            },
            "gbrain": {
                "gbrain_command": command,
                "gbrain_home": args.gbrain_home,
                "company_home": str(company_home),
                "company_source": source,
            },
            "delivery": {"server_url": url},
            "capture": {"shared_projects": projects, "poll_seconds": 5, "quiet_seconds": 15},
        },
    )
    app_settings = (
        args.app_settings or Path.home() / "Library/Application Support/GM Nightly Loop/app.json"
    )
    atomic_json(
        app_settings,
        {
            "python": sys.executable,
            "config": str(output),
            "workspace": str(root / tenant),
            "companyURL": url,
            "brainFolder": str(config_file.parent),
        },
    )
    print("  3/3  Ready. Only compiled notes from selected projects are shared.\n", file=sys.stderr)
    return {
        "config": str(output),
        "app_settings": str(app_settings),
        "shared_projects": projects,
        "start": shlex.join(["gm-nightly", "--config", str(output), "employee", "watch"]),
    }


def server_install(args):
    tenant = identifier(args.company or input("Company ID: ").strip())
    output = (args.output or Path("gm-nightly.server.toml")).resolve()
    if not args.gbrain_home:
        raise ValueError("Pass --gbrain-home for the existing company Gbrain profile")
    if not (Path(args.gbrain_home).expanduser() / ".gbrain/config.json").exists():
        raise ValueError(
            "Initialize the company Gbrain first; use deploy/compose.yaml for a new Docker stack"
        )
    url = validate_server_url(args.company_url or "http://localhost:3131")
    write_config(
        output,
        {
            "gm": {
                "tenant": tenant,
                "role": "server",
                "state_dir": str(output.parent / ".gm/company"),
            },
            "generation": {"teacher": "river"},
            "schedule": {
                "cadence": args.cadence,
                "auto_train": True,
                "hour": 2,
                "timezone": args.timezone,
            },
            "gbrain": {
                "gbrain_command": [args.gbrain_binary],
                "gbrain_home": str(Path(args.gbrain_home).resolve()),
                "company_source": args.source,
            },
            "delivery": {"server_url": url},
            "sources": [
                {
                    "name": "company-gbrain",
                    "kind": "gbrain_cli",
                    "command": [args.gbrain_binary],
                    "home": str(Path(args.gbrain_home).resolve()),
                    "source_id": args.source,
                    "tag": "gm-nightly-share",
                    "remote": args.remote,
                }
            ],
        },
    )
    return {
        "config": str(output),
        "start": shlex.join(["gm-nightly", "--config", str(output), "server", "serve"]),
    }


def invite(config: Config, employee: str, output: Path):
    identifier(employee)
    if output.exists():
        raise ValueError("Credential destination already exists")
    if config.role != "server":
        raise ValueError("Invites must be issued by the company server")
    brain = Gbrain(config.gbrain_command, config.gbrain_home, config.company_source)
    raw = brain.run(
        [
            "auth",
            "register-client",
            "gm-nightly-" + employee,
            "--grant-types",
            "client_credentials",
            "--scopes",
            "read write",
            "--source",
            config.company_source,
            "--federated-read",
            config.company_source,
            "--bound-slug-prefixes",
            f"employees/{employee}/",
        ]
    )
    client_id = re.search(r"Client ID:\s+(\S+)", raw)
    client_secret = re.search(r"Client Secret:\s+(\S+)", raw)
    if not client_id or not client_secret:
        raise RuntimeError("Upstream credential output changed; inspect Gbrain auth clients")
    atomic_json(
        output,
        {
            "company": config.tenant,
            "employee_id": employee,
            "url": config.server_url,
            "source": config.company_source,
            "client_id": client_id[1],
            "client_secret": client_secret[1],
        },
    )
    return {
        "credentials_file": str(output.resolve()),
        "employee": employee,
        "issuer": "Gbrain OAuth",
        "write_prefix": f"employees/{employee}/",
    }
