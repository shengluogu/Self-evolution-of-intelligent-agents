"""Behavioral checks for the loop and the A/B integration boundary."""

import unittest
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

from environments.alfworld_adapter import ALFWorldAdapter, MockEnvironment, Snapshot
from main import build_graph, choose_first_legal_action
from skill_hooks import SkillHooks


class CountingEnvironment(MockEnvironment):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def step(self, action):
        self.calls += 1
        return super().step(action)


class FailedEnvironment:
    def validate_action(self, action):
        from core.contracts import ValidationResult
        return ValidationResult(action == "go to table")

    def reset(self):
        return Snapshot("put an apple in the basket", "You see a table.", ["go to table"], "failed-1", "mock")

    def step(self, action):
        return Snapshot("put an apple in the basket", "The attempt failed.", [], "failed-1", "mock", True, False)


class AgentLoopTests(unittest.TestCase):
    def test_three_actions_and_full_trace(self):
        result = build_graph(MockEnvironment(), SkillHooks(), choose_first_legal_action).invoke({})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["step_count"], 3)
        self.assertEqual([item["action"] for item in result["trace"]],
                         ["go to table", "take apple from table", "put apple in basket"])
        self.assertEqual(result["skill_status"], "pending_extract_hook")

    def test_illegal_action_never_reaches_environment(self):
        environment = CountingEnvironment()

        def choose(state):
            return "invented action" if state["step_count"] == 0 else state["allowed_actions"][0]

        result = build_graph(environment, SkillHooks(), choose, max_steps=4).invoke({})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["step_count"], 4)
        self.assertEqual(environment.calls, 3)
        self.assertFalse(result["trace"][0]["valid"])

    def test_failed_task_does_not_extract_or_save(self):
        hooks = SkillHooks()
        hooks.extract = lambda task, trace: self.fail("extract called on failed task")
        hooks.save = lambda candidate: self.fail("save called on failed task")
        result = build_graph(FailedEnvironment(), hooks, choose_first_legal_action).invoke({})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["skill_status"], "skipped_failed_task")

    def test_search_failure_does_not_stop_environment_task(self):
        hooks = SkillHooks()
        hooks.search = lambda task: (_ for _ in ()).throw(RuntimeError("library unavailable"))
        result = build_graph(MockEnvironment(), hooks, choose_first_legal_action).invoke({})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["retrieved_skills"], [])
        self.assertIn("library unavailable", result["skill_errors"][0])

    def test_model_failure_is_recorded_without_environment_action(self):
        environment = CountingEnvironment()

        def fail_model(state):
            raise RuntimeError("model unavailable")

        result = build_graph(environment, SkillHooks(), fail_model).invoke({})
        self.assertEqual(result["status"], "model_error")
        self.assertEqual(environment.calls, 0)
        self.assertEqual(result["trace"][0]["feedback"], "model unavailable")

    def test_second_episode_retrieves_first_successful_skill(self):
        library = []
        hooks = SkillHooks()
        hooks.search = lambda task: list(library)
        hooks.extract = lambda task, trace: {"id": "skill-1", "name": task, "steps": [item["action"] for item in trace]}
        hooks.save = lambda candidate: library.append(candidate) or "saved"
        graph = build_graph(MockEnvironment(), hooks, choose_first_legal_action)
        first = graph.invoke({})
        second = graph.invoke({})
        self.assertEqual(first["retrieved_skills"], [])
        self.assertEqual(first["skill_status"], "saved")
        self.assertEqual(second["retrieved_skill_ids"], ["skill-1"])
        self.assertEqual(len(second["trace"]), 3)

    def test_adapter_filters_raw_expert_fields(self):
        adapter = object.__new__(ALFWorldAdapter)
        adapter._task = "put an apple in the basket"
        adapter._task_id = "episode-1"
        adapter._split = "valid_seen"
        snapshot = adapter._snapshot(["observation"], {
            "admissible_commands": [["go to table"]],
            "won": [False],
            "extra.expert_plan": [["secret expert step"]],
            "policy_commands": [["secret plan"]],
        }, done=False, reward=0.0)
        self.assertEqual(snapshot.allowed_actions, ["go to table"])
        self.assertNotIn("secret", repr(snapshot))

    def test_official_text_interface_shape_and_split(self):
        class RawEnvironment:
            closed = False

            def reset(self):
                return ["Your task is to: put an apple in the basket.\nYou see a table."], {
                    "admissible_commands": [["go to table"]],
                    "won": [False],
                    "extra.gamefile": ["/data/trial_1/game.tw-pddl"],
                    "extra.expert_plan": [["secret expert action"]],
                }

            def step(self, actions):
                self.last_actions = actions
                return ["You won!"], [1.0], [True], {
                    "admissible_commands": [[]], "won": [True],
                    "extra.expert_plan": [["secret expert action"]],
                }

            def close(self):
                self.closed = True

        raw = RawEnvironment()

        class OfficialEnvironment:
            game_files = ["one-game"]

            def init_env(self, batch_size):
                self.batch_size = batch_size
                return raw

        official = OfficialEnvironment()
        captured = {}

        def factory(config, train_eval):
            captured.update({"config": config, "split": train_eval})
            return official

        module = types.ModuleType("alfworld.agents.environment")
        module.get_environment = lambda name: factory if name == "AlfredTWEnv" else None
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            (data / "json_2.1.1" / "valid_seen").mkdir(parents=True)
            config = Path(__file__).parent / "config" / "alfworld_text.yaml"
            with patch.dict(sys.modules, {"alfworld": types.ModuleType("alfworld"),
                                          "alfworld.agents": types.ModuleType("alfworld.agents"),
                                          "alfworld.agents.environment": module}):
                adapter = ALFWorldAdapter(config, data)
            first = adapter.reset()
            second = adapter.step("go to table")
            adapter.close()
        self.assertEqual(captured["split"], "eval_in_distribution")
        self.assertEqual(official.batch_size, 1)
        self.assertEqual(first.task, "put an apple in the basket.")
        self.assertEqual(first.task_id, "trial_1")
        self.assertEqual(raw.last_actions, ["go to table"])
        self.assertTrue(second.done and second.won and raw.closed)
        self.assertNotIn("secret", repr(first) + repr(second))


    def test_dynamic_b_entry_receives_success_trace_and_saves(self):
        calls = []
        a_module = types.ModuleType("team_a_fixture")
        b_module = types.ModuleType("team_b_fixture")

        def search_skill(task):
            calls.append("search")
            return []

        def extract_skill(task, trace):
            calls.append("extract")
            self.assertEqual(task, "put an apple in the basket")
            self.assertEqual(len(trace), 3)
            self.assertTrue(all({"step", "observation", "allowed_actions", "action", "feedback", "valid"} <= item.keys() for item in trace))
            return {"id": "candidate-1", "steps": [item["action"] for item in trace]}

        def save_skill(candidate):
            calls.append("save")
            self.assertEqual(candidate["id"], "candidate-1")
            return "stored"

        a_module.search_skill = search_skill
        a_module.save_skill = save_skill
        b_module.extract_skill = extract_skill
        with patch.dict(sys.modules, {"team_a_fixture": a_module, "team_b_fixture": b_module}):
            hooks = SkillHooks("team_a_fixture:search_skill", "team_b_fixture:extract_skill",
                               "team_a_fixture:save_skill")
            result = build_graph(MockEnvironment(), hooks, choose_first_legal_action).invoke({})
        self.assertEqual(calls, ["search", "extract", "save"])
        self.assertEqual(result["skill_status"], "saved")
        self.assertEqual(result["save_result"], "stored")


if __name__ == "__main__":
    unittest.main()
