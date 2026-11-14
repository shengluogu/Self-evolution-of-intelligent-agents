"""Small task-facing adapters for the official ALFWorld text environment."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.contracts import Action, Snapshot, ValidationResult
from environments.alfworld_tools import ALFWorldTools


def _task_from_observation(observation: str) -> str:
    match = re.search(r"Your task is to:\s*([^\r\n]+)", observation, re.IGNORECASE)
    if not match:
        raise ValueError("ALFWorld 初始观察中没有找到 'Your task is to:' 任务指令")
    return match.group(1).strip()


class ALFWorldAdapter:
    """Expose only observations and legal actions; never pass raw infos to an LLM."""

    def __init__(self, config_path: str | Path, data_dir: str | Path, split: str = "valid_seen"):
        if split not in {"valid_seen", "valid_unseen"}:
            raise ValueError("split 必须是 valid_seen 或 valid_unseen，以隔离训练专家计划")
        data_dir = Path(data_dir).expanduser().resolve()
        config_path = Path(config_path).expanduser().resolve()
        if not config_path.is_file():
            raise FileNotFoundError(f"ALFWorld 配置不存在: {config_path}")
        if not (data_dir / "json_2.1.1" / split).is_dir():
            raise FileNotFoundError(f"ALFWorld 数据缺失: {data_dir / 'json_2.1.1' / split}")

        try:
            import yaml
            from alfworld.agents.environment import get_environment
        except ImportError as exc:
            raise RuntimeError("请安装 ALFWorld 文本环境及 PyYAML: pip install alfworld pyyaml") from exc

        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or config.get("env", {}).get("type") != "AlfredTWEnv":
            raise ValueError("配置必须使用官方 AlfredTWEnv 文本环境")
        config["dataset"]["data_path"] = str(data_dir / "json_2.1.1" / "train")
        config["dataset"]["eval_id_data_path"] = str(data_dir / "json_2.1.1" / "valid_seen")
        config["dataset"]["eval_ood_data_path"] = str(data_dir / "json_2.1.1" / "valid_unseen")
        config["logic"]["domain"] = str(data_dir / "logic" / "alfred.pddl")
        config["logic"]["grammar"] = str(data_dir / "logic" / "alfred.twl2")
        train_eval = "eval_in_distribution" if split == "valid_seen" else "eval_out_of_distribution"
        official = get_environment("AlfredTWEnv")(config, train_eval=train_eval)
        if not official.game_files:
            raise RuntimeError(f"ALFWorld 在 {split} 中未找到可运行游戏，请检查下载数据")
        self._env = official.init_env(batch_size=1)
        self.tools = ALFWorldTools(self._env)
        self._split = split
        self._task = ""
        self._task_id = ""
        self._done = False

    def _snapshot(self, observations: Any, infos: dict[str, Any], *, done: bool, reward: float) -> Snapshot:
        observation = str(observations[0])
        actions = [str(action) for action in infos["admissible_commands"][0]]
        if not hasattr(self, "tools"):
            self.tools = ALFWorldTools(getattr(self, "_env", None))
        self.tools.update(actions)
        # Explicit allowlist: extra.expert_plan and every other internal field stay private.
        won = bool(infos.get("won", [False])[0])
        return Snapshot(self._task, observation, actions, self._task_id, self._split, done, won, reward, terminated=done,
                        action_spec=self.tools.action_spec(),
                        metadata={"environment": "alfworld", "split": self._split})

    def reset(self) -> Snapshot:
        observations, infos = self._env.reset()
        self._task = _task_from_observation(str(observations[0]))
        gamefile = infos.get("extra.gamefile", [""])[0]
        self._task_id = Path(str(gamefile)).parent.name if gamefile else "unknown"
        self._done = False
        return self._snapshot(observations, infos, done=False, reward=0.0)

    def validate_action(self, action: Action) -> ValidationResult:
        return self.tools.validate(action)

    def step(self, action: Action) -> Snapshot:
        if self._done:
            raise RuntimeError("任务已结束，请先 reset()")
        observations, rewards, dones, infos = self.tools.execute(action)
        self._done = bool(dones[0])
        return self._snapshot(observations, infos, done=self._done, reward=float(rewards[0]))

    def close(self) -> None:
        self._env.close()



# Compatibility export for existing callers.
from environments.mock import MockEnvironment
