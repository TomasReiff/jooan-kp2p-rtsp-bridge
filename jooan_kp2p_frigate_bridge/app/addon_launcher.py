from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


OPTIONS_PATH = Path("/data/options.json")


@dataclass
class CameraConfig:
    channel: int
    stream_id: int
    rtsp_port: int
    rtsp_path: str


def load_options() -> dict:
    return json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def build_camera_configs(options: dict) -> list[CameraConfig]:
    cameras: list[CameraConfig] = []
    raw_cameras = options.get("cameras", [])
    if isinstance(raw_cameras, list):
        for raw_camera in raw_cameras:
            if not isinstance(raw_camera, dict):
                continue
            channel = _as_int(raw_camera.get("channel"), -1)
            if channel < 0:
                continue
            if not _as_bool(raw_camera.get("enabled", True), True):
                continue
            cameras.append(
                CameraConfig(
                    channel=channel,
                    stream_id=_as_int(raw_camera.get("stream_id"), 0),
                    rtsp_port=_as_int(raw_camera.get("rtsp_port"), 8554 + channel),
                    rtsp_path=str(raw_camera.get("rtsp_path", f"cam{channel + 1}")),
                )
            )
        if cameras:
            return cameras

    # Backward-compatible fallback for older fixed-slot configs.
    camera_count = max(1, min(64, _as_int(options.get("camera_count"), 8)))
    for index in range(1, camera_count + 1):
        if not _as_bool(options.get(f"camera_{index}_enabled", False)):
            continue
        cameras.append(
            CameraConfig(
                channel=index - 1,
                stream_id=_as_int(options.get(f"camera_{index}_stream_id"), 0),
                rtsp_port=_as_int(options.get(f"camera_{index}_rtsp_port"), 8553 + index),
                rtsp_path=str(options.get(f"camera_{index}_rtsp_path", f"cam{index}")),
            )
        )
    return cameras


def build_bridge_command(options: dict, camera: CameraConfig) -> list[str]:
    command = [
        sys.executable,
        "/app/frigate_rtsp_bridge.py",
        "--username",
        str(options.get("username", "admin")),
        "--password",
        str(options.get("password", "")),
        "--channel",
        str(camera.channel),
        "--stream-id",
        str(camera.stream_id),
        "--rtsp-listen-host",
        "0.0.0.0",
        "--rtsp-port",
        str(camera.rtsp_port),
        "--rtsp-path",
        camera.rtsp_path,
        "--ffmpeg-loglevel",
        str(options.get("ffmpeg_loglevel", "warning")),
        "--reconnect-delay",
        str(options.get("reconnect_delay", 3)),
        "--camera-name",
        f"cam{camera.channel + 1}",
    ]
    if options.get("use_uid", False):
        command.extend(["--uid", str(options.get("uid", ""))])
    else:
        command.extend(["--host", str(options.get("host", "192.168.1.10")), "--port", str(options.get("port", 10000))])
    return command


def terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    options = load_options()
    cameras = build_camera_configs(options)
    if not cameras:
        print("error=no enabled cameras found in add-on configuration", flush=True)
        return 1

    processes: list[subprocess.Popen[bytes]] = []
    stopping = False

    def handle_signal(signum, frame) -> None:  # type: ignore[unused-argument]
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        for camera in cameras:
            command = build_bridge_command(options, camera)
            print(
                f"starting camera={camera.channel + 1} channel={camera.channel} "
                f"stream_id={camera.stream_id} rtsp=rtsp://<HA_HOST_IP>:{camera.rtsp_port}/{camera.rtsp_path}",
                flush=True,
            )
            processes.append(subprocess.Popen(command))

        while not stopping:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    print(f"error=child process exited code={return_code}", flush=True)
                    return return_code or 1
            time.sleep(2)
        return 0
    finally:
        for process in processes:
            terminate_process(process)


if __name__ == "__main__":
    raise SystemExit(main())
