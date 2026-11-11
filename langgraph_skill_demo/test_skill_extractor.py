import unittest
from unittest.mock import patch

from environments.alfworld_adapter import MockEnvironment
from main import build_graph, choose_first_legal_action
from skill_extractor import Extraction, extract_skill
from skill_hooks import SkillHooks


class ExtractionTests(unittest.TestCase):
    def run_graph(self, refs):
        response = Extraction.model_validate({"candidate": {
            "name": "取放物品", "applicable_scenario": "将目标物品移到容器内",
            "steps": [{"instruction": text, "source_step": ref}
                      for text, ref in zip(["取得目标物品", "放入目标容器"], refs)],
        }})
        hooks = SkillHooks(extract="skill_extractor:extract_skill")
        with patch("skill_extractor.deepseek_json", return_value=response):
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
        with patch("skill_extractor.deepseek_json") as model:
            self.assertIsNone(extract_skill("task", [{"step": 1, "valid": False}]))
            model.assert_not_called()
