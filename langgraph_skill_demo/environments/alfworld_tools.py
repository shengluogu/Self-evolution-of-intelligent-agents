"""ALFWorld commands bound to one native environment instance."""
from core.contracts import Action, ValidationResult

class ALFWorldTools:
    def __init__(self, environment):
        self._env = environment
        self._commands = []

    def update(self, commands):
        self._commands = list(commands)

    def action_spec(self):
        return {"tools": [{"name": "execute", "description": "Execute a current admissible command",
                "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                               "required": ["command"], "additionalProperties": False}}],
                "format": {"tool": "execute", "command": "exact allowed_actions entry"}}

    def validate(self, action: Action) -> ValidationResult:
        if isinstance(action, str):
            command = action
        elif isinstance(action, dict) and set(action) == {"tool", "command"} and action["tool"] == "execute":
            command = action["command"]
        else:
            return ValidationResult(False, "Expected execute(command)")
        valid = isinstance(command, str) and command in self._commands
        return ValidationResult(valid, "" if valid else "Choose a current admissible command")

    def execute(self, action: Action):
        validation = self.validate(action)
        if not validation.valid:
            raise ValueError(validation.reason)
        command = action if isinstance(action, str) else action["command"]
        return self._env.step([command])
