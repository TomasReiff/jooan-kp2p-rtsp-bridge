from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "jooan_kp2p_rtsp_bridge" / "app"
sys.path.insert(0, str(APP_DIR))

from kp2p_ws_client import (  # noqa: E402
    Kp2pStreamOpenError,
    P2P_FRAME_TYPE_LIVE,
    PROC_FRAME_MAGIC,
    PROC_FRAME_TYPE_IFRAME,
    find_annexb_start,
    parse_api_header,
    parse_video_frame,
)
from rtsp_bridge import (  # noqa: E402
    _DEFAULT_INPUT_FPS,
    build_ffmpeg_command,
    build_parser,
    generate_mediamtx_config,
    reconnect_delay_for_error,
    resolve_input_fps,
)


class StreamFailureTests(unittest.TestCase):
    def build_video_payload(self, codec: bytes, stream_payload: bytes, *, extra_prefix: bytes = b"") -> bytes:
        frame_head = bytearray(24)
        frame_head[0:4] = struct.pack("<I", PROC_FRAME_MAGIC)
        frame_head[8:12] = struct.pack("<I", P2P_FRAME_TYPE_LIVE)
        frame_head[16:24] = struct.pack("<Q", 1234)

        frame_meta = struct.pack("<I", PROC_FRAME_TYPE_IFRAME) + struct.pack("<I", 0)

        params = bytearray(24)
        params[0 : len(codec)] = codec
        params[8:12] = struct.pack("<I", 15)
        params[12:16] = struct.pack("<I", 2304)
        params[16:20] = struct.pack("<I", 1296)
        return bytes(frame_head) + frame_meta + bytes(params) + extra_prefix + stream_payload

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
        self.assertEqual(reconnect_delay_for_error(3.0, 60.0, exc), 60.0)

    def test_channel_unavailable_errors_use_configured_delay(self) -> None:
        exc = Kp2pStreamOpenError(channel=1, stream_id=0, result=-40)

        self.assertEqual(reconnect_delay_for_error(3.0, 90.0, exc), 90.0)

    def test_ffmpeg_command_generates_timestamps(self) -> None:
        args = build_parser().parse_args(["--password", "secret", "--channel", "0"])

        command = build_ffmpeg_command(args, "H264", 15)

        self.assertIn("+genpts+nobuffer", command)
        self.assertIn("-use_wallclock_as_timestamps", command)
        self.assertIn("1", command)
        self.assertIn("-r", command)
        self.assertIn("15", command)

    def test_mediamtx_config_allows_longer_stream_gaps(self) -> None:
        args = build_parser().parse_args(["--password", "secret", "--channel", "0"])

        config = generate_mediamtx_config(args)

        self.assertIn("readTimeout: 30s", config)
        self.assertIn("writeTimeout: 30s", config)

    def test_source_timeout_default_is_longer(self) -> None:
        args = build_parser().parse_args(["--password", "secret", "--channel", "0"])

        self.assertEqual(args.timeout, 30.0)

    def test_missing_source_fps_uses_default(self) -> None:
        self.assertEqual(resolve_input_fps(0), _DEFAULT_INPUT_FPS)

    def test_find_annexb_start_accepts_immediate_start_code(self) -> None:
        payload = b"\x00\x00\x00\x01\x26\x01"
        self.assertEqual(find_annexb_start(payload, 0), 0)

    def test_parse_video_frame_accepts_payload_without_extra_8_bytes(self) -> None:
        stream_payload = b"\x00\x00\x00\x01\x26\x01\x02\x03"
        frame = parse_video_frame(self.build_video_payload(b"H265", stream_payload), 0)

        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.payload, stream_payload)

    def test_parse_video_frame_accepts_payload_with_extra_8_bytes(self) -> None:
        stream_payload = b"\x00\x00\x00\x01\x26\x01\x02\x03"
        frame = parse_video_frame(self.build_video_payload(b"H265", stream_payload, extra_prefix=b"\x99" * 8), 0)

        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.payload, stream_payload)


if __name__ == "__main__":
    unittest.main()
