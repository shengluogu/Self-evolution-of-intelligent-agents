"""Integration boundary for teammates A (search/save) and B (extract)."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Callable


def _load(spec: str) -> Callable[..., Any]:
    module_name, separator, function_name = spec.partition(":")
    if not separator or not module_name or not function_name:
        raise ValueError(f"接口应写为 module:function: {spec}")
    function = getattr(import_module(module_name), function_name)
    if not callable(function):
        raise TypeError(f"接口不可调用: {spec}")
    return function


class SkillHooks:
    def __init__(self, search: str | None = None, extract: str | None = None, save: str | None = None):
        self.search = _load(search) if search else None
        self.extract = _load(extract) if extract else None
        self.save = _load(save) if save else None

    def search_skill(self, task: str) -> list[dict[str, Any]]:
        if self.search is None:
            return []
        result = self.search(task)
        if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
            raise TypeError("search_skill(task) 必须返回 list[dict]")
        return result

    def extract_skill(self, task: str, trace: list[dict[str, Any]]) -> dict[str, Any] | None:
        if self.extract is None:
            return None
        result = self.extract(task, trace)
        if result is not None and not isinstance(result, dict):
            raise TypeError("extract_skill(task, trace) 必须返回 dict 或 None")
        return result

    def save_skill(self, candidate: dict[str, Any]) -> Any:
        if self.save is None:
            raise RuntimeError("尚未配置同学 A 的 save_skill 接口")
        return self.save(candidate)
