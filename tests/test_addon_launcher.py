from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "jooan_kp2p_rtsp_bridge" / "app"
sys.path.insert(0, str(APP_DIR))

import addon_launcher  # noqa: E402


class AddonLauncherOptionsTests(unittest.TestCase):
    def test_default_options_match_manifest_defaults(self) -> None:
        expected_first_camera = {
            "channel": 0,
            "enabled": True,
            "stream_id": 1,
            "rtsp_port": 8554,
            "rtsp_path": "cam1",
        }

        options = addon_launcher.default_options()

        self.assertEqual(options["host"], "192.168.1.10")
        self.assertEqual(options["cameras"][0], expected_first_camera)
        self.assertEqual(len(options["cameras"]), 8)
        self.assertTrue(all(camera["rtsp_port"] == 8554 for camera in options["cameras"]))

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

    def test_load_options_restores_backup_when_current_config_is_packaged_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            options_path = Path(temp_dir) / "options.json"
            backup_path = Path(temp_dir) / "options.last_good.json"
            options_path.write_text(json.dumps(addon_launcher.default_options()), encoding="utf-8")
            backup = {"host": "192.168.1.99", "cameras": [{"channel": 4, "enabled": True, "rtsp_path": "cam5"}]}
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

    def test_build_bridge_command_uses_shared_mediamtx_flags(self) -> None:
        options = addon_launcher.default_options()
        camera = addon_launcher.build_camera_configs(options)[0]

        command = addon_launcher.build_bridge_command(options, camera)

        self.assertIn("--shared-mediamtx", command)
        self.assertIn("--mediamtx-host", command)
        self.assertIn("127.0.0.1", command)
        self.assertEqual(command[command.index("--rtsp-port") + 1], "8554")

    def test_build_shared_mediamtx_config_contains_all_paths(self) -> None:
        cameras = [
            addon_launcher.CameraConfig(channel=0, stream_id=1, rtsp_port=8554, rtsp_path="cam1"),
            addon_launcher.CameraConfig(channel=1, stream_id=1, rtsp_port=8554, rtsp_path="cam2"),
        ]

        config = addon_launcher.build_shared_mediamtx_config(cameras)

        self.assertIn("rtspAddress: :8554", config)
        self.assertIn("  cam1:", config)
        self.assertIn("  cam2:", config)

    def test_build_shared_mediamtx_config_rejects_mixed_ports(self) -> None:
        cameras = [
            addon_launcher.CameraConfig(channel=0, stream_id=1, rtsp_port=8554, rtsp_path="cam1"),
            addon_launcher.CameraConfig(channel=1, stream_id=1, rtsp_port=8555, rtsp_path="cam2"),
        ]

        with self.assertRaisesRegex(ValueError, "same rtsp_port"):
            addon_launcher.build_shared_mediamtx_config(cameras)

    def test_start_stream_logger_re_emits_lines_with_timestamp_wrapper(self) -> None:
        messages: list[str] = []
        original_log_event = addon_launcher.log_event
        addon_launcher.log_event = messages.append
        try:
            thread = addon_launcher.start_stream_logger(
                io.BytesIO(b"mediamtx ready\nwarning here\n"),
                lambda line: f"shared_mediamtx_log={line}",
            )
            self.assertIsNotNone(thread)
            assert thread is not None
            thread.join(timeout=1)
        finally:
            addon_launcher.log_event = original_log_event

        self.assertEqual(
            messages,
            [
                "shared_mediamtx_log=mediamtx ready",
                "shared_mediamtx_log=warning here",
            ],
        )


if __name__ == "__main__":
    unittest.main()
