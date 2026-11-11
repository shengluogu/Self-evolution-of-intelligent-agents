"""skill_tools 单元测试：store / registry / schemas / 三个工具（fake LLM，离线，不需要真实 API Key）。"""

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_tools import store
from skill_tools.extract_tool import extract_skill
from skill_tools.registry import TOOLS, tool
from skill_tools.save_tool import save_skill
from skill_tools.schemas import ExtractInput, ExtractOutput, SaveOutput, SearchOutput, Skill, SkillCandidate
from skill_tools.search_tool import search_skill


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
        store.save(make_skill("skill-0001", name="a", description="da", steps=["s1"]))
        store.save(make_skill("skill-0002", name="b", description="db", steps=["s2"]))

        with patch("skill_tools.search_tool.deepseek_json",
                   return_value=SearchOutput(skill_ids=["skill-0002"])) as fake:
            result = search_skill("put an apple in the basket")
        self.assertEqual([r["id"] for r in result], ["skill-0002"])
        self.assertEqual(result[0]["steps"], ["s2"])
        payload = fake.call_args[0][1]
        self.assertEqual(payload["task"], "put an apple in the basket")
        self.assertEqual([s["id"] for s in payload["skills"]], ["skill-0001", "skill-0002"])

    def test_no_hit_returns_empty(self):
        store.save(make_skill("skill-0001", name="a", description="da", steps=["s1"]))
        with patch("skill_tools.search_tool.deepseek_json",
                   return_value=SearchOutput(skill_ids=[])):
            self.assertEqual(search_skill("unrelated task"), [])

    def test_llm_error_propagates(self):
        store.save(make_skill("skill-0001", name="a", description="da", steps=["s1"]))
        with patch("skill_tools.search_tool.deepseek_json", side_effect=RuntimeError("api down")):
            with self.assertRaises(RuntimeError):
                search_skill("any task")


class ExtractStubTests(unittest.TestCase):
    def test_stub_raises_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            extract_skill("put an apple in the basket", [{"step": 1}])

    def test_signature_matches_contract(self):
        sig = inspect.signature(extract_skill)
        self.assertEqual(list(sig.parameters), ["task", "trace"])

    def test_registered_with_io_models(self):
        entry = TOOLS["extract_skill"]
        self.assertIs(entry["input"], ExtractInput)
        self.assertIs(entry["output"], ExtractOutput)

    def test_io_models_fields(self):
        self.assertEqual(set(ExtractInput.model_fields), {"task", "trace"})
        self.assertEqual(set(ExtractOutput.model_fields),
                         {"is_new", "name", "description", "steps"})


class SaveToolTests(unittest.TestCase):
    CANDIDATE = {"name": "clean-then-place", "description": "清洁后放入容器",
                 "steps": ["take obj", "clean obj", "put obj"]}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.object(store, "SKILLS_DIR", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_empty_library_creates_without_llm(self):
        with patch("skill_tools.save_tool.deepseek_json",
                   side_effect=AssertionError("库空不该调 LLM")):
            result = save_skill(self.CANDIDATE)
        self.assertEqual(result, {"action": "created", "id": "skill-0001"})
        self.assertEqual([s.name for s in store.load_all()], ["clean-then-place"])

    def test_no_duplicate_creates_new(self):
        store.save(make_skill("skill-0001", name="old", description="d", steps=["s"]))
        verdict = SaveOutput(duplicate_ids=[], name="new one", description="nd", steps=["ns"])
        with patch("skill_tools.save_tool.deepseek_json", return_value=verdict) as fake:
            result = save_skill(self.CANDIDATE)
        self.assertEqual(result, {"action": "created", "id": "skill-0002"})
        payload = fake.call_args[0][1]
        self.assertEqual(payload["candidate"]["name"], "clean-then-place")
        self.assertEqual([s["id"] for s in payload["skills"]], ["skill-0001"])

    def test_duplicate_merges_and_keeps_first_id(self):
        store.save(make_skill("skill-0001", name="old", description="d", steps=["s"]))
        verdict = SaveOutput(duplicate_ids=["skill-0001"], name="merged",
                             description="md", steps=["m1", "m2"])
        with patch("skill_tools.save_tool.deepseek_json", return_value=verdict):
            result = save_skill(self.CANDIDATE)
        self.assertEqual(result, {"action": "merged", "id": "skill-0001"})
        skills = store.load_all()
        self.assertEqual(len(skills), 1)
        self.assertEqual((skills[0].name, skills[0].steps), ("merged", ["m1", "m2"]))

    def test_multiple_duplicates_delete_extras(self):
        store.save(make_skill("skill-0001", name="a", description="d", steps=["s"]))
        store.save(make_skill("skill-0002", name="b", description="d", steps=["s"]))
        store.save(make_skill("skill-0003", name="c", description="d", steps=["s"]))
        verdict = SaveOutput(duplicate_ids=["skill-0002", "skill-0003", "skill-0009"],
                             name="merged", description="md", steps=["m"])
        with patch("skill_tools.save_tool.deepseek_json", return_value=verdict):
            result = save_skill(self.CANDIDATE)
        self.assertEqual(result, {"action": "merged", "id": "skill-0002"})
        self.assertEqual([s.id for s in store.load_all()], ["skill-0001", "skill-0002"])
        self.assertEqual(store.load_all()[1].name, "merged")

    def test_unknown_duplicate_ids_ignored(self):
        store.save(make_skill("skill-0001", name="a", description="d", steps=["s"]))
        verdict = SaveOutput(duplicate_ids=["skill-9999"], name="fresh",
                             description="fd", steps=["f"])
        with patch("skill_tools.save_tool.deepseek_json", return_value=verdict):
            result = save_skill(self.CANDIDATE)
        self.assertEqual(result, {"action": "created", "id": "skill-0002"})

    def test_bad_candidate_rejected(self):
        for bad in [{}, {"name": "x"}, {"name": "x", "description": "y", "steps": "not a list"}]:
            with self.assertRaises(ValueError):
                save_skill(bad)

    def test_llm_error_propagates(self):
        store.save(make_skill("skill-0001", name="a", description="d", steps=["s"]))
        with patch("skill_tools.save_tool.deepseek_json", side_effect=RuntimeError("api down")):
            with self.assertRaises(RuntimeError):
                save_skill(self.CANDIDATE)


if __name__ == "__main__":
    unittest.main()
