from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "jooan_kp2p_rtsp_bridge" / "app"
sys.path.insert(0, str(APP_DIR))

import addon_launcher  # noqa: E402


class AddonLauncherOptionsTests(unittest.TestCase):
    def test_load_options_saves_non_empty_config_as_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            options_path = Path(temp_dir) / "options.json"
            backup_path = Path(temp_dir) / "options.last_good.json"
            options = {"host": "192.168.1.77", "cameras": [{"channel": 3, "enabled": True}]}
            options_path.write_text(json.dumps(options), encoding="utf-8")

            old_options_path = addon_launcher.OPTIONS_PATH
            old_backup_path = addon_launcher.OPTIONS_BACKUP_PATH
            addon_launcher.OPTIONS_PATH = options_path
            addon_launcher.OPTIONS_BACKUP_PATH = backup_path
            try:
                loaded = addon_launcher.load_options()
            finally:
                addon_launcher.OPTIONS_PATH = old_options_path
                addon_launcher.OPTIONS_BACKUP_PATH = old_backup_path

            self.assertEqual(loaded, options)
            self.assertEqual(json.loads(backup_path.read_text(encoding="utf-8")), options)

    def test_load_options_restores_backup_when_current_config_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            options_path = Path(temp_dir) / "options.json"
            backup_path = Path(temp_dir) / "options.last_good.json"
            options_path.write_text("{}", encoding="utf-8")
            backup = {"uid": "ABC123", "cameras": [{"channel": 6, "enabled": True, "rtsp_path": "cam7"}]}
            backup_path.write_text(json.dumps(backup), encoding="utf-8")

            old_options_path = addon_launcher.OPTIONS_PATH
            old_backup_path = addon_launcher.OPTIONS_BACKUP_PATH
            addon_launcher.OPTIONS_PATH = options_path
            addon_launcher.OPTIONS_BACKUP_PATH = backup_path
            try:
                loaded = addon_launcher.load_options()
            finally:
                addon_launcher.OPTIONS_PATH = old_options_path
                addon_launcher.OPTIONS_BACKUP_PATH = old_backup_path

            self.assertEqual(loaded, backup)
            self.assertEqual(json.loads(options_path.read_text(encoding="utf-8")), backup)


if __name__ == "__main__":
    unittest.main()
