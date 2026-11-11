"""search_skill 工具测试：fake LLM（patch deepseek_json），不需要真实 API Key。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_tools import store
from skill_tools.schemas import SearchOutput
from skill_tools.search_tool import search_skill


class SearchToolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.object(store, "SKILLS_DIR", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_empty_library_returns_empty_without_llm(self):
        with patch("skill_tools.search_tool.deepseek_json",
                   side_effect=AssertionError("库空不该调 LLM")):
            self.assertEqual(search_skill("put an apple in the basket"), [])

    def test_returns_full_records_for_picked_ids(self):
        store.save(store.Skill(id="skill-0001", name="a", description="da", steps=["s1"]))
        store.save(store.Skill(id="skill-0002", name="b", description="db", steps=["s2"]))

        with patch("skill_tools.search_tool.deepseek_json",
                   return_value=SearchOutput(skill_ids=["skill-0002"])) as fake:
            result = search_skill("put an apple in the basket")
        self.assertEqual([r["id"] for r in result], ["skill-0002"])
        self.assertEqual(result[0]["steps"], ["s2"])
        payload = fake.call_args[0][1]
        self.assertEqual(payload["task"], "put an apple in the basket")
        self.assertEqual([s["id"] for s in payload["skills"]], ["skill-0001", "skill-0002"])

    def test_no_hit_returns_empty(self):
        store.save(store.Skill(id="skill-0001", name="a", description="da", steps=["s1"]))
        with patch("skill_tools.search_tool.deepseek_json",
                   return_value=SearchOutput(skill_ids=[])):
            self.assertEqual(search_skill("unrelated task"), [])

    def test_llm_error_propagates(self):
        store.save(store.Skill(id="skill-0001", name="a", description="da", steps=["s1"]))
        with patch("skill_tools.search_tool.deepseek_json", side_effect=RuntimeError("api down")):
            with self.assertRaises(RuntimeError):
                search_skill("any task")


if __name__ == "__main__":
    unittest.main()
