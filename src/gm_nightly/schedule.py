from __future__ import annotations

import plistlib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Config


def compilation_slot(now: datetime, config: Config) -> datetime:
    if now.tzinfo is None:
        raise ValueError("Scheduler requires timezone-aware timestamps")
    local = now.astimezone(ZoneInfo(config.timezone))
    slot = local.replace(hour=config.hour, minute=0, second=0, microsecond=0, fold=0)
    return slot if local >= slot else slot - timedelta(days=1)


def training_slot(now: datetime, config: Config) -> datetime | None:
    if config.cadence == "manual":
        return None
    slot = compilation_slot(now, config)
    if config.cadence == "weekly":
        slot -= timedelta(days=(slot.weekday() - config.weekday) % 7)
    elif config.cadence == "monthly":
        if slot.day < config.monthday:
            slot = slot.replace(day=1) - timedelta(days=1)
        slot = slot.replace(day=config.monthday)
    return slot


def is_due(slot: datetime | None, last: str | None) -> bool:
    return slot is not None and (last is None or datetime.fromisoformat(last) < slot)


def launchd_plist(config_path: Path, config: Config, python: str | None = None) -> bytes:
    # Hourly wake checks catch missed nights after sleep. The app determines the configured local slot.
    python = python or sys.executable
    return plistlib.dumps(
        {
            "Label": f"io.gm.{config.tenant}",
            "ProgramArguments": [
                python,
                "-m",
                "gm-nightly",
                "--config",
                str(config_path.resolve()),
                "tick",
            ],
            "StartInterval": 3600,
            "RunAtLoad": True,
            "WorkingDirectory": str(config_path.resolve().parent),
            "StandardOutPath": str(config.workspace.resolve() / "scheduler.log"),
            "StandardErrorPath": str(config.workspace.resolve() / "scheduler-error.log"),
        }
    )


def systemd_units(config_path: Path, config: Config, python: str | None = None) -> tuple[str, str]:
    def quote(value: str) -> str:
        # systemd specifier and environment expansion apply even inside quotes.
        return (
            '"'
            + value.replace("%", "%%").replace("$", "$$").replace("\\", "\\\\").replace('"', '\\"')
            + '"'
        )

    args = [
        python or sys.executable,
        "-m",
        "gm-nightly",
        "--config",
        str(config_path.resolve()),
        "tick",
    ]
    service = (
        "[Unit]\nDescription=GM Nightly Loop memory compiler\n[Service]\nType=oneshot\n"
        + "ExecStart="
        + " ".join(quote(a) for a in args)
        + "\n"
        + "EnvironmentFile=%h/.config/gm-nightly/environment\n"
    )
    timer = (
        "[Unit]\nDescription=Check GM Nightly Loop nightly schedule\n[Timer]\nOnCalendar=hourly\nPersistent=true\n"
        + f"Unit=gm-nightly-{config.tenant}.service\n[Install]\nWantedBy=timers.target\n"
    )
    return service, timer
