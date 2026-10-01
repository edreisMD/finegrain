from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from .config import Config, load_config
from .demo import create_demo
from .generation import DemoTeacher
from .pipeline import compile_dataset, load_dataset
from .report import render_report
from .schedule import compilation_slot, is_due, launchd_plist, systemd_units, training_slot
from .storage import Store, workspace_lock
from .training import train_dataset


def teacher_for(config: Config, stack: ExitStack):
    if config.teacher == "demo":
        return DemoTeacher()
    from .providers.river import RiverTeacher, river_client

    client = river_client()
    stack.callback(client.close)
    return RiverTeacher(client, config)


def train(config: Config, path: Path, store: Store, stack: ExitStack):
    # Validate before creating a network client.
    manifest, _ = load_dataset(path, config.tenant)
    if manifest["demo"]:
        raise ValueError(
            "Demo datasets cannot be trained; configure a River teacher and compile first"
        )
    from .providers.river import RiverTrainer, river_client

    client = river_client()
    stack.callback(client.close)
    return train_dataset(config, path, RiverTrainer(client), store)


def tick(config: Config, store: Store, stack: ExitStack, now: datetime | None = None):
    now = now or datetime.now(UTC)
    compilation = compilation_slot(now, config)
    if is_due(compilation, store.get("compile_slot")):
        path = compile_dataset(config, teacher_for(config, stack), store)
        render_report(path, config.tenant, store.get("last_training"))
        store.put("compile_slot", compilation.isoformat())
    slot = training_slot(now, config)
    once_done = config.cadence == "once" and store.get("training_slot") is not None
    if config.auto_train and not once_done and is_due(slot, store.get("training_slot")):
        path = store.get("latest_dataset")
        if path:
            result = train(config, Path(path), store, stack)
            render_report(Path(path), config.tenant, result)
            store.put("training_slot", slot.isoformat())
            return {"training": result["gate"], "dataset": path}
    return {"dataset": store.get("latest_dataset"), "training": "not_due_or_disabled"}


def install_schedule(config: Config, config_path: Path, install: bool) -> dict:
    folder = config.workspace / "scheduler"
    folder.mkdir(parents=True, exist_ok=True)
    if platform.system() == "Darwin":
        name = f"io.gm.{config.tenant}.plist"
        rendered = folder / name
        rendered.write_bytes(launchd_plist(config_path, config))
        if install:
            target = Path.home() / "Library/LaunchAgents" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ValueError(
                    "Schedule already installed; unload and remove it before reinstalling"
                )
            target.write_bytes(rendered.read_bytes())
            try:
                subprocess.run(
                    ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)], check=True
                )
            except Exception:
                target.unlink(missing_ok=True)
                raise
        return {
            "file": str(rendered),
            "installed": install,
            "note": "River runs need RIVER_API_KEY available to the launchd user environment.",
        }
    service, timer = systemd_units(config_path, config)
    name = f"gm-nightly-{config.tenant}"
    (folder / f"{name}.service").write_text(service)
    (folder / f"{name}.timer").write_text(timer)
    if install:
        target = Path.home() / ".config/systemd/user"
        target.mkdir(parents=True, exist_ok=True)
        destinations = [target / f"{name}.{suffix}" for suffix in ("service", "timer")]
        if any(p.exists() for p in destinations):
            raise ValueError("Schedule already installed; remove existing units first")
        for destination in destinations:
            destination.write_text((folder / destination.name).read_text())
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", f"{name}.timer"], check=True)
    return {"directory": str(folder), "installed": install}


def main(argv=None) -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(
        prog="gm-nightly", description="Run GM's nightly company learning loop."
    )
    parser.add_argument("--config", default="gm-nightly.toml")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser(
        "demo", help="Compile synthetic company memories without credentials"
    )
    demo.add_argument("--output", type=Path, default=Path(".gm/demo"))
    commands.add_parser("compile", help="Build and verify SFT, RL and evaluation datasets")
    commands.add_parser("run", help="Compile, train, evaluate and apply the promotion gate")
    collect_command = commands.add_parser(
        "collect", help="Export approved local sources for the company coordinator"
    )
    collect_command.add_argument("--output", type=Path, required=True)
    commands.add_parser("train", help="Train and evaluate using River (incurs provider usage)")
    commands.add_parser("tick", help="Run work due under the configured schedule")
    commands.add_parser("status", help="Show company pipeline status")
    commands.add_parser("report", help="Render the latest dataset inspection page")
    commands.add_parser("models", help="List models enabled on your River account")
    schedule = commands.add_parser("schedule", help="Render or install the laptop scheduler")
    schedule.add_argument("--install", action="store_true")
    recover = commands.add_parser("recover", help="Clear an uncertain attempt after checking River")
    recover.add_argument("--acknowledge-remote-state", action="store_true")
    for role in ("employee", "server"):
        group = commands.add_parser(role, help=f"Install or run the {role} component")
        actions = group.add_subparsers(dest="action", required=True)
        install = actions.add_parser("install", help="Quick terminal onboarding")
        install.add_argument("--company")
        install.add_argument("--company-url")
        install.add_argument("--output", type=Path)
        install.add_argument("--gbrain-home", default="")
        install.add_argument("--gbrain-binary", default="gbrain")
        install.add_argument("--source", default="shared")
        if role == "employee":
            install.add_argument("--employee-id")
            install.add_argument("--credentials", type=Path)
            install.add_argument("--share-project", action="append", default=[])
            install.add_argument("--app-settings", type=Path)
            watch = actions.add_parser("watch")
            watch.add_argument("--once", action="store_true")
            watch.add_argument(
                "--force", action="store_true", help="Skip the quiet-session debounce"
            )
            actions.add_parser("relay")
            actions.add_parser("pause")
            actions.add_parser("resume")
        else:
            install.add_argument(
                "--cadence", choices=["nightly", "weekly", "monthly", "manual"], default="nightly"
            )
            install.add_argument("--timezone", default="UTC")
            install.add_argument("--remote", action="store_true")
            invite = actions.add_parser("invite")
            invite.add_argument("employee_id")
            invite.add_argument("--output", type=Path, required=True)
            serve = actions.add_parser("serve")
            serve.add_argument("--host", default="127.0.0.1")
            serve.add_argument("--port", type=int, default=8787)
            serve.add_argument("--no-worker", action="store_true")
            actions.add_parser("tick")
            actions.add_parser("train")
    args = parser.parse_args(argv)
    try:
        if args.command in {"employee", "server"}:
            from .employee import load_credentials, relay
            from .gbrain import Gbrain
            from .onboarding import employee_install, invite, server_install
            from .runtime import run_worker

            if args.action == "install":
                result = (
                    employee_install(args) if args.command == "employee" else server_install(args)
                )
            else:
                config = load_config(args.config)
                load_credentials(config)
                if config.role != args.command:
                    raise ValueError("This profile belongs to a different installation role")
                if args.action == "watch":
                    result = run_worker(config, once=args.once, force=args.force)
                elif args.action == "serve":
                    from .server import serve

                    serve(config, args.host, args.port, not args.no_worker)
                    return 0
                elif args.action in {"pause", "resume"}:
                    config.workspace.mkdir(parents=True, exist_ok=True)
                    marker = config.workspace / "paused"
                    marker.touch() if args.action == "pause" else marker.unlink(missing_ok=True)
                    result = {"state": args.action}
                elif args.action == "invite":
                    result = invite(config, args.employee_id, args.output)
                elif args.action == "train":
                    return main(["--config", args.config, "run"])
                elif args.action == "tick":
                    result = run_worker(config, once=True)
                else:
                    with workspace_lock(config.workspace):
                        store = Store(config.workspace)
                        try:
                            result = relay(
                                config,
                                Gbrain(
                                    config.gbrain_command, config.gbrain_home, config.gbrain_source
                                ),
                                Gbrain(
                                    config.gbrain_command,
                                    config.company_home,
                                    config.company_source,
                                    remote=True,
                                ),
                                store,
                            )
                        finally:
                            store.close()
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "models":
            from .providers.river import river_client

            client = river_client()
            try:
                result = {"models": list(client.get_capabilities())}
            finally:
                client.close()
        else:
            config_path = (
                create_demo(args.output.resolve()) if args.command == "demo" else Path(args.config)
            )
            config = load_config(config_path)
            from .employee import load_credentials

            load_credentials(config)
            if config.role == "employee" and args.command in {
                "compile",
                "run",
                "train",
                "tick",
                "collect",
            }:
                raise ValueError(
                    "Employee profiles capture and relay only; use the company server to generate datasets or train"
                )
            with workspace_lock(config.workspace), ExitStack() as stack:
                store = Store(config.workspace)
                stack.callback(store.close)
                if args.command in {"demo", "compile", "run"}:
                    path = compile_dataset(config, teacher_for(config, stack), store)
                    report = render_report(path, config.tenant, store.get("last_training"))
                    manifest, _ = load_dataset(path, config.tenant)
                    result = {
                        "dataset": str(path),
                        "report": str(report),
                        "counts": manifest["counts"],
                        "demo": manifest["demo"],
                    }
                    if args.command == "run":
                        result = train(config, path, store, stack)
                        render_report(path, config.tenant, result)
                elif args.command == "tick":
                    result = tick(config, store, stack)
                elif args.command == "collect":
                    from dataclasses import asdict

                    from .pipeline import write_jsonl
                    from .privacy import rejection_reason
                    from .sources import collect

                    records = [
                        m for source in config.sources for m in collect(source, config.tenant)
                    ]
                    approved = [
                        asdict(m)
                        for m in records
                        if rejection_reason(m, config.tenant, config.max_source_chars) is None
                    ]
                    if args.output.exists():
                        raise ValueError(
                            "Collection output already exists; choose a new snapshot filename"
                        )
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    write_jsonl(args.output, approved)
                    result = {
                        "output": str(args.output.resolve()),
                        "approved": len(approved),
                        "excluded": len(records) - len(approved),
                    }
                elif args.command == "schedule":
                    result = install_schedule(config, config_path, args.install)
                elif args.command == "status":
                    result = {
                        k: store.get(k)
                        for k in ("latest_dataset", "last_compile", "active_training", "promoted")
                    }
                elif args.command == "recover":
                    if not args.acknowledge_remote_state:
                        raise ValueError(
                            "Inspect the prior run in River, then use --acknowledge-remote-state"
                        )
                    previous = store.get("active_training")
                    store.put("active_training", None)
                    result = {
                        "cleared": previous,
                        "note": "A new train command may incur additional usage.",
                    }
                else:
                    path = store.get("latest_dataset")
                    if not path:
                        raise ValueError("No dataset yet. Run compile first.")
                    if args.command == "train":
                        result = train(config, Path(path), store, stack)
                    else:
                        result = {
                            "report": str(
                                render_report(Path(path), config.tenant, store.get("last_training"))
                            )
                        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (
        OSError,
        ValueError,
        RuntimeError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"gm-nightly: {exc}", file=sys.stderr)
        return 1
