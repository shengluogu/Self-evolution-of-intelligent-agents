"""CLI assembly. Environment, agent and skill components are independent."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from core.runner import State, build_graph, save_run
from environments.factory import create_environment
from policies.llm_policy import ActionChoice, choose_action_with_deepseek, choose_first_legal_action
from skill_hooks import SkillHooks

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
    parser.add_argument("--skills-dir", type=Path, help="Independent skill library directory")
    args = parser.parse_args()
    if args.episodes < 1 or args.max_steps < 1:
        parser.error("--episodes 和 --max-steps 必须大于零")
    if args.mode == "mock" and args.save_hook:
        parser.error("模拟模式不可连接正式 save_skill；请用真实 ALFWorld 任务保存 Skill")

    if args.skills_dir:
        from skill_tools import store
        store.configure(args.skills_dir)
    if args.graph:
        from environments.mock import MockEnvironment
        graph = build_graph(MockEnvironment(), SkillHooks(), choose_first_legal_action, args.max_steps)
        print(graph.get_graph().draw_mermaid())
        return
    try:
        environment = create_environment(args.mode, config_path=args.alfworld_config,
                                         data_dir=args.alfworld_data, split=args.split)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    try:
        hooks = SkillHooks(args.search_hook, args.extract_hook, args.save_hook)
        chooser = choose_first_legal_action if args.mode == "mock" else choose_action_with_deepseek
        graph = build_graph(environment, hooks, chooser, args.max_steps)
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
