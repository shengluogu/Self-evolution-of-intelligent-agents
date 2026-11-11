"""extract_skill 存根测试：接口可加载、类型齐备、未实现时抛 NotImplementedError。"""

import inspect
import unittest

from skill_tools.extract_tool import extract_skill
from skill_tools.registry import TOOLS
from skill_tools.schemas import ExtractInput, ExtractOutput


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


if __name__ == "__main__":
    unittest.main()
