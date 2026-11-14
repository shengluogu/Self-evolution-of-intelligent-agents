"""MiniWoB interactions bound to one native environment; no global registry."""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, StrictBool, ValidationError
from core.contracts import ValidationResult

class Click(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["click"]
    ref: StrictInt

class TypeText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["type_text"]
    ref: StrictInt
    text: StrictStr
    clear: StrictBool = False

class PressKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["press_key"]
    key: StrictStr

MODELS = {"click": Click, "type_text": TypeText, "press_key": PressKey}
DOM_KEYS = ("ref", "parent", "tag", "text", "value", "id", "classes", "type", "flags",
            "left", "top", "width", "height", "bg_color", "fg_color")

def json_value(value):
    if hasattr(value, "tolist"): return value.tolist()
    if isinstance(value, dict): return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [json_value(v) for v in value]
    return value

class MiniWoBTools:
    def __init__(self, environment):
        self._env = environment
        self._observation = {"dom_elements": ()}
        self.native_actions = []

    def update(self, observation):
        self._observation = observation

    def get_dom(self):
        return [{key: json_value(element[key]) for key in DOM_KEYS if key in element}
                for element in self._observation["dom_elements"]]

    def action_spec(self):
        return {"tools": [{"name": name, "parameters": model.model_json_schema()}
                          for name, model in MODELS.items()],
                "format": {"tool": "click", "ref": 1},
                "allowed_keys": list(self._env.unwrapped.action_space_config.allowed_keys),
                "instruction": "Choose one listed tool. type_text appends by default; clear=true replaces. "
                               "Use refs from the latest DOM. clear=true may perform multiple native actions."}

    def validate(self, action):
        if not isinstance(action, dict) or not isinstance(action.get("tool"), str) or action["tool"] not in MODELS:
            return ValidationResult(False, "Choose click, type_text or press_key")
        try:
            parsed = MODELS[action["tool"]].model_validate(action)
        except ValidationError as exc:
            return ValidationResult(False, str(exc))
        config = self._env.unwrapped.action_space_config
        if hasattr(parsed, "ref"):
            elements = {int(e["ref"]): e for e in self._observation["dom_elements"]}
            if parsed.ref not in elements:
                return ValidationResult(False, "Unknown ref in current DOM; inspect the latest observation")
            if parsed.tool == "type_text" and elements[parsed.ref].get("tag", "").lower() not in ("input", "textarea"):
                return ValidationResult(False, "type_text requires an input or textarea")
        if parsed.tool == "type_text" and len(parsed.text) > config.text_max_len:
            return ValidationResult(False, "Text exceeds configured maximum length")
        if parsed.tool == "press_key" and parsed.key not in config.allowed_keys:
            return ValidationResult(False, "Key is not in allowed_keys")
        return ValidationResult(True)

    def execute(self, action):
        validation = self.validate(action)
        if not validation.valid: raise ValueError(validation.reason)
        from miniwob.action import ActionTypes
        commands = []
        if action["tool"] == "click":
            commands = [(ActionTypes.CLICK_ELEMENT, {"ref": action["ref"]})]
        elif action["tool"] == "press_key":
            commands = [(ActionTypes.PRESS_KEY, {"key": self._env.unwrapped.action_space_config.allowed_keys.index(action["key"])})]
        elif action.get("clear", False):
            keys = self._env.unwrapped.action_space_config.allowed_keys
            commands = [(ActionTypes.CLICK_ELEMENT, {"ref": action["ref"]}),
                        (ActionTypes.PRESS_KEY, {"key": keys.index("C-a")}),
                        (ActionTypes.PRESS_KEY, {"key": keys.index("<Backspace>")}),
                        (ActionTypes.TYPE_TEXT, {"text": action["text"]})]
        else:
            commands = [(ActionTypes.FOCUS_ELEMENT_AND_TYPE_TEXT, {"ref": action["ref"], "text": action["text"]})]
        self.native_actions = []
        for kind, kwargs in commands:
            result = self._env.step(self._env.unwrapped.create_action(kind, **kwargs))
            self.native_actions.append({"type": kind.name, **kwargs})
            self.update(result[0])
            if result[2] or result[3]: break
        return result
