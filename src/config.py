"""Configuration loader for the bank statement chat bot."""

import os
from pathlib import Path
import yaml

# Environment variable overrides for containerized deployments. Each maps a
# BANKBOT_* variable to a (section, key) in the config dict, following the
# INVESTEC_* env-var pattern already used for credentials.
ENV_OVERRIDES = {
    "BANKBOT_LLM_BACKEND": ("llm", "backend"),
    "BANKBOT_LLM_HOST": ("llm", "host"),
    "BANKBOT_LLM_PORT": ("llm", "port"),
    "BANKBOT_LLM_MODEL": ("llm", "model"),
    "BANKBOT_DB": ("paths", "database"),
    "BANKBOT_STATEMENTS_DIR": ("paths", "statements_dir"),
}


def load_config(config_path: str | Path = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    return config


def _apply_env_overrides(config: dict) -> dict:
    """Apply BANKBOT_* environment variable overrides to the config dict."""
    for env_var, (section, key) in ENV_OVERRIDES.items():
        value = os.environ.get(env_var)
        if value is None:
            continue
        config.setdefault(section, {})[key] = value
    return config


def get_config() -> dict:
    """Get configuration, searching in common locations."""
    search_paths = [
        Path("config.yaml"),
        Path(__file__).parent.parent / "config.yaml",
    ]

    for path in search_paths:
        if path.exists():
            return _apply_env_overrides(load_config(path))

    raise FileNotFoundError("Could not find config.yaml in any expected location")  # pragma: no cover
