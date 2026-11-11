import unittest
from unittest.mock import patch

from environments.alfworld_adapter import MockEnvironment
from main import build_graph, choose_first_legal_action
from skill_extractor import extract_skill
from skill_tools.schemas import ExtractOutput, SearchOutput
from tempfile import TemporaryDirectory
from pathlib import Path
from skill_hooks import SkillHooks


class ExtractionTests(unittest.TestCase):
    def run_graph(self, refs):
        response = ExtractOutput(is_new=True, name="取放物品", description="移动目标物品",
                                 steps=["取得目标物品", "放入目标容器"], source_steps=refs)
        hooks = SkillHooks(extract="skill_extractor:extract_skill")
        with patch("skill_tools.extract_tool.deepseek_json", return_value=response):
            return build_graph(MockEnvironment(), hooks, choose_first_legal_action).invoke({})

    def test_candidate_from_successful_episode(self):
        state = self.run_graph([2, 3])
        self.assertEqual(state["skill_status"], "pending_save_hook")
        candidate = state["candidate_skill"]
        self.assertEqual(candidate["steps"], ["取得目标物品", "放入目标容器"])
        self.assertEqual(candidate["evidence"][1]["action"], "put apple in basket")

    def test_invented_step_rejected(self):
        self.assertEqual(self.run_graph([2, 99])["skill_status"], "no_candidate")

    def test_invalid_actions_do_not_trigger_model_call(self):
        with patch("skill_tools.extract_tool.deepseek_json") as model:
            self.assertIsNone(extract_skill("task", [{"step": 1, "valid": False}]))
            model.assert_not_called()

    def test_registered_hooks_create_retrieve_and_skip_covered_skill(self):
        hooks = SkillHooks("a_module:search_skill", "a_module:extract_skill", "a_module:save_skill")
        first = ExtractOutput(is_new=True, name="取放", description="将物品移动到目标容器",
                              steps=["拿起物品", "放入目标容器"], source_steps=[2, 3])
        with TemporaryDirectory() as temp, patch("skill_tools.store.SKILLS_DIR", Path(temp)), \
             patch("skill_tools.extract_tool.deepseek_json",
                   side_effect=[first, ExtractOutput(is_new=False)]) as model, \
             patch("skill_tools.search_tool.deepseek_json",
                   return_value=SearchOutput(skill_ids=["skill-0001"])):
            graph = build_graph(MockEnvironment(), hooks, choose_first_legal_action)
            created = graph.invoke({})
            self.assertEqual(created["save_result"], {"action": "created", "id": "skill-0001"})
            second = graph.invoke({})
            self.assertEqual(second["retrieved_skill_ids"], ["skill-0001"])
            self.assertEqual(second["skill_status"], "no_candidate")
            self.assertEqual(model.call_args.args[1]["skills"],
                             [{"name": first.name, "description": first.description}])
            self.assertEqual(len(list(Path(temp).glob("*.json"))), 1)
