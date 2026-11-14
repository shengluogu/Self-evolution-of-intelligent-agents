"""skills/ 文件夹读写层：一文件一 skill，文件名 skill-%04d.json。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from skill_tools.schemas import Skill

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

_FILENAME = re.compile(r"skill-(\d{4})\.json$")


def configure(directory: str | Path) -> None:
    """Select a library at application assembly time; hooks stay unchanged."""
    global SKILLS_DIR
    SKILLS_DIR = Path(directory).expanduser().resolve()


def _paths() -> list[Path]:
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(p for p in SKILLS_DIR.iterdir() if _FILENAME.match(p.name))


def load_all() -> list[Skill]:
    """读出全部 skill（坏文件会抛错，不静默跳过）。"""
    return [Skill.model_validate_json(path.read_text(encoding="utf-8")) for path in _paths()]


def next_id() -> str:
    numbers = [int(_FILENAME.match(p.name).group(1)) for p in _paths()]
    return f"skill-{(max(numbers) + 1 if numbers else 1):04d}"


def save(skill: Skill) -> Path:
    """校验后落盘为 skills/<id>.json（id 相同则覆盖）。"""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    destination = SKILLS_DIR / f"{skill.id}.json"
    destination.write_text(skill.model_dump_json(indent=2), encoding="utf-8")
    return destination


def delete(skill_id: str) -> None:
    (SKILLS_DIR / f"{skill_id}.json").unlink(missing_ok=True)
