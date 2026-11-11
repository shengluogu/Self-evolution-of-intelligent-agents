"""工具② extract_skill：接口 + 类型已定，实现待接手同学补全。

交接说明
--------
- 调用时机：任务**成功**后，由框架 `main.py:finish_task` 调用一次；失败任务不调用。
- 入参：``task`` 为任务文本；``trace`` 为执行轨迹，每步含
  ``step``/``observation``/``allowed_actions``/``action``/``feedback``/``valid``，
  实际执行过的动作还带 ``reward``（非法动作步没有 reward）。
- 返回：``dict | None``。``None`` 表示轨迹已被现有 skill 覆盖、无需新增；
  ``dict`` 形如 ``{"name": ..., "description": ..., "steps": [...]}``
  （即 SkillCandidate；id 由 save_skill 分配）。
- 建议实现（与 search/save 同套路）：一次 ``deepseek_json`` 调用——
  LLM 读 task + 精简 trace + 全库 skill 的 name/description（摘要，
  取自 ``skill_tools.store.load_all()``），输出 ``ExtractOutput``：
  ``is_new=False`` 则返回 None，否则组装 SkillCandidate 返回。
  注意 ``deepseek_json`` 的 ``max_tokens=256``，提示词要求简洁输出。
- 异常约定：抛出的异常会被框架记为 ``hook_error``，不影响任务成功状态，
  因此实现里可直接抛错，不必吞异常。
"""

from __future__ import annotations

from skill_tools.registry import tool
from skill_tools.schemas import ExtractInput, ExtractOutput


@tool(name="extract_skill", description="从成功轨迹提取 skill（待实现）",
      input=ExtractInput, output=ExtractOutput)
def extract_skill(task: str, trace: list[dict]) -> dict | None:
    raise NotImplementedError(
        "由接手同学实现：LLM 读 trace + 全库 name/description 产出候选或 None；"
        "交接说明见本文件 docstring"
    )
