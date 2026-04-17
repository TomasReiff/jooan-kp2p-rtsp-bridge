from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import socket
import ssl
import struct
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


APP_PROTO_MAGIC = 0x4B503250
APP_PROTO_VERSION = 1
APP_PROTO_AES128_KEY = b"~!JUAN*&Vision-="
APP_PROTO_PARAM_AUTH_NAME_STRLEN = 32
APP_PROTO_PARAM_AUTH_PASSWD_STRLEN = 32
APP_PROTO_PARAM_LIVE_CAM_DESC_STRLEN = 32

APP_PROTO_CMD_AUTH_REQ = 10
APP_PROTO_CMD_AUTH_RSP = 11
APP_PROTO_CMD_LIVE_REQ = 30
APP_PROTO_CMD_LIVE_RSP = 31

APP_PROTO_PARAM_LIVE_CMD_STOP = 1
APP_PROTO_PARAM_LIVE_CMD_START = 2
APP_PROTO_RESULT_STREAM_UNAVAILABLE = -40

PROC_FRAME_MAGIC = 0x4652414D
PROC_FRAME_MAGIC2 = 0x4652414E

PROC_FRAME_TYPE_AUDIO = 0
PROC_FRAME_TYPE_IFRAME = 1
PROC_FRAME_TYPE_PFRAME = 2

P2P_FRAME_TYPE_LIVE = 0

IOT_HDR_LEN = 32
IOT_LINK_CMD_TURN_REQ = 12
IOT_LINK_CMD_TURN_S2A = 16
IOT_LINK_CMD_PING = 17
IOT_LINK_CMD_PONG = 18
IOT_LINK_CMD_DATA = 19
IOT_LINK_CMD_OPEN_REQ = 20
IOT_LINK_CMD_OPEN_RES = 21
IOT_LINK_CMD_CLIENT_LOGINTURN_REQ = 36
IOT_LINK_CMD_CLIENT_LOGINTURN_RES = 37
IOT_LINK_CMD_DATA_PRIOR = 43

TRANSPORT_MAGIC = bytes((0xCE, 0xFA, 0xEF, 0xFE))
ARQ_OPEN_CONN_PREFIX = bytes.fromhex("d9ffcc028c38eed2d199ac6026947fae")
ARQ_OPEN_CONN_RES = bytes.fromhex("96d5390d12fcbe8f4790d932ccd849f3")

WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


S_BOX = (
    0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
    0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
    0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
    0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
    0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
    0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
    0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
    0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
    0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
    0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
    0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
    0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
    0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
    0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
    0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
    0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16,
)

RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


class Kp2pError(RuntimeError):
    pass


def describe_live_result(result: int) -> str:
    if result == APP_PROTO_RESULT_STREAM_UNAVAILABLE:
        return "channel unavailable or not enabled on the device"
    return ""


class Kp2pStreamOpenError(Kp2pError):
    def __init__(self, channel: int, stream_id: int, result: int) -> None:
        self.channel = channel
        self.stream_id = stream_id
        self.result = result
        self.retryable = result != APP_PROTO_RESULT_STREAM_UNAVAILABLE
        detail = describe_live_result(result)
        suffix = f" ({detail})" if detail else ""
        super().__init__(f"Open stream failed with result={result}{suffix}")


@dataclass
class Endpoint:
    host: str
    port: int
    sid: int
    ws_key: int
    turntype: int = 0
    uid: str = ""


@dataclass
class ApiHeader:
    magic: int
    version: int
    ticket: int
    cmd: int
    result: int
    size: int


@dataclass
class VideoFrame:
    codec: str
    frame_type: int
    channel: int
    width: int
    height: int
    fps: int
    timestamp_ms: int
    payload: bytes


@dataclass
class AudioFrame:
    codec: str
    frame_type: int
    channel: int
    sample_rate: int
    sample_width: int
    channels: int
    timestamp_ms: int
    payload: bytes


def _rot_word(word: bytes) -> bytes:
    return word[1:] + word[:1]


def _sub_word(word: bytes) -> bytes:
    return bytes(S_BOX[b] for b in word)


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def _expand_key_128(key: bytes) -> list[bytes]:
    if len(key) != 16:
        raise ValueError("AES-128 key must be 16 bytes")
    words = [key[i : i + 4] for i in range(0, 16, 4)]
    for index in range(4, 44):
        temp = words[index - 1]
        if index % 4 == 0:
            temp = bytearray(_sub_word(_rot_word(temp)))
            temp[0] ^= RCON[(index // 4) - 1]
            temp = bytes(temp)
        words.append(_xor_bytes(words[index - 4], temp))
    return [b"".join(words[i : i + 4]) for i in range(0, 44, 4)]


def _xtime(value: int) -> int:
    value <<= 1
    if value & 0x100:
        value ^= 0x11B
    return value & 0xFF


def _mix_single_column(column: list[int]) -> list[int]:
    total = column[0] ^ column[1] ^ column[2] ^ column[3]
    original = column[:]
    return [
        column[0] ^ total ^ _xtime(original[0] ^ original[1]),
        column[1] ^ total ^ _xtime(original[1] ^ original[2]),
        column[2] ^ total ^ _xtime(original[2] ^ original[3]),
        column[3] ^ total ^ _xtime(original[3] ^ original[0]),
    ]


def _add_round_key(state: list[int], round_key: bytes) -> None:
    for idx, value in enumerate(round_key):
        state[idx] ^= value


def _sub_bytes(state: list[int]) -> None:
    for idx, value in enumerate(state):
        state[idx] = S_BOX[value]


def _shift_rows(state: list[int]) -> None:
    for row in range(1, 4):
        values = [state[row + 4 * col] for col in range(4)]
        values = values[row:] + values[:row]
        for col, value in enumerate(values):
            state[row + 4 * col] = value


def _mix_columns(state: list[int]) -> None:
    for col in range(4):
        values = [state[row + 4 * col] for row in range(4)]
        mixed = _mix_single_column(values)
        for row, value in enumerate(mixed):
            state[row + 4 * col] = value


def aes128_ecb_encrypt(data: bytes, key: bytes = APP_PROTO_AES128_KEY) -> bytes:
    if len(data) % 16 != 0:
        raise ValueError("AES ECB input must be a multiple of 16 bytes")
    round_keys = _expand_key_128(key)
    output = bytearray()
    for offset in range(0, len(data), 16):
        state = list(data[offset : offset + 16])
        _add_round_key(state, round_keys[0])
        for round_index in range(1, 10):
            _sub_bytes(state)
            _shift_rows(state)
            _mix_columns(state)
            _add_round_key(state, round_keys[round_index])
        _sub_bytes(state)
        _shift_rows(state)
        _add_round_key(state, round_keys[10])
        output.extend(state)
    return bytes(output)


def pack_u32(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def pack_u64(value: int) -> bytes:
    return struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF)


def parse_s32_le(data: bytes, start: int) -> int:
    return int.from_bytes(data[start : start + 4], "little", signed=True)


def parse_api_header(data: bytes) -> ApiHeader:
    if len(data) < 24:
        raise Kp2pError(f"Short API header: {len(data)} bytes")
    return ApiHeader(
        magic=int.from_bytes(data[0:4], "little"),
        version=int.from_bytes(data[4:8], "little"),
        ticket=int.from_bytes(data[8:12], "little"),
        cmd=int.from_bytes(data[12:16], "little"),
        result=parse_s32_le(data, 16),
        size=int.from_bytes(data[20:24], "little"),
    )


def build_api_packet(cmd: int, ticket: int, payload: bytes) -> bytes:
    return (
        pack_u32(APP_PROTO_MAGIC)
        + pack_u32(APP_PROTO_VERSION)
        + pack_u32(ticket)
        + pack_u32(cmd)
        + pack_u32(0)
        + pack_u32(len(payload))
        + payload
    )


def encrypt_auth_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    if len(raw) >= APP_PROTO_PARAM_AUTH_NAME_STRLEN:
        raise ValueError("Authentication strings must be shorter than 32 bytes")
    first = raw[:16].ljust(16, b"\x00")
    second = raw[16:32].ljust(16, b"\x00")
    return aes128_ecb_encrypt(first + second)


def build_auth_payload(username: str, password: str) -> bytes:
    return encrypt_auth_string(username) + encrypt_auth_string(password)


def build_live_payload(channel: int, stream_id: int, live_cmd: int) -> bytes:
    return pack_u32(channel) + pack_u32(stream_id) + pack_u32(live_cmd)


def build_iot_header(cmd: int, ticket: int, sid: int, payload: bytes) -> bytes:
    return (
        b"\xAB\xBC\xCD\xDE"
        + pack_u32(cmd)
        + pack_u32(1)
        + pack_u32(ticket)
        + pack_u32(sid)
        + pack_u32(0)
        + pack_u32(0)
        + pack_u32(len(payload))
        + payload
    )


def build_iot_open_req(sid: int, turntype: int) -> bytes:
    return pack_u32(sid) + pack_u32(turntype)


def build_iot_turn_req(uid: str, turntype: int, channel_count: int) -> bytes:
    payload = bytearray(40)
    uid_bytes = uid.encode("utf-8")
    payload[: min(32, len(uid_bytes))] = uid_bytes[:32]
    payload[32:36] = pack_u32(turntype)
    payload[36:40] = pack_u32(channel_count)
    return bytes(payload)


def build_iot_loginturn(sid: int) -> bytes:
    return pack_u32(sid)


def build_iot_ping(identity: str) -> bytes:
    payload = bytearray(96)
    encoded = identity.encode("utf-8")
    payload[: min(96, len(encoded))] = encoded[:96]
    return bytes(payload)


def parse_iot_header(data: bytes) -> tuple[int, int, int, int, bytes]:
    if len(data) < IOT_HDR_LEN:
        raise Kp2pError(f"Short IOT packet: {len(data)} bytes")
    magic = int.from_bytes(data[0:4], "big")
    if magic != 0xABBCCDDE:
        raise Kp2pError(f"Unexpected IOT magic 0x{magic:08X}")
    cmd = int.from_bytes(data[4:8], "little")
    ticket = int.from_bytes(data[12:16], "little")
    sid = int.from_bytes(data[16:20], "little")
    ecode = parse_s32_le(data, 24)
    payload_len = int.from_bytes(data[28:32], "little")
    payload = data[32 : 32 + payload_len]
    return cmd, ticket, sid, ecode, payload


def parse_turn_s2a(payload: bytes) -> tuple[int, str, int, int]:
    if len(payload) < 64:
        raise Kp2pError(f"Short TURN_S2A payload: {len(payload)} bytes")
    sid = int.from_bytes(payload[0:4], "little")
    turntype = int.from_bytes(payload[36:40], "little")
    ip = ".".join(str(byte) for byte in payload[40:44])
    port = int.from_bytes(payload[60:64], "little")
    return sid, ip, port, turntype


def parse_live_response(payload: bytes) -> tuple[int, int, int, str]:
    if len(payload) < 12:
        raise Kp2pError(f"Short live response payload: {len(payload)} bytes")
    channel = int.from_bytes(payload[0:4], "little")
    stream_id = int.from_bytes(payload[4:8], "little")
    live_cmd = int.from_bytes(payload[8:12], "little")
    cam_desc = payload[12 : 12 + APP_PROTO_PARAM_LIVE_CAM_DESC_STRLEN].split(b"\x00", 1)[0].decode(
        "utf-8", "replace"
    )
    return channel, stream_id, live_cmd, cam_desc


def find_annexb_start(payload: bytes, start: int, max_probe: int = 32) -> int:
    end = min(len(payload), start + max_probe)
    for index in range(start, end):
        if payload[index : index + 4] == b"\x00\x00\x00\x01":
            return index
        if payload[index : index + 3] == b"\x00\x00\x01":
            return index
    return start


def parse_video_frame(payload: bytes, timestamp_ms: int) -> Optional[VideoFrame]:
    offset = 0
    if len(payload) >= 40 and int.from_bytes(payload[0:4], "little") == PROC_FRAME_MAGIC2:
        offset += 40
    if len(payload) < offset + 24:
        return None
    if int.from_bytes(payload[offset : offset + 4], "little") != PROC_FRAME_MAGIC:
        return None
    frame_head = payload[offset : offset + 24]
    headtype = int.from_bytes(frame_head[8:12], "little")
    if headtype != P2P_FRAME_TYPE_LIVE:
        return None
    timestamp_ms = int.from_bytes(frame_head[16:24], "little")
    offset += 24
    if len(payload) < offset + 8:
        return None
    frame_type = int.from_bytes(payload[offset : offset + 4], "little")
    channel = int.from_bytes(payload[offset + 4 : offset + 8], "little")
    offset += 8
    if frame_type not in (PROC_FRAME_TYPE_IFRAME, PROC_FRAME_TYPE_PFRAME):
        return None
    if len(payload) < offset + 24:
        return None
    params = payload[offset : offset + 24]
    codec = params[0:8].split(b"\x00", 1)[0].decode("utf-8", "replace")
    fps = int.from_bytes(params[8:12], "little")
    width = int.from_bytes(params[12:16], "little")
    height = int.from_bytes(params[16:20], "little")
    offset += 24
    offset = find_annexb_start(payload, offset)
    if len(payload) < offset:
        return None
    return VideoFrame(codec, frame_type, channel, width, height, fps, timestamp_ms, payload[offset:])


def parse_audio_frame(payload: bytes, timestamp_ms: int) -> Optional[AudioFrame]:
    offset = 0
    if len(payload) >= 40 and int.from_bytes(payload[0:4], "little") == PROC_FRAME_MAGIC2:
        offset += 40
    if len(payload) < offset + 24:
        return None
    if int.from_bytes(payload[offset : offset + 4], "little") != PROC_FRAME_MAGIC:
        return None
    frame_head = payload[offset : offset + 24]
    headtype = int.from_bytes(frame_head[8:12], "little")
    if headtype != P2P_FRAME_TYPE_LIVE:
        return None
    timestamp_ms = int.from_bytes(frame_head[16:24], "little")
    offset += 24
    if len(payload) < offset + 8:
        return None
    frame_type = int.from_bytes(payload[offset : offset + 4], "little")
    channel = int.from_bytes(payload[offset + 4 : offset + 8], "little")
    offset += 8
    if frame_type != PROC_FRAME_TYPE_AUDIO:
        return None
    if len(payload) < offset + 24:
        return None
    params = payload[offset : offset + 24]
    codec = params[0:8].split(b"\x00", 1)[0].decode("utf-8", "replace")
    sample_rate = int.from_bytes(params[8:12], "little")
    sample_width = int.from_bytes(params[12:16], "little")
    channels = int.from_bytes(params[16:20], "little")
    offset += 24 + 8
    if len(payload) < offset:
        return None
    return AudioFrame(codec, frame_type, channel, sample_rate, sample_width, channels, timestamp_ms, payload[offset:])


class SimpleWebSocket:
    def __init__(self, uri: str, timeout: float = 10.0) -> None:
        self.uri = uri
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self.closed = False

    def connect(self) -> None:
        parsed = urllib.parse.urlsplit(self.uri)
        if parsed.scheme not in {"ws", "wss"}:
            raise ValueError(f"Unsupported websocket scheme: {parsed.scheme}")
        host = parsed.hostname
        if not host:
            raise ValueError(f"Websocket URI must include a host: {self.uri}")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        raw_socket = socket.create_connection((host, port), timeout=self.timeout)
        if parsed.scheme == "wss":
            context = ssl.create_default_context()
            raw_socket = context.wrap_socket(raw_socket, server_hostname=host)
        raw_socket.settimeout(self.timeout)
        self.socket = raw_socket

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Origin: null\r\n"
            "\r\n"
        ).encode("ascii")
        self.socket.sendall(request)
        response = self._read_http_response()
        if not response.startswith("HTTP/1.1 101"):
            raise Kp2pError(f"WebSocket upgrade failed: {response.splitlines()[0]}")
        headers = {}
        for line in response.split("\r\n")[1:]:
            if not line or ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        accept = base64.b64encode(hashlib.sha1((key + WEBSOCKET_GUID).encode("ascii")).digest()).decode("ascii")
        if headers.get("sec-websocket-accept") != accept:
            raise Kp2pError("WebSocket handshake validation failed")

    def _read_http_response(self) -> str:
        assert self.socket is not None
        buffer = bytearray()
        while b"\r\n\r\n" not in buffer:
            chunk = self.socket.recv(4096)
            if not chunk:
                raise Kp2pError("Socket closed during WebSocket handshake")
            buffer.extend(chunk)
        response, _, _ = buffer.partition(b"\r\n\r\n")
        return response.decode("latin1", "replace")

    def _read_exact(self, size: int) -> bytes:
        assert self.socket is not None
        buffer = bytearray()
        while len(buffer) < size:
            chunk = self.socket.recv(size - len(buffer))
            if not chunk:
                raise Kp2pError("WebSocket connection closed unexpectedly")
            buffer.extend(chunk)
        return bytes(buffer)

    def send_binary(self, payload: bytes) -> None:
        self._send_frame(0x2, payload)

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        assert self.socket is not None
        header = bytearray()
        header.append(0x80 | opcode)
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(payload[i] ^ mask[i % 4] for i in range(length))
        self.socket.sendall(header + masked)

    def recv(self) -> tuple[int, bytes]:
        fragments = bytearray()
        message_opcode: Optional[int] = None
        while True:
            opcode, fin, payload = self._recv_frame()
            if opcode == 0x8:
                self.closed = True
                raise Kp2pError("WebSocket closed by remote peer")
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x0:
                if message_opcode is None:
                    raise Kp2pError("Unexpected continuation frame")
                fragments.extend(payload)
                if fin:
                    return message_opcode, bytes(fragments)
                continue
            if opcode not in {0x1, 0x2}:
                continue
            if fin:
                return opcode, payload
            message_opcode = opcode
            fragments.extend(payload)

    def _recv_frame(self) -> tuple[int, bool, bytes]:
        first, second = self._read_exact(2)
        fin = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else b""
        payload = self._read_exact(length)
        if masked:
            payload = bytes(payload[i] ^ mask[i % 4] for i in range(length))
        return opcode, fin, payload

    def close(self) -> None:
        if self.socket is None:
            return
        try:
            self._send_frame(0x8, b"")
        except OSError:
            pass
        self.socket.close()
        self.socket = None
        self.closed = True


class Kp2pClient:
    def __init__(self, endpoint: Endpoint, timeout: float = 10.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.ws: Optional[SimpleWebSocket] = None
        self.ticket = 0
        self.link_open = False
        self.last_ping = 0.0

    def connect(self) -> None:
        ws_uri = f"ws://{self.endpoint.host}:{self.endpoint.port}"
        self.ws = SimpleWebSocket(ws_uri, timeout=self.timeout)
        self.ws.connect()
        self.ws.send_binary(ARQ_OPEN_CONN_PREFIX + pack_u32(self.endpoint.ws_key))
        self._wait_for_arq_open()
        if self.endpoint.uid:
            self._send_iot(IOT_LINK_CMD_CLIENT_LOGINTURN_REQ, build_iot_loginturn(self.endpoint.sid))
            self._wait_for_turn_login()
        self._send_iot(IOT_LINK_CMD_OPEN_REQ, build_iot_open_req(self.endpoint.sid, self.endpoint.turntype))
        self._wait_for_iot_open()
        self.link_open = True
        self.last_ping = time.time()

    def _wait_for_arq_open(self) -> None:
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            opcode, payload = self.ws.recv()  # type: ignore[union-attr]
            if opcode != 0x2:
                continue
            if payload == ARQ_OPEN_CONN_RES:
                return
            if payload.startswith(TRANSPORT_MAGIC):
                continue
        raise Kp2pError("Timed out waiting for ARQ open response")

    def _wait_for_iot_open(self) -> None:
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            cmd, _, _, ecode, _ = self._recv_iot_packet()
            if cmd == IOT_LINK_CMD_OPEN_RES:
                if ecode != 0:
                    raise Kp2pError(f"IOT open failed with ecode={ecode}")
                return
        raise Kp2pError("Timed out waiting for IOT open response")

    def _wait_for_turn_login(self) -> None:
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            cmd, _, _, ecode, _ = self._recv_iot_packet()
            if cmd == IOT_LINK_CMD_CLIENT_LOGINTURN_RES:
                if ecode != 0:
                    raise Kp2pError(f"TURN login failed with ecode={ecode}")
                return
        raise Kp2pError("Timed out waiting for CLIENT_LOGINTURN_RES")

    def login(self, username: str, password: str) -> None:
        self.ticket += 1
        packet = build_api_packet(APP_PROTO_CMD_AUTH_REQ, self.ticket, build_auth_payload(username, password))
        self._send_iot(IOT_LINK_CMD_DATA, packet)
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            payload = self._recv_inner_payload()
            if int.from_bytes(payload[0:4], "little") != APP_PROTO_MAGIC:
                continue
            header = parse_api_header(payload)
            if header.cmd != APP_PROTO_CMD_AUTH_RSP:
                continue
            if header.result != 0:
                raise Kp2pError(f"Authentication failed with result={header.result}")
            return
        raise Kp2pError("Timed out waiting for auth response")

    def open_stream(self, channel: int, stream_id: int) -> str:
        self.ticket += 1
        packet = build_api_packet(
            APP_PROTO_CMD_LIVE_REQ,
            self.ticket,
            build_live_payload(channel, stream_id, APP_PROTO_PARAM_LIVE_CMD_START),
        )
        self._send_iot(IOT_LINK_CMD_DATA, packet)
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            payload = self._recv_inner_payload()
            if int.from_bytes(payload[0:4], "little") != APP_PROTO_MAGIC:
                continue
            header = parse_api_header(payload)
            if header.cmd != APP_PROTO_CMD_LIVE_RSP:
                continue
            result = header.result
            response_payload = payload[24 : 24 + header.size]
            channel_no, stream_no, live_cmd, cam_desc = parse_live_response(response_payload)
            if channel_no != channel or stream_no != stream_id or live_cmd != APP_PROTO_PARAM_LIVE_CMD_START:
                continue
            if result != 0:
                raise Kp2pStreamOpenError(channel, stream_id, result)
            return cam_desc
        raise Kp2pError("Timed out waiting for live open response")

    def close_stream(self, channel: int, stream_id: int) -> None:
        self.ticket += 1
        packet = build_api_packet(
            APP_PROTO_CMD_LIVE_REQ,
            self.ticket,
            build_live_payload(channel, stream_id, APP_PROTO_PARAM_LIVE_CMD_STOP),
        )
        self._send_iot(IOT_LINK_CMD_DATA, packet)

    def recv_media(self) -> Optional[VideoFrame | AudioFrame]:
        self._maybe_send_ping()
        payload = self._recv_inner_payload()
        magic = int.from_bytes(payload[0:4], "little") if len(payload) >= 4 else -1
        if magic not in {PROC_FRAME_MAGIC, PROC_FRAME_MAGIC2, APP_PROTO_MAGIC}:
            return None
        if magic == APP_PROTO_MAGIC:
            return None
        frame = parse_audio_frame(payload, 0)
        if frame is not None:
            return frame
        return parse_video_frame(payload, 0)

    def _maybe_send_ping(self) -> None:
        if not self.link_open:
            return
        now = time.time()
        if now - self.last_ping < 10.0:
            return
        identity = self.endpoint.uid if self.endpoint.uid else ""
        self._send_iot(IOT_LINK_CMD_PING, build_iot_ping(identity))
        self.last_ping = now

    def _recv_inner_payload(self) -> bytes:
        while True:
            cmd, _, _, _, payload = self._recv_iot_packet()
            if cmd in {IOT_LINK_CMD_DATA, IOT_LINK_CMD_DATA_PRIOR}:
                return payload

    def _recv_iot_packet(self) -> tuple[int, int, int, int, bytes]:
        while True:
            opcode, payload = self.ws.recv()  # type: ignore[union-attr]
            if opcode != 0x2:
                continue
            if payload.startswith(TRANSPORT_MAGIC):
                continue
            if payload == ARQ_OPEN_CONN_RES:
                continue
            cmd, ticket, sid, ecode, inner = parse_iot_header(payload)
            if cmd == IOT_LINK_CMD_PONG:
                continue
            return cmd, ticket, sid, ecode, inner

    def _send_iot(self, cmd: int, payload: bytes) -> None:
        packet = build_iot_header(cmd, 0, self.endpoint.sid, payload)
        transport_header = TRANSPORT_MAGIC + pack_u32(len(packet))
        self.ws.send_binary(transport_header)  # type: ignore[union-attr]
        self.ws.send_binary(packet)  # type: ignore[union-attr]

    def close(self) -> None:
        if self.ws is not None:
            self.ws.close()


def discover_uid(uid: str, timeout: float) -> tuple[str, int, int, int, int]:
    url = (
        "http://ngw.dvr163.com/address/client?"
        + urllib.parse.urlencode({"id": uid, "ch_count": 1, "r": random.randint(1, 10_000_000)})
    )
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return (
        str(payload["ipv4"]),
        int(payload["tcpport"]),
        int(payload["apconv"]),
        int(payload["amconv"]),
        int(payload["sid"]),
    )


def connect_via_uid(uid: str, timeout: float) -> Endpoint:
    p2p_ip, p2p_port, p2p_key, turn_key, sid = discover_uid(uid, timeout)
    ws = SimpleWebSocket(f"ws://{p2p_ip}:{p2p_port}", timeout=timeout)
    ws.connect()
    try:
        ws.send_binary(ARQ_OPEN_CONN_PREFIX + pack_u32(p2p_key))
        deadline = time.time() + timeout
        while time.time() < deadline:
            opcode, payload = ws.recv()
            if opcode != 0x2:
                continue
            if payload == ARQ_OPEN_CONN_RES:
                break
            if payload.startswith(TRANSPORT_MAGIC):
                continue
        else:
            raise Kp2pError("Timed out waiting for UID ARQ open response")

        turn_packet = build_iot_header(IOT_LINK_CMD_TURN_REQ, 0, sid, build_iot_turn_req(uid, 0, 1))
        ws.send_binary(TRANSPORT_MAGIC + pack_u32(len(turn_packet)))
        ws.send_binary(turn_packet)

        deadline = time.time() + timeout
        while time.time() < deadline:
            opcode, payload = ws.recv()
            if opcode != 0x2 or payload.startswith(TRANSPORT_MAGIC) or payload == ARQ_OPEN_CONN_RES:
                continue
            cmd, _, _, _, inner = parse_iot_header(payload)
            if cmd == IOT_LINK_CMD_TURN_S2A:
                _, turn_ip, turn_port, turntype = parse_turn_s2a(inner)
                return Endpoint(turn_ip, turn_port, sid, turn_key, turntype, uid)
        raise Kp2pError("Timed out waiting for TURN_S2A")
    finally:
        ws.close()


def resolve_endpoint(args: argparse.Namespace) -> Endpoint:
    if args.uid:
        turn_endpoint = connect_via_uid(args.uid, args.timeout)
        print(f"discovery_mode=uid")
        print(f"turn_host={turn_endpoint.host}")
        print(f"turn_port={turn_endpoint.port}")
        print(f"sid={turn_endpoint.sid}")
        return turn_endpoint
    ws_key = random.randint(1, 10000)
    print(f"discovery_mode=direct")
    print(f"sid={ws_key}")
    return Endpoint(args.host, args.port, ws_key, ws_key, 0, "")


def save_payload(path: Optional[Path], payload: bytes) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(payload)


def self_test() -> int:
    key = bytes.fromhex("000102030405060708090A0B0C0D0E0F")
    plain = bytes.fromhex("00112233445566778899AABBCCDDEEFF")
    expected = bytes.fromhex("69C4E0D86A7B0430D8CDB78070B4C55A")
    actual = aes128_ecb_encrypt(plain, key)
    if actual != expected:
        print(f"aes_test=failed actual={actual.hex()} expected={expected.hex()}")
        return 1
    header = build_api_packet(APP_PROTO_CMD_AUTH_REQ, 7, b"abc")[:24]
    parsed = parse_api_header(header)
    if parsed.magic != APP_PROTO_MAGIC or parsed.ticket != 7 or parsed.size != 3:
        print("api_header_test=failed")
        return 1
    print("self_test=ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pure-Python kp2p WebSocket probe for Jooan/Juanvision devices and the vendor TURN path."
    )
    parser.add_argument("--host", default="192.168.1.10", help="Direct device host for local ws://host:port mode.")
    parser.add_argument("--port", type=int, default=10000, help="Direct device websocket port.")
    parser.add_argument("--uid", default="", help="Optional cloud UID. When set, resolve via ngw.dvr163.com and use TURN.")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="")
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--stream-id", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--seconds", type=float, default=15.0)
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after this many media frames. 0 means unlimited.")
    parser.add_argument("--save-video", type=Path, default=None, help="Append raw video elementary stream here.")
    parser.add_argument("--save-audio", type=Path, default=None, help="Append raw audio frames here.")
    parser.add_argument("--no-login", action="store_true", help="Skip APP auth and just print low-level activity.")
    parser.add_argument("--self-test", action="store_true", help="Run built-in protocol/AES tests and exit.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.self_test:
        return self_test()

    endpoint = resolve_endpoint(args)
    client = Kp2pClient(endpoint, timeout=args.timeout)
    video_frames = 0
    audio_frames = 0
    media_frames = 0
    started = time.time()
    try:
        print(f"connect_host={endpoint.host}")
        print(f"connect_port={endpoint.port}")
        client.connect()
        print("transport_open=ok")

        if not args.no_login:
            client.login(args.username, args.password)
            print("login=ok")
            cam_desc = client.open_stream(args.channel, args.stream_id)
            print(f"open_stream=ok channel={args.channel} stream={args.stream_id} cam_desc={cam_desc!r}")

        deadline = started + args.seconds
        while time.time() < deadline:
            frame = client.recv_media()
            if frame is None:
                continue
            media_frames += 1
            if isinstance(frame, VideoFrame):
                video_frames += 1
                save_payload(args.save_video, frame.payload)
                print(
                    f"video_frame index={video_frames} type={frame.frame_type} codec={frame.codec} "
                    f"channel={frame.channel} size={len(frame.payload)} width={frame.width} "
                    f"height={frame.height} fps={frame.fps} ts_ms={frame.timestamp_ms}"
                )
            else:
                audio_frames += 1
                save_payload(args.save_audio, frame.payload)
                print(
                    f"audio_frame index={audio_frames} codec={frame.codec} channel={frame.channel} "
                    f"size={len(frame.payload)} sample_rate={frame.sample_rate} "
                    f"sample_width={frame.sample_width} channels={frame.channels} ts_ms={frame.timestamp_ms}"
                )
            if args.max_frames and media_frames >= args.max_frames:
                break

        if not args.no_login:
            client.close_stream(args.channel, args.stream_id)
        print(f"media_frames={media_frames}")
        print(f"video_frames={video_frames}")
        print(f"audio_frames={audio_frames}")
        if args.save_video is not None and args.save_video.exists():
            print(f"video_output={args.save_video}")
            print(f"video_output_size={args.save_video.stat().st_size}")
        if args.save_audio is not None and args.save_audio.exists():
            print(f"audio_output={args.save_audio}")
            print(f"audio_output_size={args.save_audio.stat().st_size}")
        return 0
    except Exception as exc:
        print(f"error={exc}")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
