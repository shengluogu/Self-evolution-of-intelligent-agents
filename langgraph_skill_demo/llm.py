"""DeepSeek JSON 调用封装，供 main 与 skill_tools 共用。

从 main.py 拆出；.env 读取放在这里，import 时自动加载。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import BaseModel


def _load_env() -> None:
    """读取同目录 .env（KEY=VALUE 逐行）；已存在的环境变量优先。"""
    env_path = Path(__file__).parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_env()

MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")


def deepseek_json(system_prompt: str, payload: dict[str, Any], schema: type[BaseModel]) -> BaseModel:
    """Keep the original DeepSeek JSON + Pydantic boundary for action selection."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("请先设置 DEEPSEEK_API_KEY（环境变量或 skill_demo 目录下 .env）")
    response = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=60.0,
                      max_retries=2).chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        max_tokens=256,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("DeepSeek 返回空 JSON 内容")
    return schema.model_validate_json(content)
