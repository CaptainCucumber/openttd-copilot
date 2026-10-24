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
    state: int = 2,
    valid_tile: int = 1,
    has_rail: int = 1,
    track: int = 2,
    rail_type: int = 1,
    company_valid: int = 1,
) -> bytes:
    header = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, request_kind, request_id, 0)
    body = world_id.encode() + b"\0" + struct.pack(
        "<QQQBQQQQBIBBqqIIBBBBBBqq",
        9, 10, 11, state, operation_hi, operation_lo, 7, 8,
        0, 321, rail_type, track, 500, 90, 0, 456,
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

    def test_copilot_build_infrastructure_serializes_kind_and_length(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            response = operation_response(11, 77, track=0) + struct.pack("<BBI", 1, 2, 123)

            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                values = struct.unpack_from("<HBIBIBBBBqQQQQQQQ", payload)
                self.assertEqual(values[1], 11)
                self.assertEqual(values[3:9], (0, 8254, 0, 0, 1, 2))
                self.assertEqual(
                    payload,
                    struct.pack("<HBIBIBBBBqQQQQQQQ", COPILOT_PROTOCOL_VERSION, 11, 77,
                                0, 8254, 0, 0, 1, 2, 1000, 9, 10, 11, 5, 6, 7, 8)
                    + b"world-123\0",
                )
                server_sock.sendall(frame(130, response))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_build_infrastructure(
                world_id="world-123", company_id=0, tile=8254, rail_type=0,
                orientation=0, infrastructure_kind=1, length=2, max_cost=1000,
                expected_sequence=9, expected_head_hi=10, expected_head_lo=11,
                operation_hi=5, operation_lo=6, payload_hash_hi=7, payload_hash_lo=8,
                request_id=77,
            )
            thread.join(timeout=1)
            self.assertEqual(result["created_asset_id"], 123)
            self.assertEqual(result["infrastructure_kind"], 1)
            self.assertEqual(result["length"], 2)
        finally:
            client.close()
            server_sock.close()

    def test_infrastructure_input_and_extension_are_strict(self) -> None:
        client, server_sock = connected_client()
        try:
            kwargs = dict(
                world_id="world", company_id=0, tile=1, rail_type=0, orientation=0,
                infrastructure_kind=2, length=2, max_cost=1, expected_sequence=0,
                expected_head_hi=0, expected_head_lo=0, operation_hi=1, operation_lo=2,
                payload_hash_hi=3, payload_hash_lo=4,
            )
            with self.assertRaisesRegex(ValueError, "depot length"):
                client.copilot_build_infrastructure(**kwargs)
        finally:
            client.close()
            server_sock.close()
        malformed = operation_response(11, 1)
        with self.assertRaises(AdminProtocolError):
            AdminClient._decode_copilot_operation(malformed, 11)

    def test_copilot_build_train_serializes_frozen_purchase_request(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            response = operation_response(13, 77, track=0, rail_type=255)
            response += struct.pack("<BBIH", 3, 0, 0x12345678, 42)

            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                self.assertEqual(
                    payload,
                    struct.pack(
                        "<HBIBIHqQQQQQQQ", COPILOT_PROTOCOL_VERSION, 13, 77,
                        0, 8254, 42, 100000, 2, 3, 4, 5, 6, 7, 8,
                    ) + b"world-123\0",
                )
                server_sock.sendall(frame(130, response))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_build_train(
                world_id="world-123", company_id=0, depot_tile=8254, engine_id=42,
                max_cost=100000, expected_sequence=2, expected_head_hi=3,
                expected_head_lo=4, operation_hi=5, operation_lo=6,
                payload_hash_hi=7, payload_hash_lo=8, request_id=77,
            )
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result["infrastructure_kind"], 3)
            self.assertEqual(result["engine_id"], 42)
            self.assertEqual(result["created_asset_id"], 0x12345678)
        finally:
            client.close()
            server_sock.close()

    def test_train_purchase_status_accepts_old_infrastructure_records(self) -> None:
        base = operation_response(14, 1, track=0)
        station = AdminClient._decode_copilot_operation(
            base + struct.pack("<BBIH", 1, 2, 19, 0xFFFF), 14
        )
        self.assertEqual(
            (station["infrastructure_kind"], station["length"],
             station["created_asset_id"], station["engine_id"]),
            (1, 2, 19, 0xFFFF),
        )
        purchase = operation_response(14, 1, track=0, rail_type=255) + struct.pack("<BBIH", 3, 0, 19, 42)
        result = AdminClient._decode_copilot_operation(purchase, 14)
        self.assertEqual(
            (result["infrastructure_kind"], result["created_asset_id"], result["engine_id"]),
            (3, 19, 42),
        )

    def test_train_purchase_decoder_rejects_invalid_sentinels_and_geometry(self) -> None:
        base = operation_response(13, 1, track=0, rail_type=255)
        valid = base + struct.pack("<BBIH", 3, 0, 19, 42)
        invalid = [
            valid[:-1], valid + b"\0",
            base + struct.pack("<BBIH", 3, 1, 19, 42),
            base + struct.pack("<BBIH", 3, 0, 0xFFFFFFFF, 42),
            base + struct.pack("<BBIH", 3, 0, 19, 0xFFFF),
            base + struct.pack("<BBIH", 4, 0, 19, 42),
            operation_response(13, 1, state=3, track=0, rail_type=255)
            + struct.pack("<BBIH", 3, 0, 19, 42),
            operation_response(13, 1, track=1, rail_type=255) + struct.pack("<BBIH", 3, 0, 19, 42),
            operation_response(13, 1, track=0, rail_type=1) + struct.pack("<BBIH", 3, 0, 19, 42),
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(AdminProtocolError):
                    AdminClient._decode_copilot_operation(payload, 13)

    def test_train_status_preserves_legacy_validation_and_historical_fields(self) -> None:
        for kind, length, track, asset_id in ((0, 0, 2, 0xFFFFFFFF), (1, 2, 1, 7), (2, 1, 3, 8)):
            payload = operation_response(14, 1, track=track) + struct.pack("<BBIH", kind, length, asset_id, 0xFFFF)
            result = AdminClient._decode_copilot_operation(payload, 14)
            self.assertEqual(result["engine_id"], 0xFFFF)
            self.assertNotIn("engine_id", result["readback"])
            self.assertNotIn("created_asset_id", result["readback"])
        for kind, length, track in ((1, 2, 2), (2, 1, 4)):
            payload = operation_response(14, 1, track=track) + struct.pack("<BBIH", kind, length, 7, 0xFFFF)
            with self.assertRaises(AdminProtocolError):
                AdminClient._decode_copilot_operation(payload, 14)
        rejected = operation_response(14, 1, state=3, track=0, rail_type=255)
        result = AdminClient._decode_copilot_operation(
            rejected + struct.pack("<BBIH", 3, 0, 0xFFFFFFFF, 42), 14)
        self.assertEqual(result["state_name"], "rejected")

    def test_train_status_serializes_and_rejects_wrong_world(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                self.assertEqual(payload, struct.pack("<HBIQQ", COPILOT_PROTOCOL_VERSION, 14, 77, 5, 6)
                                 + b"world-123\0")
                response = operation_response(14, 77, world_id="other-world", track=0, rail_type=255)
                server_sock.sendall(frame(130, response + struct.pack("<BBIH", 3, 0, 19, 42)))

            thread = threading.Thread(target=reply)
            thread.start()
            with self.assertRaisesRegex(AdminProtocolError, "world ID mismatch"):
                client.copilot_train_purchase_status(
                    world_id="world-123", operation_hi=5, operation_lo=6, request_id=77)
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
        finally:
            client.close()
            server_sock.close()

    def test_train_purchase_input_rejects_invalid_engine_sentinel(self) -> None:
        client, server_sock = connected_client()
        try:
            with self.assertRaisesRegex(ValueError, "engine_id"):
                client.copilot_build_train(
                    world_id="world", company_id=0, depot_tile=1, engine_id=0xFFFF,
                    max_cost=1, expected_sequence=0, expected_head_hi=0,
                    expected_head_lo=0, operation_hi=1, operation_lo=2,
                    payload_hash_hi=3, payload_hash_lo=4,
                )
        finally:
            client.close()
            server_sock.close()

    def test_status12_accepts_rail_extension_without_readback_identity(self) -> None:
        payload = operation_response(12, 1, track=2) + struct.pack("<BBI", 0, 0, 0xFFFFFFFF)
        result = AdminClient._decode_copilot_operation(payload, 12)
        self.assertEqual(
            (result["infrastructure_kind"], result["length"], result["created_asset_id"]),
            (0, 0, 0xFFFFFFFF),
        )
        self.assertNotIn("infrastructure_kind", result["readback"])
        self.assertNotIn("created_asset_id", result["readback"])

    def test_infrastructure_extension_rejects_bad_shape_kind_id_and_orientation(self) -> None:
        valid = operation_response(11, 1, track=0) + struct.pack("<BBI", 1, 2, 9)
        cases = [
            valid[:-1], valid + b"\x00",
            operation_response(11, 1, track=0) + struct.pack("<BBI", 3, 2, 9),
            operation_response(11, 1, track=0) + struct.pack("<BBI", 1, 0, 9),
            operation_response(11, 1, track=0) + struct.pack("<BBI", 1, 2, 0xFFFFFFFF),
            operation_response(11, 1, track=2) + struct.pack("<BBI", 1, 2, 9),
            operation_response(11, 1, track=0) + struct.pack("<BBI", 0, 0, 9),
            operation_response(11, 1, track=0) + struct.pack("<BBI", 0, 0, 0xFFFFFFFF),
            operation_response(11, 1, track=4) + struct.pack("<BBI", 2, 1, 9),
            operation_response(11, 1, state=1, track=0) + struct.pack("<BBI", 1, 2, 9),
            operation_response(11, 1, state=9, track=0) + struct.pack("<BBI", 1, 2, 9),
        ]
        for payload in cases:
            with self.subTest(length=len(payload)):
                with self.assertRaises(AdminProtocolError):
                    AdminClient._decode_copilot_operation(payload, 11)

    def test_infrastructure_status_request_is_byte_exact_and_correlated(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                self.assertEqual(
                    payload,
                    struct.pack("<HBIQQ", COPILOT_PROTOCOL_VERSION, 12, 77, 5, 6)
                    + b"world-123\0",
                )
                server_sock.sendall(frame(
                    130, operation_response(12, 77, operation_hi=5, operation_lo=6, track=2)
                    + struct.pack("<BBI", 0, 0, 0xFFFFFFFF)
                ))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_infrastructure_status(
                world_id="world-123", operation_hi=5, operation_lo=6, request_id=77,
            )
            thread.join(timeout=1)
            self.assertEqual(result["request_kind"], 12)
            self.assertEqual(result["operation"], {"hi": 5, "lo": 6})
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
            12: "journal is full",
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

    def test_copilot_industry_snapshot_round_trip_decodes_cargo_and_page(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                self.assertEqual(
                    struct.unpack_from("<HBIIB", payload),
                    (COPILOT_PROTOCOL_VERSION, 5, 43, 2, 16),
                )
                self.assertEqual(payload[struct.calcsize("<HBIIB"):], b"world-123\0")
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 5, 43, 0)
                response += b"world-123\0" + struct.pack("<IIB", 456, 2, 1)
                response += struct.pack("<HBI", 77, 4, 1024) + bytes([2, 0, 3, 2, 1, 2])
                server_sock.sendall(frame(130, response))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_industry_snapshot("world-123", 2, 16, request_id=43)
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(
                {key: result[key] for key in ("world_id", "frame", "start_index", "count")},
                {"world_id": "world-123", "frame": 456, "start_index": 2, "count": 1},
            )
            self.assertEqual(result["industries"], [{
                "industry_id": 77, "industry_type": 4, "tile": 1024,
                "produced_cargo": [0, 3], "accepted_cargo": [1, 2],
            }])
        finally:
            client.close()
            server_sock.close()

    def test_copilot_industry_snapshot_rejects_invalid_bounds_and_records(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            for count in (0, 17, True):
                with self.subTest(count=count), self.assertRaises(ValueError):
                    client.copilot_industry_snapshot("world-123", 0, count)
        finally:
            client.close()
            server_sock.close()

        cases = [
            (struct.pack("<IIB", 10, 0, 17), b"", "industry limit"),
            (struct.pack("<IIB", 10, 0, 1) + b"\x01", b"", "truncated Copilot industry snapshot record"),
            (struct.pack("<IIB", 10, 0, 1) + struct.pack("<HBI", 1, 2, 3) + bytes([17]), b"", "produced cargo list"),
            (struct.pack("<IIB", 10, 0, 1) + struct.pack("<HBI", 1, 2, 3) + bytes([1, 255, 0]), b"", "invalid cargo type"),
            (struct.pack("<IIB", 10, 0, 0), b"x", "trailing data"),
        ]
        for fixed, suffix, message in cases:
            client, server_sock = connected_client(timeout=1)
            try:
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 5, 44, 0)
                response += b"world-123\0" + fixed + suffix
                server_sock.sendall(frame(130, response))
                with self.subTest(message=message), self.assertRaisesRegex(AdminProtocolError, message):
                    client.copilot_industry_snapshot("world-123", 0, 1, request_id=44)
            finally:
                client.close()
                server_sock.close()

    def test_copilot_industry_details_round_trip_name_bounds_and_cargo(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                self.assertEqual(struct.unpack_from("<HBIIB", payload),
                                 (COPILOT_PROTOCOL_VERSION, 10, 54, 3, 8))
                self.assertEqual(payload[struct.calcsize("<HBIIB"):], b"world-123\0")
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 10, 54, 0)
                response += b"world-123\0" + struct.pack("<IIB", 789, 3, 1)
                response += struct.pack("<HBIHH", 77, 4, 1024, 3, 2)
                response += "Coal Mine — North".encode("utf-8") + b"\0"
                response += bytes([0, 1, 0, 2, 1, 2])
                server_sock.sendall(frame(130, response))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_industry_details("world-123", 3, request_id=54)
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual((result["world_id"], result["frame"], result["start_index"],
                              result["count"]), ("world-123", 789, 3, 1))
            self.assertEqual(result["industries"], [{
                "industry_id": 77, "industry_type": 4, "tile": 1024,
                "location_width": 3, "location_height": 2,
                "name": "Coal Mine — North", "name_truncated": False,
                "produced_cargo": [0], "accepted_cargo": [1, 2],
            }])
        finally:
            client.close()
            server_sock.close()

    def test_copilot_industry_details_accepts_explicit_truncation(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 10, 55, 0)
            response += b"world-123\0" + struct.pack("<IIB", 790, 0, 1)
            response += struct.pack("<HBIHH", 1, 2, 3, 2, 1)
            response += b"A" * 96 + b"\0" + bytes([1, 0, 0])
            server_sock.sendall(frame(130, response))
            result = client.copilot_industry_details("world-123", 0, 1, request_id=55)
            self.assertEqual(result["industries"][0]["name"], "A" * 96)
            self.assertTrue(result["industries"][0]["name_truncated"])
        finally:
            client.close()
            server_sock.close()

    def test_copilot_industry_details_rejects_bad_bounds_and_records(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            for count in (0, 9, True):
                with self.subTest(count=count), self.assertRaises(ValueError):
                    client.copilot_industry_details("world-123", 0, count)
        finally:
            client.close()
            server_sock.close()

        fixed = struct.pack("<HBIHH", 1, 2, 3, 2, 1)
        valid_suffix = bytes([0, 0, 0])
        invalid = [
            (b"", b"", "truncated Copilot industry detail record"),
            (fixed + b"\x01", b"", "lacks NUL terminator"),
            (fixed + b"\xff\0" + valid_suffix, b"", "not UTF-8"),
            (fixed + b"name\0" + bytes([2]) + valid_suffix, b"", "truncation marker"),
            (struct.pack("<HBIHH", 1, 2, 3, 0, 1) + b"name\0" + bytes([0]) + valid_suffix,
             b"", "location or type"),
            (fixed + b"name\0" + bytes([0, 1, 64, 0, 0]), b"", "cargo type"),
            (fixed + b"name\0" + bytes([0, 0, 0, 0]) + b"x", b"", "trailing data"),
        ]
        for record, suffix, message in invalid:
            client, server_sock = connected_client(timeout=1)
            try:
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 10, 56, 0)
                response += b"world-123\0" + struct.pack("<IIB", 10, 0, 1)
                response += record + suffix
                server_sock.sendall(frame(130, response))
                with self.subTest(message=message), self.assertRaisesRegex(AdminProtocolError, message):
                    client.copilot_industry_details("world-123", 0, 1, request_id=56)
            finally:
                client.close()
                server_sock.close()

    def test_copilot_rail_catalog_round_trip_is_bounded_and_correlated(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                self.assertEqual(
                    struct.unpack_from("<HBIBIB", payload),
                    (COPILOT_PROTOCOL_VERSION, 6, 45, 3, 2, 16),
                )
                self.assertEqual(payload[struct.calcsize("<HBIBIB"):], b"world-123\0")
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 6, 45, 0)
                response += b"world-123\0" + struct.pack("<IBQIB", 789, 3, 5, 2, 1)
                response += struct.pack(
                    "<HBBQBIQQQHHHB", 17, 1, 0, 3, 0, 120, 1 << 3,
                    45000, 1200, 100, 2400, 80, 2,
                )
                server_sock.sendall(frame(130, response))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_rail_catalog("world-123", 3, 2, 16, request_id=45)
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(
                {key: result[key] for key in ("world_id", "frame", "company_id",
                                               "company_railtypes", "start_index", "count")},
                {"world_id": "world-123", "frame": 789, "company_id": 3,
                 "company_railtypes": 5, "start_index": 2, "count": 1},
            )
            self.assertEqual(result["engines"], [{
                "engine_id": 17, "buildable": True, "railveh_type": 0,
                "railtypes": 3, "default_cargo": 0, "default_capacity": 120,
                "refit_mask": 1 << 3, "purchase_cost": 45000, "running_cost": 1200,
                "max_speed": 100, "power": 2400, "weight": 80, "shorten_factor": 2,
            }])
        finally:
            client.close()
            server_sock.close()

    def test_copilot_rail_catalog_rejects_invalid_bounds_and_records(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            for count in (0, 17, True):
                with self.subTest(count=count), self.assertRaises(ValueError):
                    client.copilot_rail_catalog("world-123", 0, 0, count)
        finally:
            client.close()
            server_sock.close()

        fixed = struct.pack("<IBQIB", 10, 0, 1, 0, 1)
        bad_record = struct.pack("<HBBQBIQQQHHHB", 1, 2, 0, 1, 255, 0,
                                 0, 10, 1, 10, 100, 50, 0)
        cases = [
            (struct.pack("<IBQIB", 10, 0, 1, 0, 17), b"", "engine limit"),
            (fixed, b"", "truncated Copilot rail catalog record"),
            (fixed + bad_record, b"", "buildable marker"),
            (fixed + struct.pack("<HBBQBIQQQHHHB", 1, 1, 3, 1, 255, 0,
                                 0, 10, 1, 10, 100, 50, 0), b"", "vehicle class"),
            (fixed + struct.pack("<HBBQBIQQQHHHB", 1, 1, 0, 1, 64, 0,
                                 0, 10, 1, 10, 100, 50, 0), b"", "default cargo"),
            (fixed + struct.pack("<HBBQBIQQQHHHB", 1, 1, 0, 1, 255, 0,
                                 0, 0x8000000000000000, 1, 10, 100, 50, 0), b"", "Money range"),
            (struct.pack("<IBQIB", 10, 0, 1, 0, 0), b"x", "trailing data"),
        ]
        for page, suffix, message in cases:
            client, server_sock = connected_client(timeout=1)
            try:
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 6, 46, 0)
                response += b"world-123\0" + page + suffix
                server_sock.sendall(frame(130, response))
                with self.subTest(message=message), self.assertRaisesRegex(AdminProtocolError, message):
                    client.copilot_rail_catalog("world-123", 0, 0, 1, request_id=46)
            finally:
                client.close()
                server_sock.close()

    def test_copilot_rail_assets_station_and_depot_pages(self) -> None:
        for asset_kind, record_format, record in (
            (0, "<HIIHHQ", (12, 100, 101, 2, 1, 1 << 5)),
            (1, "<HIBB", (4, 202, 1, 0)),
        ):
            client, server_sock = connected_client(timeout=1)
            try:
                def reply() -> None:
                    packet_type, payload = read_frame(server_sock)
                    self.assertEqual(packet_type, 11)
                    self.assertEqual(struct.unpack_from("<HBIBBIB", payload),
                                     (COPILOT_PROTOCOL_VERSION, 7, 47, 3, asset_kind, 2, 16))
                    self.assertEqual(payload[struct.calcsize("<HBIBBIB"):], b"world-123\0")
                    response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 7, 47, 0)
                    response += b"world-123\0" + struct.pack("<IBBIB", 789, 3, asset_kind, 2, 1)
                    response += struct.pack(record_format, *record)
                    server_sock.sendall(frame(130, response))

                thread = threading.Thread(target=reply)
                thread.start()
                result = client.copilot_rail_assets("world-123", 3, asset_kind, 2, 16, request_id=47)
                thread.join(timeout=1)
                self.assertFalse(thread.is_alive())
                self.assertEqual((result["company_id"], result["asset_kind"], result["frame"]),
                                 (3, asset_kind, 789))
                records = result["stations"] if asset_kind == 0 else result["depots"]
                self.assertEqual(result["count"], 1)
                self.assertEqual(len(records), 1)
                if asset_kind == 0:
                    self.assertEqual(records[0], {"station_id": 12, "base_tile": 100,
                        "platform_tile": 101, "platform_width": 2, "platform_height": 1,
                        "acceptance_mask": 1 << 5})
                else:
                    self.assertEqual(records[0], {"depot_id": 4, "tile": 202,
                        "direction": 1, "rail_type": 0})
            finally:
                client.close()
                server_sock.close()

    def test_copilot_rail_assets_rejects_bad_bounds_and_response(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            for args in (("world-123", 0, 2, 0, 1), ("world-123", 0, 0, 0, 0),
                         ("world-123", 0, 0, 0, 17)):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    client.copilot_rail_assets(*args)
        finally:
            client.close()
            server_sock.close()

        fixed = struct.pack("<IBBIB", 9, 0, 0, 0, 1)
        cases = [(fixed, b"", "truncated Copilot rail station record"),
                 (struct.pack("<IBBIB", 9, 0, 0, 0, 17), b"", "selector or count"),
                 (struct.pack("<IBBIB", 9, 0, 0, 0, 0), b"x", "trailing data")]
        for page, suffix, message in cases:
            client, server_sock = connected_client(timeout=1)
            try:
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 7, 48, 0)
                response += b"world-123\0" + page + suffix
                server_sock.sendall(frame(130, response))
                with self.subTest(message=message), self.assertRaisesRegex(AdminProtocolError, message):
                    client.copilot_rail_assets("world-123", 0, 0, 0, 1, request_id=48)
            finally:
                client.close()
                server_sock.close()

    def test_copilot_train_parts_page_and_bounds(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            record = struct.pack("<IBIIIHHIBBIH", 21, 3, 21, 0xFFFFFFFF,
                                 22, 17, 4, 1234, 3, 1, 40, 30)

            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                self.assertEqual(struct.unpack_from("<HBIBIBH", payload),
                                 (COPILOT_PROTOCOL_VERSION, 8, 49, 3, 0xFFFFFFFF, 4, 32))
                self.assertEqual(payload[struct.calcsize("<HBIBIBH"):], b"world-123\0")
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 8, 49, 0)
                response += b"world-123\0" + struct.pack("<IBIBIB", 900, 3, 0xFFFFFFFF,
                                                           1, 25, 0) + record
                server_sock.sendall(frame(130, response))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_train_parts("world-123", 3, max_records=4,
                                                scan_budget=32, request_id=49)
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual((result["frame"], result["count"], result["next_after_id"],
                              result["complete"]), (900, 1, 25, False))
            self.assertEqual(result["parts"][0], {
                "vehicle_id": 21, "owner": 3, "first_vehicle_id": 21,
                "previous_vehicle_id": 0xFFFFFFFF, "next_vehicle_id": 22,
                "engine_id": 17, "unit_number": 4, "tile": 1234,
                "is_primary": True, "stopped": True, "crashed": False,
                "in_depot": False, "cargo_type": 1, "cargo_amount": 40,
                "cargo_capacity": 30,
            })
        finally:
            client.close()
            server_sock.close()

    def test_copilot_train_parts_rejects_bad_bounds_and_records(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            for kwargs in ({"max_records": 0}, {"max_records": 17},
                           {"scan_budget": 0}, {"scan_budget": 257},
                           {"after_vehicle_id": 0x100000}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    client.copilot_train_parts("world-123", 0, **kwargs)
        finally:
            client.close()
            server_sock.close()

        fixed = struct.pack("<IBIBIB", 800, 0, 0xFFFFFFFF, 1, 20, 0)
        bad = struct.pack("<IBIIIHHIBBIH", 21, 0, 22, 0xFFFFFFFF,
                          0xFFFFFFFF, 17, 4, 1234, 1, 1, 20, 30)
        cases = [(fixed, b"", "truncated Copilot train part record"),
                 (struct.pack("<IBIBIB", 800, 0, 0xFFFFFFFF, 17, 20, 0), b"",
                  "page count or completion"),
                 (fixed + struct.pack("<IBIIIHHIBBIH", 21, 0, 21, 0xFFFFFFFF,
                                      0xFFFFFFFF, 17, 4, 1234, 0x80, 255, 0, 0), b"",
                  "state bits"),
                 (fixed + bad, b"", "not its chain root"),
                 (struct.pack("<IBIBIB", 800, 0, 0xFFFFFFFF, 0, 0xFFFFFFFF, 0), b"x",
                  "trailing data")]
        for page, suffix, message in cases:
            client, server_sock = connected_client(timeout=1)
            try:
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 8, 50, 0)
                response += b"world-123\0" + page + suffix
                server_sock.sendall(frame(130, response))
                with self.subTest(message=message), self.assertRaisesRegex(AdminProtocolError, message):
                    client.copilot_train_parts("world-123", 0, request_id=50)
            finally:
                client.close()
                server_sock.close()

    def test_copilot_train_orders_page_and_bounds(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            orders = struct.pack("<BIBBB", 1, 0, 2, 0, 0)
            orders += struct.pack("<BIBBB", 1, 1, 4, 1, 0)

            def reply() -> None:
                packet_type, payload = read_frame(server_sock)
                self.assertEqual(packet_type, 11)
                self.assertEqual(struct.unpack_from("<HBIBIHB", payload),
                                 (COPILOT_PROTOCOL_VERSION, 9, 51, 0, 2, 0, 16))
                self.assertEqual(payload[struct.calcsize("<HBIBIHB"):], b"world-123\0")
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 9, 51, 0)
                response += b"world-123\0" + struct.pack("<IBIHHB", 900, 0, 2, 2, 0, 2)
                response += orders
                server_sock.sendall(frame(130, response))

            thread = threading.Thread(target=reply)
            thread.start()
            result = client.copilot_train_orders("world-123", 0, 2, request_id=51)
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertEqual((result["frame"], result["total_orders"], result["count"]),
                             (900, 2, 2))
            self.assertEqual(result["orders"], [
                {"order_type": 1, "destination_id": 0, "load_type": 2,
                 "unload_type": 0, "nonstop_flags": 0},
                {"order_type": 1, "destination_id": 1, "load_type": 4,
                 "unload_type": 1, "nonstop_flags": 0},
            ])
        finally:
            client.close()
            server_sock.close()

        client, server_sock = connected_client(timeout=1)
        try:
            response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 9, 53, 0)
            response += b"world-123\0" + struct.pack("<IBIHHB", 901, 0, 2, 1, 0, 1)
            response += struct.pack("<BIBBB", 7, 0xFFFFFFFF, 0xFF, 0xFF, 0xFF)
            server_sock.sendall(frame(130, response))
            result = client.copilot_train_orders("world-123", 0, 2, request_id=53)
            self.assertEqual(result["orders"], [{
                "order_type": 7, "destination_id": 0xFFFFFFFF,
                "load_type": 0xFF, "unload_type": 0xFF, "nonstop_flags": 0xFF,
            }])
        finally:
            client.close()
            server_sock.close()

    def test_copilot_train_orders_rejects_bad_bounds_and_records(self) -> None:
        client, server_sock = connected_client(timeout=1)
        try:
            for kwargs in ({"vehicle_id": 0x100000}, {"start_index": 0x10000},
                           {"count": 0}, {"count": 17}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    client.copilot_train_orders("world-123", 0, **{"vehicle_id": 2, **kwargs})
        finally:
            client.close()
            server_sock.close()

        fixed = struct.pack("<IBIHHB", 800, 0, 2, 1, 0, 1)
        invalid = [
            (fixed, b"", "truncated Copilot train order record"),
            (struct.pack("<IBIHHB", 800, 0, 2, 1, 2, 0), b"", "page range"),
            (fixed + struct.pack("<BIBBB", 9, 0, 2, 0, 0), b"", "order type"),
            (fixed + struct.pack("<BIBBB", 1, 0xFFFFFFFF, 2, 0, 0), b"", "destination"),
            (fixed + struct.pack("<BIBBB", 1, 0, 1, 0, 0), b"", "load/unload"),
            (fixed + struct.pack("<BIBBB", 1, 0, 2, 0, 4), b"", "stop flags"),
            (fixed + struct.pack("<BIBBB", 7, 0xFFFFFFFF, 0, 0xFF, 0xFF), b"",
             "non-station"),
            (fixed + struct.pack("<BIBBB", 7, 0xFFFFFFFF, 0xFF, 0xFF, 0), b"",
             "non-goto"),
            (fixed + struct.pack("<BIBBB", 1, 0, 2, 0, 0), b"x", "trailing data"),
        ]
        for page, suffix, message in invalid:
            client, server_sock = connected_client(timeout=1)
            try:
                response = struct.pack("<HBIB", COPILOT_PROTOCOL_VERSION, 9, 52, 0)
                response += b"world-123\0" + page + suffix
                server_sock.sendall(frame(130, response))
                with self.subTest(message=message), self.assertRaisesRegex(AdminProtocolError, message):
                    client.copilot_train_orders("world-123", 0, 2, request_id=52)
            finally:
                client.close()
                server_sock.close()


if __name__ == "__main__":
    unittest.main()
