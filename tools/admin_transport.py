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
COPILOT_PROTOCOL_VERSION = 3
COPILOT_COMPANY_ALL = 0xFF
_COPILOT_IDENTITY = 0
_COPILOT_BUILD_SINGLE_RAIL = 1
_COPILOT_OPERATION_STATUS = 2
_COPILOT_VEHICLE_EVENTS = 3
_COPILOT_TILE_SNAPSHOT = 4
_COPILOT_INDUSTRY_SNAPSHOT = 5
_COPILOT_RAIL_CATALOG = 6
_COPILOT_RAIL_ASSETS = 7
_COPILOT_TRAIN_PARTS = 8
_MAX_COPILOT_WORLD_ID_BYTES = 65  # 64 UTF-8 bytes plus the wire NUL terminator.
_MAX_COPILOT_EVENTS = 16
_MAX_COPILOT_TILE_SNAPSHOT_COUNT = 32
_MAX_COPILOT_INDUSTRY_SNAPSHOT_COUNT = 16
_MAX_COPILOT_RAIL_CATALOG_COUNT = 16
_MAX_COPILOT_RAIL_ASSET_COUNT = 16
_MAX_COPILOT_TRAIN_PART_COUNT = 16
_MAX_COPILOT_TRAIN_SCAN_BUDGET = 256
_COPILOT_INITIAL_VEHICLE_CURSOR = 0xFFFFFFFF
_COPILOT_OPERATION_STATE_NAMES = {
    0: "empty",
    1: "pending",
    2: "completed",
    3: "rejected",
    4: "uncertain",
}


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
        5: "Copilot world identity mismatch",
        6: "Copilot company is not human-owned",
        7: "invalid Copilot argument",
        8: "Copilot operation identity conflict",
        9: "Copilot operation journal is busy",
        10: "Copilot operation was not found",
        11: "stale Copilot world journal position",
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

    def copilot_build_single_rail(
        self,
        *,
        world_id: str,
        company_id: int,
        tile: int,
        rail_type: int,
        track: int,
        max_cost: int,
        expected_sequence: int,
        expected_head_hi: int,
        expected_head_lo: int,
        operation_hi: int,
        operation_lo: int,
        payload_hash_hi: int,
        payload_hash_lo: int,
        protocol_version: int = COPILOT_PROTOCOL_VERSION,
        request_id: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Execute one bounded rail build through the native command pipeline."""
        request_id = self._check_copilot_request_header(protocol_version, request_id)
        company_id = self._check_uint("company_id", company_id, 8)
        tile = self._check_uint("tile", tile, 32)
        rail_type = self._check_uint("rail_type", rail_type, 8)
        track = self._check_uint("track", track, 8)
        max_cost = self._check_int64("max_cost", max_cost)
        expected_sequence = self._check_uint("expected_sequence", expected_sequence, 64)
        expected_head_hi = self._check_uint("expected_head_hi", expected_head_hi, 64)
        expected_head_lo = self._check_uint("expected_head_lo", expected_head_lo, 64)
        operation_hi = self._check_uint("operation_hi", operation_hi, 64)
        operation_lo = self._check_uint("operation_lo", operation_lo, 64)
        payload_hash_hi = self._check_uint("payload_hash_hi", payload_hash_hi, 64)
        payload_hash_lo = self._check_uint("payload_hash_lo", payload_hash_lo, 64)
        world = self._copilot_world_id(world_id)

        payload = struct.pack(
            "<HBIBIBBqQQQQQQQ",
            protocol_version,
            _COPILOT_BUILD_SINGLE_RAIL,
            request_id,
            company_id,
            tile,
            rail_type,
            track,
            max_cost,
            expected_sequence,
            expected_head_hi,
            expected_head_lo,
            operation_hi,
            operation_lo,
            payload_hash_hi,
            payload_hash_lo,
        ) + world
        response = self._copilot_operation_request(
            _COPILOT_BUILD_SINGLE_RAIL,
            "copilot_build_single_rail",
            request_id,
            payload,
            timeout,
            {"company_id": company_id, "tile": tile},
        )
        self._validate_copilot_operation_correlation(
            response, world_id, operation_hi, operation_lo
        )
        return response

    def copilot_operation_status(
        self,
        *,
        world_id: str,
        operation_hi: int,
        operation_lo: int,
        protocol_version: int = COPILOT_PROTOCOL_VERSION,
        request_id: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Read one durable operation outcome without retrying its mutation."""
        request_id = self._check_copilot_request_header(protocol_version, request_id)
        operation_hi = self._check_uint("operation_hi", operation_hi, 64)
        operation_lo = self._check_uint("operation_lo", operation_lo, 64)
        world = self._copilot_world_id(world_id)
        payload = struct.pack(
            "<HBIQQ",
            protocol_version,
            _COPILOT_OPERATION_STATUS,
            request_id,
            operation_hi,
            operation_lo,
        ) + world
        response = self._copilot_operation_request(
            _COPILOT_OPERATION_STATUS,
            "copilot_operation_status",
            request_id,
            payload,
            timeout,
        )
        self._validate_copilot_operation_correlation(
            response, world_id, operation_hi, operation_lo
        )
        return response

    def copilot_vehicle_events(
        self,
        world_id: str,
        company_id: int,
        vehicle_id: int,
        cursor: int = 0,
        epoch: int | None = None,
        timeout: float | None = None,
        request_id: int | None = None,
    ) -> dict[str, Any]:
        """Read a bounded page of vehicle-tagged departure and delivery events.

        ``epoch`` is accepted for callers carrying a prior observation epoch;
        the native v3 request identifies the page with only the cursor, so it
        is validated for compatibility but is not sent on the wire.
        """
        request_id = self._check_copilot_request_header(COPILOT_PROTOCOL_VERSION, request_id)
        company_id = self._check_uint("company_id", company_id, 8)
        vehicle_id = self._check_uint("vehicle_id", vehicle_id, 32)
        cursor = self._check_uint("cursor", cursor, 64)
        if epoch is not None:
            self._check_uint("epoch", epoch, 64)
        world = self._copilot_world_id(world_id)
        payload = struct.pack(
            "<HBIBIQ",
            COPILOT_PROTOCOL_VERSION,
            _COPILOT_VEHICLE_EVENTS,
            request_id,
            company_id,
            vehicle_id,
            cursor,
        ) + world
        response = self._copilot_vehicle_events_request(
            request_id, payload, timeout, {"company_id": company_id, "vehicle_id": vehicle_id, "cursor": cursor}
        )
        if response["world_id"] != world_id:
            raise AdminProtocolError("Copilot vehicle events response world ID mismatch")
        return response

    def copilot_tile_snapshot(
        self,
        world_id: str,
        start_tile: int,
        count: int,
        timeout: float | None = None,
        request_id: int | None = None,
        protocol_version: int = COPILOT_PROTOCOL_VERSION,
    ) -> dict[str, Any]:
        """Read a bounded contiguous page of typed world tile observations."""
        request_id = self._check_copilot_request_header(protocol_version, request_id)
        start_tile = self._check_uint("start_tile", start_tile, 32)
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 1 <= count <= _MAX_COPILOT_TILE_SNAPSHOT_COUNT
        ):
            raise ValueError(
                f"count must be an integer from 1 through {_MAX_COPILOT_TILE_SNAPSHOT_COUNT}"
            )
        world = self._copilot_world_id(world_id)
        payload = struct.pack(
            "<HBIIB", protocol_version, _COPILOT_TILE_SNAPSHOT,
            request_id, start_tile, count
        ) + world
        self._require_connected()
        deadline = self._deadline(timeout)
        self._send_packet(_ADMIN_COPILOT, payload, deadline)
        self.events.append(
            {
                "time": time.time(),
                "direction": "sent",
                "packet_type": "copilot_tile_snapshot",
                "packet_length": len(payload) + _HEADER_SIZE,
                "request_id": request_id,
                "protocol_version": protocol_version,
                "start_tile": start_tile,
                "count": count,
            }
        )
        while True:
            packet_type, response_payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(response_payload)
            if packet_type == _SERVER_COPILOT:
                response = self._decode_copilot_tile_snapshot(response_payload)
                if response["request_id"] != request_id:
                    raise AdminProtocolError("Copilot response request ID mismatch")
                self.events.append(
                    {
                        "time": time.time(),
                        "direction": "received",
                        "packet_type": "copilot_tile_snapshot",
                        "packet_length": len(response_payload) + _HEADER_SIZE,
                        "request_id": request_id,
                        "status": response["status"],
                    }
                )
                if response["status"] != 0:
                    raise CopilotBridgeError(response["status"])
                if response["world_id"] != world_id:
                    raise AdminProtocolError("Copilot tile snapshot response world ID mismatch")
                if response["start_tile"] != start_tile or response["count"] != count:
                    raise AdminProtocolError("Copilot tile snapshot response range mismatch")
                return response
            if packet_type == _SERVER_GAMESCRIPT:
                message = self._decode_gamescript(
                    response_payload, "received", len(response_payload) + _HEADER_SIZE
                )
                self._preserve_response(message)

    @staticmethod
    def _decode_copilot_tile_snapshot(payload: bytes) -> dict[str, Any]:
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
        if request_kind != _COPILOT_TILE_SNAPSHOT:
            raise AdminProtocolError(f"unexpected Copilot response kind {request_kind}")
        if status != 0:
            if len(payload) != 8:
                raise AdminProtocolError("Copilot error response has trailing data")
            return response

        position = 8
        world_id, position = AdminClient._decode_copilot_cstring(payload, position, "world ID")
        fixed_format = "<IIB"
        fixed_size = struct.calcsize(fixed_format)
        if position + fixed_size > len(payload):
            raise AdminProtocolError("truncated Copilot tile snapshot response")
        frame, start_tile, count = struct.unpack_from(fixed_format, payload, position)
        position += fixed_size
        if not 1 <= count <= _MAX_COPILOT_TILE_SNAPSHOT_COUNT:
            raise AdminProtocolError("Copilot tile snapshot response exceeds tile limit")
        record_format = "<IBBBBBBB"
        record_size = struct.calcsize(record_format)
        if position + count * record_size > len(payload):
            raise AdminProtocolError("truncated Copilot tile snapshot record")
        tiles: list[dict[str, Any]] = []
        for offset in range(count):
            tile, valid, tile_type, owner, slope, height, track_bits, rail_type = struct.unpack_from(
                record_format, payload, position
            )
            position += record_size
            if valid not in (0, 1):
                raise AdminProtocolError("invalid Copilot tile snapshot validity marker")
            if tile != start_tile + offset:
                raise AdminProtocolError("Copilot tile snapshot tile sequence mismatch")
            tiles.append(
                {
                    "tile": tile,
                    "valid": bool(valid),
                    "tile_type": tile_type,
                    "owner": owner,
                    "slope": slope,
                    "height": height,
                    "track_bits": track_bits,
                    "rail_type": rail_type,
                }
            )
        if position != len(payload):
            raise AdminProtocolError("Copilot tile snapshot response has trailing data")
        response.update(
            {
                "world_id": world_id,
                "frame": frame,
                "start_tile": start_tile,
                "count": count,
                "tiles": tiles,
            }
        )
        return response

    def copilot_industry_snapshot(
        self,
        world_id: str,
        start_index: int,
        count: int,
        timeout: float | None = None,
        request_id: int | None = None,
        protocol_version: int = COPILOT_PROTOCOL_VERSION,
    ) -> dict[str, Any]:
        """Read one bounded page of industry IDs, locations, and cargo types.

        ``start_index`` is an ordinal in the engine's industry-pool iteration.
        Continue at ``start_index + count`` until a short page is returned; if
        the total is an exact multiple of the page size, one final empty page
        signals exhaustion. Locations are the industry's anchor tile, not its
        full footprint. Pages are individually frame-stamped, not atomic.
        """
        request_id = self._check_copilot_request_header(protocol_version, request_id)
        start_index = self._check_uint("start_index", start_index, 32)
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 1 <= count <= _MAX_COPILOT_INDUSTRY_SNAPSHOT_COUNT
        ):
            raise ValueError(
                f"count must be an integer from 1 through {_MAX_COPILOT_INDUSTRY_SNAPSHOT_COUNT}"
            )
        world = self._copilot_world_id(world_id)
        payload = struct.pack(
            "<HBIIB", protocol_version, _COPILOT_INDUSTRY_SNAPSHOT,
            request_id, start_index, count
        ) + world
        self._require_connected()
        deadline = self._deadline(timeout)
        self._send_packet(_ADMIN_COPILOT, payload, deadline)
        self.events.append({
            "time": time.time(), "direction": "sent", "packet_type": "copilot_industry_snapshot",
            "packet_length": len(payload) + _HEADER_SIZE, "request_id": request_id,
            "protocol_version": protocol_version, "start_index": start_index, "count": count,
        })
        while True:
            packet_type, response_payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(response_payload)
            if packet_type == _SERVER_COPILOT:
                response = self._decode_copilot_industry_snapshot(response_payload)
                if response["request_id"] != request_id:
                    raise AdminProtocolError("Copilot response request ID mismatch")
                self.events.append({
                    "time": time.time(), "direction": "received", "packet_type": "copilot_industry_snapshot",
                    "packet_length": len(response_payload) + _HEADER_SIZE, "request_id": request_id,
                    "status": response["status"],
                })
                if response["status"] != 0:
                    raise CopilotBridgeError(response["status"])
                if response["world_id"] != world_id:
                    raise AdminProtocolError("Copilot industry snapshot response world ID mismatch")
                if response["start_index"] != start_index or response["count"] > count:
                    raise AdminProtocolError("Copilot industry snapshot response range mismatch")
                return response
            if packet_type == _SERVER_GAMESCRIPT:
                message = self._decode_gamescript(
                    response_payload, "received", len(response_payload) + _HEADER_SIZE
                )
                self._preserve_response(message)

    @staticmethod
    def _decode_copilot_industry_snapshot(payload: bytes) -> dict[str, Any]:
        if len(payload) < 8:
            raise AdminProtocolError("truncated Copilot response header")
        version, request_kind, request_id, status = struct.unpack_from("<HBIB", payload)
        response: dict[str, Any] = {
            "version": version, "request_kind": request_kind, "request_id": request_id, "status": status,
        }
        if version != COPILOT_PROTOCOL_VERSION:
            raise AdminProtocolError(f"unsupported Copilot response version {version}")
        if request_kind != _COPILOT_INDUSTRY_SNAPSHOT:
            raise AdminProtocolError(f"unexpected Copilot response kind {request_kind}")
        if status != 0:
            if len(payload) != 8:
                raise AdminProtocolError("Copilot error response has trailing data")
            return response

        position = 8
        world_id, position = AdminClient._decode_copilot_cstring(payload, position, "world ID")
        fixed_size = struct.calcsize("<IIB")
        if position + fixed_size > len(payload):
            raise AdminProtocolError("truncated Copilot industry snapshot response")
        frame, start_index, count = struct.unpack_from("<IIB", payload, position)
        position += fixed_size
        if count > _MAX_COPILOT_INDUSTRY_SNAPSHOT_COUNT:
            raise AdminProtocolError("Copilot industry snapshot response exceeds industry limit")
        industries: list[dict[str, Any]] = []
        for _ in range(count):
            if position + 8 > len(payload):
                raise AdminProtocolError("truncated Copilot industry snapshot record")
            industry_id, industry_type, tile = struct.unpack_from("<HBI", payload, position)
            position += 7
            produced_count = payload[position]
            position += 1
            if produced_count > 16 or position + produced_count + 1 > len(payload):
                raise AdminProtocolError("invalid or truncated produced cargo list")
            produced = list(payload[position:position + produced_count])
            position += produced_count
            accepted_count = payload[position]
            position += 1
            if accepted_count > 16 or position + accepted_count > len(payload):
                raise AdminProtocolError("invalid or truncated accepted cargo list")
            accepted = list(payload[position:position + accepted_count])
            position += accepted_count
            if 255 in produced or 255 in accepted:
                raise AdminProtocolError("invalid cargo type in industry snapshot")
            industries.append({
                "industry_id": industry_id, "industry_type": industry_type, "tile": tile,
                "produced_cargo": produced, "accepted_cargo": accepted,
            })
        if position != len(payload):
            raise AdminProtocolError("Copilot industry snapshot response has trailing data")
        response.update({
            "world_id": world_id, "frame": frame, "start_index": start_index,
            "count": count, "industries": industries,
        })
        return response

    def copilot_rail_catalog(
        self,
        world_id: str,
        company_id: int,
        start_index: int,
        count: int,
        timeout: float | None = None,
        request_id: int | None = None,
        protocol_version: int = COPILOT_PROTOCOL_VERSION,
    ) -> dict[str, Any]:
        """Read a bounded rail-engine page; prices are nonnegative engine money units."""
        request_id = self._check_copilot_request_header(protocol_version, request_id)
        company_id = self._check_uint("company_id", company_id, 8)
        start_index = self._check_uint("start_index", start_index, 32)
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 1 <= count <= _MAX_COPILOT_RAIL_CATALOG_COUNT
        ):
            raise ValueError(
                f"count must be an integer from 1 through {_MAX_COPILOT_RAIL_CATALOG_COUNT}"
            )
        world = self._copilot_world_id(world_id)
        payload = struct.pack(
            "<HBIBIB", protocol_version, _COPILOT_RAIL_CATALOG,
            request_id, company_id, start_index, count
        ) + world
        self._require_connected()
        deadline = self._deadline(timeout)
        self._send_packet(_ADMIN_COPILOT, payload, deadline)
        self.events.append({
            "time": time.time(), "direction": "sent", "packet_type": "copilot_rail_catalog",
            "packet_length": len(payload) + _HEADER_SIZE, "request_id": request_id,
            "protocol_version": protocol_version, "company_id": company_id,
            "start_index": start_index, "count": count,
        })
        while True:
            packet_type, response_payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(response_payload)
            if packet_type == _SERVER_COPILOT:
                response = self._decode_copilot_rail_catalog(response_payload)
                if response["request_id"] != request_id:
                    raise AdminProtocolError("Copilot response request ID mismatch")
                self.events.append({
                    "time": time.time(), "direction": "received", "packet_type": "copilot_rail_catalog",
                    "packet_length": len(response_payload) + _HEADER_SIZE, "request_id": request_id,
                    "status": response["status"],
                })
                if response["status"] != 0:
                    raise CopilotBridgeError(response["status"])
                if response["world_id"] != world_id:
                    raise AdminProtocolError("Copilot rail catalog response world ID mismatch")
                if response["company_id"] != company_id:
                    raise AdminProtocolError("Copilot rail catalog response company ID mismatch")
                if response["start_index"] != start_index or response["count"] > count:
                    raise AdminProtocolError("Copilot rail catalog response range mismatch")
                return response
            if packet_type == _SERVER_GAMESCRIPT:
                message = self._decode_gamescript(
                    response_payload, "received", len(response_payload) + _HEADER_SIZE
                )
                self._preserve_response(message)

    @staticmethod
    def _decode_copilot_rail_catalog(payload: bytes) -> dict[str, Any]:
        if len(payload) < 8:
            raise AdminProtocolError("truncated Copilot response header")
        version, request_kind, request_id, status = struct.unpack_from("<HBIB", payload)
        response: dict[str, Any] = {
            "version": version, "request_kind": request_kind, "request_id": request_id, "status": status,
        }
        if version != COPILOT_PROTOCOL_VERSION:
            raise AdminProtocolError(f"unsupported Copilot response version {version}")
        if request_kind != _COPILOT_RAIL_CATALOG:
            raise AdminProtocolError(f"unexpected Copilot response kind {request_kind}")
        if status != 0:
            if len(payload) != 8:
                raise AdminProtocolError("Copilot error response has trailing data")
            return response

        position = 8
        world_id, position = AdminClient._decode_copilot_cstring(payload, position, "world ID")
        fixed_format = "<IBQIB"
        fixed_size = struct.calcsize(fixed_format)
        if position + fixed_size > len(payload):
            raise AdminProtocolError("truncated Copilot rail catalog response")
        frame, company_id, company_railtypes, start_index, count = struct.unpack_from(
            fixed_format, payload, position
        )
        position += fixed_size
        if count > _MAX_COPILOT_RAIL_CATALOG_COUNT:
            raise AdminProtocolError("Copilot rail catalog response exceeds engine limit")
        record_format = "<HBBQBIQQQHHHB"
        record_size = struct.calcsize(record_format)
        if position + count * record_size > len(payload):
            raise AdminProtocolError("truncated Copilot rail catalog record")
        engines: list[dict[str, Any]] = []
        for _ in range(count):
            (engine_id, buildable, railveh_type, railtypes, default_cargo, default_capacity,
             refit_mask, purchase_cost, running_cost, max_speed, power, weight,
             shorten_factor) = struct.unpack_from(record_format, payload, position)
            position += record_size
            if buildable not in (0, 1):
                raise AdminProtocolError("invalid buildable marker in rail catalog")
            if railveh_type not in (0, 1, 2):
                raise AdminProtocolError("invalid rail vehicle class in rail catalog")
            if default_cargo != 255 and default_cargo >= 64:
                raise AdminProtocolError("invalid default cargo in rail catalog")
            if purchase_cost > 0x7FFFFFFFFFFFFFFF or running_cost > 0x7FFFFFFFFFFFFFFF:
                raise AdminProtocolError("engine cost exceeds the signed Money range")
            engines.append({
                "engine_id": engine_id, "buildable": bool(buildable),
                "railveh_type": railveh_type, "railtypes": railtypes,
                "default_cargo": default_cargo, "default_capacity": default_capacity,
                "refit_mask": refit_mask, "purchase_cost": purchase_cost,
                "running_cost": running_cost, "max_speed": max_speed,
                "power": power, "weight": weight, "shorten_factor": shorten_factor,
            })
        if position != len(payload):
            raise AdminProtocolError("Copilot rail catalog response has trailing data")
        response.update({
            "world_id": world_id, "frame": frame, "company_id": company_id,
            "company_railtypes": company_railtypes, "start_index": start_index,
            "count": count, "engines": engines,
        })
        return response

    def copilot_rail_assets(
        self, world_id: str, company_id: int, asset_kind: int, start_index: int,
        count: int, timeout: float | None = None, request_id: int | None = None,
        protocol_version: int = COPILOT_PROTOCOL_VERSION,
    ) -> dict[str, Any]:
        """Read one page of this human company's rail stations or depots.

        ``asset_kind`` is 0 for rail stations and 1 for rail depots. Station
        records include the train-platform area and current cargo acceptance
        mask. That mask describes existing stations only; it does not predict
        acceptance for a proposed station. Depot records include tile, entrance
        direction, and rail type.
        """
        request_id = self._check_copilot_request_header(protocol_version, request_id)
        company_id = self._check_uint("company_id", company_id, 8)
        asset_kind = self._check_uint("asset_kind", asset_kind, 8)
        if asset_kind not in (0, 1):
            raise ValueError("asset_kind must be 0 (station) or 1 (depot)")
        start_index = self._check_uint("start_index", start_index, 32)
        if (isinstance(count, bool) or not isinstance(count, int) or
                not 1 <= count <= _MAX_COPILOT_RAIL_ASSET_COUNT):
            raise ValueError(f"count must be an integer from 1 through {_MAX_COPILOT_RAIL_ASSET_COUNT}")
        world = self._copilot_world_id(world_id)
        payload = struct.pack("<HBIBBIB", protocol_version, _COPILOT_RAIL_ASSETS,
                              request_id, company_id, asset_kind, start_index, count) + world
        self._require_connected()
        deadline = self._deadline(timeout)
        self._send_packet(_ADMIN_COPILOT, payload, deadline)
        packet_name = "copilot_rail_assets"
        self.events.append({"time": time.time(), "direction": "sent", "packet_type": packet_name,
                            "packet_length": len(payload) + _HEADER_SIZE, "request_id": request_id,
                            "protocol_version": protocol_version, "company_id": company_id,
                            "asset_kind": asset_kind, "start_index": start_index, "count": count})
        while True:
            packet_type, response_payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(response_payload)
            if packet_type == _SERVER_COPILOT:
                response = self._decode_copilot_rail_assets(response_payload)
                if response["request_id"] != request_id:
                    raise AdminProtocolError("Copilot response request ID mismatch")
                self.events.append({"time": time.time(), "direction": "received", "packet_type": packet_name,
                                    "packet_length": len(response_payload) + _HEADER_SIZE,
                                    "request_id": request_id, "status": response["status"]})
                if response["status"] != 0:
                    raise CopilotBridgeError(response["status"])
                if response["world_id"] != world_id:
                    raise AdminProtocolError("Copilot rail assets response world ID mismatch")
                if response["company_id"] != company_id or response["asset_kind"] != asset_kind:
                    raise AdminProtocolError("Copilot rail assets response selector mismatch")
                if response["start_index"] != start_index or response["count"] > count:
                    raise AdminProtocolError("Copilot rail assets response range mismatch")
                return response
            if packet_type == _SERVER_GAMESCRIPT:
                message = self._decode_gamescript(response_payload, "received", len(response_payload) + _HEADER_SIZE)
                self._preserve_response(message)

    @staticmethod
    def _decode_copilot_rail_assets(payload: bytes) -> dict[str, Any]:
        if len(payload) < 8:
            raise AdminProtocolError("truncated Copilot response header")
        version, request_kind, request_id, status = struct.unpack_from("<HBIB", payload)
        response: dict[str, Any] = {"version": version, "request_kind": request_kind,
                                    "request_id": request_id, "status": status}
        if version != COPILOT_PROTOCOL_VERSION:
            raise AdminProtocolError(f"unsupported Copilot response version {version}")
        if request_kind != _COPILOT_RAIL_ASSETS:
            raise AdminProtocolError(f"unexpected Copilot response kind {request_kind}")
        if status != 0:
            if len(payload) != 8:
                raise AdminProtocolError("Copilot error response has trailing data")
            return response
        position = 8
        world_id, position = AdminClient._decode_copilot_cstring(payload, position, "world ID")
        fixed_format = "<IBBIB"
        fixed_size = struct.calcsize(fixed_format)
        if position + fixed_size > len(payload):
            raise AdminProtocolError("truncated Copilot rail assets response")
        frame, company_id, asset_kind, start_index, count = struct.unpack_from(fixed_format, payload, position)
        position += fixed_size
        if asset_kind not in (0, 1) or count > _MAX_COPILOT_RAIL_ASSET_COUNT:
            raise AdminProtocolError("invalid Copilot rail assets page selector or count")
        if asset_kind == 0:
            record_format = "<HIIHHQ"
            record_size = struct.calcsize(record_format)
            if position + count * record_size > len(payload):
                raise AdminProtocolError("truncated Copilot rail station record")
            assets = []
            for _ in range(count):
                station_id, base_tile, platform_tile, width, height, acceptance_mask = struct.unpack_from(
                    record_format, payload, position)
                position += record_size
                assets.append({"station_id": station_id, "base_tile": base_tile,
                               "platform_tile": platform_tile, "platform_width": width,
                               "platform_height": height, "acceptance_mask": acceptance_mask})
            key = "stations"
        else:
            record_format = "<HIBB"
            record_size = struct.calcsize(record_format)
            if position + count * record_size > len(payload):
                raise AdminProtocolError("truncated Copilot rail depot record")
            assets = []
            for _ in range(count):
                depot_id, tile, direction, rail_type = struct.unpack_from(record_format, payload, position)
                position += record_size
                assets.append({"depot_id": depot_id, "tile": tile,
                               "direction": direction, "rail_type": rail_type})
            key = "depots"
        if position != len(payload):
            raise AdminProtocolError("Copilot rail assets response has trailing data")
        response.update({"world_id": world_id, "frame": frame, "company_id": company_id,
                         "asset_kind": asset_kind, "start_index": start_index,
                         "count": count, key: assets})
        return response

    def copilot_train_parts(
        self, world_id: str, company_id: int,
        after_vehicle_id: int = _COPILOT_INITIAL_VEHICLE_CURSOR,
        max_records: int = _MAX_COPILOT_TRAIN_PART_COUNT,
        scan_budget: int = _MAX_COPILOT_TRAIN_SCAN_BUDGET,
        timeout: float | None = None, request_id: int | None = None,
        protocol_version: int = COPILOT_PROTOCOL_VERSION,
    ) -> dict[str, Any]:
        """Read a bounded ID-ordered page of this company's rail vehicles.

        The cursor is exclusive; UINT32_MAX begins a scan. ``scan_budget``
        bounds pool IDs inspected while ``max_records`` bounds returned train
        parts. A complete response means the pool end was reached. Pages are
        frame-stamped individually and do not form an atomic snapshot.
        """
        request_id = self._check_copilot_request_header(protocol_version, request_id)
        company_id = self._check_uint("company_id", company_id, 8)
        after_vehicle_id = self._check_uint("after_vehicle_id", after_vehicle_id, 32)
        if (after_vehicle_id != _COPILOT_INITIAL_VEHICLE_CURSOR and after_vehicle_id > 0xFFFFF):
            raise ValueError("after_vehicle_id must be UINT32_MAX or a legal vehicle ID")
        if (isinstance(max_records, bool) or not isinstance(max_records, int) or
                not 1 <= max_records <= _MAX_COPILOT_TRAIN_PART_COUNT):
            raise ValueError(f"max_records must be an integer from 1 through {_MAX_COPILOT_TRAIN_PART_COUNT}")
        if (isinstance(scan_budget, bool) or not isinstance(scan_budget, int) or
                not 1 <= scan_budget <= _MAX_COPILOT_TRAIN_SCAN_BUDGET):
            raise ValueError(f"scan_budget must be an integer from 1 through {_MAX_COPILOT_TRAIN_SCAN_BUDGET}")
        world = self._copilot_world_id(world_id)
        payload = struct.pack("<HBIBIBH", protocol_version, _COPILOT_TRAIN_PARTS,
                              request_id, company_id, after_vehicle_id,
                              max_records, scan_budget) + world
        self._require_connected()
        deadline = self._deadline(timeout)
        self._send_packet(_ADMIN_COPILOT, payload, deadline)
        packet_name = "copilot_train_parts"
        self.events.append({"time": time.time(), "direction": "sent", "packet_type": packet_name,
                            "packet_length": len(payload) + _HEADER_SIZE, "request_id": request_id,
                            "company_id": company_id, "after_vehicle_id": after_vehicle_id,
                            "max_records": max_records, "scan_budget": scan_budget})
        while True:
            packet_type, response_payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(response_payload)
            if packet_type == _SERVER_COPILOT:
                response = self._decode_copilot_train_parts(response_payload)
                if response["request_id"] != request_id:
                    raise AdminProtocolError("Copilot response request ID mismatch")
                self.events.append({"time": time.time(), "direction": "received", "packet_type": packet_name,
                                    "packet_length": len(response_payload) + _HEADER_SIZE,
                                    "request_id": request_id, "status": response["status"]})
                if response["status"] != 0:
                    raise CopilotBridgeError(response["status"])
                if response["world_id"] != world_id:
                    raise AdminProtocolError("Copilot train parts response world ID mismatch")
                if response["company_id"] != company_id or response["after_vehicle_id"] != after_vehicle_id:
                    raise AdminProtocolError("Copilot train parts response selector mismatch")
                if response["count"] > max_records:
                    raise AdminProtocolError("Copilot train parts response exceeds requested record count")
                if response["next_after_id"] == after_vehicle_id:
                    if not response["complete"] or response["count"] != 0:
                        raise AdminProtocolError("Copilot train parts cursor did not advance")
                elif (after_vehicle_id != _COPILOT_INITIAL_VEHICLE_CURSOR and
                      response["next_after_id"] != _COPILOT_INITIAL_VEHICLE_CURSOR and
                      response["next_after_id"] < after_vehicle_id):
                    raise AdminProtocolError("Copilot train parts cursor moved backwards")
                elif response["next_after_id"] == _COPILOT_INITIAL_VEHICLE_CURSOR and response["count"] != 0:
                    raise AdminProtocolError("Copilot train parts page has records without an advanced cursor")
                previous = -1 if after_vehicle_id == _COPILOT_INITIAL_VEHICLE_CURSOR else after_vehicle_id
                for part in response["parts"]:
                    if part["vehicle_id"] <= previous or part["vehicle_id"] > response["next_after_id"]:
                        raise AdminProtocolError("Copilot train part IDs are outside cursor range")
                    if part["owner"] != company_id:
                        raise AdminProtocolError("Copilot train part owner does not match selector")
                    previous = part["vehicle_id"]
                return response
            if packet_type == _SERVER_GAMESCRIPT:
                message = self._decode_gamescript(response_payload, "received", len(response_payload) + _HEADER_SIZE)
                self._preserve_response(message)

    @staticmethod
    def _decode_copilot_train_parts(payload: bytes) -> dict[str, Any]:
        if len(payload) < 8:
            raise AdminProtocolError("truncated Copilot response header")
        version, request_kind, request_id, status = struct.unpack_from("<HBIB", payload)
        response: dict[str, Any] = {"version": version, "request_kind": request_kind,
                                    "request_id": request_id, "status": status}
        if version != COPILOT_PROTOCOL_VERSION:
            raise AdminProtocolError(f"unsupported Copilot response version {version}")
        if request_kind != _COPILOT_TRAIN_PARTS:
            raise AdminProtocolError(f"unexpected Copilot response kind {request_kind}")
        if status != 0:
            if len(payload) != 8:
                raise AdminProtocolError("Copilot error response has trailing data")
            return response
        position = 8
        world_id, position = AdminClient._decode_copilot_cstring(payload, position, "world ID")
        fixed_format = "<IBIBIB"
        fixed_size = struct.calcsize(fixed_format)
        if position + fixed_size > len(payload):
            raise AdminProtocolError("truncated Copilot train parts response")
        frame, company_id, after_vehicle_id, count, next_after_id, complete = struct.unpack_from(
            fixed_format, payload, position)
        position += fixed_size
        if count > _MAX_COPILOT_TRAIN_PART_COUNT or complete not in (0, 1):
            raise AdminProtocolError("invalid Copilot train parts page count or completion marker")
        record_format = "<IBIIIHHIBBIH"
        record_size = struct.calcsize(record_format)
        if position + count * record_size > len(payload):
            raise AdminProtocolError("truncated Copilot train part record")
        parts: list[dict[str, Any]] = []
        allowed_state = 0x0F
        for _ in range(count):
            (vehicle_id, owner, first_vehicle_id, previous_vehicle_id, next_vehicle_id,
             engine_id, unit_number, tile, state, cargo_type, cargo_amount, cargo_capacity) = struct.unpack_from(
                 record_format, payload, position)
            position += record_size
            if state & ~allowed_state:
                raise AdminProtocolError("unknown Copilot train part state bits")
            if state & 1 and vehicle_id != first_vehicle_id:
                raise AdminProtocolError("primary Copilot train part is not its chain root")
            if cargo_type != 0xFF and cargo_type >= 64:
                raise AdminProtocolError("invalid Copilot train part cargo type")
            parts.append({
                "vehicle_id": vehicle_id, "owner": owner, "first_vehicle_id": first_vehicle_id,
                "previous_vehicle_id": previous_vehicle_id, "next_vehicle_id": next_vehicle_id,
                "engine_id": engine_id, "unit_number": unit_number, "tile": tile,
                "is_primary": bool(state & 1), "stopped": bool(state & 2),
                "crashed": bool(state & 4), "in_depot": bool(state & 8),
                "cargo_type": cargo_type, "cargo_amount": cargo_amount,
                "cargo_capacity": cargo_capacity,
            })
        if position != len(payload):
            raise AdminProtocolError("Copilot train parts response has trailing data")
        response.update({"world_id": world_id, "frame": frame, "company_id": company_id,
                         "after_vehicle_id": after_vehicle_id, "count": count,
                         "next_after_id": next_after_id, "complete": bool(complete), "parts": parts})
        return response

    def _copilot_vehicle_events_request(
        self,
        request_id: int,
        payload: bytes,
        timeout: float | None,
        event_fields: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_connected()
        deadline = self._deadline(timeout)
        self._send_packet(_ADMIN_COPILOT, payload, deadline)
        sent_event = {
            "time": time.time(),
            "direction": "sent",
            "packet_type": "copilot_vehicle_events",
            "packet_length": len(payload) + _HEADER_SIZE,
            "request_id": request_id,
            "protocol_version": COPILOT_PROTOCOL_VERSION,
        }
        sent_event.update(event_fields)
        self.events.append(sent_event)
        while True:
            packet_type, response_payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(response_payload)
            if packet_type == _SERVER_COPILOT:
                response = self._decode_copilot_vehicle_events(response_payload)
                if response["request_id"] != request_id:
                    raise AdminProtocolError("Copilot response request ID mismatch")
                self.events.append(
                    {
                        "time": time.time(),
                        "direction": "received",
                        "packet_type": "copilot_vehicle_events",
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


    def _copilot_operation_request(
        self,
        request_kind: int,
        event_kind: str,
        request_id: int,
        payload: bytes,
        timeout: float | None,
        event_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_connected()
        deadline = self._deadline(timeout)
        self._send_packet(_ADMIN_COPILOT, payload, deadline)
        sent_event = {
            "time": time.time(),
            "direction": "sent",
            "packet_type": event_kind,
            "packet_length": len(payload) + _HEADER_SIZE,
            "request_id": request_id,
            "protocol_version": struct.unpack_from("<H", payload)[0],
        }
        if event_fields is not None:
            sent_event.update(event_fields)
        self.events.append(sent_event)
        while True:
            packet_type, response_payload = self._read_frame(deadline)
            if packet_type == _SERVER_ERROR:
                self._raise_server_error(response_payload)
            if packet_type == _SERVER_COPILOT:
                response = self._decode_copilot_operation(response_payload, request_kind)
                if response["request_id"] != request_id:
                    raise AdminProtocolError("Copilot response request ID mismatch")
                self.events.append(
                    {
                        "time": time.time(),
                        "direction": "received",
                        "packet_type": event_kind,
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
            # Pong and other bounded asynchronous Admin frames are harmless.

    @staticmethod
    def _check_uint(name: str, value: int, bits: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < (1 << bits):
            raise ValueError(f"{name} must be an unsigned {bits}-bit integer")
        return value

    @staticmethod
    def _check_int64(name: str, value: int) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not -(1 << 63) <= value < (1 << 63)
        ):
            raise ValueError(f"{name} must be a signed 64-bit integer")
        return value

    @classmethod
    def _check_copilot_request_header(cls, protocol_version: int, request_id: int | None) -> int:
        cls._check_uint("protocol_version", protocol_version, 16)
        if request_id is None:
            request_id = uuid.uuid4().int & 0xFFFFFFFF
        return cls._check_uint("request_id", request_id, 32)

    @classmethod
    def _copilot_world_id(cls, world_id: str) -> bytes:
        if not isinstance(world_id, str) or not world_id or "\x00" in world_id:
            raise ValueError("world_id must be non-empty text without NUL")
        return cls._cstring(world_id, _MAX_COPILOT_WORLD_ID_BYTES - 1)

    @staticmethod
    def _validate_copilot_operation_correlation(
        response: dict[str, Any], world_id: str, operation_hi: int, operation_lo: int
    ) -> None:
        if response["world_id"] != world_id:
            raise AdminProtocolError("Copilot operation response world ID mismatch")
        if (response["operation_hi"], response["operation_lo"]) != (operation_hi, operation_lo):
            raise AdminProtocolError("Copilot operation response operation ID mismatch")

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
        position = 8
        world_id, position = AdminClient._decode_copilot_cstring(
            payload, position, "world ID"
        )
        if position + 42 > len(payload):
            raise AdminProtocolError("truncated Copilot identity response")
        sequence, head_hi, head_lo, frame, seed, calendar_date, width, height, landscape, company_count = (
            struct.unpack_from("<QQQIIIHHBB", payload, position)
        )
        position += 42
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
                "world_id": world_id,
                "sequence": sequence,
                "head_hi": head_hi,
                "head_lo": head_lo,
                "head": None if (head_hi, head_lo) == (0, 0) else {"hi": head_hi, "lo": head_lo},
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

    @staticmethod
    def _decode_copilot_operation(payload: bytes, expected_kind: int) -> dict[str, Any]:
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
        if request_kind != expected_kind:
            raise AdminProtocolError(f"unexpected Copilot response kind {request_kind}")
        if status != 0:
            if len(payload) != 8:
                raise AdminProtocolError("Copilot error response has trailing data")
            return response

        position = 8
        world_id, position = AdminClient._decode_copilot_cstring(
            payload, position, "world ID"
        )
        operation_format = "<QQQBQQQQBIBBqqIIBBBBBBqq"
        operation_size = struct.calcsize(operation_format)
        if position + operation_size > len(payload):
            raise AdminProtocolError("truncated Copilot operation response")
        values = struct.unpack_from(operation_format, payload, position)
        position += operation_size
        if position != len(payload):
            raise AdminProtocolError("Copilot operation response has trailing data")
        (
            sequence,
            head_hi,
            head_lo,
            state,
            operation_hi,
            operation_lo,
            payload_hash_hi,
            payload_hash_lo,
            company_id,
            tile,
            rail_type,
            track,
            max_cost,
            actual_cost,
            error,
            frame,
            valid_tile,
            has_rail,
            owner,
            track_bits,
            readback_rail_type,
            company_valid,
            money,
            loan,
        ) = values
        if valid_tile not in (0, 1) or has_rail not in (0, 1) or company_valid not in (0, 1):
            raise AdminProtocolError("invalid Copilot operation boolean marker")
        response.update(
            {
                "world_id": world_id,
                "sequence": sequence,
                "head_hi": head_hi,
                "head_lo": head_lo,
                "head": None if (head_hi, head_lo) == (0, 0) else {"hi": head_hi, "lo": head_lo},
                "state": state,
                "state_name": _COPILOT_OPERATION_STATE_NAMES.get(state, "unknown"),
                "operation_hi": operation_hi,
                "operation_lo": operation_lo,
                "operation": {"hi": operation_hi, "lo": operation_lo},
                "payload_hash_hi": payload_hash_hi,
                "payload_hash_lo": payload_hash_lo,
                "payload_hash": {"hi": payload_hash_hi, "lo": payload_hash_lo},
                "company_id": company_id,
                "tile": tile,
                "rail_type": rail_type,
                "track": track,
                "max_cost": max_cost,
                "actual_cost": actual_cost,
                "error": error,
                "frame": frame,
                "valid_tile": bool(valid_tile),
                "has_rail": bool(has_rail),
                "owner": owner,
                "track_bits": track_bits,
                "readback_rail_type": readback_rail_type,
                "company_valid": bool(company_valid),
                "money": money,
                "loan": loan,
                "readback": {
                    "valid_tile": bool(valid_tile),
                    "has_rail": bool(has_rail),
                    "owner": owner,
                    "track_bits": track_bits,
                    "rail_type": readback_rail_type,
                    "company_valid": bool(company_valid),
                    "money": money,
                    "loan": loan,
                },
            }
        )
        return response

    @staticmethod
    def _decode_copilot_vehicle_events(payload: bytes) -> dict[str, Any]:
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
        if request_kind != _COPILOT_VEHICLE_EVENTS:
            raise AdminProtocolError(f"unexpected Copilot response kind {request_kind}")
        if status != 0:
            if len(payload) != 8:
                raise AdminProtocolError("Copilot error response has trailing data")
            return response

        position = 8
        world_id, position = AdminClient._decode_copilot_cstring(payload, position, "world ID")
        fixed_format = "<QQQIBB"
        fixed_size = struct.calcsize(fixed_format)
        if position + fixed_size > len(payload):
            raise AdminProtocolError("truncated Copilot vehicle events response")
        epoch, oldest_seq, next_seq, frame, gap, event_count = struct.unpack_from(
            fixed_format, payload, position
        )
        position += fixed_size
        if gap not in (0, 1):
            raise AdminProtocolError("invalid Copilot vehicle events gap marker")
        if event_count > _MAX_COPILOT_EVENTS:
            raise AdminProtocolError("Copilot vehicle events response exceeds event limit")
        if next_seq < oldest_seq:
            raise AdminProtocolError("invalid Copilot vehicle event sequence bounds")

        event_format = "<QBIIBHBIIH"
        event_size = struct.calcsize(event_format)
        if position + event_count * event_size > len(payload):
            raise AdminProtocolError("truncated Copilot vehicle event record")
        events: list[dict[str, Any]] = []
        kind_names = {1: "departure", 2: "delivery"}
        previous_seq = -1
        for _ in range(event_count):
            values = struct.unpack_from(event_format, payload, position)
            position += event_size
            seq, kind, event_frame, vehicle, company, station, cargo, amount, capacity, industry = values
            if kind not in kind_names:
                raise AdminProtocolError(f"unknown Copilot vehicle event kind {kind}")
            if not oldest_seq <= seq < next_seq or seq <= previous_seq:
                raise AdminProtocolError("Copilot vehicle events are outside bounds or unordered")
            previous_seq = seq
            events.append(
                {
                    "seq": seq,
                    "kind": kind_names[kind],
                    "frame": event_frame,
                    "vehicle": vehicle,
                    "company": company,
                    "station": station,
                    "cargo": cargo,
                    "amount": amount,
                    "capacity": capacity,
                    "industry": industry,
                }
            )
        if position != len(payload):
            raise AdminProtocolError("Copilot vehicle events response has trailing data")
        response.update(
            {
                "world_id": world_id,
                "epoch": epoch,
                "oldest_seq": oldest_seq,
                "next_seq": next_seq,
                "frame": frame,
                "gap": bool(gap),
                "events": events,
            }
        )
        return response

    @staticmethod
    def _decode_copilot_cstring(payload: bytes, position: int, label: str) -> tuple[str, int]:
        end = payload.find(b"\x00", position)
        if end < 0:
            raise AdminProtocolError(f"Copilot {label} lacks NUL terminator")
        if end == position:
            raise AdminProtocolError(f"Copilot {label} is empty")
        if end - position >= _MAX_COPILOT_WORLD_ID_BYTES:
            raise AdminProtocolError(f"Copilot {label} is too long")
        try:
            value = payload[position:end].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AdminProtocolError(f"Copilot {label} is not UTF-8") from exc
        return value, end + 1

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
