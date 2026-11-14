"""Application-level environment assembly; optional dependencies load lazily."""
def create_environment(mode, *, config_path=None, data_dir=None, split="valid_seen"):
    if mode == "mock":
        from environments.mock import MockEnvironment
        return MockEnvironment()
    if mode == "alfworld":
        from environments.alfworld_adapter import ALFWorldAdapter
        return ALFWorldAdapter(config_path, data_dir, split)
    raise ValueError(f"Unknown environment: {mode}")
