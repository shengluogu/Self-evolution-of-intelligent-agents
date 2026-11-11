"""同学 A 的 hook 入口：
--search-hook a_module:search_skill --extract-hook a_module:extract_skill --save-hook a_module:save_skill

extract_skill 为接口存根（实现待接手同学补全，见 skill_tools/extract_tool.py）。
"""

from skill_tools.extract_tool import extract_skill
from skill_tools.save_tool import save_skill
from skill_tools.search_tool import search_skill

__all__ = ["search_skill", "extract_skill", "save_skill"]
