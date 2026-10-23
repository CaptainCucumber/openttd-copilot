"""Small, deliberately bounded OpenTTD 15.3 Admin Network client.

This module implements the legacy loopback login, GameScript JSON, ping, and
the bounded native Copilot identity packets used by the current probes. It does
not expose RCON, arbitrary commands, or the secure authentication protocols.
"""

from __future__ import annotations

import json
import math
import socket
import struct
import time
import uuid
from typing import Any


ADMIN_PROTOCOL_VERSION = 3  # NETWORK_GAME_ADMIN_VERSION in OpenTTD 15.3
COMPAT_MTU = 1460
MAX_GAMESCRIPT_JSON_BYTES = 1449
MAX_PACKET_SIZE = COMPAT_MTU
_HEADER_SIZE = 3  # uint16 packet size + uint8 packet type

_ADMIN_JOIN = 0
_ADMIN_QUIT = 1
_ADMIN_UPDATE_FREQUENCY = 2
_ADMIN_GAMESCRIPT = 6
_ADMIN_PING = 7
_ADMIN_COPILOT = 11
_SERVER_ERROR = 102
_SERVER_PROTOCOL = 103
_SERVER_WELCOME = 104
_SERVER_GAMESCRIPT = 124
_SERVER_PONG = 126
_SERVER_COPILOT = 130
_UPDATE_GAMESCRIPT = 9
_UPDATE_AUTOMATIC = 1 << 6
MAX_PENDING_RESPONSES = 64
COPILOT_PROTOCOL_VERSION = 1
COPILOT_COMPANY_ALL = 0xFF
_COPILOT_IDENTITY = 0


class AdminTransportError(RuntimeError):
    """Base class for transport and protocol failures."""


class AdminProtocolError(AdminTransportError):
    """The peer sent a malformed or unsupported Admin packet."""


class AdminServerError(AdminTransportError):
    """OpenTTD rejected the connection or request."""

    def __init__(self, code: int, message: str | None = None) -> None:
        self.code = code
        self.error_code = code
        super().__init__(message or f"OpenTTD Admin server error {code}")


class CopilotBridgeError(AdminTransportError):
    """The native Copilot bridge rejected a typed request."""

    _MESSAGES = {
        1: "unsupported Copilot protocol version",
        2: "unsupported Copilot request",
        3: "Copilot company was not found",
        4: "Copilot bridge requires a loopback peer",
    }

    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(self._MESSAGES.get(status, f"Copilot bridge error {status}"))


class AdminClient:
    """A bounded standard-library client for OpenTTD's loopback Admin port."""

    def __init__(self, port: int, password: str, timeout: float = 5.0) -> None:
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("port must be an integer from 1 through 65535")
        if not isinstance(password, str):
            raise TypeError("password must be a string")
        if "\x00" in password:
            raise ValueError("password must not contain NUL")
        if len(password.encode("utf-8")) > 32:
            raise ValueError("password is too long for OpenTTD's Admin login")
        self.port = port
        self.password = password
        self.timeout = self._check_timeout(timeout)
        self._sock: socket.socket | None = None
        self._recv_buffer = bytearray()
        self._pending_responses: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self._connected = False

    @staticmethod
    def _check_timeout(timeout: float) -> float:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be a non-negative number")
        value = float(timeout)
        if not math.isfinite(value) or value < 0:
            raise ValueError("timeout must be a finite non-negative number")
        return value

    @property
    def connected(self) -> bool:
        return self._connected and self._sock is not None

    def connect(self) -> "AdminClient":
        if self.connected:
            return self
        self.close()
        deadline = self._deadline(None)
        connect_timeout = _remaining(deadline)
        if connect_timeout <= 0:
            raise TimeoutError("Admin connect timed out")
        try:
            sock = socket.create_connection(("127.0.0.1", self.port), connect_timeout)
        except OSError:
            self._sock = None
            raise
        self._sock = sock
        self._recv_buffer.clear()
        self._pending_responses.clear()
        try:
            join_payload = self._cstring(self.password, 32)
            join_payload += self._cstring("OpenTTD Copilot", 24)
            join_payload += self._cstring("openttd-copilot/0.1", 32)
            self._send_packet(_ADMIN_JOIN, join_payload, deadline)

            packet_type, payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(payload)
            if packet_type != _SERVER_PROTOCOL:
                raise AdminProtocolError("expected Admin protocol packet after login")
            self._parse_protocol(payload)

            packet_type, payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(payload)
            if packet_type != _SERVER_WELCOME:
                raise AdminProtocolError("expected Admin welcome packet after protocol")
            self._parse_welcome(payload)
            self._connected = True

            # OpenTTD's AdminUpdateType is sent as uint16_t, despite being an
            # enum with an underlying uint8_t in the source.
            self._send_packet(
                _ADMIN_UPDATE_FREQUENCY,
                struct.pack("<HH", _UPDATE_GAMESCRIPT, _UPDATE_AUTOMATIC),
                deadline,
            )
            return self
        except BaseException:
            self.close()
            raise

    def send_request(self, request: dict[str, Any]) -> str:
        """Send one versioned GameScript request and return its request id."""
        return self._send_request(request, self._deadline(None))

    def request(self, request: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        """Send a request and wait for its matching response."""
        deadline = self._deadline(timeout)
        rid = self._send_request(request, deadline)
        remaining = _remaining(deadline)
        if remaining <= 0:
            raise TimeoutError("Admin request timed out")
        return self.receive_response(rid, remaining)

    def receive_response(self, rid: str, timeout: float | None = None) -> dict[str, Any]:
        """Wait for *rid*, retaining partial frames across a timeout."""
        if not isinstance(rid, str) or not rid or "\x00" in rid:
            raise ValueError("rid must be a non-empty string without NUL")
        self._require_connected()
        deadline = self._deadline(timeout)
        response = self._pending_responses.pop(rid, None)
        if response is not None:
            return response
        while True:
            packet_type, payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(payload)
            if packet_type == _SERVER_GAMESCRIPT:
                message = self._decode_gamescript(payload, "received", len(payload) + _HEADER_SIZE)
                if isinstance(message, dict) and message.get("rid") == rid:
                    return self._validate_response(message, rid)
                self._preserve_response(message)
                continue
            if packet_type == _SERVER_PONG:
                continue
            # Welcome/new-game/date/etc. are asynchronous Admin traffic. Their
            # bounded frames are consumed and ignored by this narrow client.

    def ping(self, value: int, timeout: float | None = None) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("ping value must be an unsigned 32-bit integer")
        self._require_connected()
        deadline = self._deadline(timeout)
        self._send_packet(_ADMIN_PING, struct.pack("<I", value), deadline)
        while True:
            packet_type, payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(payload)
            if packet_type == _SERVER_PONG:
                if len(payload) != 4:
                    raise AdminProtocolError("malformed Admin pong packet")
                return struct.unpack("<I", payload)[0]
            if packet_type == _SERVER_GAMESCRIPT:
                message = self._decode_gamescript(payload, "received", len(payload) + _HEADER_SIZE)
                self._preserve_response(message)

    def copilot_identity(
        self,
        company_id: int = COPILOT_COMPANY_ALL,
        *,
        protocol_version: int = COPILOT_PROTOCOL_VERSION,
        request_id: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Read bounded world/company identity from the native bridge."""
        if isinstance(company_id, bool) or not isinstance(company_id, int) or not 0 <= company_id <= 0xFF:
            raise ValueError("company_id must be an unsigned 8-bit integer")
        if (
            isinstance(protocol_version, bool)
            or not isinstance(protocol_version, int)
            or not 0 <= protocol_version <= 0xFFFF
        ):
            raise ValueError("protocol_version must be an unsigned 16-bit integer")
        if request_id is None:
            request_id = uuid.uuid4().int & 0xFFFFFFFF
        if isinstance(request_id, bool) or not isinstance(request_id, int) or not 0 <= request_id <= 0xFFFFFFFF:
            raise ValueError("request_id must be an unsigned 32-bit integer")

        self._require_connected()
        deadline = self._deadline(timeout)
        payload = struct.pack("<HBIB", protocol_version, _COPILOT_IDENTITY, request_id, company_id)
        self._send_packet(_ADMIN_COPILOT, payload, deadline)
        self.events.append(
            {
                "time": time.time(),
                "direction": "sent",
                "packet_type": "copilot_identity",
                "packet_length": len(payload) + _HEADER_SIZE,
                "request_id": request_id,
                "company_id": company_id,
                "protocol_version": protocol_version,
            }
        )
        while True:
            packet_type, response_payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(response_payload)
            if packet_type == _SERVER_COPILOT:
                response = self._decode_copilot_identity(response_payload)
                if response["request_id"] != request_id:
                    raise AdminProtocolError("Copilot response request ID mismatch")
                self.events.append(
                    {
                        "time": time.time(),
                        "direction": "received",
                        "packet_type": "copilot_identity",
                        "packet_length": len(response_payload) + _HEADER_SIZE,
                        "request_id": request_id,
                        "status": response["status"],
                    }
                )
                if response["status"] != 0:
                    raise CopilotBridgeError(response["status"])
                return response
            if packet_type == _SERVER_GAMESCRIPT:
                message = self._decode_gamescript(
                    response_payload, "received", len(response_payload) + _HEADER_SIZE
                )
                self._preserve_response(message)

    @staticmethod
    def _decode_copilot_identity(payload: bytes) -> dict[str, Any]:
        if len(payload) < 8:
            raise AdminProtocolError("truncated Copilot response header")
        version, request_kind, request_id, status = struct.unpack_from("<HBIB", payload)
        response: dict[str, Any] = {
            "version": version,
            "request_kind": request_kind,
            "request_id": request_id,
            "status": status,
        }
        if version != COPILOT_PROTOCOL_VERSION:
            raise AdminProtocolError(f"unsupported Copilot response version {version}")
        if request_kind != _COPILOT_IDENTITY:
            raise AdminProtocolError(f"unexpected Copilot response kind {request_kind}")
        if status != 0:
            if len(payload) != 8:
                raise AdminProtocolError("Copilot error response has trailing data")
            return response
        if len(payload) < 26:
            raise AdminProtocolError("truncated Copilot identity response")
        frame, seed, calendar_date, width, height, landscape, company_count = struct.unpack_from(
            "<IIIHHBB", payload, 8
        )
        position = 26
        companies: list[dict[str, Any]] = []
        for _ in range(company_count):
            if position + 18 > len(payload):
                raise AdminProtocolError("truncated Copilot company record")
            company_id, is_ai, money, loan = struct.unpack_from("<BBqq", payload, position)
            if is_ai not in (0, 1):
                raise AdminProtocolError("invalid Copilot company AI marker")
            position += 18
            end = payload.find(b"\x00", position)
            if end < 0:
                raise AdminProtocolError("Copilot company name lacks NUL terminator")
            try:
                name = payload[position:end].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise AdminProtocolError("Copilot company name is not UTF-8") from exc
            position = end + 1
            companies.append(
                {"id": company_id, "is_ai": bool(is_ai), "money": money, "loan": loan, "name": name}
            )
        if position != len(payload):
            raise AdminProtocolError("Copilot identity response has trailing data")
        response.update(
            {
                "frame": frame,
                "seed": seed,
                "calendar_date": calendar_date,
                "map_width": width,
                "map_height": height,
                "landscape": landscape,
                "companies": companies,
            }
        )
        return response

    def close(self) -> None:
        sock, self._sock = self._sock, None
        self._connected = False
        self._recv_buffer.clear()
        self._pending_responses.clear()
        if sock is None:
            return
        try:
            # A close packet is helpful to the server, but failure to send it
            # must never hide the caller's original error or block shutdown.
            sock.settimeout(min(self.timeout, 0.25))
            frame = self._frame(_ADMIN_QUIT, b"")
            sock.sendall(frame)
        except (OSError, TimeoutError):
            pass
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _abort_socket(self, sock: socket.socket) -> None:
        """Close a socket that may contain a partially written frame.

        Do not send the normal Admin quit packet here: after a failed send the
        peer may already have received a prefix of the failed frame, so a quit
        frame could be interpreted as more payload and desynchronize the
        stream further.
        """
        if self._sock is sock:
            self._sock = None
            self._connected = False
        try:
            sock.close()
        except OSError:
            pass

    def __enter__(self) -> "AdminClient":
        return self.connect()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _send_request(self, request: dict[str, Any], deadline: float) -> str:
        self._require_connected()
        envelope = self._make_envelope(request)
        encoded = json.dumps(
            envelope,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if b"\x00" in encoded:
            raise ValueError("request JSON must not contain NUL")
        if len(encoded) > MAX_GAMESCRIPT_JSON_BYTES:
            raise ValueError(f"request JSON exceeds {MAX_GAMESCRIPT_JSON_BYTES} UTF-8 bytes")
        self._send_packet(_ADMIN_GAMESCRIPT, encoded + b"\x00", deadline)
        self._record_gamescript("sent", envelope, len(encoded) + 1 + _HEADER_SIZE)
        return envelope["rid"]

    def _make_envelope(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise TypeError("request must be a dict")
        self._validate_json_value(request)
        command = request.get("cmd")
        if not isinstance(command, str) or not command or "\x00" in command:
            raise ValueError("request requires a non-empty string cmd")
        rid = request.get("rid")
        if rid is None:
            rid = uuid.uuid4().hex
        if not isinstance(rid, str) or not rid or "\x00" in rid:
            raise ValueError("rid must be a non-empty string without NUL")
        version = request.get("v", 1)
        if isinstance(version, bool) or not isinstance(version, int) or not 0 <= version <= 255:
            raise ValueError("request protocol version must be an integer from 0 through 255")
        envelope: dict[str, Any] = {"v": version, "rid": rid, "cmd": command}
        for key, value in request.items():
            if key not in {"v", "rid", "cmd"}:
                envelope[key] = value
        return envelope

    @classmethod
    def _validate_json_value(cls, value: Any) -> None:
        if value is None or isinstance(value, (bool, int)):
            return
        if isinstance(value, float):
            if not math.isfinite(value):
                raise ValueError("request JSON must not contain NaN or infinity")
            return
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("request JSON must not contain NUL")
            return
        if isinstance(value, list):
            for item in value:
                cls._validate_json_value(item)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise TypeError("request JSON object keys must be strings")
                cls._validate_json_value(key)
                cls._validate_json_value(item)
            return
        raise TypeError(f"unsupported JSON value: {type(value).__name__}")

    @staticmethod
    def _cstring(value: str, max_bytes: int) -> bytes:
        if not isinstance(value, str) or "\x00" in value:
            raise ValueError("Admin strings must be non-NUL text")
        encoded = value.encode("utf-8")
        if len(encoded) > max_bytes:
            raise ValueError("Admin string is too long")
        return encoded + b"\x00"

    def _send_packet(self, packet_type: int, payload: bytes, deadline: float) -> None:
        self._require_socket()
        frame = self._frame(packet_type, payload)
        sock = self._sock
        assert sock is not None
        view = memoryview(frame)
        try:
            while view:
                remaining = _remaining(deadline)
                if remaining <= 0:
                    raise TimeoutError("Admin send timed out")
                sock.settimeout(remaining)
                try:
                    sent = sock.send(view)
                except socket.timeout as exc:
                    raise TimeoutError("Admin send timed out") from exc
                if not sent:
                    raise EOFError("Admin socket closed during send")
                view = view[sent:]
        except (OSError, EOFError):
            self._abort_socket(sock)
            raise
        finally:
            try:
                sock.settimeout(None)
            except OSError:
                pass

    @staticmethod
    def _frame(packet_type: int, payload: bytes) -> bytes:
        if not isinstance(payload, bytes):
            payload = bytes(payload)
        size = _HEADER_SIZE + len(payload)
        if not 3 <= size <= MAX_PACKET_SIZE:
            raise ValueError(f"Admin packet size must be between 3 and {MAX_PACKET_SIZE}")
        return struct.pack("<HB", size, packet_type) + payload

    def _read_frame(self, deadline: float) -> tuple[int, bytes]:
        self._require_socket()
        sock = self._sock
        assert sock is not None
        try:
            while len(self._recv_buffer) < 2:
                self._recv_more(sock, deadline)
            size = struct.unpack_from("<H", self._recv_buffer)[0]
            if size < _HEADER_SIZE:
                raise AdminProtocolError(f"invalid Admin packet length {size}")
            if size > MAX_PACKET_SIZE:
                raise AdminProtocolError(f"oversize Admin packet length {size}")
            while len(self._recv_buffer) < size:
                self._recv_more(sock, deadline)
            frame = bytes(self._recv_buffer[:size])
            del self._recv_buffer[:size]
            return frame[2], frame[3:]
        except (AdminProtocolError, EOFError):
            self.close()
            raise

    def _recv_more(self, sock: socket.socket, deadline: float) -> None:
        remaining = _remaining(deadline)
        if remaining <= 0:
            raise TimeoutError("Admin receive timed out")
        sock.settimeout(remaining)
        try:
            try:
                data = sock.recv(4096)
            except socket.timeout as exc:
                raise TimeoutError("Admin receive timed out") from exc
        finally:
            try:
                sock.settimeout(None)
            except OSError:
                pass
        if not data:
            raise EOFError("Admin socket closed while receiving a packet")
        self._recv_buffer.extend(data)

    def _parse_protocol(self, payload: bytes) -> None:
        if not payload:
            raise AdminProtocolError("empty Admin protocol packet")
        version = payload[0]
        if version != ADMIN_PROTOCOL_VERSION:
            raise AdminProtocolError(
                f"unsupported OpenTTD Admin protocol version {version}; expected {ADMIN_PROTOCOL_VERSION}"
            )
        pos = 1
        while True:
            if pos >= len(payload):
                raise AdminProtocolError("unterminated Admin protocol update table")
            present = payload[pos]
            pos += 1
            if present == 0:
                break
            if present not in (1,):
                raise AdminProtocolError("invalid Admin protocol update marker")
            if pos + 4 > len(payload):
                raise AdminProtocolError("truncated Admin protocol update table")
            update_type, frequencies = struct.unpack_from("<HH", payload, pos)
            pos += 4
            if update_type >= 10 or frequencies == 0:
                raise AdminProtocolError("invalid Admin protocol update table entry")

    @staticmethod
    def _parse_welcome(payload: bytes) -> None:
        pos = 0
        for _ in range(2):
            end = payload.find(b"\x00", pos)
            if end < 0:
                raise AdminProtocolError("malformed Admin welcome string")
            pos = end + 1
        if pos + 1 > len(payload):
            raise AdminProtocolError("truncated Admin welcome packet")
        pos += 1  # dedicated bool
        end = payload.find(b"\x00", pos)
        if end < 0:
            raise AdminProtocolError("malformed Admin welcome map string")
        pos = end + 1
        if pos + 13 > len(payload):
            raise AdminProtocolError("truncated Admin welcome packet")

    def _decode_gamescript(self, payload: bytes, direction: str, packet_length: int) -> Any:
        end = payload.find(b"\x00")
        if end < 0:
            raise AdminProtocolError("GameScript packet lacks NUL terminator")
        try:
            text = payload[:end].decode("utf-8")
            message = json.loads(text, parse_constant=_reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise AdminProtocolError("malformed GameScript JSON packet") from exc
        self._record_gamescript(direction, message, packet_length)
        return message

    def _record_gamescript(self, direction: str, payload: Any, packet_length: int) -> None:
        self.events.append(
            {
                "time": time.time(),
                "direction": direction,
                "packet_type": "gamescript",
                "packet_length": packet_length,
                "payload": payload,
            }
        )

    @staticmethod
    def _validate_response(message: Any, rid: str) -> dict[str, Any]:
        if not isinstance(message, dict):
            raise AdminProtocolError("GameScript response is not an object")
        if (
            isinstance(message.get("v"), bool)
            or not isinstance(message.get("v"), int)
            or message.get("v") != 1
            or message.get("rid") != rid
            or not isinstance(message.get("ok"), bool)
        ):
            raise AdminProtocolError("malformed GameScript response envelope")
        return message

    def _preserve_response(self, message: Any) -> None:
        """Retain valid unrelated replies so another RID can collect them."""
        if not isinstance(message, dict) or not isinstance(message.get("rid"), str):
            return
        try:
            response = self._validate_response(message, message["rid"])
        except AdminProtocolError:
            return
        rid = message["rid"]
        if rid not in self._pending_responses and len(self._pending_responses) >= MAX_PENDING_RESPONSES:
            raise AdminTransportError("pending Admin response limit reached")
        self._pending_responses[rid] = response

    @staticmethod
    def _raise_server_error(payload: bytes) -> None:
        if not payload:
            raise AdminProtocolError("empty OpenTTD Admin server error packet")
        raise AdminServerError(payload[0])

    def _require_socket(self) -> None:
        if self._sock is None:
            raise AdminTransportError("Admin client is not connected")

    def _require_connected(self) -> None:
        if not self.connected:
            raise AdminTransportError("Admin client is not connected")

    def _deadline(self, timeout: float | None) -> float:
        value = self.timeout if timeout is None else self._check_timeout(timeout)
        return time.monotonic() + value


def _remaining(deadline: float) -> float:
    return deadline - time.monotonic()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


__all__ = [
    "ADMIN_PROTOCOL_VERSION",
    "COPILOT_COMPANY_ALL",
    "COPILOT_PROTOCOL_VERSION",
    "AdminClient",
    "AdminProtocolError",
    "AdminServerError",
    "AdminTransportError",
    "CopilotBridgeError",
    "COMPAT_MTU",
    "MAX_GAMESCRIPT_JSON_BYTES",
    "MAX_PENDING_RESPONSES",
    "MAX_PACKET_SIZE",
]
