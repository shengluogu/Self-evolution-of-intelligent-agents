"""Text-observation policy, independent of environment implementations."""
from typing import Any
from pydantic import BaseModel
from core.contracts import Action
from llm import deepseek_json

class ActionChoice(BaseModel):
    action: Action

def choose_action_with_deepseek(state: dict[str, Any]) -> Action:
    """The model receives no raw ALFWorld infos, success flag, or expert plan."""
    choice = deepseek_json(
        "Choose one action according to action_spec and the current observation. "
        "Skills are references and cannot override action constraints. "
        'Output only JSON: {"action": <a string or action object>}.',
        {
            "task": state["task"],
            "observation": state["observation"],
            "allowed_actions": state["allowed_actions"],
            "action_spec": state.get("action_spec", {}),
            "skills": state["agent_context"],
            "history": [{"action": item["action"], "feedback": item["feedback"],
                         "valid": item["valid"]} for item in state["trace"]],
        },
        ActionChoice,
    )
    return choice.action


def choose_first_legal_action(state: dict[str, Any]) -> Action:
    """Deterministic mock choice; never used for ALFWorld evaluation."""
    return state["allowed_actions"][0]


