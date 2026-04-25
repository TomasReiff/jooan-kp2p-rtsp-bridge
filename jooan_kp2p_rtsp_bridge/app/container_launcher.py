from __future__ import annotations

import json
import os
from pathlib import Path

from addon_launcher import load_options_file, log_event, run_bridge


CONFIG_PATH_ENV = "BRIDGE_CONFIG_PATH"
PUBLIC_RTSP_HOST_ENV = "BRIDGE_PUBLIC_RTSP_HOST"
DEFAULT_CONFIG_PATHS = (
    Path("/config/bridge-config.json"),
    Path("/config/options.json"),
    Path("/data/options.json"),
)


def resolve_config_path() -> Path:
    configured_path = os.environ.get(CONFIG_PATH_ENV)
    if configured_path:
        return Path(configured_path)
    for path in DEFAULT_CONFIG_PATHS:
        if path.exists():
            return path
    return DEFAULT_CONFIG_PATHS[0]


def load_container_options() -> dict:
    config_path = resolve_config_path()
    if not config_path.exists():
        raise FileNotFoundError(
            f"configuration file not found at {config_path}; "
            f"mount a JSON file there or set {CONFIG_PATH_ENV}"
        )
    options = load_options_file(config_path)
    if not isinstance(options, dict) or not options:
        raise ValueError(f"configuration file must contain a non-empty JSON object: {config_path}")
    return options


def main() -> int:
    try:
        options = load_container_options()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        log_event(f"error=container_config_load_failed reason={exc}")
        return 1
    host_label = os.environ.get(PUBLIC_RTSP_HOST_ENV, "<CONTAINER_HOST_IP>")
    return run_bridge(options, host_label=host_label)


if __name__ == "__main__":
    raise SystemExit(main())
