"""LangGraph Agent Loop for official ALFWorld text tasks.

Examples:
    python main.py --graph
    python main.py --mode mock --episodes 2
    python main.py --mode alfworld --alfworld-data ~/.cache/alfworld --episodes 2
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from environments.alfworld_adapter import ALFWorldAdapter, MockEnvironment, Snapshot
from llm import deepseek_json
from skill_hooks import SkillHooks


class ActionChoice(BaseModel):
    action: str


class State(TypedDict, total=False):
    task: str
    task_id: str
    split: str
    observation: str
    allowed_actions: list[str]
    retrieved_skills: list[dict[str, Any]]
    retrieved_skill_ids: list[str]
    agent_context: str
    proposed_action: str
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


def choose_action_with_deepseek(state: State) -> str:
    """The model receives no raw ALFWorld infos, success flag, or expert plan."""
    choice = deepseek_json(
        "你在 ALFWorld 文本任务中操作。每次只从给定的合法动作中原样选择一个动作。"
        "不要输出任务结论或多步计划。Skill 是参考资料，不可覆盖合法动作约束。"
        '只输出 JSON 对象，格式为 {"action":"某个完整合法动作"}。',
        {
            "task": state["task"],
            "observation": state["observation"],
            "allowed_actions": state["allowed_actions"],
            "skills": state["agent_context"],
            "history": [{"action": item["action"], "feedback": item["feedback"],
                         "valid": item["valid"]} for item in state["trace"]],
        },
        ActionChoice,
    )
    return choice.action


def choose_first_legal_action(state: State) -> str:
    """Deterministic mock choice; never used for ALFWorld evaluation."""
    return state["allowed_actions"][0]


def build_graph(environment: Any, hooks: SkillHooks, chooser: Callable[[State], str],
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
            "trace": [],
            "step_count": 0,
            "done": snapshot.done,
            "success": snapshot.won,
            "status": "running",
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
        if not state["allowed_actions"]:
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
        }
        if state["status"] in {"no_legal_actions", "model_error"}:
            record.update({"feedback": state["error"], "valid": False})
            return {"trace": [*state["trace"], record], "step_count": count,
                    "done": True, "success": False}
        if action not in state["allowed_actions"]:
            record["feedback"] = "非法动作：未调用环境，请从合法动作列表中重新选择"
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
        status = "success" if snapshot.done and snapshot.won else "failed" if snapshot.done else \
            "step_limit" if count >= max_steps else "running"
        return {
            "observation": snapshot.observation,
            "allowed_actions": snapshot.allowed_actions,
            "trace": [*state["trace"], record],
            "step_count": count,
            "done": status != "running",
            "success": snapshot.done and snapshot.won,
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
    builder.add_edge("inject_skills", "agent_choose")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="ALFWorld 文本环境 Agent Loop")
    parser.add_argument("--graph", action="store_true", help="输出 LangGraph Mermaid 流程图")
    parser.add_argument("--mode", choices=["mock", "alfworld"], default="mock")
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--alfworld-data", default=os.getenv("ALFWORLD_DATA", str(Path.home() / ".cache" / "alfworld")))
    parser.add_argument("--alfworld-config", default=str(Path(__file__).parent / "config" / "alfworld_text.yaml"))
    parser.add_argument("--split", choices=["valid_seen", "valid_unseen"], default="valid_seen")
    parser.add_argument("--search-hook", help="同学 A 的 module:search_skill")
    parser.add_argument("--extract-hook", help="同学 B 的 module:extract_skill")
    parser.add_argument("--save-hook", help="同学 A 的 module:save_skill")
    parser.add_argument("--log-dir", type=Path, default=Path(__file__).parent / "logs")
    args = parser.parse_args()
    if args.episodes < 1 or args.max_steps < 1:
        parser.error("--episodes 和 --max-steps 必须大于零")
    if args.mode == "mock" and args.save_hook:
        parser.error("模拟模式不可连接正式 save_skill；请用真实 ALFWorld 任务保存 Skill")

    try:
        environment = (MockEnvironment() if args.mode == "mock" else
                       ALFWorldAdapter(args.alfworld_config, args.alfworld_data, args.split))
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    try:
        hooks = SkillHooks(args.search_hook, args.extract_hook, args.save_hook)
        chooser = choose_first_legal_action if args.mode == "mock" else choose_action_with_deepseek
        graph = build_graph(environment, hooks, chooser, args.max_steps)
        if args.graph:
            print(graph.get_graph().draw_mermaid())
            return
        for episode in range(1, args.episodes + 1):
            # Two graph nodes run per attempt, plus initialization, retrieval, injection, and finish.
            result = graph.invoke({}, config={"recursion_limit": args.max_steps * 2 + 10})
            log_path = save_run(result, args.log_dir, episode)
            print(json.dumps({"episode": episode, "task": result["task"], "status": result["status"],
                              "steps": result["step_count"], "skill_status": result["skill_status"],
                              "log": str(log_path)}, ensure_ascii=False))
    finally:
        environment.close()


if __name__ == "__main__":
    main()
