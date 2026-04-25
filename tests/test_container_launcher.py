from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "jooan_kp2p_rtsp_bridge" / "app"
sys.path.insert(0, str(APP_DIR))

import container_launcher  # noqa: E402


class ContainerLauncherTests(unittest.TestCase):
    def test_resolve_config_path_prefers_environment_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            expected = Path(temp_dir) / "custom-config.json"
            old_value = os.environ.get(container_launcher.CONFIG_PATH_ENV)
            os.environ[container_launcher.CONFIG_PATH_ENV] = str(expected)
            try:
                resolved = container_launcher.resolve_config_path()
            finally:
                if old_value is None:
                    del os.environ[container_launcher.CONFIG_PATH_ENV]
                else:
                    os.environ[container_launcher.CONFIG_PATH_ENV] = old_value

            self.assertEqual(resolved, expected)

    def test_resolve_config_path_uses_first_existing_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "bridge-config.json"
            second = Path(temp_dir) / "options.json"
            second.write_text("{}", encoding="utf-8")

            old_paths = container_launcher.DEFAULT_CONFIG_PATHS
            old_value = os.environ.get(container_launcher.CONFIG_PATH_ENV)
            container_launcher.DEFAULT_CONFIG_PATHS = (first, second)
            if old_value is not None:
                del os.environ[container_launcher.CONFIG_PATH_ENV]
            try:
                resolved = container_launcher.resolve_config_path()
            finally:
                container_launcher.DEFAULT_CONFIG_PATHS = old_paths
                if old_value is not None:
                    os.environ[container_launcher.CONFIG_PATH_ENV] = old_value

            self.assertEqual(resolved, second)

    def test_load_container_options_rejects_empty_object(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "bridge-config.json"
            config_path.write_text("{}", encoding="utf-8")

            old_paths = container_launcher.DEFAULT_CONFIG_PATHS
            old_value = os.environ.get(container_launcher.CONFIG_PATH_ENV)
            container_launcher.DEFAULT_CONFIG_PATHS = (config_path,)
            if old_value is not None:
                del os.environ[container_launcher.CONFIG_PATH_ENV]
            try:
                with self.assertRaisesRegex(ValueError, "non-empty JSON object"):
                    container_launcher.load_container_options()
            finally:
                container_launcher.DEFAULT_CONFIG_PATHS = old_paths
                if old_value is not None:
                    os.environ[container_launcher.CONFIG_PATH_ENV] = old_value

    def test_load_container_options_reads_json_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "bridge-config.json"
            options = {"host": "192.168.1.44", "password": "secret", "cameras": [{"channel": 0, "enabled": True}]}
            config_path.write_text(json.dumps(options), encoding="utf-8")

            old_paths = container_launcher.DEFAULT_CONFIG_PATHS
            old_value = os.environ.get(container_launcher.CONFIG_PATH_ENV)
            container_launcher.DEFAULT_CONFIG_PATHS = (config_path,)
            if old_value is not None:
                del os.environ[container_launcher.CONFIG_PATH_ENV]
            try:
                loaded = container_launcher.load_container_options()
            finally:
                container_launcher.DEFAULT_CONFIG_PATHS = old_paths
                if old_value is not None:
                    os.environ[container_launcher.CONFIG_PATH_ENV] = old_value

            self.assertEqual(loaded, options)


if __name__ == "__main__":
    unittest.main()
