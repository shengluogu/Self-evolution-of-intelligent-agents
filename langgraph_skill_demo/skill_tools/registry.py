"""工具注册表：加工具 = 新建文件 + @tool 四件套（name/description/input/output）。"""

from __future__ import annotations

from typing import Any, Callable

TOOLS: dict[str, dict[str, Any]] = {}


def tool(name: str, description: str, input: type, output: type) -> Callable[[Callable], Callable]:
    def decorator(fn: Callable) -> Callable:
        TOOLS[name] = {"name": name, "description": description,
                       "input": input, "output": output, "fn": fn}
        return fn

    return decorator
