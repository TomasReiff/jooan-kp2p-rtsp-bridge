from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "jooan_kp2p_rtsp_bridge" / "app"
sys.path.insert(0, str(APP_DIR))

from kp2p_ws_client import Kp2pStreamOpenError, parse_api_header  # noqa: E402
from rtsp_bridge import build_ffmpeg_command, build_parser, reconnect_delay_for_error  # noqa: E402


class StreamFailureTests(unittest.TestCase):
    def test_parse_api_header_uses_signed_result(self) -> None:
        payload = (
            struct.pack("<I", 0x4B503250)
            + struct.pack("<I", 1)
            + struct.pack("<I", 7)
            + struct.pack("<I", 31)
            + struct.pack("<i", -40)
            + struct.pack("<I", 0)
        )

        header = parse_api_header(payload)

        self.assertEqual(header.result, -40)

    def test_channel_unavailable_errors_back_off_longer(self) -> None:
        exc = Kp2pStreamOpenError(channel=1, stream_id=0, result=-40)

        self.assertFalse(exc.retryable)
        self.assertEqual(reconnect_delay_for_error(3.0, exc), 60.0)

    def test_ffmpeg_command_generates_timestamps(self) -> None:
        args = build_parser().parse_args(["--password", "secret", "--channel", "0"])

        command = build_ffmpeg_command(args, "H264")

        self.assertIn("+genpts+nobuffer", command)


if __name__ == "__main__":
    unittest.main()
