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
    convert_length_prefixed_to_annexb,
    detect_codec_from_annexb,
    find_annexb_start,
    iter_annexb_nal_units,
    normalize_video_payload,
    parse_api_header,
    parse_video_frame,
    slice_declared_frame_payload,
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
    def build_video_payload(
        self,
        codec: bytes,
        stream_payload: bytes,
        *,
        extra_prefix: bytes = b"",
        declared_length: int | None = None,
    ) -> bytes:
        frame_head = bytearray(24)
        frame_head[0:4] = struct.pack("<I", PROC_FRAME_MAGIC)
        header_overhead = 24 + 8 + 24 + len(extra_prefix)
        actual_declared_length = declared_length if declared_length is not None else header_overhead + len(stream_payload)
        frame_head[4:8] = struct.pack("<I", actual_declared_length)
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

    def test_convert_length_prefixed_to_annexb(self) -> None:
        payload = b"\x00\x00\x00\x04\x26\x01\x02\x03\x00\x00\x00\x03\x44\x55\x66"
        expected = b"\x00\x00\x00\x01\x26\x01\x02\x03\x00\x00\x00\x01\x44\x55\x66"

        self.assertEqual(convert_length_prefixed_to_annexb(payload), expected)

    def test_iter_annexb_nal_units_returns_units(self) -> None:
        payload = b"\x00\x00\x00\x01\x67\x01\x02\x00\x00\x00\x01\x68\x03"

        self.assertEqual(iter_annexb_nal_units(payload), [b"\x67\x01\x02", b"\x68\x03"])

    def test_detect_codec_from_annexb_detects_h264(self) -> None:
        payload = b"\x00\x00\x00\x01\x67\x64\x00\x1f\x00\x00\x00\x01\x68\xee"

        self.assertEqual(detect_codec_from_annexb(payload), "H264")

    def test_detect_codec_from_annexb_detects_h265(self) -> None:
        payload = b"\x00\x00\x00\x01\x40\x01\x0c\x01\xff\x00\x00\x00\x01\x42\x01\x01"

        self.assertEqual(detect_codec_from_annexb(payload), "H265")

    def test_slice_declared_frame_payload_accepts_total_declared_length(self) -> None:
        payload = b"\x11" * 56 + b"\xaa\xbb\xcc\xdd" + b"\xee\xff"

        sliced = slice_declared_frame_payload(payload, 0, 56, 60)

        self.assertEqual(sliced, b"\xaa\xbb\xcc\xdd")

    def test_slice_declared_frame_payload_accepts_data_only_declared_length(self) -> None:
        payload = b"\x11" * 56 + b"\xaa\xbb\xcc\xdd" + b"\xee\xff"

        sliced = slice_declared_frame_payload(payload, 0, 56, 4)

        self.assertEqual(sliced, b"\xaa\xbb\xcc\xdd")

    def test_normalize_video_payload_accepts_length_prefixed_with_prefix_bytes(self) -> None:
        payload = b"\x99" * 8 + b"\x00\x00\x00\x04\x26\x01\x02\x03"

        normalized = normalize_video_payload(payload, 0)

        self.assertEqual(normalized, b"\x00\x00\x00\x01\x26\x01\x02\x03")

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

    def test_parse_video_frame_accepts_length_prefixed_payload(self) -> None:
        stream_payload = b"\x00\x00\x00\x04\x26\x01\x02\x03"
        frame = parse_video_frame(self.build_video_payload(b"H265", stream_payload), 0)

        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.payload, b"\x00\x00\x00\x01\x26\x01\x02\x03")

    def test_parse_video_frame_overrides_wrong_codec_metadata(self) -> None:
        stream_payload = b"\x00\x00\x00\x01\x67\x64\x00\x1f"
        frame = parse_video_frame(self.build_video_payload(b"H265", stream_payload), 0)

        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.codec, "H264")

    def test_parse_video_frame_uses_declared_length_to_drop_trailing_bytes(self) -> None:
        stream_payload = b"\x00\x00\x00\x01\x67\x64\x00\x1f"
        frame = parse_video_frame(
            self.build_video_payload(
                b"H264",
                stream_payload + b"\x99\x88\x77\x66",
                declared_length=56 + len(stream_payload),
            ),
            0,
        )

        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame.payload, stream_payload)


if __name__ == "__main__":
    unittest.main()
