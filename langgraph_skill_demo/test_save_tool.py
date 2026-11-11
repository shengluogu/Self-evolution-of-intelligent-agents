"""save_skill 工具测试：fake LLM（patch deepseek_json），不需要真实 API Key。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_tools import store
from skill_tools.save_tool import save_skill
from skill_tools.schemas import SaveOutput

CANDIDATE = {"name": "clean-then-place", "description": "清洁后放入容器",
             "steps": ["take obj", "clean obj", "put obj"]}


class SaveToolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.object(store, "SKILLS_DIR", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_empty_library_creates_without_llm(self):
        with patch("skill_tools.save_tool.deepseek_json",
                   side_effect=AssertionError("库空不该调 LLM")):
            result = save_skill(CANDIDATE)
        self.assertEqual(result, {"action": "created", "id": "skill-0001"})
        self.assertEqual([s.name for s in store.load_all()], ["clean-then-place"])

    def test_no_duplicate_creates_new(self):
        store.save(store.Skill(id="skill-0001", name="old", description="d", steps=["s"]))
        verdict = SaveOutput(duplicate_ids=[], name="new one", description="nd", steps=["ns"])
        with patch("skill_tools.save_tool.deepseek_json", return_value=verdict) as fake:
            result = save_skill(CANDIDATE)
        self.assertEqual(result, {"action": "created", "id": "skill-0002"})
        payload = fake.call_args[0][1]
        self.assertEqual(payload["candidate"]["name"], "clean-then-place")
        self.assertEqual([s["id"] for s in payload["skills"]], ["skill-0001"])

    def test_duplicate_merges_and_keeps_first_id(self):
        store.save(store.Skill(id="skill-0001", name="old", description="d", steps=["s"]))
        verdict = SaveOutput(duplicate_ids=["skill-0001"], name="merged",
                             description="md", steps=["m1", "m2"])
        with patch("skill_tools.save_tool.deepseek_json", return_value=verdict):
            result = save_skill(CANDIDATE)
        self.assertEqual(result, {"action": "merged", "id": "skill-0001"})
        skills = store.load_all()
        self.assertEqual(len(skills), 1)
        self.assertEqual((skills[0].name, skills[0].steps), ("merged", ["m1", "m2"]))

    def test_multiple_duplicates_delete_extras(self):
        store.save(store.Skill(id="skill-0001", name="a", description="d", steps=["s"]))
        store.save(store.Skill(id="skill-0002", name="b", description="d", steps=["s"]))
        store.save(store.Skill(id="skill-0003", name="c", description="d", steps=["s"]))
        verdict = SaveOutput(duplicate_ids=["skill-0002", "skill-0003", "skill-0009"],
                             name="merged", description="md", steps=["m"])
        with patch("skill_tools.save_tool.deepseek_json", return_value=verdict):
            result = save_skill(CANDIDATE)
        self.assertEqual(result, {"action": "merged", "id": "skill-0002"})
        self.assertEqual([s.id for s in store.load_all()], ["skill-0001", "skill-0002"])
        self.assertEqual(store.load_all()[1].name, "merged")

    def test_unknown_duplicate_ids_ignored(self):
        store.save(store.Skill(id="skill-0001", name="a", description="d", steps=["s"]))
        verdict = SaveOutput(duplicate_ids=["skill-9999"], name="fresh",
                             description="fd", steps=["f"])
        with patch("skill_tools.save_tool.deepseek_json", return_value=verdict):
            result = save_skill(CANDIDATE)
        self.assertEqual(result, {"action": "created", "id": "skill-0002"})

    def test_bad_candidate_rejected(self):
        for bad in [{}, {"name": "x"}, {"name": "x", "description": "y", "steps": "not a list"}]:
            with self.assertRaises(ValueError):
                save_skill(bad)

    def test_llm_error_propagates(self):
        store.save(store.Skill(id="skill-0001", name="a", description="d", steps=["s"]))
        with patch("skill_tools.save_tool.deepseek_json", side_effect=RuntimeError("api down")):
            with self.assertRaises(RuntimeError):
                save_skill(CANDIDATE)


if __name__ == "__main__":
    unittest.main()
