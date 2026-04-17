from __future__ import annotations

import argparse
import random
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kp2p_ws_client import (
    Endpoint,
    Kp2pClient,
    Kp2pError,
    Kp2pStreamOpenError,
    PROC_FRAME_TYPE_IFRAME,
    VideoFrame,
    connect_via_uid,
)

# Seconds to wait for a subprocess to exit after SIGTERM before escalating to SIGKILL.
_PROCESS_STOP_TIMEOUT_SECS = 5
# Seconds to wait for mediamtx to bind its RTSP port before giving up.
_MEDIAMTX_STARTUP_TIMEOUT_SECS = 5.0
# Fallback FPS to use when the source stream does not report one.
_DEFAULT_INPUT_FPS = 15.0

# NALU types that carry codec initialisation parameters (must precede every IDR).
_HEVC_PS_NALU_TYPES = frozenset((32, 33, 34))  # VPS, SPS, PPS
_H264_PS_NALU_TYPES = frozenset((7, 8))         # SPS, PPS


def _extract_parameter_sets(payload: bytes, is_hevc: bool) -> bytes:
    """Return all parameter-set NAL units found in an Annex B bitstream.

    For HEVC the function collects VPS (type 32), SPS (type 33) and PPS (type 34).
    For H.264 it collects SPS (type 7) and PPS (type 8).
    Start codes are preserved in the returned bytes.
    Returns b"" when no matching NAL units are found.
    """
    ps_types = _HEVC_PS_NALU_TYPES if is_hevc else _H264_PS_NALU_TYPES
    n = len(payload)
    # Collect (start_code_position, start_code_length) for every Annex B start code.
    sc_list: list[tuple[int, int]] = []
    i = 0
    while i < n:
        # Fast path: start codes always begin with 0x00.
        if payload[i] != 0:
            i += 1
            continue
        if i + 4 <= n and payload[i : i + 4] == b"\x00\x00\x00\x01":
            sc_list.append((i, 4))
            i += 4
        elif i + 3 <= n and payload[i : i + 3] == b"\x00\x00\x01":
            sc_list.append((i, 3))
            i += 3
        else:
            i += 1
    result = bytearray()
    for k, (sc_pos, sc_len) in enumerate(sc_list):
        nalu_hdr = sc_pos + sc_len
        if nalu_hdr >= n:
            continue
        nalu_byte = payload[nalu_hdr]
        nalu_type = (nalu_byte >> 1) & 0x3F if is_hevc else nalu_byte & 0x1F
        if nalu_type not in ps_types:
            continue
        nalu_end = sc_list[k + 1][0] if k + 1 < len(sc_list) else n
        result.extend(payload[sc_pos:nalu_end])
    return bytes(result)


@dataclass
class BridgeConfig:
    endpoint: Endpoint
    username: str
    password: str
    channel: int
    stream_id: int
    timeout: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Restream a Jooan/Juanvision kp2p camera as local RTSP. "
            "Run one bridge process per camera."
        )
    )
    parser.add_argument("--host", default="192.168.1.10", help="Direct device host for local ws://host:port mode.")
    parser.add_argument("--port", type=int, default=10000, help="Direct device websocket port.")
    parser.add_argument("--uid", default="", help="Optional cloud UID. When set, use the vendor TURN path.")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--channel", type=int, required=True, help="Zero-based channel index. Channel 2 means cam 3.")
    parser.add_argument("--stream-id", type=int, default=0, help="0=main stream, 1=substream.")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--ffmpeg-bin", default="ffmpeg", help="ffmpeg executable path.")
    parser.add_argument("--mediamtx-bin", default="mediamtx", help="mediamtx executable path.")
    parser.add_argument("--ffmpeg-loglevel", default="warning")
    parser.add_argument("--rtsp-listen-host", default="0.0.0.0", help="Host ffmpeg should bind the RTSP server to.")
    parser.add_argument("--rtsp-port", type=int, default=8554)
    parser.add_argument("--rtsp-path", default="cam3", help="RTSP path name, for example cam3.")
    parser.add_argument(
        "--client-host",
        "--frigate-host",
        dest="client_host",
        default="127.0.0.1",
        help="Hostname or IP clients should use to reach this bridge. Only affects printed output.",
    )
    parser.add_argument(
        "--camera-name",
        default="cam3",
        help="Camera name to use when printing an example client snippet.",
    )
    parser.add_argument(
        "--reconnect-delay",
        type=float,
        default=3.0,
        help="Seconds to wait before reconnecting after a source error.",
    )
    parser.add_argument(
        "--unavailable-stream-reconnect-delay",
        type=float,
        default=60.0,
        help="Seconds to wait before retrying channels that report stream unavailable.",
    )
    parser.add_argument(
        "--print-example-config",
        "--print-frigate-config",
        dest="print_example_config",
        action="store_true",
        help="Print a minimal example config snippet for this RTSP URL.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved RTSP URL and ffmpeg command, then exit without connecting.",
    )
    return parser


def make_direct_endpoint(host: str, port: int) -> Endpoint:
    ws_key = random.randint(1, 10000)
    return Endpoint(host, port, ws_key, ws_key, 0, "")


def resolve_bridge_config(args: argparse.Namespace) -> BridgeConfig:
    endpoint = connect_via_uid(args.uid, args.timeout) if args.uid else make_direct_endpoint(args.host, args.port)
    return BridgeConfig(
        endpoint=endpoint,
        username=args.username,
        password=args.password,
        channel=args.channel,
        stream_id=args.stream_id,
        timeout=args.timeout,
    )


def rtsp_listen_url(args: argparse.Namespace) -> str:
    return f"rtsp://{args.rtsp_listen_host}:{args.rtsp_port}/{args.rtsp_path.lstrip('/')}"


def client_rtsp_url(args: argparse.Namespace) -> str:
    return f"rtsp://{args.client_host}:{args.rtsp_port}/{args.rtsp_path.lstrip('/')}"


def print_example_config(args: argparse.Namespace) -> None:
    url = client_rtsp_url(args)
    print("example_rtsp_url:")
    print(f"  {url}")
    print("example_frigate_yaml:")
    print(f"  cameras:")
    print(f"    {args.camera_name}:")
    print(f"      ffmpeg:")
    print(f"        inputs:")
    print(f"          - path: {url}")
    print("            roles:")
    print("              - detect")
    print("              - record")


def resolve_input_fps(frame_fps: int) -> float:
    return float(frame_fps) if frame_fps > 0 else _DEFAULT_INPUT_FPS


def build_ffmpeg_command(args: argparse.Namespace, codec: str, frame_fps: int) -> list[str]:
    fmt = "hevc" if codec.upper() == "H265" else "h264"
    input_fps = resolve_input_fps(frame_fps)
    # Push to the local mediamtx relay on loopback.  mediamtx then serves
    # RTSP pull connections to clients on the same port.
    push_url = f"rtsp://127.0.0.1:{args.rtsp_port}/{args.rtsp_path.lstrip('/')}"
    return [
        args.ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        args.ffmpeg_loglevel,
        "-fflags",
        "+genpts+nobuffer",
        "-use_wallclock_as_timestamps",
        "1",
        "-flags",
        "low_delay",
        "-err_detect",
        "ignore_err",
        "-r",
        f"{input_fps:g}",
        "-f",
        fmt,
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "copy",
        "-f",
        "rtsp",
        "-rtsp_transport",
        "tcp",
        push_url,
    ]


class FfmpegRtspPublisher:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.codec: Optional[str] = None
        self.input_fps: Optional[float] = None
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.needs_keyframe: bool = True
        # Cached parameter-set NAL units (VPS/SPS/PPS for HEVC, SPS/PPS for H.264).
        # Kept across ffmpeg restarts so that IDR frames arriving without inline
        # parameter sets can still be decoded after a publisher reset.
        self._parameter_sets: bytes = b""
        # Counts how many ffmpeg sessions have been started for this publisher.
        # Used to distinguish the initial session from restarts (retransmissions).
        self._session_count: int = 0
        # Becomes True after the first payload write in the current ffmpeg session.
        self._has_written: bool = False

    @property
    def stream_num(self) -> int:
        """1-based camera/stream number derived from the zero-based channel index."""
        return self.args.channel + 1

    def ensure_started(self, codec: str, frame_fps: int) -> None:
        codec = codec.upper()
        input_fps = resolve_input_fps(frame_fps)
        if (
            self.process is not None
            and self.process.poll() is None
            and self.codec == codec
            and self.input_fps == input_fps
        ):
            return
        if self.codec is not None and self.codec != codec:
            # Discard stale parameter sets when the codec changes.
            self._parameter_sets = b""
        self.stop()
        command = build_ffmpeg_command(self.args, codec, frame_fps)
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=None,
            bufsize=0,
        )
        self.codec = codec
        self.input_fps = input_fps
        self.needs_keyframe = True
        self._session_count += 1
        self._has_written = False
        print(
            f"stream={self.stream_num} ffmpeg_started codec={codec} input_fps={input_fps:g} "
            f"rtsp_url={rtsp_listen_url(self.args)}",
            flush=True,
        )

    def write(self, payload: bytes) -> None:
        if self.process is None or self.process.stdin is None:
            raise Kp2pError(f"stream={self.stream_num} ffmpeg publisher is not started")
        if self.process.poll() is not None:
            raise Kp2pError(f"stream={self.stream_num} ffmpeg exited with code {self.process.returncode}")
        try:
            self.process.stdin.write(payload)
            self.process.stdin.flush()
        except BrokenPipeError as exc:
            raise Kp2pError(f"stream={self.stream_num} ffmpeg stdin broken pipe: {exc}") from exc
        if not self._has_written:
            self._has_written = True
            if self._session_count == 1:
                print(
                    f"stream={self.stream_num} jooan_to_rtsp=first_data_ok "
                    f"rtsp_url={rtsp_listen_url(self.args)}",
                    flush=True,
                )
            else:
                print(
                    f"stream={self.stream_num} jooan_to_rtsp=retransmission_ok "
                    f"session={self._session_count} rtsp_url={rtsp_listen_url(self.args)}",
                    flush=True,
                )

    def write_video_frame(self, frame: VideoFrame) -> None:
        """Write a video frame to ffmpeg, injecting parameter sets when necessary.

        Many cameras only embed VPS/SPS/PPS (HEVC) or SPS/PPS (H.264) in the
        very first IDR frame of a stream.  If ffmpeg is restarted mid-stream the
        next IDR frame arriving from the camera will lack those parameter sets and
        ffmpeg cannot initialise its decoder, causing the
        "PPS id out of range" / "Skipping invalid undecodable NALU" errors.

        This method caches the parameter sets whenever they are seen and
        transparently prepends them to any IDR frame that arrives without them.
        """
        payload = frame.payload
        if frame.frame_type == PROC_FRAME_TYPE_IFRAME:
            is_hevc = frame.codec.upper() == "H265"
            ps = _extract_parameter_sets(payload, is_hevc)
            if ps:
                # Fresher parameter sets – update the cache.
                self._parameter_sets = ps
            elif self._parameter_sets:
                # IDR arrived without parameter sets; prepend the cached copy.
                payload = self._parameter_sets + payload
        self.write(payload)

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=_PROCESS_STOP_TIMEOUT_SECS)
            except subprocess.TimeoutExpired:
                self.process.kill()
                try:
                    self.process.wait(timeout=_PROCESS_STOP_TIMEOUT_SECS)
                except subprocess.TimeoutExpired:
                    pass  # SIGKILL was sent; the OS will reap the process.
        self.process = None
        self.codec = None
        self.input_fps = None


def _terminate_process(process: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Terminate a process gracefully, killing it if it does not stop in time."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=_PROCESS_STOP_TIMEOUT_SECS)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=_PROCESS_STOP_TIMEOUT_SECS)
        except subprocess.TimeoutExpired:
            pass  # SIGKILL was sent; the OS will reap the process.


def generate_mediamtx_config(args: argparse.Namespace) -> str:
    """Return a minimal mediamtx YAML configuration for this camera's RTSP port.

    All non-RTSP protocols (RTMP, HLS, WebRTC, SRT) are explicitly disabled so
    that multiple per-camera mediamtx instances can run side-by-side without
    fighting over shared default ports (1935, 8888, 8889, 8890, …).  A single
    port-binding failure on any of those protocols causes mediamtx to exit,
    which would prevent cameras 2–N from ever publishing their streams.
    """
    rtsp_path = args.rtsp_path.lstrip("/")
    return (
        "logLevel: warn\n"
        "logDestinations: [stdout]\n"
        "api: no\n"
        "metrics: no\n"
        "pprof: no\n"
        "readTimeout: 30s\n"
        "writeTimeout: 30s\n"
        # RTSP is the only protocol we need; everything else must be disabled
        # to avoid port conflicts when several instances start concurrently.
        "rtsp: yes\n"
        f"rtspAddress: :{args.rtsp_port}\n"
        "protocols: [tcp]\n"
        "rtmp: no\n"
        "hls: no\n"
        "webrtc: no\n"
        "srt: no\n"
        "paths:\n"
        f"  {rtsp_path}:\n"
        "    source: publisher\n"
    )


def start_mediamtx_process(args: argparse.Namespace) -> subprocess.Popen[bytes]:
    """Write a per-camera mediamtx config and start the process.

    mediamtx acts as the RTSP relay: ffmpeg pushes the encoded stream to it via
    RTSP ANNOUNCE/RECORD, and RTSP clients (Frigate, go2rtc, VLC, …) pull from
    it via the standard DESCRIBE/SETUP/PLAY flow.  This replaces ffmpeg's own
    ``-rtsp_flags listen`` server mode, which fails with "Connection refused" on
    Alpine Linux builds.
    """
    config_path = Path(f"/tmp/mediamtx_{args.rtsp_port}.yml")
    config_path.write_text(generate_mediamtx_config(args))
    process: subprocess.Popen[bytes] = subprocess.Popen(
        [args.mediamtx_bin, str(config_path)],
        stdout=subprocess.DEVNULL,
        stderr=None,
        bufsize=0,
    )
    # Poll until mediamtx binds to the RTSP port (or fail fast if it exits).
    deadline = time.monotonic() + _MEDIAMTX_STARTUP_TIMEOUT_SECS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise Kp2pError(f"mediamtx exited unexpectedly with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", args.rtsp_port), timeout=0.1):
                break  # Port is accepting connections.
        except OSError:
            time.sleep(0.05)
    else:
        _terminate_process(process)
        raise Kp2pError(
            f"mediamtx did not bind to port {args.rtsp_port} within "
            f"{_MEDIAMTX_STARTUP_TIMEOUT_SECS:.0f}s"
        )
    return process


def check_runtime_requirements(args: argparse.Namespace) -> None:
    if shutil.which(args.ffmpeg_bin) is None and not Path(args.ffmpeg_bin).exists():
        raise Kp2pError(f"ffmpeg executable not found: {args.ffmpeg_bin}")
    if shutil.which(args.mediamtx_bin) is None and not Path(args.mediamtx_bin).exists():
        raise Kp2pError(f"mediamtx executable not found: {args.mediamtx_bin}")


def reconnect_delay_for_error(base_delay: float, unavailable_delay: float, exc: Exception) -> float:
    if isinstance(exc, Kp2pStreamOpenError) and not exc.retryable:
        return max(base_delay, unavailable_delay)
    return base_delay


def run_source_session(config: BridgeConfig, publisher: FfmpegRtspPublisher) -> None:
    stream_num = publisher.stream_num
    client = Kp2pClient(config.endpoint, timeout=config.timeout)
    try:
        client.connect()
        print(f"stream={stream_num} source_transport_open=ok", flush=True)
        client.login(config.username, config.password)
        print(f"stream={stream_num} source_login=ok", flush=True)
        cam_desc = client.open_stream(config.channel, config.stream_id)
        print(f"stream={stream_num} source_stream_open=ok channel={config.channel} stream={config.stream_id} cam_desc={cam_desc!r}", flush=True)
        while True:
            frame = client.recv_media()
            if not isinstance(frame, VideoFrame):
                continue
            publisher.ensure_started(frame.codec, frame.fps)
            if publisher.needs_keyframe:
                if frame.frame_type != PROC_FRAME_TYPE_IFRAME:
                    continue
                publisher.needs_keyframe = False
                print(
                    f"stream={stream_num} source_keyframe=ok codec={frame.codec} width={frame.width} "
                    f"height={frame.height} fps={frame.fps}",
                    flush=True,
                )
            publisher.write_video_frame(frame)
    finally:
        try:
            client.close_stream(config.channel, config.stream_id)
        except Exception:
            pass
        client.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    stream_num = args.channel + 1
    print(f"stream={stream_num} rtsp_listen_url={rtsp_listen_url(args)}", flush=True)
    print(f"stream={stream_num} client_rtsp_url={client_rtsp_url(args)}", flush=True)
    if args.print_example_config:
        print_example_config(args)

    if args.dry_run:
        if shutil.which(args.ffmpeg_bin) is None and not Path(args.ffmpeg_bin).exists():
            print(f"stream={stream_num} ffmpeg_status=missing path={args.ffmpeg_bin}", flush=True)
        else:
            print(f"stream={stream_num} ffmpeg_status=found path={args.ffmpeg_bin}", flush=True)
        if shutil.which(args.mediamtx_bin) is None and not Path(args.mediamtx_bin).exists():
            print(f"stream={stream_num} mediamtx_status=missing path={args.mediamtx_bin}", flush=True)
        else:
            print(f"stream={stream_num} mediamtx_status=found path={args.mediamtx_bin}", flush=True)
        print(
            f"stream={stream_num} ffmpeg_command="
            + subprocess.list2cmdline(build_ffmpeg_command(args, "H265", int(_DEFAULT_INPUT_FPS))),
            flush=True,
        )
        return 0

    try:
        check_runtime_requirements(args)
    except Exception as exc:
        print(f"stream={stream_num} error={exc}", flush=True)
        return 1

    mediamtx_process: Optional[subprocess.Popen[bytes]] = None
    publisher = FfmpegRtspPublisher(args)
    try:
        while True:
            try:
                # Start or restart mediamtx if the relay process is not running.
                if mediamtx_process is None:
                    mediamtx_process = start_mediamtx_process(args)
                    print(f"stream={stream_num} mediamtx_started rtsp_url={rtsp_listen_url(args)}", flush=True)
                elif mediamtx_process.poll() is not None:
                    print(
                        f"stream={stream_num} mediamtx_exited code={mediamtx_process.returncode}, restarting",
                        flush=True,
                    )
                    publisher.stop()
                    mediamtx_process = start_mediamtx_process(args)
                    print(f"stream={stream_num} mediamtx_restarted rtsp_url={rtsp_listen_url(args)}", flush=True)
                config = resolve_bridge_config(args)
                if args.uid:
                    print(
                        f"stream={stream_num} source_mode=uid turn_host={config.endpoint.host} "
                        f"turn_port={config.endpoint.port} sid={config.endpoint.sid}",
                        flush=True,
                    )
                else:
                    print(
                        f"stream={stream_num} source_mode=direct host={config.endpoint.host} "
                        f"port={config.endpoint.port} sid={config.endpoint.sid}",
                        flush=True,
                    )
                run_source_session(config, publisher)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                delay = reconnect_delay_for_error(
                    args.reconnect_delay,
                    args.unavailable_stream_reconnect_delay,
                    exc,
                )
                print(f"stream={stream_num} source_error={exc}", flush=True)
                print(f"stream={stream_num} source_retry_in={delay:g}s", flush=True)
                time.sleep(delay)
    except KeyboardInterrupt:
        print(f"stream={stream_num} bridge_stopped=keyboard_interrupt", flush=True)
        return 0
    finally:
        publisher.stop()
        if mediamtx_process is not None:
            _terminate_process(mediamtx_process)


if __name__ == "__main__":
    raise SystemExit(main())
