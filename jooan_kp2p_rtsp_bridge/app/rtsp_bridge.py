from __future__ import annotations

import argparse
import random
import shutil
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
    PROC_FRAME_TYPE_IFRAME,
    VideoFrame,
    connect_via_uid,
)


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
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--ffmpeg-bin", default="ffmpeg", help="ffmpeg executable path.")
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


def build_ffmpeg_command(args: argparse.Namespace, codec: str) -> list[str]:
    fmt = "hevc" if codec.upper() == "H265" else "h264"
    return [
        args.ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        args.ffmpeg_loglevel,
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
        "-err_detect",
        "ignore_err",
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
        "-rtsp_flags",
        "listen",
        rtsp_listen_url(args),
    ]


class FfmpegRtspPublisher:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.codec: Optional[str] = None
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.needs_keyframe: bool = True

    def ensure_started(self, codec: str) -> None:
        codec = codec.upper()
        if self.process is not None and self.process.poll() is None and self.codec == codec:
            return
        self.stop()
        command = build_ffmpeg_command(self.args, codec)
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=None,
            bufsize=0,
        )
        self.codec = codec
        self.needs_keyframe = True
        print(f"ffmpeg_started codec={codec} rtsp_url={rtsp_listen_url(self.args)}")

    def write(self, payload: bytes) -> None:
        if self.process is None or self.process.stdin is None:
            raise Kp2pError("ffmpeg publisher is not started")
        if self.process.poll() is not None:
            raise Kp2pError(f"ffmpeg exited with code {self.process.returncode}")
        self.process.stdin.write(payload)
        self.process.stdin.flush()

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
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        self.codec = None


def check_runtime_requirements(args: argparse.Namespace) -> None:
    if shutil.which(args.ffmpeg_bin) is None and not Path(args.ffmpeg_bin).exists():
        raise Kp2pError(f"ffmpeg executable not found: {args.ffmpeg_bin}")


def run_source_session(config: BridgeConfig, publisher: FfmpegRtspPublisher) -> None:
    client = Kp2pClient(config.endpoint, timeout=config.timeout)
    try:
        client.connect()
        print("source_transport_open=ok")
        client.login(config.username, config.password)
        print("source_login=ok")
        cam_desc = client.open_stream(config.channel, config.stream_id)
        print(f"source_stream_open=ok channel={config.channel} stream={config.stream_id} cam_desc={cam_desc!r}")
        while True:
            frame = client.recv_media()
            if not isinstance(frame, VideoFrame):
                continue
            publisher.ensure_started(frame.codec)
            if publisher.needs_keyframe:
                if frame.frame_type != PROC_FRAME_TYPE_IFRAME:
                    continue
                publisher.needs_keyframe = False
                print(
                    f"source_keyframe=ok codec={frame.codec} width={frame.width} "
                    f"height={frame.height} fps={frame.fps}"
                )
            publisher.write(frame.payload)
    finally:
        try:
            client.close_stream(config.channel, config.stream_id)
        except Exception:
            pass
        client.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print(f"rtsp_listen_url={rtsp_listen_url(args)}")
    print(f"client_rtsp_url={client_rtsp_url(args)}")
    if args.print_example_config:
        print_example_config(args)

    if args.dry_run:
        if shutil.which(args.ffmpeg_bin) is None and not Path(args.ffmpeg_bin).exists():
            print(f"ffmpeg_status=missing path={args.ffmpeg_bin}")
        else:
            print(f"ffmpeg_status=found path={args.ffmpeg_bin}")
        print("ffmpeg_command=" + subprocess.list2cmdline(build_ffmpeg_command(args, "H265")))
        return 0

    try:
        check_runtime_requirements(args)
    except Exception as exc:
        print(f"error={exc}")
        return 1

    publisher = FfmpegRtspPublisher(args)
    try:
        while True:
            try:
                config = resolve_bridge_config(args)
                if args.uid:
                    print(
                        f"source_mode=uid turn_host={config.endpoint.host} "
                        f"turn_port={config.endpoint.port} sid={config.endpoint.sid}"
                    )
                else:
                    print(
                        f"source_mode=direct host={config.endpoint.host} "
                        f"port={config.endpoint.port} sid={config.endpoint.sid}"
                    )
                run_source_session(config, publisher)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                print(f"source_error={exc}")
                time.sleep(args.reconnect_delay)
    except KeyboardInterrupt:
        print("bridge_stopped=keyboard_interrupt")
        return 0
    finally:
        publisher.stop()


if __name__ == "__main__":
    raise SystemExit(main())
