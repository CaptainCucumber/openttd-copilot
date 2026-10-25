"""Bounded JSON transport for the native passenger-bus bridge."""

from __future__ import annotations

import json
import math
import struct
import time
from typing import Any

import admin_transport as transport


_REQUEST_KIND = 18
_MAX_JSON_BYTES = 1400


def _uint(name: str, value: Any, bits: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 1 << bits:
        raise ValueError(f"{name} must be an unsigned {bits}-bit integer")
    return value


class BusBridge:
    """Authenticated, versioned access to bounded native bus observations/actions."""

    def __init__(self, admin: transport.AdminClient, timeout: float = 10.0) -> None:
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be a finite non-negative number")
        self.admin = admin
        self.timeout = float(timeout)
        if not math.isfinite(self.timeout) or self.timeout < 0:
            raise ValueError("timeout must be a finite non-negative number")

    def request(self, action: str, *, timeout: float | None = None, **kwargs: Any) -> dict[str, Any]:
        if not isinstance(action, str) or not action or "\x00" in action:
            raise ValueError("action must be a non-empty string without NUL")
        body = {"action": action, "company_id": 0, **kwargs}
        encoded = json.dumps(body, separators=(",", ":"), sort_keys=True, allow_nan=False).encode()
        if len(encoded) > _MAX_JSON_BYTES or b"\x00" in encoded:
            raise ValueError("bus request JSON exceeds the bounded packet payload")
        request_id = self.admin._check_copilot_request_header(  # noqa: SLF001
            transport.COPILOT_PROTOCOL_VERSION, None
        )
        payload = struct.pack(
            "<HBI", transport.COPILOT_PROTOCOL_VERSION, _REQUEST_KIND, request_id
        ) + encoded + b"\0"
        self.admin._require_connected()  # noqa: SLF001
        deadline = self.admin._deadline(self.timeout if timeout is None else timeout)  # noqa: SLF001
        self.admin._send_packet(transport._ADMIN_COPILOT, payload, deadline)  # noqa: SLF001
        while True:
            packet_type, response = self.admin._read_frame(deadline)  # noqa: SLF001
            if packet_type == transport._SERVER_ERROR:
                self.admin._raise_server_error(response)  # noqa: SLF001
            if packet_type == transport._SERVER_GAMESCRIPT:
                message = self.admin._decode_gamescript(  # noqa: SLF001
                    response, "received", len(response) + transport._HEADER_SIZE
                )
                self.admin._preserve_response(message)  # noqa: SLF001
                continue
            if packet_type != transport._SERVER_COPILOT:
                continue
            result = self._decode(response)
            if result["request_id"] != request_id:
                raise transport.AdminProtocolError("Copilot bus response request ID mismatch")
            if result["status"]:
                raise transport.CopilotBridgeError(result["status"])
            world = kwargs.get("world_id")
            if world is not None and result["world_id"] != world:
                raise transport.AdminProtocolError("Copilot bus response world ID mismatch")
            return result["body"]

    @staticmethod
    def _decode(payload: bytes) -> dict[str, Any]:
        if len(payload) < 8:
            raise transport.AdminProtocolError("truncated Copilot bus response header")
        version, kind, request_id, status = struct.unpack_from("<HBIB", payload)
        if version != transport.COPILOT_PROTOCOL_VERSION or kind != _REQUEST_KIND:
            raise transport.AdminProtocolError("unexpected Copilot bus response version or kind")
        result = {"request_id": request_id, "status": status}
        if status:
            if len(payload) != 8:
                raise transport.AdminProtocolError("Copilot bus error response has trailing data")
            return result
        position = 8
        world, position = transport.AdminClient._decode_copilot_cstring(  # noqa: SLF001
            payload, position, "bus world ID"
        )
        raw, position = transport.AdminClient._decode_copilot_cstring(  # noqa: SLF001
            payload, position, "bus JSON", _MAX_JSON_BYTES + 1
        )
        if position != len(payload):
            raise transport.AdminProtocolError("Copilot bus response has trailing data")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise transport.AdminProtocolError("invalid Copilot bus response JSON") from exc
        if not isinstance(body, dict) or body.get("world_id") != world:
            raise transport.AdminProtocolError("invalid Copilot bus response body")
        return {**result, "world_id": world, "body": body}

    def towns(self, world_id: str, start: int = 0, count: int = 8) -> dict[str, Any]:
        return self.request("towns", world_id=world_id, start=_uint("start", start, 32),
                            count=_uint("count", count, 8))

    def tiles(self, world_id: str, start_tile: int, count: int = 8) -> dict[str, Any]:
        if count > 8:
            raise ValueError("count must not exceed 8 for bounded JSON tile pages")
        return self.request("tiles", world_id=world_id, start_tile=_uint("start_tile", start_tile, 32),
                            count=_uint("count", count, 8))

    def catalog(self, world_id: str, start: int = 0, count: int = 8) -> dict[str, Any]:
        return self.request("catalog", world_id=world_id, start=_uint("start", start, 32),
                            count=_uint("count", count, 8))

    def assets(self, world_id: str, kind: str = "vehicles", start: int = 0,
               count: int = 8) -> dict[str, Any]:
        if kind not in ("vehicles", "stops", "depots"):
            raise ValueError("kind must be vehicles, stops, or depots")
        return self.request("assets", world_id=world_id, kind=kind,
                            start=_uint("start", start, 32), count=_uint("count", count, 8))

    def orders(self, world_id: str, vehicle_id: int) -> dict[str, Any]:
        return self.request("orders", world_id=world_id,
                            vehicle_id=_uint("vehicle_id", vehicle_id, 32))

    def quote(self, world_id: str, kind: int, tile: int = 0, *, orientation: int = 0,
              road_bits: int = 0, town_id: int = 0xFFFF,
              engine_id: int = 0xFFFF) -> dict[str, Any]:
        return self.request("quote", world_id=world_id, kind=_uint("kind", kind, 8),
                            tile=_uint("tile", tile, 32), orientation=_uint("orientation", orientation, 8),
                            road_bits=_uint("road_bits", road_bits, 8),
                            town_id=_uint("town_id", town_id, 16),
                            engine_id=_uint("engine_id", engine_id, 16))

    def mutate(self, world_id: str, kind: int, tile: int, max_cost: int,
               expected_sequence: int, expected_head_hi: int, expected_head_lo: int,
               operation_hi: int, operation_lo: int, payload_hash_hi: int,
               payload_hash_lo: int, *, orientation: int = 0, road_bits: int = 0,
               engine_id: int = 0xFFFF, vehicle_id: int = 0xFFFFFFFF,
               target_id: int = 0xFFFFFFFF, order_index: int = 0, policy: int = 0,
               company_id: int = 0,
               timeout: float | None = None) -> dict[str, Any]:
        if _uint("company_id", company_id, 8) != 0:
            raise ValueError("company_id must be 0 for the bounded bus bridge")
        fields = {
            "world_id": world_id, "kind": _uint("kind", kind, 8), "tile": _uint("tile", tile, 32),
            "max_cost": _uint("max_cost", max_cost, 63),
            "expected_sequence": _uint("expected_sequence", expected_sequence, 64),
            "expected_head_hi": _uint("expected_head_hi", expected_head_hi, 64),
            "expected_head_lo": _uint("expected_head_lo", expected_head_lo, 64),
            "operation_hi": _uint("operation_hi", operation_hi, 64),
            "operation_lo": _uint("operation_lo", operation_lo, 64),
            "payload_hash_hi": _uint("payload_hash_hi", payload_hash_hi, 64),
            "payload_hash_lo": _uint("payload_hash_lo", payload_hash_lo, 64),
            "orientation": _uint("orientation", orientation, 8),
            "road_bits": _uint("road_bits", road_bits, 8),
            "engine_id": _uint("engine_id", engine_id, 16),
            "vehicle_id": _uint("vehicle_id", vehicle_id, 32),
            "target_id": _uint("target_id", target_id, 32),
            "order_index": _uint("order_index", order_index, 16),
            "policy": _uint("policy", policy, 8),
        }
        return self.request("mutate", timeout=timeout, **fields)

    def operation(self, world_id: str, operation_hi: int, operation_lo: int,
                  *, timeout: float | None = None) -> dict[str, Any]:
        return self.request("operation", timeout=timeout, world_id=world_id,
                            operation_hi=_uint("operation_hi", operation_hi, 64),
                            operation_lo=_uint("operation_lo", operation_lo, 64))
