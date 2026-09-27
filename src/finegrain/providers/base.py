from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRef:
    provider: str
    base_model: str
    checkpoint: str | None = None


@dataclass
class TrainResult:
    model: ModelRef
    metrics: dict


RewardFn = Callable[[dict, str], float]


class TrainingProvider(ABC):
    name: str

    @abstractmethod
    def list_base_models(self) -> list[str]: ...

    @abstractmethod
    def sample(
        self,
        model: ModelRef,
        prompts: list[list[dict]],
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> list[str]: ...

    @abstractmethod
    def train_sft(
        self, base: ModelRef, examples_path: str, lora_rank: int, epochs: int, learning_rate: float
    ) -> TrainResult: ...

    @abstractmethod
    def train_rl(
        self,
        start: ModelRef,
        tasks_path: str,
        reward_fn: RewardFn,
        steps: int,
        group_size: int,
        learning_rate: float,
    ) -> TrainResult: ...
