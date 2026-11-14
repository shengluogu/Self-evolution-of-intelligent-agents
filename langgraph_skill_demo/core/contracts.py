"""Environment-neutral contracts; legacy snapshot fields remain compatible."""
from dataclasses import dataclass, field
from typing import Any, Protocol

Action = str | dict[str, Any]

@dataclass(frozen=True)
class Snapshot:
    task: str
    observation: str
    allowed_actions: list[str] = field(default_factory=list)
    task_id: str = ""
    split: str = ""
    done: bool = False
    won: bool = False
    reward: float = 0.0
    terminated: bool = False
    truncated: bool = False
    action_spec: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.won

    @property
    def finished(self) -> bool:
        return self.done or self.terminated or self.truncated


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str = ""

class Environment(Protocol):
    def reset(self) -> Snapshot: ...
    def validate_action(self, action: Action) -> ValidationResult: ...
    def step(self, action: Action) -> Snapshot: ...
    def close(self) -> None: ...
