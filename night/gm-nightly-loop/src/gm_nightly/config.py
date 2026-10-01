from __future__ import annotations

import math
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass
class Config:
    tenant: str = "demo-company"
    role: str = "standalone"
    employee_id: str = ""
    server_url: str = ""
    credentials_file: str = ""
    shared_projects: list[str] = field(default_factory=list)
    capture_sources: list[dict] = field(default_factory=list)
    memory_compiler: str = "extractive"
    local_model: str = ""
    local_model_url: str = "http://127.0.0.1:11434/v1/chat/completions"
    poll_seconds: int = 5
    quiet_seconds: int = 15
    gbrain_command: list[str] = field(default_factory=lambda: ["gbrain"])
    gbrain_home: str = ""
    gbrain_source: str = "default"
    company_home: str = ""
    company_source: str = "shared"
    share_tag: str = "finegrain-share"
    gbrain_ingest: bool = True
    state_dir: Path = Path(".gm/nightly")
    teacher: str = "demo"
    teacher_model: str = "nvidia/Kimi-K2.6-NVFP4"
    critic_model: str = "nvidia/GLM-5.2-NVFP4"
    student_model: str = "Qwen/Qwen3.5-9B"
    foundation_checkpoint: str = ""
    sources: list[dict] = field(default_factory=list)
    provider: str = "river"
    cadence: str = "weekly"
    timezone: str = "UTC"
    hour: int = 2
    weekday: int = 0
    monthday: int = 1
    auto_train: bool = False
    experimental_sessions: bool = False
    holdout_fraction: float = 0.2
    min_eval_tasks: int = 4
    min_score: float = 0.8
    max_regression: float = 0.02
    min_recall_gain: float = 0.05
    max_confident_wrong_increase: float = 0.0
    max_general_regression: float = 0.03
    min_train_tasks: int = 4
    max_memories: int = 100
    max_source_chars: int = 16000
    max_generation_tokens: int = 8192
    sft_epochs: int = 1
    batch_size: int = 4
    rl_steps: int = 2
    group_size: int = 4
    learning_rate: float = 0.0001
    rl_learning_rate: float = 0.00001
    lora_rank: int = 16
    max_tokens: int = 1024
    max_context_tokens: int = 8192

    def validate(self) -> Config:
        if self.role not in {"standalone", "employee", "server"}:
            raise ValueError("Invalid installation role")
        if self.memory_compiler not in {"extractive", "local-model"}:
            raise ValueError("Memory compiler must run locally")
        if not self.gbrain_command or not all(
            isinstance(x, str) and x for x in self.gbrain_command
        ):
            raise ValueError("gbrain_command must be an argv list")
        if self.poll_seconds < 1 or self.quiet_seconds < 0:
            raise ValueError("Invalid capture interval")
        if not isinstance(self.shared_projects, list) or any(
            not isinstance(p, str) or not Path(p).expanduser().is_absolute()
            for p in self.shared_projects
        ):
            raise ValueError("Shared projects must be absolute folder paths")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", self.tenant):
            raise ValueError("tenant must be a simple identifier")
        if self.teacher not in {"river", "demo"} or self.provider != "river":
            raise ValueError("This release supports River, plus an offline demo teacher")
        if not isinstance(self.foundation_checkpoint, str):
            raise ValueError("foundation_checkpoint must be a string")
        if self.cadence not in {"once", "nightly", "weekly", "monthly", "manual"}:
            raise ValueError("Unknown training cadence")
        ZoneInfo(self.timezone)
        if type(self.auto_train) is not bool or type(self.experimental_sessions) is not bool:
            raise ValueError("auto_train and experimental_sessions must be booleans")
        if self.auto_train and self.teacher == "demo":
            raise ValueError("Demo artifacts cannot enable automatic training")
        for name, low, high in [
            ("hour", 0, 23),
            ("weekday", 0, 6),
            ("monthday", 1, 28),
            ("lora_rank", 1, 32),
            ("group_size", 2, 32),
        ]:
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"Invalid {name}")
        for name in (
            "min_eval_tasks",
            "min_train_tasks",
            "max_memories",
            "max_source_chars",
            "max_generation_tokens",
            "sft_epochs",
            "batch_size",
            "max_tokens",
            "max_context_tokens",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.rl_steps) is not int or self.rl_steps < 0:
            raise ValueError("rl_steps must be nonnegative")
        for name in (
            "holdout_fraction",
            "min_score",
            "max_regression",
            "min_recall_gain",
            "max_confident_wrong_increase",
            "max_general_regression",
            "learning_rate",
            "rl_learning_rate",
        ):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"Invalid {name}")
        if self.holdout_fraction >= 1 or min(self.learning_rate, self.rl_learning_rate) <= 0:
            raise ValueError("Holdout must be <1 and learning rates must be positive")
        if self.min_recall_gain <= 0:
            raise ValueError("min_recall_gain must be positive")
        if self.max_tokens >= self.max_context_tokens:
            raise ValueError("max_tokens must be less than max_context_tokens")
        names = [s.get("name") for s in self.sources]
        if len(set(names)) != len(names) or any(not isinstance(n, str) or not n for n in names):
            raise ValueError("Every source needs a unique name")
        for source in self.sources:
            if type(source.get("training_allowed", False)) is not bool:
                raise ValueError("Source training_allowed must be a boolean")
        return self

    @property
    def workspace(self) -> Path:
        return self.state_dir / self.tenant


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    data = tomllib.loads(path.read_text())
    flat = dict(data.get("gm", {}))
    for section in (
        "generation",
        "training",
        "schedule",
        "quality",
        "delivery",
        "capture",
        "gbrain",
    ):
        flat.update(data.get(section, {}))
    flat["sources"] = data.get("sources", [])
    # GM Part 1 publishes the River base model and training checkpoint through its
    # environment contract. Explicit environment values take precedence so the
    # checkpoint never needs to be committed to a configuration file.
    if os.environ.get("GM_BASE_MODEL"):
        flat["student_model"] = os.environ["GM_BASE_MODEL"]
    if os.environ.get("GM_CHECKPOINT"):
        flat["foundation_checkpoint"] = os.environ["GM_CHECKPOINT"]
    if os.environ.get("GM_LORA_RANK"):
        try:
            flat["lora_rank"] = int(os.environ["GM_LORA_RANK"])
        except ValueError:
            raise ValueError("GM_LORA_RANK must be an integer") from None
    state = Path(flat.get("state_dir", ".gm/nightly")).expanduser()
    flat["state_dir"] = state if state.is_absolute() else path.parent / state
    if flat.get("credentials_file"):
        p = Path(flat["credentials_file"]).expanduser()
        flat["credentials_file"] = str(p if p.is_absolute() else path.parent / p)
    for source in flat["sources"]:
        for key in ("path", "previous_path"):
            if key in source:
                p = Path(source[key]).expanduser()
                source[key] = str(p if p.is_absolute() else path.parent / p)
    return Config(**flat).validate()
