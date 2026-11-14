"""Application-level environment assembly; optional dependencies load lazily."""
def create_environment(mode, *, config_path=None, data_dir=None, split="valid_seen",
                       task="click-test-2", seed=0, miniwob_config=None):
    if mode == "mock":
        from environments.mock import MockEnvironment
        return MockEnvironment()
    if mode == "alfworld":
        from environments.alfworld_adapter import ALFWorldAdapter
        return ALFWorldAdapter(config_path, data_dir, split)
    if mode == "miniwob":
        from environments.miniwob.adapter import MiniWoBAdapter
        return MiniWoBAdapter(task=task, seed=seed, **(miniwob_config or {}))
    raise ValueError(f"Unknown environment: {mode}")
