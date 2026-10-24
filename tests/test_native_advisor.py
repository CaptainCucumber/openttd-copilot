from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import native_railway  # noqa: E402
from tools import native_mcp_server as native_server  # noqa: E402


def identity(*, sequence=4, head=None, frame=100, money=10_000, loan=2_000):
    if head is None and sequence:
        head = {"hi": 0, "lo": sequence}
    return {
        "world_id": "world-1", "sequence": sequence, "head": head,
        "head_hi": 0 if head is None else head["hi"],
        "head_lo": 0 if head is None else head["lo"],
        "frame": frame, "map_width": 8, "map_height": 8,
        "companies": [{"money": money, "loan": loan}],
    }


class Session:
    def __init__(self, admin):
        self.admin = admin
        self.manifest = {"before": "unchanged"}
        self.writes = 0

    def remaining(self):
        return 1.0

    def write(self):
        self.writes += 1


def discovery():
    return {
        "world_id": "world-1", "sequence": 4,
        "industries": [
            {"industry_id": 1, "name": "Mine", "tile": 1,
             "produced_cargo": [1], "accepted_cargo": []},
            {"industry_id": 2, "name": "Power", "tile": 6,
             "produced_cargo": [], "accepted_cargo": [1]},
        ],
        "business_pairs": [{"source_id": 1, "destination_id": 2}],
    }


def install_plan_mocks(session):
    geometry = {
        "source_station": {"tile": 8, "axis": 0, "length": 2, "footprint": [8, 9]},
        "destination_station": {"tile": 14, "axis": 0, "length": 2, "footprint": [14, 15]},
        "depot": {"tile": 16, "orientation": 2, "length": 1},
        "rails": [], "operation_count": 9, "footprint": [8, 9, 14, 15, 16],
    }
    quote = {
        "quote_success": True, "supported_profile": True, "cost": 10,
        "covers_producer": True, "industry_acceptance": 8,
        "operation_state": 0, "capacity": 20, "retained_count": 0, "error": "",
    }
    patches = [
        patch.object(native_railway, "discover", return_value=discovery()),
        patch.object(native_railway, "read_tile_window", return_value={
            "rows": [[{"tile": n} for n in range(64)]], "frame_min": 10, "frame_max": 11,
        }),
        patch.object(native_railway.planner, "station_candidates",
                     side_effect=[[{"tile": 8, "axis": 0, "length": 2, "footprint": [8, 9]}],
                                  [{"tile": 14, "axis": 0, "length": 2, "footprint": [14, 15]}]]),
        patch.object(native_railway.planner, "find_route", return_value=geometry),
        patch.object(native_railway, "_quote", return_value=quote),
        patch.object(native_railway.purchase, "read_catalog", return_value=(
            [{"engine_id": 3, "railveh_type": 0, "default_capacity": 0,
              "purchase_cost": 10, "buildable": True},
             {"engine_id": 4, "railveh_type": 2, "default_capacity": 20,
              "purchase_cost": 10, "buildable": True}], [])),
        patch.object(native_railway.purchase, "choose_engines", return_value=(
            {"engine_id": 3, "railveh_type": 0, "purchase_cost": 10},
            {"engine_id": 4, "default_capacity": 20, "purchase_cost": 10},
        )),
    ]
    for item in patches:
        item.start()
        session._patches = getattr(session, "_patches", []) + [item]
    return geometry


class NativeAdvisorTests(unittest.TestCase):
    def _inspection(self, *, event_pages=None, identities=None):
        admin = Mock()
        session = Session(admin)
        admin.copilot_identity.side_effect = identities or [identity(), identity()]
        native_events = event_pages or [{
            "epoch": 7, "gap": False, "events": [{"seq": 1, "kind": "delivery"}],
            "next_seq": 2, "frame": 105,
        }]
        admin.copilot_vehicle_events.side_effect = native_events
        assets = {
            "world_id": "world-1",
            "stations": [{"station_id": 3, "tile": 8}],
            "depots": [{"depot_id": 4, "tile": 16}],
            "parts": [{"vehicle_id": 9, "first_vehicle_id": 9, "is_primary": True,
                       "cargo_id": 1, "cargo_units": 12, "stopped": False}],
        }
        catalog = [{"engine_id": 3, "buildable": True, "railveh_type": 0}]
        with patch.object(native_railway, "discover", return_value=discovery()), \
             patch.object(native_railway.purchase, "snapshot", return_value=assets), \
             patch.object(native_railway.purchase, "read_catalog",
                          return_value=(catalog, [{"frame": 102}])), \
             patch.object(native_railway, "read_orders",
                          return_value=([{"destination_id": 3, "load_type": 2}],
                                        [{"frame": 103}])):
            return session, native_railway.inspect_game(session)

    def test_inspection_returns_fresh_world_identity_and_frame_span(self):
        session, result = self._inspection()
        self.assertEqual(result["world_id"], "world-1")
        self.assertEqual(result["position"], {"sequence": 4, "head": {"hi": 0, "lo": 4}})
        self.assertEqual(result["observation_frame_span"], [100, 105])
        self.assertEqual(result["identity"]["companies"][0]["money"], 10_000)
        self.assertEqual(result["stations"][0]["station_id"], 3)
        self.assertEqual(session.writes, 0)

    def test_inspection_contains_cash_assets_catalog_cargo_orders_and_events(self):
        _, result = self._inspection()
        self.assertEqual(result["train_parts"][0]["cargo_units"], 12)
        self.assertEqual(result["trains"][0]["orders"][0]["load_type"], 2)
        self.assertEqual(result["trains"][0]["recent_events"]["events"][0]["kind"], "delivery")
        self.assertEqual(result["buildable_rail_engines"][0]["engine_id"], 3)

    def test_inspection_discloses_missing_profit_production_and_non_atomic_reads(self):
        _, result = self._inspection()
        limitations = " ".join(result["limitations"]).casefold()
        self.assertIn("profit", limitations)
        self.assertIn("production", limitations)
        self.assertIs(result["atomic"], False)

    def test_inspection_rejects_world_position_change(self):
        with self.assertRaisesRegex(RuntimeError, "world/operation position"):
            self._inspection(identities=[identity(), identity(sequence=5)])

    def test_inspection_reports_event_gap_and_truncation(self):
        pages = [
            {"epoch": 7, "gap": True, "events": [{"seq": n} for n in range(16)],
             "next_seq": n + 16, "frame": 101 + n}
            for n in (0, 16, 32, 48)
        ]
        _, result = self._inspection(event_pages=pages)
        recent = result["trains"][0]["recent_events"]
        self.assertTrue(recent["gap"])
        self.assertFalse(recent["complete"])
        self.assertEqual(len(recent["events"]), 64)
        self.assertEqual(recent["next_cursor"], 64)

    def test_plan_record_false_does_not_write_manifest_or_job_state(self):
        admin = Mock()
        admin.copilot_identity.side_effect = [identity(), identity()]
        session = Session(admin)
        before = dict(session.manifest)
        install_plan_mocks(session)
        try:
            plan = native_railway.plan_railway(session, 1, 2, 1_000, 0, record=False)
        finally:
            for item in session._patches:
                item.stop()
        self.assertEqual(plan["world_id"], "world-1")
        self.assertEqual(session.manifest, before)
        self.assertEqual(session.writes, 0)

    def test_plan_rejects_position_change_before_returning_advice(self):
        admin = Mock()
        admin.copilot_identity.side_effect = [identity(), identity(sequence=5)]
        session = Session(admin)
        install_plan_mocks(session)
        try:
            with self.assertRaisesRegex(RuntimeError, "world/operation position"):
                native_railway.plan_railway(session, 1, 2, 1_000, 0, record=False)
        finally:
            for item in session._patches:
                item.stop()


class FakeNativeSession:
    instances = []

    def __init__(self, **kwargs):
        self.artifacts = Path(tempfile.mkdtemp(prefix="native-advisor-"))
        self.admin = object()
        self.manifest = {}
        self.write_count = 0
        self.__class__.instances.append(self)

    def start_world(self, label, save=None):
        self.started = (label, save)

    def write(self):
        self.write_count += 1

    def save(self, name):
        return self.artifacts / f"{name}.sav"

    def finish(self, failure=None):
        self.finished = failure


class NativePreviewTests(unittest.TestCase):
    def setUp(self):
        FakeNativeSession.instances.clear()
        self.session_patch = patch.object(native_server, "NativeSession", FakeNativeSession)
        self.discover_patch = patch.object(native_server.native_railway, "discover",
                                           return_value=discovery())
        self.plan_patch = patch.object(native_server.native_railway, "plan_railway",
                                       return_value={
                                           "world_id": "world-1",
                                           "position": {"sequence": 4, "head": {"hi": 0, "lo": 4}},
                                           "source": discovery()["industries"][0],
                                           "destination": discovery()["industries"][1],
                                           "quoted_total": 20, "construction_cap": 100,
                                           "operating_reserve": 10,
                                           "geometry": {"rails": []}, "operation_count": 9,
                                           "available_records": 20,
                                           "locomotive": {"engine_id": 3},
                                           "wagon": {"engine_id": 4},
                                           "observation_frame_span": [1, 2],
                                           "scope": "test",
                                       })
        self.session_patch.start()
        self.discover_patch.start()
        self.plan_mock = self.plan_patch.start()
        self.addCleanup(self.session_patch.stop)
        self.addCleanup(self.discover_patch.stop)
        self.addCleanup(self.plan_patch.stop)
        self.job = native_server.NativeJob("server", "client", 10, 6, False)
        self.job.open({})
        self.args = {
            "job_id": self.job.job_id, "source_id": 1, "destination_id": 2,
            "construction_cap": 100, "operating_reserve": 10,
            "wait_for_full_load": True, "cargo": "coal",
        }

    def tearDown(self):
        self.job.cleanup()

    def test_preview_is_read_only_and_does_not_start_worker_or_change_payload(self):
        session = FakeNativeSession.instances[0]
        manifest = dict(session.manifest)
        result = self.job.preview(self.args)
        self.assertTrue(result["read_only"])
        self.assertFalse(result["construction_started"])
        self.assertIsNone(self.job.worker)
        self.assertIsNone(self.job.payload)
        self.assertFalse(self.job.construction_started)
        self.assertEqual(session.manifest, manifest)
        self.plan_mock.assert_called_once_with(session, 1, 2, 100, 10, record=False)

    def test_preview_and_inspect_strict_arguments_raise_tool_error(self):
        with self.assertRaises(native_server.ToolError):
            self.job.preview({**self.args, "extra": 1})
        with self.assertRaises(native_server.ToolError):
            self.job.inspect({"unexpected": True})
        response = native_server.NativeMcpServer(self.job).handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "plan_native_railway", "arguments": {"bad": 1}},
        })
        self.assertTrue(response["result"]["isError"])
        self.assertIn("seven documented build fields", response["result"]["content"][0]["text"])

    def test_idle_guard_blocks_live_read_and_preview_during_shared_admin_worker(self):
        started = threading.Event()
        release = threading.Event()

        def active():
            started.set()
            release.wait(2)

        self.job.worker = threading.Thread(target=active)
        self.job.worker.start()
        self.assertTrue(started.wait(1))
        try:
            with self.assertRaisesRegex(native_server.ToolError, "native job is active"):
                self.job.inspect({})
            with self.assertRaisesRegex(native_server.ToolError, "native job is active"):
                self.job.preview(self.args)
        finally:
            release.set()
            self.job.worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
