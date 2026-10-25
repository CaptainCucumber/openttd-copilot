import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import admin_transport
from native_bus_transport import BusBridge


def packet(request_id, body, status=0):
    raw = struct.pack("<HBIB", 3, 18, request_id, status)
    if not status:
        raw += b"world\0" + json.dumps(body, separators=(",", ":")).encode() + b"\0"
    return raw


class FakeAdmin:
    def __init__(self, body):
        self.body = body
        self.sent = None

    def _check_copilot_request_header(self, version, request_id):
        return 42

    def _require_connected(self):
        pass

    def _deadline(self, timeout):
        return timeout

    def _send_packet(self, kind, payload, deadline):
        self.sent = payload

    def _read_frame(self, deadline):
        return admin_transport._SERVER_COPILOT, packet(42, self.body)


class BusBridgeTests(unittest.TestCase):
    def test_towns_encodes_bounded_json_and_returns_body(self):
        body = {"world_id": "world", "frame": 1, "towns": [], "count": 0,
                "next_start": 0, "complete": True}
        admin = FakeAdmin(body)
        result = BusBridge(admin).towns("world")
        self.assertEqual(result, body)
        self.assertEqual(json.loads(admin.sent[7:-1]), {
            "action": "towns", "company_id": 0, "count": 8, "start": 0,
            "world_id": "world"
        })

    def test_assets_and_integer_validation(self):
        body = {"world_id": "world", "frame": 1, "vehicles": [], "kind": "vehicles",
                "count": 0, "next_start": 0, "complete": True}
        self.assertTrue(BusBridge(FakeAdmin(body)).assets("world")["complete"])
        with self.assertRaises(ValueError):
            BusBridge(FakeAdmin(body)).tiles("world", True)
        with self.assertRaises(ValueError):
            BusBridge(FakeAdmin(body)).assets("world", "trucks")

    def test_decode_rejects_world_mismatch(self):
        admin = FakeAdmin({"world_id": "other"})
        with self.assertRaises(admin_transport.AdminProtocolError):
            BusBridge(admin).orders("world", 1)

    def test_quote_sends_unused_uint16_sentinels(self):
        body = {"world_id": "world", "frame": 1, "quote_success": True}
        admin = FakeAdmin(body)
        BusBridge(admin).quote("world", 7, tile=123, road_bits=5)
        request = json.loads(admin.sent[7:-1])
        self.assertEqual(request["town_id"], 0xFFFF)
        self.assertEqual(request["engine_id"], 0xFFFF)

    def test_mutate_accepts_only_explicit_company_zero(self):
        body = {"world_id": "world", "state_name": "pending"}
        admin = FakeAdmin(body)
        BusBridge(admin).mutate(
            world_id="world", company_id=0, kind=7, tile=123, road_bits=5,
            max_cost=10, expected_sequence=0, expected_head_hi=0,
            expected_head_lo=0, operation_hi=1, operation_lo=2,
            payload_hash_hi=3, payload_hash_lo=4,
        )
        request = json.loads(admin.sent[7:-1])
        self.assertEqual(request["company_id"], 0)
        self.assertEqual(request["engine_id"], 0xFFFF)
        self.assertEqual(request["vehicle_id"], 0xFFFFFFFF)
        self.assertEqual(request["target_id"], 0xFFFFFFFF)
        for company_id in (True, 1):
            with self.subTest(company_id=company_id), self.assertRaises(ValueError):
                BusBridge(FakeAdmin(body)).mutate(
                    world_id="world", company_id=company_id, kind=7, tile=123,
                    road_bits=5, max_cost=10, expected_sequence=0,
                    expected_head_hi=0, expected_head_lo=0, operation_hi=1,
                    operation_lo=2, payload_hash_hi=3, payload_hash_lo=4,
                )


if __name__ == "__main__":
    unittest.main()
