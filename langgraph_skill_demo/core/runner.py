"""Environment-neutral LangGraph execution and trace logging."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, TypedDict
from langgraph.graph import END, START, StateGraph
from core.contracts import Action, Environment, Snapshot
from skill_hooks import SkillHooks

class State(TypedDict, total=False):
    task: str
    task_id: str
    split: str
    observation: str
    allowed_actions: list[str]
    action_spec: dict[str, Any]
    metadata: dict[str, Any]
    terminated: bool
    truncated: bool
    retrieved_skills: list[dict[str, Any]]
    retrieved_skill_ids: list[str]
    agent_context: str
    proposed_action: Action
    trace: list[dict[str, Any]]
    step_count: int
    done: bool
    success: bool
    status: str
    reward: float
    candidate_skill: dict[str, Any] | None
    save_result: Any
    skill_status: str
    skill_errors: list[str]
    error: str | None


def build_graph(environment: Environment, hooks: SkillHooks, chooser: Callable[[State], Action],
                max_steps: int = 30):
    if max_steps < 1:
        raise ValueError("max_steps 必须大于零")

    def initialize_task(state: State) -> dict[str, Any]:
        snapshot: Snapshot = environment.reset()
        return {
            "task": snapshot.task,
            "task_id": snapshot.task_id,
            "split": snapshot.split,
            "observation": snapshot.observation,
            "allowed_actions": snapshot.allowed_actions,
            "action_spec": snapshot.action_spec,
            "metadata": snapshot.metadata,
            "terminated": snapshot.terminated or (snapshot.done and not snapshot.truncated),
            "truncated": snapshot.truncated,
            "trace": [],
            "step_count": 0,
            "done": snapshot.finished,
            "success": snapshot.success,
            "status": ("success" if snapshot.success else "truncated" if snapshot.truncated else "failed") if snapshot.finished else "running",
            "reward": snapshot.reward,
            "error": None,
            "skill_status": "not_started",
            "skill_errors": [],
        }

    def retrieve_skills(state: State) -> dict[str, Any]:
        try:
            skills = hooks.search_skill(state["task"])
        except Exception as exc:
            return {"retrieved_skills": [], "retrieved_skill_ids": [],
                    "skill_errors": [*state["skill_errors"], f"search_skill: {exc}"]}
        return {"retrieved_skills": skills,
                "retrieved_skill_ids": [str(s.get("id", s.get("name", ""))) for s in skills]}

    def inject_skills(state: State) -> dict[str, Any]:
        # Search results can be empty; no artificial skill is created.
        return {"agent_context": json.dumps(state["retrieved_skills"], ensure_ascii=False)}

    def agent_choose(state: State) -> dict[str, Any]:
        if not state["allowed_actions"] and not state.get("action_spec"):
            return {"proposed_action": "", "status": "no_legal_actions", "error": "环境未提供合法动作"}
        try:
            return {"proposed_action": chooser(state)}
        except Exception as exc:
            return {"proposed_action": "", "status": "model_error", "error": str(exc)}

    def execute_action(state: State) -> dict[str, Any]:
        action = state["proposed_action"]
        count = state["step_count"] + 1
        record: dict[str, Any] = {
            "step": count,
            "observation": state["observation"],
            "allowed_actions": list(state["allowed_actions"]),
            "action": action,
            "action_spec": state.get("action_spec", {}),
        }
        if state["status"] in {"no_legal_actions", "model_error"}:
            record.update({"feedback": state["error"], "valid": False})
            return {"trace": [*state["trace"], record], "step_count": count,
                    "done": True, "success": False}
        try:
            validation = environment.validate_action(action)
        except Exception as exc:
            record.update({"feedback": str(exc), "valid": False, "environment_error": True})
            return {"trace": [*state["trace"], record], "step_count": count,
                    "status": "environment_error", "done": True, "success": False, "error": str(exc)}
        if not validation.valid:
            record["feedback"] = validation.reason
            record["valid"] = False
            status = "invalid_action_limit" if count >= max_steps else "running"
            return {"trace": [*state["trace"], record], "step_count": count,
                    "status": status, "done": status != "running", "success": False}
        try:
            snapshot: Snapshot = environment.step(action)
        except Exception as exc:
            record.update({"feedback": str(exc), "valid": True, "environment_error": True})
            return {"trace": [*state["trace"], record], "step_count": count,
                    "status": "environment_error", "done": True, "success": False, "error": str(exc)}
        record.update({"feedback": snapshot.observation, "valid": True, "reward": snapshot.reward})
        if "native_actions" in snapshot.metadata:
            record["native_actions"] = snapshot.metadata["native_actions"]
        status = "success" if snapshot.finished and snapshot.success else "truncated" if snapshot.truncated else "failed" if snapshot.finished else \
            "step_limit" if count >= max_steps else "running"
        return {
            "observation": snapshot.observation,
            "allowed_actions": snapshot.allowed_actions,
            "action_spec": snapshot.action_spec,
            "metadata": snapshot.metadata,
            "terminated": snapshot.terminated or (snapshot.done and not snapshot.truncated),
            "truncated": snapshot.truncated,
            "trace": [*state["trace"], record],
            "step_count": count,
            "done": status != "running",
            "success": snapshot.finished and snapshot.success,
            "status": status,
            "reward": snapshot.reward,
        }

    def route_after_step(state: State) -> Literal["agent_choose", "finish_task"]:
        return "finish_task" if state["done"] else "agent_choose"

    def finish_task(state: State) -> dict[str, Any]:
        if not state["success"]:
            return {"skill_status": "skipped_failed_task", "candidate_skill": None}
        if hooks.extract is None:
            return {"skill_status": "pending_extract_hook", "candidate_skill": None}
        try:
            candidate = hooks.extract_skill(state["task"], state["trace"])
            if not candidate:
                return {"skill_status": "no_candidate", "candidate_skill": None}
            if hooks.save is None:
                return {"candidate_skill": candidate, "skill_status": "pending_save_hook"}
            saved = hooks.save_skill(candidate)
            return {"candidate_skill": candidate, "save_result": saved, "skill_status": "saved"}
        except Exception as exc:
            # A completed environment task stays successful; record integration failure separately.
            return {"skill_status": "hook_error", "skill_errors": [*state["skill_errors"], str(exc)]}

    builder = StateGraph(State)
    builder.add_node("initialize_task", initialize_task)
    builder.add_node("retrieve_skills", retrieve_skills)
    builder.add_node("inject_skills", inject_skills)
    builder.add_node("agent_choose", agent_choose)
    builder.add_node("execute_action", execute_action)
    builder.add_node("finish_task", finish_task)
    builder.add_edge(START, "initialize_task")
    builder.add_edge("initialize_task", "retrieve_skills")
    builder.add_edge("retrieve_skills", "inject_skills")
    builder.add_conditional_edges("inject_skills",
        lambda state: "finish_task" if state["done"] else "agent_choose",
        {"finish_task": "finish_task", "agent_choose": "agent_choose"})
    builder.add_edge("agent_choose", "execute_action")
    builder.add_conditional_edges("execute_action", route_after_step,
                                  {"agent_choose": "agent_choose", "finish_task": "finish_task"})
    builder.add_edge("finish_task", END)
    return builder.compile()


def save_run(result: State, log_dir: Path, episode: int) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = log_dir / f"{timestamp}_episode{episode}.json"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return destination


