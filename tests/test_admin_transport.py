from __future__ import annotations

import json
import socket
import struct
import threading
import unittest
from unittest import mock

from tools.admin_transport import (
    ADMIN_PROTOCOL_VERSION,
    COPILOT_PROTOCOL_VERSION,
    AdminClient,
    AdminProtocolError,
    AdminServerError,
    AdminTransportError,
    CopilotBridgeError,
    MAX_GAMESCRIPT_JSON_BYTES,
    MAX_PENDING_RESPONSES,
)


def frame(packet_type: int, payload: bytes = b"") -> bytes:
    return struct.pack("<HB", len(payload) + 3, packet_type) + payload


def protocol_packet(version: int = ADMIN_PROTOCOL_VERSION) -> bytes:
    # The source sends one present/type/frequency tuple per update type,
    # followed by a false marker.
    payload = bytes([version]) + b"".join(
        b"\x01" + struct.pack("<HH", i, 1 << 6) for i in range(10)
    ) + b"\x00"
    return frame(103, payload)


def welcome_packet() -> bytes:
    payload = b"test server\x00r15.3\x00\x01\x00"
    payload += struct.pack("<IBIHH", 1234, 0, 0, 256, 256)
    return frame(104, payload)


def connected_client(timeout: float = 0.15) -> tuple[AdminClient, socket.socket]:
    client_sock, server_sock = socket.socketpair()
    client = AdminClient(3977, "secret", timeout)
    client._sock = client_sock
    client._connected = True
    return client, server_sock


def read_frame(sock: socket.socket) -> tuple[int, bytes]:
    header = _read_exact(sock, 2)
    size = struct.unpack("<H", header)[0]
    body = _read_exact(sock, size - 2)
    return body[0], body[1:]


def _read_exact(sock: socket.socket, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        result.extend(sock.recv(size - len(result)))
    return bytes(result)


def operation_response(
    request_kind: int,
    request_id: int,
    *,
    world_id: str = "world-123",
    operation_hi: int = 5,
    operation_lo: int = 6,
    valid_tile: int = 1,
    has_rail: int = 1,
    company_valid: int = 1,
) -> bytes:
    header = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, request_kind, request_id, 0)
    body = world_id.encode() + b"\0" + struct.pack(
        "<QQQBQQQQBIBBqqIIBBBBBBqq",
        9, 10, 11, 2, operation_hi, operation_lo, 7, 8,
        0, 321, 1, 2, 500, 90, 0, 456,
        valid_tile, has_rail, 0, 4, 1, company_valid, 10000, 100000,
    )
    return header + body


class AdminTransportTests(unittest.TestCase):
    def test_connect_legacy_join_layout_and_subscription_without_auth_event(self) -> None:
        client_sock, server_sock = socket.socketpair()
        with mock.patch("tools.admin_transport.socket.create_connection", return_value=client_sock):

            def server() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 0)
                self.assertEqual(
                    payload.split(b"\x00"),
                    [b"secret", b"OpenTTD Copilot", b"openttd-copilot/0.1", b""],
                )
                server_sock.sendall(protocol_packet() + welcome_packet())
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 2)
                self.assertEqual(payload, struct.pack("<HH", 9, 1 << 6))

            thread = threading.Thread(target=server)
            thread.start()
            client = AdminClient(3977, "secret", timeout=1)
            try:
                self.assertIs(client.connect(), client)
                thread.join(timeout=1)
                self.assertFalse(thread.is_alive())
                self.assertEqual(client.events, [])
            finally:
                client.close()
                server_sock.close()


    def test_send_request_is_compact_bounded_and_records_sanitized_event(self) -> None:
        client, server_sock = connected_client()
        try:
            rid = client.send_request({"cmd": "observe", "tiles": [1, 2], "note": "ok"})
            packet_type, payload = read_frame(server_sock)
            self.assertEqual(packet_type, 6)
            self.assertTrue(payload.endswith(b"\x00"))
            sent = json.loads(payload[:-1])
            self.assertEqual(sent, {"v": 1, "rid": rid, "cmd": "observe", "tiles": [1, 2], "note": "ok"})
            self.assertNotIn(b" ", payload)
            self.assertEqual(client.events[0]["direction"], "sent")
            self.assertEqual(client.events[0]["packet_length"], len(payload) + 3)
            self.assertNotIn("secret", repr(client.events))
        finally:
            client.close()
            server_sock.close()


    def test_request_rejects_nonfinite_and_nul_values(self) -> None:
        client, server_sock = connected_client()
        try:
            for bad in ({"cmd": "x", "value": float("nan")}, {"cmd": "x", "value": "a\x00b"}):
                with self.subTest(bad=bad):
                    with self.assertRaises((ValueError, TypeError)):
                        client.send_request(bad)
        finally:
            client.close()
            server_sock.close()


    def test_request_rejects_utf8_json_above_bound(self) -> None:
        client, server_sock = connected_client()
        try:
            with self.assertRaisesRegex(ValueError, "1449"):
                client.send_request({"cmd": "x", "value": "é" * MAX_GAMESCRIPT_JSON_BYTES})
        finally:
            client.close()
            server_sock.close()


    def test_receive_response_handles_coalescing_and_ignores_other_rid(self) -> None:
        client, server_sock = connected_client()
        try:
            client.send_request({"cmd": "x", "rid": "wanted"})
            read_frame(server_sock)
            other = {"v": 1, "rid": "other", "ok": True, "value": 1}
            wanted = {"v": 1, "rid": "wanted", "ok": True, "value": 2}
            server_sock.sendall(frame(124, json.dumps(other, separators=(",", ":")).encode() + b"\0"))
            server_sock.sendall(frame(124, json.dumps(wanted, separators=(",", ":")).encode() + b"\0"))
            self.assertEqual(client.receive_response("wanted"), wanted)
            self.assertEqual(client.receive_response("other"), other)
            self.assertEqual([event["direction"] for event in client.events], ["sent", "received", "received"])
        finally:
            client.close()
            server_sock.close()


    def test_partial_frame_timeout_retains_buffer(self) -> None:
        client, server_sock = connected_client(timeout=0.03)
        try:
            response = frame(124, b'{"v":1,"rid":"r","ok":true}\0')
            server_sock.sendall(response[:1])
            with self.assertRaises(TimeoutError):
                client.receive_response("r")
            server_sock.sendall(response[1:])
            self.assertTrue(client.receive_response("r", timeout=0.2)["ok"])
        finally:
            client.close()
            server_sock.close()

    def test_malformed_oversize_and_eof_are_rejected(self) -> None:
        client, server_sock = connected_client()
        try:
            server_sock.sendall(struct.pack("<H", 2))
            with self.assertRaises(AdminProtocolError):
                client.receive_response("r")
        finally:
            client.close()
            server_sock.close()

        client, server_sock = connected_client()
        try:
            server_sock.sendall(struct.pack("<H", 1461))
            with self.assertRaises(AdminProtocolError):
                client.receive_response("r")
        finally:
            client.close()
            server_sock.close()

        client, server_sock = connected_client()
        server_sock.close()
        with self.assertRaises(EOFError):
            client.receive_response("r")
        client.close()

    def test_ping_and_server_error(self) -> None:
        client, server_sock = connected_client()
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 7)
                self.assertEqual(struct.unpack("<I", payload)[0], 123)
                server_sock.sendall(frame(126, struct.pack("<I", 123)))

            thread = threading.Thread(target=reply)
            thread.start()
            self.assertEqual(client.ping(123), 123)
            thread.join(timeout=1)
        finally:
            client.close()
            server_sock.close()

        client, server_sock = connected_client()
        try:
            server_sock.sendall(frame(102, b"\x07"))
            with self.assertRaises(AdminServerError) as caught:
                client.receive_response("r")
            self.assertEqual(caught.exception.code, 7)
        finally:
            client.close()
            server_sock.close()

    def test_ping_preserves_game_script_response_for_later_rid(self) -> None:
        client, server_sock = connected_client()
        response = {"v": 1, "rid": "later", "ok": True, "value": 9}
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 7)
                self.assertEqual(struct.unpack("<I", payload)[0], 123)
                gs = frame(124, json.dumps(response, separators=(",", ":")).encode() + b"\0")
                server_sock.sendall(gs + frame(126, struct.pack("<I", 123)))

            thread = threading.Thread(target=reply)
            thread.start()
            self.assertEqual(client.ping(123), 123)
            self.assertEqual(client.receive_response("later"), response)
            thread.join(timeout=1)
        finally:
            client.close()
            server_sock.close()

    def test_failed_partial_send_poison_closes_socket_without_quit(self) -> None:
        client, server_sock = connected_client()
        failed_socket = mock.Mock()
        failed_socket.send.side_effect = [1, socket.timeout()]
        original_socket = client._sock
        assert original_socket is not None
        original_socket.close()
        client._sock = failed_socket
        client._connected = True
        try:
            with self.assertRaises(TimeoutError):
                client.send_request({"cmd": "mutate", "rid": "uncertain"})
            self.assertFalse(client.connected)
            failed_socket.close.assert_called_once_with()
            failed_socket.sendall.assert_not_called()
            with self.assertRaises(AdminTransportError):
                client.send_request({"cmd": "mutate", "rid": "retry"})
        finally:
            client.close()
            server_sock.close()

    def test_pending_response_overflow_is_explicit_and_does_not_evict(self) -> None:
        client, server_sock = connected_client()
        try:
            responses = [
                {"v": 1, "rid": f"r{i}", "ok": True, "value": i}
                for i in range(MAX_PENDING_RESPONSES + 1)
            ]
            server_sock.sendall(
                b"".join(frame(124, json.dumps(response, separators=(",", ":")).encode() + b"\0")
                       for response in responses)
            )
            with self.assertRaisesRegex(AdminTransportError, "pending Admin response limit"):
                client.receive_response("wanted", timeout=0.2)
            self.assertEqual(client.receive_response("r0"), responses[0])
        finally:
            client.close()
            server_sock.close()

    def test_connect_rejects_unknown_protocol_version(self) -> None:
        client_sock, server_sock = socket.socketpair()
        with mock.patch("tools.admin_transport.socket.create_connection", return_value=client_sock):
            server_sock.sendall(protocol_packet(version=2))
            client = AdminClient(3977, "secret", timeout=0.2)
            try:
                with self.assertRaisesRegex(AdminProtocolError, "version"):
                    client.connect()
            finally:
                client.close()
                server_sock.close()

    def test_copilot_identity_round_trip_is_typed_and_correlated(self) -> None:
        client, server_sock = connected_client(timeout=1)
        company = struct.pack("<BBqq", 0, 0, 987654, 100000) + b"Copper Transport\x00"
        response = (
            struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 0, 42, 0)
            + b"world-123\0"
            + struct.pack("<QQQIIIHHBB", 9, 10, 11, 123, 456, 789, 256, 512, 0, 1)
            + company
        )
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                self.assertEqual(payload, struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 0, 42, 255))
                server_sock.sendall(frame(130, response))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_identity(request_id=42)
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result["world_id"], "world-123")
            self.assertEqual(result["sequence"], 9)
            self.assertEqual(result["head"], {"hi": 10, "lo": 11})
            self.assertEqual(result["frame"], 123)
            self.assertEqual(result["seed"], 456)
            self.assertEqual(result["map_width"], 256)
            self.assertEqual(result["map_height"], 512)
            self.assertEqual(
                result["companies"],
                [{"id": 0, "is_ai": False, "money": 987654, "loan": 100000, "name": "Copper Transport"}],
            )
            self.assertEqual([event["packet_type"] for event in client.events], ["copilot_identity"] * 2)
        finally:
            client.close()
            server_sock.close()

    def test_copilot_identity_rejects_bridge_error_and_malformed_payload(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            server_sock.sendall(frame(130, struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 0, 7, 3)))
            with self.assertRaisesRegex(CopilotBridgeError, "company was not found"):
                client.copilot_identity(company_id=14, request_id=7)

            server_sock.sendall(frame(130, struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 0, 8, 0)))
            with self.assertRaisesRegex(AdminProtocolError, "world ID"):
                client.copilot_identity(request_id=8)
        finally:
            client.close()
            server_sock.close()

    def test_copilot_build_single_rail_round_trip_and_async_gamescript(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                fixed_size = struct.calcsize("<HBIBIBBqQQQQQQQ")
                values = struct.unpack_from("<HBIBIBBqQQQQQQQ", payload)
                self.assertEqual(
                    values,
                    (COPILOT_PROTOCOL_VERSION, 1, 42, 0, 321, 1, 2, 500, 3, 10, 11, 5, 6, 7, 8),
                )
                self.assertEqual(payload[fixed_size:], b"world-123\0")
                unrelated = b'{"v":1,"rid":"later","ok":true}\0'
                server_sock.sendall(frame(124, unrelated) + frame(126, struct.pack("<I", 99)))
                server_sock.sendall(frame(130, operation_response(1, 42)))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_build_single_rail(
                world_id="world-123", company_id=0, tile=321, rail_type=1, track=2,
                max_cost=500, expected_sequence=3, expected_head_hi=10,
                expected_head_lo=11, operation_hi=5, operation_lo=6,
                payload_hash_hi=7, payload_hash_lo=8, request_id=42,
            )
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result["state_name"], "completed")
            self.assertEqual(result["operation"], {"hi": 5, "lo": 6})
            self.assertEqual(result["payload_hash"], {"hi": 7, "lo": 8})
            self.assertEqual(result["actual_cost"], 90)
            self.assertEqual(
                result["readback"],
                {"valid_tile": True, "has_rail": True, "owner": 0, "track_bits": 4,
                 "rail_type": 1, "company_valid": True, "money": 10000, "loan": 100000},
            )
            self.assertTrue(client.receive_response("later")["ok"])
        finally:
            client.close()
            server_sock.close()

    def test_copilot_operation_status_layout_and_status_messages(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                self.assertEqual(
                    payload,
                    struct.pack("<HBIQQ", COPILOT_PROTOCOL_VERSION, 2, 77, 5, 6) + b"world-123\0",
                )
                server_sock.sendall(frame(130, operation_response(2, 77)))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_operation_status(
                world_id="world-123", operation_hi=5, operation_lo=6, request_id=77
            )
            thread.join(timeout=1)
            self.assertEqual(result["sequence"], 9)
            self.assertEqual(result["head_hi"], 10)
        finally:
            client.close()
            server_sock.close()

        messages = {
            5: "world identity mismatch",
            6: "not human-owned",
            7: "invalid Copilot argument",
            8: "identity conflict",
            9: "journal is busy",
            10: "was not found",
            11: "stale Copilot world journal position",
        }
        for status, message in messages.items():
            client, server_sock = connected_client(timeout=1)
            try:
                server_sock.sendall(frame(130, struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 2, status, status)))
                with self.assertRaisesRegex(CopilotBridgeError, message):
                    client.copilot_operation_status(
                        world_id="world-123", operation_hi=5, operation_lo=6,
                        request_id=status,
                    )
            finally:
                client.close()
                server_sock.close()

    def test_copilot_operation_validation_and_malformed_boolean(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            valid = dict(
                world_id="world-123", company_id=0, tile=1, rail_type=0, track=0,
                max_cost=0, expected_sequence=0, expected_head_hi=0, expected_head_lo=0,
                operation_hi=5, operation_lo=6, payload_hash_hi=7, payload_hash_lo=8,
            )
            for field, bad in (("company_id", 256), ("tile", -1), ("max_cost", 1 << 63),
                               ("operation_hi", True), ("world_id", "bad\0world")):
                with self.subTest(field=field):
                    args = dict(valid)
                    args[field] = bad
                    with self.assertRaises((TypeError, ValueError)):
                        client.copilot_build_single_rail(**args)

            with self.assertRaisesRegex(ValueError, "too long"):
                client.copilot_operation_status(
                    world_id="w" * 65, operation_hi=5, operation_lo=6
                )

            server_sock.sendall(frame(130, operation_response(2, 88, valid_tile=2)))
            with self.assertRaisesRegex(AdminProtocolError, "boolean"):
                client.copilot_operation_status(
                    world_id="world-123", operation_hi=5, operation_lo=6, request_id=88
                )
        finally:
            client.close()
            server_sock.close()

    def test_copilot_vehicle_events_round_trip(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                fixed = struct.unpack_from("<HBIBIQ", payload)
                self.assertEqual(
                    fixed,
                    (COPILOT_PROTOCOL_VERSION, 3, 42, 0, 77, 12),
                )
                self.assertEqual(payload[struct.calcsize("<HBIBIQ"):], b"world-123\0")
                response = struct.pack(
                    "<HBIB", COPILOT_PROTOCOL_VERSION, 3, 42, 0
                ) + b"world-123\0"
                response += struct.pack("<QQQIBB", 1001, 4, 9, 321, 0, 2)
                response += struct.pack(
                    "<QBIIBHBIIH", 4, 1, 200, 77, 0, 12, 2, 500, 80, 33
                )
                response += struct.pack(
                    "<QBIIBHBIIH", 8, 2, 320, 77, 0, 45, 1, 80, 80, 33
                )
                server_sock.sendall(frame(130, response))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_vehicle_events(
                world_id="world-123", company_id=0, vehicle_id=77,
                cursor=12, epoch=1000, request_id=42,
            )
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(
                {key: result[key] for key in ("epoch", "oldest_seq", "next_seq", "frame", "gap")},
                {"epoch": 1001, "oldest_seq": 4, "next_seq": 9, "frame": 321, "gap": False},
            )
            self.assertEqual(
                result["events"],
                [
                    {"seq": 4, "kind": "departure", "frame": 200, "vehicle": 77,
                     "company": 0, "station": 12, "cargo": 2, "amount": 500,
                     "capacity": 80, "industry": 33},
                    {"seq": 8, "kind": "delivery", "frame": 320, "vehicle": 77,
                     "company": 0, "station": 45, "cargo": 1, "amount": 80,
                     "capacity": 80, "industry": 33},
                ],
            )
        finally:
            client.close()
            server_sock.close()

    def test_copilot_vehicle_events_rejects_bad_count_kind_gap_and_trailing_data(self) -> None:
        cases = [
            (struct.pack("<QQQIBB", 1, 0, 1, 10, 0, 17), b"", "event limit"),
            (struct.pack("<QQQIBB", 1, 0, 1, 10, 2, 0), b"", "gap marker"),
            (struct.pack("<QQQIBB", 1, 0, 1, 10, 0, 1)
             + struct.pack("<QBIIBHBIIH", 1, 99, 10, 77, 0, 1, 1, 1, 1, 1), b"", "event kind"),
            (struct.pack("<QQQIBB", 1, 0, 1, 10, 0, 0), b"x", "trailing data"),
        ]
        for fixed, suffix, message in cases:
            client, server_sock = connected_client(timeout=1)
            try:
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 3, 9, 0)
                response += b"world-123\0" + fixed + suffix
                server_sock.sendall(frame(130, response))
                with self.subTest(message=message), self.assertRaisesRegex(AdminProtocolError, message):
                    client.copilot_vehicle_events(
                        world_id="world-123", company_id=0, vehicle_id=77, request_id=9
                    )
            finally:
                client.close()
                server_sock.close()

    def test_copilot_tile_snapshot_round_trip_is_bounded_and_correlated(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                self.assertEqual(
                    struct.unpack_from("<HBIIB", payload),
                    (COPILOT_PROTOCOL_VERSION, 4, 42, 1000, 2),
                )
                self.assertEqual(payload[struct.calcsize("<HBIIB"):], b"world-123\0")
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 4, 42, 0)
                response += b"world-123\0" + struct.pack("<IIB", 321, 1000, 2)
                response += struct.pack("<IBBBBBBB", 1000, 1, 4, 0, 2, 7, 16, 1)
                response += struct.pack("<IBBBBBBB", 1001, 0, 0, 255, 0, 0, 0, 255)
                server_sock.sendall(frame(130, response))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_tile_snapshot(
                world_id="world-123", start_tile=1000, count=2, request_id=42
            )
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(
                {key: result[key] for key in ("world_id", "frame", "start_tile", "count")},
                {"world_id": "world-123", "frame": 321, "start_tile": 1000, "count": 2},
            )
            self.assertEqual(
                result["tiles"],
                [
                    {"tile": 1000, "valid": True, "tile_type": 4, "owner": 0,
                     "slope": 2, "height": 7, "track_bits": 16, "rail_type": 1},
                    {"tile": 1001, "valid": False, "tile_type": 0, "owner": 255,
                     "slope": 0, "height": 0, "track_bits": 0, "rail_type": 255},
                ],
            )
        finally:
            client.close()
            server_sock.close()

    def test_copilot_tile_snapshot_rejects_invalid_bounds_and_response(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            for count in (0, 33, True):
                with self.subTest(count=count), self.assertRaises(ValueError):
                    client.copilot_tile_snapshot("world-123", 1, count)
        finally:
            client.close()
            server_sock.close()

        cases = [
            (struct.pack("<IIB", 10, 1, 0), b"", "tile limit"),
            (struct.pack("<IIB", 10, 1, 1) + struct.pack("<IBBBBBBB", 1, 2, 0, 0, 0, 0, 0, 0), b"", "validity marker"),
            (struct.pack("<IIB", 10, 1, 1) + b"x", b"", "truncated"),
            (struct.pack("<IIB", 10, 1, 1) + struct.pack("<IBBBBBBB", 1, 1, 0, 0, 0, 0, 0, 0), b"x", "trailing data"),
            (struct.pack("<IIB", 10, 1, 1) + struct.pack("<IBBBBBBB", 11, 1, 0, 0, 0, 0, 0, 0), b"", "tile sequence"),
        ]
        for fixed, suffix, message in cases:
            client, server_sock = connected_client(timeout=1)
            try:
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 4, 7, 0)
                response += b"world-123\0" + fixed + suffix
                server_sock.sendall(frame(130, response))
                with self.subTest(message=message), self.assertRaisesRegex(AdminProtocolError, message):
                    client.copilot_tile_snapshot("world-123", 1, 1, request_id=7)
            finally:
                client.close()
                server_sock.close()


if __name__ == "__main__":
    unittest.main()
