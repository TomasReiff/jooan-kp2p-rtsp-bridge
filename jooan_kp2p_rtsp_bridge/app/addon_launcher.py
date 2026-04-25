from __future__ import annotations

import json
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Callable


OPTIONS_PATH = Path("/data/options.json")
OPTIONS_BACKUP_PATH = Path("/data/options.last_good.json")
STARTUP_STAGGER_SECONDS = 1.0
PROCESS_STOP_TIMEOUT_SECS = 5.0
MEDIAMTX_STARTUP_TIMEOUT_SECS = 5.0


def log_event(message: str) -> None:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"{timestamp} {message}", flush=True)


def start_stream_logger(
    stream: BinaryIO | None,
    format_message: Callable[[str], str],
) -> threading.Thread | None:
    if stream is None:
        return None

    def drain() -> None:
        try:
            while True:
                raw_line = stream.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if line:
                    log_event(format_message(line))
        finally:
            stream.close()

    thread = threading.Thread(target=drain, name="subprocess-log-drain", daemon=True)
    thread.start()
    return thread


@dataclass
class CameraConfig:
    channel: int
    stream_id: int
    rtsp_port: int
    rtsp_path: str


def default_options() -> dict:
    return {
        "use_uid": False,
        "host": "192.168.1.10",
        "port": 10000,
        "uid": "",
        "username": "admin",
        "password": "",
        "reconnect_delay": 3,
        "ffmpeg_loglevel": "warning",
        "cameras": [
            {
                "channel": channel,
                "enabled": True,
                "stream_id": 1,
                "rtsp_port": 8554,
                "rtsp_path": f"cam{channel + 1}",
            }
            for channel in range(8)
        ],
    }


def load_options_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_options_file(path: Path, options: dict) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(options, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def has_persistable_options(options: object) -> bool:
    return isinstance(options, dict) and bool(options)


def is_default_options(options: object) -> bool:
    return isinstance(options, dict) and options == default_options()


def load_options() -> dict:
    try:
        options = load_options_file(OPTIONS_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        if OPTIONS_BACKUP_PATH.exists():
            log_event(f"options_warning=load_failed using_backup reason={exc}")
            return load_options_file(OPTIONS_BACKUP_PATH)
        raise

    if OPTIONS_BACKUP_PATH.exists():
        restored = load_options_file(OPTIONS_BACKUP_PATH)
        if is_default_options(options) and has_persistable_options(restored) and restored != options:
            write_options_file(OPTIONS_PATH, restored)
            log_event("options_restore=last_good_backup reason=defaults_reset")
            return restored
        if not has_persistable_options(options) and has_persistable_options(restored):
            write_options_file(OPTIONS_PATH, restored)
            log_event("options_restore=last_good_backup reason=empty_config")
            return restored

    if has_persistable_options(options):
        write_options_file(OPTIONS_BACKUP_PATH, options)
        return options
    return options


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
                    rtsp_port=_as_int(raw_camera.get("rtsp_port"), 8551 + channel),
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
                rtsp_port=_as_int(options.get(f"camera_{index}_rtsp_port"), 8550 + index),
                rtsp_path=str(options.get(f"camera_{index}_rtsp_path", f"cam{index}")),
            )
        )
    return cameras


def build_bridge_command(options: dict, camera: CameraConfig) -> list[str]:
    command = [
        sys.executable,
        "/app/rtsp_bridge.py",
        "--shared-mediamtx",
        "--mediamtx-host",
        "127.0.0.1",
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
        "--unavailable-stream-reconnect-delay",
        str(options.get("unavailable_stream_reconnect_delay", 60)),
        "--camera-name",
        f"cam{camera.channel + 1}",
    ]
    if options.get("use_uid", False):
        command.extend(["--uid", str(options.get("uid", ""))])
    else:
        command.extend(["--host", str(options.get("host", "192.168.1.10")), "--port", str(options.get("port", 10000))])
    return command


def build_shared_mediamtx_config(cameras: list[CameraConfig]) -> str:
    if not cameras:
        raise ValueError("At least one camera is required")
    rtsp_port = cameras[0].rtsp_port
    if any(camera.rtsp_port != rtsp_port for camera in cameras):
        raise ValueError("All enabled cameras must use the same rtsp_port with shared mediamtx")
    paths: list[str] = []
    for camera in cameras:
        rtsp_path = camera.rtsp_path.lstrip("/")
        if not rtsp_path:
            raise ValueError(f"Camera {camera.channel + 1} must have a non-empty rtsp_path")
        if rtsp_path in paths:
            raise ValueError(f"Duplicate rtsp_path configured: {rtsp_path}")
        paths.append(rtsp_path)
    config = [
        "logLevel: warn",
        "logDestinations: [stdout]",
        "api: no",
        "metrics: no",
        "pprof: no",
        "readTimeout: 30s",
        "writeTimeout: 30s",
        "rtsp: yes",
        f"rtspAddress: :{rtsp_port}",
        "protocols: [tcp]",
        "rtmp: no",
        "hls: no",
        "webrtc: no",
        "srt: no",
        "paths:",
    ]
    for rtsp_path in paths:
        config.append(f"  {rtsp_path}:")
        config.append("    source: publisher")
    return "\n".join(config) + "\n"


def start_shared_mediamtx_process(cameras: list[CameraConfig], mediamtx_bin: str = "mediamtx") -> subprocess.Popen[bytes]:
    config_path = Path("/tmp/mediamtx_shared.yml")
    config_path.write_text(build_shared_mediamtx_config(cameras), encoding="utf-8")
    process: subprocess.Popen[bytes] = subprocess.Popen(
        [mediamtx_bin, str(config_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    start_stream_logger(process.stdout, lambda line: f"shared_mediamtx_log={line}")
    deadline = time.monotonic() + MEDIAMTX_STARTUP_TIMEOUT_SECS
    rtsp_port = cameras[0].rtsp_port
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"mediamtx exited unexpectedly with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", rtsp_port), timeout=0.1):
                return process
        except OSError:
            time.sleep(0.05)
    terminate_process(process)
    raise RuntimeError(f"mediamtx did not bind to port {rtsp_port} within {MEDIAMTX_STARTUP_TIMEOUT_SECS:.0f}s")


def terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=PROCESS_STOP_TIMEOUT_SECS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=PROCESS_STOP_TIMEOUT_SECS)


def run_bridge(options: dict, host_label: str = "<HA_HOST_IP>") -> int:
    cameras = build_camera_configs(options)
    if not cameras:
        log_event("error=no enabled cameras found in configuration")
        return 1

    processes: list[subprocess.Popen[bytes]] = []
    mediamtx_process: subprocess.Popen[bytes] | None = None
    stopping = False

    def handle_signal(signum, frame) -> None:  # type: ignore[unused-argument]
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        mediamtx_process = start_shared_mediamtx_process(cameras)
        log_event(f"shared_rtsp_server=started rtsp=rtsp://{host_label}:{cameras[0].rtsp_port}/<camera_path>")
        for camera in cameras:
            command = build_bridge_command(options, camera)
            log_event(
                f"starting camera={camera.channel + 1} channel={camera.channel} "
                f"stream_id={camera.stream_id} rtsp=rtsp://{host_label}:{camera.rtsp_port}/{camera.rtsp_path}"
            )
            processes.append(subprocess.Popen(command))
            time.sleep(STARTUP_STAGGER_SECONDS)

        while not stopping:
            if mediamtx_process is not None and mediamtx_process.poll() is not None:
                log_event(f"error=shared mediamtx exited code={mediamtx_process.returncode}")
                return mediamtx_process.returncode or 1
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    log_event(f"error=child process exited code={return_code}")
                    return return_code or 1
            time.sleep(2)
        return 0
    finally:
        for process in processes:
            terminate_process(process)
        if mediamtx_process is not None:
            terminate_process(mediamtx_process)


def main() -> int:
    options = load_options()
    return run_bridge(options)


if __name__ == "__main__":
    raise SystemExit(main())
