"""skill_tools 单元测试：store / registry / schemas（不需要真实 API Key）。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_tools import store
from skill_tools.registry import TOOLS, tool
from skill_tools.schemas import Skill, SkillCandidate


def make_skill(skill_id: str = "skill-0001", **overrides) -> Skill:
    fields = {"id": skill_id, "name": "demo", "description": "demo skill",
              "steps": ["step one", "step two"]}
    fields.update(overrides)
    return Skill(**fields)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.object(store, "SKILLS_DIR", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_load_roundtrip(self):
        skill = make_skill()
        path = store.save(skill)
        self.assertEqual(path.name, "skill-0001.json")
        self.assertEqual(store.load_all(), [skill])

    def test_next_id_increments(self):
        self.assertEqual(store.next_id(), "skill-0001")
        store.save(make_skill("skill-0001"))
        store.save(make_skill("skill-0007"))
        self.assertEqual(store.next_id(), "skill-0008")

    def test_save_same_id_overwrites(self):
        store.save(make_skill(name="old"))
        store.save(make_skill(name="new"))
        self.assertEqual([s.name for s in store.load_all()], ["new"])

    def test_delete(self):
        store.save(make_skill())
        store.delete("skill-0001")
        self.assertEqual(store.load_all(), [])

    def test_missing_required_field_rejected(self):
        with self.assertRaises(Exception):
            Skill(id="skill-0001", name="x", description="y")  # 缺 steps

    def test_extra_field_allowed(self):
        skill = make_skill(tags=["a"])
        store.save(skill)
        self.assertEqual(store.load_all()[0].tags, ["a"])

    def test_corrupt_file_raises(self):
        (Path(self._tmp.name) / "skill-0001.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(Exception):
            store.load_all()


class RegistryTests(unittest.TestCase):
    def test_tool_registers_metadata(self):
        @tool(name="demo_tool", description="demo", input=SkillCandidate, output=Skill)
        def demo_tool():
            return None

        entry = TOOLS["demo_tool"]
        self.assertEqual(entry["description"], "demo")
        self.assertIs(entry["input"], SkillCandidate)
        self.assertIs(entry["output"], Skill)
        self.assertIs(entry["fn"], demo_tool)


if __name__ == "__main__":
    unittest.main()
