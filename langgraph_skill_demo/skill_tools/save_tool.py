"""工具③ save_skill：查重与合并/新建写在一个函数里，一次 LLM 调用产出最终 skill。"""

from __future__ import annotations

from pydantic import ValidationError

from llm import deepseek_json
from skill_tools import store
from skill_tools.registry import tool
from skill_tools.schemas import SaveInput, SaveOutput, Skill, SkillCandidate

_SAVE_PROMPT = (
    "你是 skill 库管理员。给定一个新提取的 skill 候选和现有 skill 库（含 id/name/description/steps）。"
    "判断候选是否与某条现有 skill 重复（解决同一类任务、策略相同）：\n"
    "- 无重复：duplicate_ids 返回 []，并输出候选本身的 name/description/steps（可润色但不扩写）。\n"
    "- 有重复：duplicate_ids 返回重复的 id 列表，再综合候选与这些 skill 的内容输出一条合并后的 skill"
    "（保留仍有价值的步骤，去重去杂）。\n"
    '只输出 JSON 对象，格式为 {"duplicate_ids": [...], "name": ..., "description": ..., "steps": [...]}。'
)


@tool(name="save_skill", description="查重后合并或新建 skill 入库",
      input=SaveInput, output=SaveOutput)
def save_skill(candidate: dict) -> dict:
    """任务成功且 extract 给出候选后调用。返回 {"action": "created"|"merged", "id": ...}。"""
    try:
        draft = SkillCandidate.model_validate(candidate)
    except ValidationError as exc:
        raise ValueError(f"candidate 不符合 SkillCandidate 结构: {exc}") from exc

    library = store.load_all()
    if not library:
        saved = store.save(Skill(id=store.next_id(), **draft.model_dump()))
        return {"action": "created", "id": saved.stem}

    verdict: SaveOutput = deepseek_json(
        _SAVE_PROMPT,
        {"candidate": draft.model_dump(), "skills": [s.model_dump() for s in library]},
        SaveOutput,
    )
    known = {s.id for s in library}
    duplicates = [i for i in verdict.duplicate_ids if i in known]
    if not duplicates:
        saved = store.save(Skill(id=store.next_id(), name=verdict.name,
                                 description=verdict.description, steps=verdict.steps))
        return {"action": "created", "id": saved.stem}

    keep_id = duplicates[0]
    store.save(Skill(id=keep_id, name=verdict.name,
                     description=verdict.description, steps=verdict.steps))
    for extra in duplicates[1:]:
        store.delete(extra)
    return {"action": "merged", "id": keep_id}
