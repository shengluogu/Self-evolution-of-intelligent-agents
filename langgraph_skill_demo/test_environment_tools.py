import unittest
from environments.alfworld_tools import ALFWorldTools

class Native:
    def __init__(self): self.actions = []
    def step(self, action):
        self.actions.append(action)
        return action

class ALFWorldToolTests(unittest.TestCase):
    def test_structured_and_legacy_commands(self):
        env = Native(); tools = ALFWorldTools(env); tools.update(["look"])
        tools.execute({"tool": "execute", "command": "look"})
        tools.execute("look")
        self.assertEqual(env.actions, [["look"], ["look"]])
        self.assertEqual([t["name"] for t in tools.action_spec()["tools"]], ["execute"])

    def test_invalid_and_stale_commands_never_execute(self):
        env = Native(); tools = ALFWorldTools(env); tools.update(["look"])
        tools.update(["go north"])
        for action in ("look", {"tool": "click", "ref": 1}, {"tool": "execute", "command": []}):
            with self.assertRaises(ValueError): tools.execute(action)
        self.assertEqual(env.actions, [])

    def test_instance_isolation(self):
        a = ALFWorldTools(Native()); b = ALFWorldTools(Native())
        a.update(["look"]); b.update(["wait"])
        self.assertFalse(b.validate("look").valid)
        self.assertTrue(a.validate("look").valid)
