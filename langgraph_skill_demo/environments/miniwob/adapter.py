"""MiniWoB lifecycle and public observations. Interaction lives in tools.py."""
import json
from core.contracts import Snapshot, ValidationResult
from environments.miniwob.tools import MiniWoBTools

class MiniWoBAdapter:
    def __init__(self, task="click-test-2", seed=0, wait_ms=150, episode_timeout_ms=120000,
                 data_mode="test", environment=None):
        if wait_ms < 0 or episode_timeout_ms <= 0:
            raise ValueError("wait_ms must be nonnegative and episode_timeout_ms positive")
        if environment is None:
            try:
                import gymnasium as gym
                import miniwob
                from miniwob.action import ActionSpaceConfig, ActionTypes
                from miniwob.reward import get_binary_reward
            except ImportError as exc:
                raise RuntimeError("Install requirements-miniwob.txt and Chrome/ChromeDriver") from exc
            config = ActionSpaceConfig(action_types=[ActionTypes.CLICK_ELEMENT,
                ActionTypes.FOCUS_ELEMENT_AND_TYPE_TEXT, ActionTypes.TYPE_TEXT, ActionTypes.PRESS_KEY],
                allowed_keys=["<Enter>", "<Tab>", "<Backspace>", "<Delete>", "C-a",
                              "<ArrowUp>", "<ArrowDown>", "<ArrowLeft>", "<ArrowRight>", "<Escape>"])
            environment = gym.make(f"miniwob/{task}-v1", render_mode=None,
                action_space_config=config, reward_processor=get_binary_reward,
                wait_ms=wait_ms, data_mode=data_mode)
        self._env = environment
        self.tools = MiniWoBTools(environment)
        self.task = task
        self.seed = seed
        self.timeout = episode_timeout_ms
        self.data_mode = data_mode
        self._episode = 0
        self._done = True

    def _snapshot(self, observation, reward=0.0, terminated=False, truncated=False):
        self.tools.update(observation)
        return Snapshot(task=observation["utterance"],
            observation=json.dumps({"dom_elements": self.tools.get_dom()}, ensure_ascii=False),
            task_id=f"{self.task}:seed={self._current_seed}", split=self.data_mode,
            won=bool(terminated and not truncated and reward == 1), reward=float(reward),
            terminated=bool(terminated), truncated=bool(truncated),
            action_spec=self.tools.action_spec(), metadata={"environment": "miniwob", "task": self.task,
                "seed": self._current_seed, "episode_timeout_ms": self.timeout,
                "native_actions": list(self.tools.native_actions)})

    def reset(self):
        self._done = True
        self._current_seed = self.seed + self._episode
        self._configure_timer()
        observation, _ = self._env.reset(seed=self._current_seed)
        self._episode += 1
        self.tools.native_actions = []
        self._done = False
        return self._snapshot(observation)

    def _configure_timer(self):
        # Explicitly configured wall-clock limit, recorded in metadata; never pause the clock.
        driver = self._env.unwrapped.instance.driver
        driver.execute_script("core.EPISODE_MAX_TIME = arguments[0];", self.timeout)

    def validate_action(self, action):
        if self._done: return ValidationResult(False, "Episode ended; reset first")
        return self.tools.validate(action)

    def step(self, action):
        validation = self.validate_action(action)
        if not validation.valid: raise ValueError(validation.reason)
        observation, reward, terminated, truncated, _ = self.tools.execute(action)
        self._done = bool(terminated or truncated)
        return self._snapshot(observation, reward, terminated, truncated)

    def close(self):
        self._done = True
        self._env.close()
