"""Skill 与三个工具 I/O 的 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Skill(BaseModel):
    """库中一条 skill。必填 id/name/description/steps，允许额外字段。"""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    description: str
    steps: list[str]


class SkillCandidate(BaseModel):
    """extract 产出、save 消费的候选；id 由 save 分配。"""

    model_config = ConfigDict(extra="allow")

    name: str
    description: str
    steps: list[str]


class SearchInput(BaseModel):
    task: str


class SearchOutput(BaseModel):
    skill_ids: list[str]


class ExtractInput(BaseModel):
    task: str
    trace: list[dict[str, object]]


class ExtractOutput(BaseModel):
    """is_new=False 表示轨迹已被现有 skill 覆盖，其余字段留空。"""

    is_new: bool
    name: str = ""
    description: str = ""
    steps: list[str] = []


class SaveInput(BaseModel):
    candidate: SkillCandidate
    skills: list[Skill]


class SaveOutput(BaseModel):
    """duplicate_ids 为空表示无重复（新建）；否则合并进第一条重复。"""

    duplicate_ids: list[str]
    name: str
    description: str
    steps: list[str]
