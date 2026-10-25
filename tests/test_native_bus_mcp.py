import copy
import inspect
import unittest
from unittest.mock import Mock, patch

from tests.test_native_mcp_server import DISCOVERY, FakeSession
from tools import native_mcp_server as server


class NativeBusMcpTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(server, "NativeSession", FakeSession),
            patch.object(server.native_railway, "discover", return_value=copy.deepcopy(DISCOVERY)),
            patch.object(server.native_bus, "plan_bus", return_value={"bus": "plan"}),
            patch.object(server.native_bus, "execute_bus", return_value={"vehicle": 9}),
            patch.object(server.native_bus, "verify_bus", return_value={"vehicle": 9, "service_summary": {"delivered": True}}),
        ]
        self.mocks = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)
        self.job = server.NativeJob("server", "client", 900, 6, False)
        self.job.open({})
        self.addCleanup(self.job.cleanup)
        self.args = {"job_id": self.job.job_id, "source_town_id": 1,
                     "destination_town_id": 2, "construction_cap": 10000, "operating_reserve": 1000}

    def test_strict_bus_contract(self):
        for fields in ({"source_town_id": True}, {"construction_cap": 0},
                       {"destination_town_id": 1}, {"job_id": "wrong"},
                       {"cargo": "coal"}, {"wait_for_full_load": True}):
            with self.subTest(fields=fields), self.assertRaises(server.ToolError):
                self.job.build({**self.args, **fields}, bus=True)
        self.mocks[2].assert_not_called()

    def test_bus_dispatch_duplicate_and_revised_request_after_rejection(self):
        self.mocks[2].side_effect = RuntimeError("road corridor blocked")
        self.job.build(self.args, bus=True)
        self.job.worker.join(2)
        self.assertEqual(self.job.status, "rejected")
        self.assertFalse(self.job.construction_started)
        self.job.build(self.args, bus=True)
        self.assertEqual(self.mocks[2].call_count, 1)
        self.mocks[2].side_effect = None
        self.job.build({**self.args, "construction_cap": 12000}, bus=True)
        self.job.worker.join(2)
        self.assertEqual(self.job.status, "operating")
        self.assertTrue(self.job.construction_started)
        self.mocks[3].assert_called_once()
        self.mocks[4].assert_called_once()

    def test_bus_failure_after_executor_entry_blocks_changed_request(self):
        self.mocks[3].side_effect = RuntimeError("send outcome unknown")
        self.job.build(self.args, bus=True)
        self.job.worker.join(2)
        self.assertEqual(self.job.status, "failed")
        self.assertTrue(self.job.construction_started)
        with self.assertRaises(server.ToolError):
            self.job.build({**self.args, "construction_cap": 12000}, bus=True)
        self.mocks[3].assert_called_once()

    def test_preview_does_not_change_payload_start_worker_or_write_manifest(self):
        plan = {"world_id": "world-1", "source": {}, "destination": {}, "quoted_total": 1000,
                "construction_cap": 10000, "operating_reserve": 1000, "operation_count": 7,
                "available_records": 64, "engine": {}, "observation_frame_span": [1, 2],
                "road_tiles_to_build": 0, "scope": "bus", "geometry": {"path": [1, 2]}}
        self.mocks[2].return_value = plan
        before, writes = copy.deepcopy(self.job.session.manifest), self.job.session.write_count
        preview = self.job.preview_bus(self.args)
        self.assertTrue(preview["read_only"])
        self.assertFalse(preview["construction_started"])
        self.assertEqual(self.job.session.manifest, before)
        self.assertEqual(self.job.session.write_count, writes)
        self.assertIsNone(self.job.worker)
        self.assertIsNone(self.job.payload)
        self.mocks[2].assert_called_once_with(self.job.session, 1, 2, 10000, 1000, record=False)
        self.mocks[3].assert_not_called()

    def test_active_worker_cannot_share_socket_with_bus_preview(self):
        self.job.worker = Mock()
        self.job.worker.is_alive.return_value = True
        with self.assertRaisesRegex(server.ToolError, "active"):
            self.job.preview_bus(self.args)
        self.mocks[2].assert_not_called()
        self.job.worker = None

    def test_status_bounded_wait_is_optional_and_strict(self):
        result = self.job.refresh({"job_id": self.job.job_id, "wait_seconds": 10})
        self.assertEqual(result["status"], "waiting_for_build")
        for wait in (-1, True, 11, 1.5):
            with self.subTest(wait=wait), self.assertRaises(server.ToolError):
                self.job.refresh({"job_id": self.job.job_id, "wait_seconds": wait})

    def test_fresh_stop_quotes_must_still_serve_the_selected_town(self):
        quote = {"supported_profile": True, "operation_state": 0, "quote_success": True,
                 "cost": 150, "error": 0, "passenger_acceptance": 8, "passenger_production": 1}
        server.native_bus.require_quote(quote, stop=True)
        for changed in ({"passenger_acceptance": 7}, {"passenger_production": 0}):
            with self.subTest(changed=changed), self.assertRaisesRegex(RuntimeError, "selected town"):
                server.native_bus.require_quote({**quote, **changed}, stop=True)

    def test_shared_executor_wire_matches_real_bus_transport_signatures(self):
        wire = {"world_id": "world", "company_id": 0, "tile": 12, "max_cost": 100,
                "expected_sequence": 0, "expected_head_hi": 0, "expected_head_lo": 0,
                "operation_hi": 1, "operation_lo": 2, "payload_hash_hi": 3, "payload_hash_lo": 4,
                "timeout": 1.0}
        for fields in (
            {"kind": 7, "road_bits": 5}, {"kind": 8, "orientation": 0},
            {"kind": 9, "orientation": 2}, {"kind": 10, "engine_id": 116},
            {"kind": 11, "vehicle_id": 1, "target_id": 2, "order_index": 0, "policy": 0},
            {"kind": 12, "vehicle_id": 1, "target_id": 0xFFFFFFFF, "policy": 1},
        ):
            with self.subTest(fields=fields):
                inspect.signature(server.native_bus.BusBridge.mutate).bind(None, **wire, **fields)
        inspect.signature(server.native_bus.BusBridge.operation).bind(
            None, world_id="world", operation_hi=1, operation_lo=2, timeout=1.0)

    def test_normal_map_open_and_inspect_include_town_and_bus_observations(self):
        self.job.close({})
        self.job.map_style = "normal"
        with patch.object(server.native_bus, "discover", return_value=[{"town_id": 1, "name": "Town"}]), \
             patch.object(server.native_bus, "inspect", return_value={
                 "buses": [{"vehicle_id": 3}], "world_id": "world-1",
                 "position": {"sequence": 0, "head": None}, "observation_frame_span": [3, 4]}), \
             patch.object(server.native_railway, "inspect_game", return_value={
                 "world_id": "world-1", "position": {"sequence": 0, "head": None},
                 "observation_frame_span": [1, 2]}):
            result = self.job.open({})
            self.assertEqual(result["towns"][0]["name"], "Town")
            self.assertEqual(self.job.inspect({})["observations"]["buses"], [{"vehicle_id": 3}])
