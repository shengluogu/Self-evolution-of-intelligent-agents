"""Boundary tests: structured actions, termination, isolation and evidence."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.contracts import Snapshot, ValidationResult
from core.runner import build_graph
from skill_hooks import SkillHooks
from skill_tools import store
from skill_tools.save_tool import save_skill
from skill_tools.schemas import Skill, SaveOutput, ExtractOutput
from skill_tools.extract_tool import extract_skill

class StructuredEnvironment:
    def __init__(self, truncated=False, initial_done=False):
        self.calls = 0
        self.truncated = truncated
        self.initial_done = initial_done
    def reset(self):
        return Snapshot("activate", "A switch", [], "switch-1", "", done=self.initial_done,
                        action_spec={"type": "object", "op": "activate"})
    def validate_action(self, action):
        return ValidationResult(action == {"op": "activate"}, "Expected activate")
    def step(self, action):
        self.calls += 1
        return Snapshot("activate", "updated", [], "switch-1", "", won=not self.truncated,
                        reward=float(not self.truncated), terminated=not self.truncated,
                        truncated=self.truncated)
    def close(self): pass

class BoundaryTests(unittest.TestCase):
    def test_structured_action_and_skill_cycle(self):
        library = []
        hooks = SkillHooks()
        hooks.search = lambda task: list(library)
        hooks.extract = lambda task, trace: {"name": task, "description": task, "steps": ["activate"]}
        hooks.save = lambda skill: library.append(dict(skill, id="skill-1"))
        graph = build_graph(StructuredEnvironment(), hooks, lambda state: {"op": "activate"})
        first = graph.invoke({})
        self.assertEqual(first["status"], "success")
        self.assertTrue(first["terminated"])
        self.assertEqual(first["trace"][0]["action"], {"op": "activate"})
        self.assertEqual(graph.invoke({})["retrieved_skill_ids"], ["skill-1"])

    def test_invalid_object_does_not_execute(self):
        env = StructuredEnvironment()
        result = build_graph(env, SkillHooks(), lambda state: {"op": "bad"}, 2).invoke({})
        self.assertEqual(env.calls, 0)
        self.assertEqual(result["status"], "invalid_action_limit")
        self.assertEqual(result["trace"][0]["feedback"], "Expected activate")

    def test_validation_exception_is_environment_error(self):
        env = StructuredEnvironment()
        def broken(action):
            raise RuntimeError("validator unavailable")
        env.validate_action = broken
        result = build_graph(env, SkillHooks(), lambda state: {"op": "activate"}).invoke({})
        self.assertEqual(result["status"], "environment_error")
        self.assertEqual(env.calls, 0)
        self.assertFalse(result["trace"][0]["valid"])

    def test_agent_step_limit_is_not_environment_truncation(self):
        env = StructuredEnvironment()
        env.step = lambda action: Snapshot("activate", "still running", action_spec={"op": "activate"})
        result = build_graph(env, SkillHooks(), lambda state: {"op": "activate"}, 1).invoke({})
        self.assertEqual(result["status"], "step_limit")
        self.assertTrue(result["done"])
        self.assertFalse(result["terminated"])
        self.assertFalse(result["truncated"])

    def test_truncation_skips_extraction(self):
        hooks = SkillHooks()
        hooks.extract = lambda *args: self.fail("must skip truncated task")
        result = build_graph(StructuredEnvironment(truncated=True), hooks,
                             lambda state: {"op": "activate"}).invoke({})
        self.assertEqual(result["status"], "truncated")
        self.assertTrue(result["truncated"])
        self.assertFalse(result["success"])

    def test_initial_terminal_does_not_choose(self):
        env = StructuredEnvironment(initial_done=True)
        result = build_graph(env, SkillHooks(), lambda state: self.fail("must not choose")).invoke({})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(env.calls, 0)

    def test_import_and_graph_without_alfworld(self):
        code = """
import sys
class Block:
    def find_spec(self, fullname, *args):
        if fullname == 'alfworld' or fullname == 'environments.alfworld_adapter':
            raise AssertionError('ALFWorld imported')
sys.meta_path.insert(0, Block())
import main
sys.argv = ['main.py', '--mode', 'alfworld', '--alfworld-data', '/missing', '--graph']
main.main()
"""
        result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parent,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("initialize_task", result.stdout)

    def test_independent_library_directories(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(store, "SKILLS_DIR", store.SKILLS_DIR):
            store.configure(Path(temp)/"a")
            store.save(Skill(id="skill-0001", name="a", description="a", steps=["a"]))
            store.configure(Path(temp)/"b")
            self.assertEqual(store.load_all(), [])
            store.configure(Path(temp)/"a")
            self.assertEqual(store.load_all()[0].name, "a")

    def test_save_preserves_metadata_on_create_and_merge(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(store, "SKILLS_DIR", Path(temp)):
            store.save(Skill(id="skill-0001", name="old", description="d", steps=["s"], evidence=[{"step": 1}], scope="test"))
            candidate = dict(name="new", description="d", steps=["s"], evidence=[{"step": 2}], scope="test")
            for duplicates in ([], ["skill-0001"]):
                with patch("skill_tools.save_tool.deepseek_json", return_value=SaveOutput(
                        duplicate_ids=duplicates, name="new", description="d", steps=["s"])):
                    result = save_skill(candidate)
                saved = next(s for s in store.load_all() if s.id == result["id"])
                self.assertEqual(saved.scope, "test")
                self.assertIn({"step": 2}, saved.evidence)
                if duplicates:
                    self.assertIn({"step": 1}, saved.evidence)

    def test_extractor_receives_observation_and_object_action(self):
        row = dict(step=1, observation="button Submit", action={"click": 17}, feedback="complete", valid=True)
        with patch("skill_tools.extract_tool.store.load_all", return_value=[]), patch(
                "skill_tools.extract_tool.deepseek_json", return_value=ExtractOutput(
                    is_new=True, name="submit", description="submit form", steps=["click Submit"], source_steps=[1])) as fake:
            result = extract_skill("submit", [row])
        self.assertEqual(fake.call_args.kwargs["max_tokens"], 1024)
        self.assertEqual(fake.call_args.args[1]["trace"][0]["observation"], row["observation"])
        self.assertEqual(result["evidence"][0]["action"], {"click": 17})
