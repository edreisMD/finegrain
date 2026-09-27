import plistlib
from contextlib import ExitStack
from datetime import datetime

import pytest

from gm_nightly.cli import tick
from gm_nightly.schedule import (
    compilation_slot,
    is_due,
    launchd_plist,
    systemd_units,
    training_slot,
)


@pytest.mark.parametrize(
    "cadence,now,expected",
    [
        ("nightly", "2026-09-27T01:00:00+00:00", "2026-09-26T02:00:00+00:00"),
        ("nightly", "2026-09-27T03:00:00+00:00", "2026-09-27T02:00:00+00:00"),
        ("weekly", "2026-09-27T03:00:00+00:00", "2026-09-21T02:00:00+00:00"),
        ("monthly", "2026-09-27T03:00:00+00:00", "2026-09-01T02:00:00+00:00"),
        ("monthly", "2026-01-01T01:00:00+00:00", "2025-12-01T02:00:00+00:00"),
        ("once", "2026-09-27T03:00:00+00:00", "2026-09-27T02:00:00+00:00"),
        ("manual", "2026-09-27T03:00:00+00:00", None),
    ],
)
def test_calendar_cadences(config, cadence, now, expected):
    config.cadence = cadence
    actual = training_slot(datetime.fromisoformat(now), config)
    assert (actual.isoformat() if actual else None) == expected


def test_dst_fallback_does_not_repeat_a_night(config):
    config.timezone = "America/Los_Angeles"
    config.hour = 1
    first = compilation_slot(datetime.fromisoformat("2026-11-01T08:30:00+00:00"), config)
    second = compilation_slot(datetime.fromisoformat("2026-11-01T09:30:00+00:00"), config)
    assert not is_due(second, first.isoformat())


def test_dst_spring_catches_up(config):
    config.timezone = "America/Los_Angeles"
    slot = compilation_slot(datetime.fromisoformat("2026-03-08T10:30:00+00:00"), config)
    assert slot.date().isoformat() == "2026-03-08"


def test_tick_compiles_once_and_never_trains_demo(config, store):
    with ExitStack() as stack:
        now = datetime.fromisoformat("2026-09-27T03:00:00+00:00")
        first = tick(config, store, stack, now)
        last_compile = store.get("last_compile")
        second = tick(config, store, stack, now)
        assert first == second
        assert store.get("last_compile") == last_compile
        assert store.get("last_training") is None


def test_scheduler_config_paths_with_spaces(config, tmp_path):
    path = tmp_path / "company workspace" / "gm-nightly.toml"
    data = plistlib.loads(launchd_plist(path, config, "/my venv/bin/python"))
    assert data["ProgramArguments"][0] == "/my venv/bin/python"
    assert data["ProgramArguments"][4] == str(path)
    assert "RIVER_API_KEY" not in str(data)
    service, timer = systemd_units(path, config, "/my venv/bin/python")
    assert '"/my venv/bin/python"' in service
    assert "Persistent=true" in timer


@pytest.mark.parametrize(
    "field,value",
    [
        ("auto_train", "false"),
        ("hour", 24),
        ("holdout_fraction", 1),
        ("learning_rate", float("nan")),
        ("rl_steps", -1),
        ("group_size", 1),
        ("tenant", "../escape"),
        ("min_train_tasks", 0),
    ],
)
def test_bad_configuration_fails(config, field, value):
    setattr(config, field, value)
    with pytest.raises(ValueError):
        config.validate()
