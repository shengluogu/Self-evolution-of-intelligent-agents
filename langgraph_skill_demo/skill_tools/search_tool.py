"""工具① search_skill：LLM 读全库 name/description，挑出与任务相关的 skill。"""

from __future__ import annotations

from llm import deepseek_json
from skill_tools import store
from skill_tools.registry import tool
from skill_tools.schemas import SearchInput, SearchOutput, Skill

_SEARCH_PROMPT = (
    "你是 skill 检索助手。给定一个任务和候选 skill 列表（只有 id/name/description），"
    "挑选出对该任务有参考价值的 skill。宁缺毋滥：没有明显相关的就返回空列表。"
    '只输出 JSON 对象，格式为 {"skill_ids": ["skill-0001", ...]}。'
)


@tool(name="search_skill", description="按任务检索相关 skill",
      input=SearchInput, output=SearchOutput)
def search_skill(task: str) -> list[dict]:
    """任务开始时调用一次。返回完整 skill 记录 list[dict]；库空返回 []（不调 LLM）。"""
    library = store.load_all()
    if not library:
        return []
    summary = [{"id": s.id, "name": s.name, "description": s.description} for s in library]
    picked: SearchOutput = deepseek_json(_SEARCH_PROMPT, {"task": task, "skills": summary}, SearchOutput)
    wanted = set(picked.skill_ids)
    matched: list[Skill] = [s for s in library if s.id in wanted]
    return [s.model_dump() for s in matched]
