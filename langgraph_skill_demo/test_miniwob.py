"""Offline tests need neither MiniWoB, Selenium nor a browser."""
import json
import sys
import types
import unittest
from enum import Enum
from types import SimpleNamespace
from unittest.mock import patch
from environments.miniwob.adapter import MiniWoBAdapter
from environments.alfworld_tools import ALFWorldTools
from core.runner import build_graph
from skill_hooks import SkillHooks

class Types(Enum):
    CLICK_ELEMENT = 1
    PRESS_KEY = 2
    TYPE_TEXT = 3
    FOCUS_ELEMENT_AND_TYPE_TEXT = 4

class Driver:
    def __init__(self): self.scripts = []
    def execute_script(self, script, *args): self.scripts.append((script, args))

class Native:
    def __init__(self):
        self.unwrapped = self
        self.action_space_config = SimpleNamespace(allowed_keys=["C-a", "<Backspace>", "<Enter>"], text_max_len=20)
        self.instance = SimpleNamespace(driver=Driver())
        self.actions = []; self.seeds = []; self.closed = False; self.result = (False, False, 0)
        self.observation = {"utterance": "Fill input", "dom_elements": (
            {"ref": 1, "parent": 0, "tag": "input", "value": "old", "flags": [0, 1]},
            {"ref": 2, "parent": 0, "tag": "button", "text": "Submit"})}
    def reset(self, seed):
        assert self.instance.driver.scripts, "Timer must be configured BEFORE reset"
        self.seeds.append(seed); return self.observation, {"private": "secret"}
    def create_action(self, kind, **kwargs): return {"kind": kind, **kwargs}
    def step(self, action):
        self.actions.append(action)
        terminated, truncated, reward = self.result
        return self.observation, reward, terminated, truncated, {"private": "secret"}
    def close(self): self.closed = True

class MiniWoBTests(unittest.TestCase):
    def setUp(self):
        fake = types.ModuleType("miniwob.action"); fake.ActionTypes = Types
        self.patcher = patch.dict(sys.modules, {"miniwob.action": fake})
        self.patcher.start(); self.addCleanup(self.patcher.stop)
        self.raw = Native(); self.env = MiniWoBAdapter(seed=12, environment=self.raw)
        self.start = self.env.reset()

    def test_only_environment_tools_and_public_dom(self):
        self.assertEqual([t["name"] for t in self.start.action_spec["tools"]], ["click", "type_text", "press_key"])
        self.assertEqual([t["name"] for t in ALFWorldTools(None).action_spec()["tools"]], ["execute"])
        self.assertNotIn("secret", self.start.observation)
        self.assertEqual(json.loads(self.start.observation)["dom_elements"][0]["value"], "old")
        self.assertNotIn("get_dom", [t["name"] for t in self.start.action_spec["tools"]])

    def test_click_mapping(self):
        self.env.step({"tool": "click", "ref": 2})
        self.assertEqual(self.raw.actions, [{"kind": Types.CLICK_ELEMENT, "ref": 2}])

    def test_type_append_and_clear(self):
        self.env.step({"tool": "type_text", "ref": 1, "text": "new"})
        self.assertEqual(self.raw.actions[-1]["kind"], Types.FOCUS_ELEMENT_AND_TYPE_TEXT)
        snapshot = self.env.step({"tool": "type_text", "ref": 1, "text": "new", "clear": True})
        self.assertEqual([a["kind"] for a in self.raw.actions[1:]],
            [Types.CLICK_ELEMENT, Types.PRESS_KEY, Types.PRESS_KEY, Types.TYPE_TEXT])
        self.assertEqual(len(snapshot.metadata["native_actions"]), 4)

    def test_clear_stops_if_intermediate_action_ends_episode(self):
        self.raw.result = (True, False, 1)
        self.env.step({"tool": "type_text", "ref": 1, "text": "new", "clear": True})
        self.assertEqual(len(self.raw.actions), 1)

    def test_press_key(self):
        self.env.step({"tool": "press_key", "key": "<Enter>"})
        self.assertEqual(self.raw.actions[-1]["key"], 2)

    def test_invalid_parameters_never_execute(self):
        for action in ({"tool": "click", "ref": 99}, {"tool": "click", "ref": True},
                       {"tool": "click", "ref": 1, "extra": 1}, {"tool": "scroll"},
                       {"tool": "type_text", "ref": 2, "text": "x"},
                       {"tool": "type_text", "ref": 1, "text": "x"*21},
                       {"tool": "press_key", "key": "unknown"}, {"tool": []}):
            with self.subTest(action=action):
                self.assertFalse(self.env.validate_action(action).valid)
                with self.assertRaises(ValueError): self.env.step(action)
        self.assertEqual(self.raw.actions, [])

    def test_stale_refs(self):
        self.env.tools.update({"dom_elements": ()})
        self.assertFalse(self.env.validate_action({"tool": "click", "ref": 1}).valid)

    def test_seed_reset_and_close(self):
        self.env.reset(); self.assertEqual(self.raw.seeds, [12, 13])
        self.env.close(); self.assertTrue(self.raw.closed)
        self.assertFalse(self.env.validate_action({"tool": "click", "ref": 2}).valid)

    def test_instance_isolation(self):
        other = MiniWoBAdapter(environment=Native()); other.reset()
        self.env.tools.update({"dom_elements": ()})
        self.assertTrue(other.validate_action({"tool": "click", "ref": 2}).valid)

    def test_terminal_and_truncated(self):
        for terminated, truncated, reward, expected in ((True, False, 1, True), (True, False, -1, False), (False, True, 0, False)):
            self.env.reset(); self.raw.result = (terminated, truncated, reward)
            result = self.env.step({"tool": "click", "ref": 2})
            self.assertEqual(result.success, expected)
            self.assertTrue(result.finished)

    def test_runner_records_compound_native_actions(self):
        self.raw.result = (True, False, 1)
        result = build_graph(self.env, SkillHooks(), lambda state: {"tool": "click", "ref": 2}).invoke({})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["trace"][0]["native_actions"], [{"type": "CLICK_ELEMENT", "ref": 2}])
