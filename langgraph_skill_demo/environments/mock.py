"""Independent integration fixture."""
from core.contracts import Action, Snapshot, ValidationResult

class MockEnvironment:
    """Clearly labeled three-action fixture for local integration checks."""

    def __init__(self):
        self._position = 0
        self._done = False

    def reset(self) -> Snapshot:
        self._position = 0
        self._done = False
        return self._snapshot()

    def _snapshot(self) -> Snapshot:
        observations = ["You see a table and a basket.", "You are at the table. An apple is here.", "You hold the apple.", "The apple is in the basket."]
        actions = [["go to table"], ["take apple from table"], ["put apple in basket"], []]
        return Snapshot("put an apple in the basket", observations[self._position], actions[self._position],
                        "mock-apple", "mock", self._done, self._done, float(self._done))

    def validate_action(self, action: Action) -> ValidationResult:
        valid = isinstance(action, str) and action in self._snapshot().allowed_actions
        return ValidationResult(valid, "" if valid else "Invalid mock action")

    def step(self, action: str) -> Snapshot:
        if self._done or action not in self._snapshot().allowed_actions:
            raise ValueError(f"模拟环境不接受动作: {action}")
        self._position += 1
        self._done = self._position == 3
        return self._snapshot()

    def close(self) -> None:
        pass
