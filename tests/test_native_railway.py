from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import native_railway  # noqa: E402


def identity(*, sequence=0, head=None, money=10_000, loan=2_000):
    result = {
        "world_id": "world-1", "sequence": sequence, "head": head,
        "head_hi": 0 if head is None else head["hi"],
        "head_lo": 0 if head is None else head["lo"],
        "map_width": 8, "map_height": 8,
        "companies": [{"money": money, "loan": loan}],
    }
    return result


class Session:
    def __init__(self, admin, root: Path):
        self.admin = admin
        self.artifacts = root
        self.manifest = {}
        self.writes = 0

    def remaining(self):
        return 1.0

    def write(self):
        self.writes += 1

    def save(self, name):
        return self.artifacts / f"{name}.sav"


class NativeRailwayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_discover_uses_native_industry_schema_and_builds_sorted_pairs(self):
        admin = Mock()
        admin.copilot_identity.side_effect = [
            {**identity(), "map_width": 8},
            {**identity(), "map_width": 8},
        ]
        records = [
            {"industry_id": 20, "name": "Power", "tile": 18,
             "produced_cargo": [], "accepted_cargo": [1]},
            {"industry_id": 10, "name": "Mine", "tile": 1,
             "produced_cargo": [1], "accepted_cargo": []},
        ]
        admin.copilot_industry_details.return_value = {
            "count": 2, "industries": records,
        }
        result = native_railway.discover(admin)
        self.assertEqual(result["industries"], records)
        self.assertEqual(result["business_pairs"][0]["source_id"], 10)
        self.assertEqual(result["business_pairs"][0]["destination_id"], 20)
        admin.copilot_industry_details.assert_called_once_with("world-1", 0, 8)

    def test_discover_rejects_malformed_industry_record(self):
        admin = Mock()
        admin.copilot_identity.side_effect = [identity(), identity()]
        admin.copilot_industry_details.return_value = {
            "count": 1, "industries": [{"industry_id": 1, "produced_cargo": [1]}],
        }
        with self.assertRaises((KeyError, ValueError, TypeError)):
            native_railway.discover(admin)

    def test_plan_rejects_bool_negative_and_malformed_ids_caps_and_reserve(self):
        session = Mock()
        for args in (
            (True, 2, 100, 0),
            (1, False, 100, 0),
            (1, 2, True, 0),
            (1, 2, 100, True),
            (-1, 2, 100, 0),
            (1, 2, 0, 0),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                native_railway.plan_railway(session, *args)
        session.admin.copilot_identity.assert_not_called()

    def _patch_planner(self, *, quote_state=0, capacity=20, retained=0):
        source = {"industry_id": 1, "name": "Mine", "tile": 1,
                  "produced_cargo": [1], "accepted_cargo": []}
        destination = {"industry_id": 2, "name": "Power", "tile": 6,
                       "produced_cargo": [], "accepted_cargo": [1]}
        discovery = {"world_id": "world-1", "sequence": 0,
                     "industries": [source, destination], "business_pairs": []}
        geometry = {
            "source_station": {"tile": 8, "axis": 0, "length": 2, "footprint": [8, 9]},
            "destination_station": {"tile": 14, "axis": 0, "length": 2, "footprint": [14, 15]},
            "depot": {"tile": 16, "orientation": 2, "length": 1},
            "rails": [], "operation_count": 9, "footprint": [8, 9, 14, 15, 16],
        }
        quote = {
            "quote_success": True, "supported_profile": True, "cost": 10,
            "covers_producer": True, "industry_acceptance": 8,
            "operation_state": quote_state, "capacity": capacity,
            "retained_count": retained, "error": "",
        }
        session = Session(Mock(), self.root)
        session.admin.copilot_identity.side_effect = [
            {**identity(), "map_width": 8, "map_height": 8},
            {**identity(), "map_width": 8, "map_height": 8},
        ]
        patches = [
            patch.object(native_railway, "discover", return_value=discovery),
            patch.object(native_railway, "read_tile_window",
                         return_value={"rows": [[{"tile": n} for n in range(64)]],
                                       "frame_min": 1, "frame_max": 1}),
            patch.object(native_railway.planner, "station_candidates",
                         side_effect=[[{"tile": 8, "axis": 0, "length": 2,
                                         "footprint": [8, 9]}],
                                       [{"tile": 14, "axis": 0, "length": 2,
                                         "footprint": [14, 15]}]]),
            patch.object(native_railway.planner, "find_route", return_value=geometry),
            patch.object(native_railway, "_quote", return_value=quote),
            patch.object(native_railway.purchase, "read_catalog",
                         return_value=([{"engine_id": 3, "railveh_type": 0,
                                         "default_capacity": 0, "purchase_cost": 10},
                                        {"engine_id": 4, "railveh_type": 2,
                                         "default_capacity": 20, "purchase_cost": 10}], [])),
            patch.object(native_railway.purchase, "choose_engines",
                         return_value=({"engine_id": 3, "railveh_type": 0,
                                        "purchase_cost": 10},
                                       {"engine_id": 4, "default_capacity": 20,
                                        "purchase_cost": 10})),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return session

    def test_plan_rejects_construction_cap_before_mutation(self):
        session = self._patch_planner()
        with self.assertRaisesRegex(RuntimeError, "above construction cap"):
            native_railway.plan_railway(session, 1, 2, 1, 0)

    def test_plan_rejects_operating_reserve_before_mutation(self):
        session = self._patch_planner()
        with self.assertRaisesRegex(RuntimeError, "operating reserve"):
            native_railway.plan_railway(session, 1, 2, 1_000, 9_999)

    def test_plan_rejects_pending_operation_profile(self):
        session = self._patch_planner(quote_state=1)
        with self.assertRaisesRegex(RuntimeError, "pending/uncertain"):
            native_railway.plan_railway(session, 1, 2, 1_000, 0)

    def test_plan_rejects_retained_operation_capacity(self):
        session = self._patch_planner(capacity=9, retained=1)
        with self.assertRaisesRegex(RuntimeError, "retained records"):
            native_railway.plan_railway(session, 1, 2, 1_000, 0)

    def _plan(self, *, position=None, steps=None, quoted_total=10):
        return {
            "world_id": "world-1",
            "position": position or {"sequence": 0, "head": None},
            "source": {"industry_id": 1}, "destination": {"industry_id": 2},
            "quoted_total": quoted_total, "construction_cap": 1_000,
            "operating_reserve": 0,
            "steps": steps or [{"kind": 0, "tile": 8, "track": 0,
                                "rail_type": 0, "max_cost": 10}],
            "geometry": {"depot": {"tile": 16}},
            "locomotive": {"engine_id": 3, "purchase_cost": 10},
            "wagon": {"engine_id": 4, "purchase_cost": 10,
                      "default_capacity": 20},
        }

    def test_execute_rejects_stale_approved_world_before_persist_or_send(self):
        admin = Mock()
        admin.copilot_identity.return_value = identity(sequence=1, head={"hi": 1, "lo": 2})
        session = Session(admin, self.root)
        with self.assertRaisesRegex(RuntimeError, "differs from the approved plan"):
            native_railway.execute_railway(session, self._plan(), "stale")
        self.assertFalse((self.root / "jobs" / "stale.json").exists())
        admin.copilot_build_single_rail.assert_not_called()

    def test_execute_returns_exact_completed_job_without_mutation(self):
        result = {"job_id": "done", "vehicle": 7}
        path = self.root / "jobs" / "done.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"plan": self._plan(), "state": "commissioned",
                                    "outcomes": [{"outcome": identity()}],
                                    "result": result}), encoding="utf-8")
        admin = Mock()
        admin.copilot_identity.return_value = identity()
        session = Session(admin, self.root)
        self.assertEqual(native_railway.execute_railway(session, self._plan(), "done"), result)
        admin.copilot_build_single_rail.assert_not_called()
        admin.copilot_identity.return_value = identity(sequence=1, head={"hi": 1, "lo": 2})
        with self.assertRaisesRegex(RuntimeError, "loaded world/operation position"):
            native_railway.execute_railway(session, self._plan(), "done")

    def test_execute_rejects_conflicting_or_partial_durable_job(self):
        path = self.root / "jobs"
        path.mkdir()
        plan = self._plan()
        (path / "conflict.json").write_text(
            json.dumps({"plan": {**plan, "quoted_total": 11},
                        "state": "commissioned", "result": {}}), encoding="utf-8")
        (path / "partial.json").write_text(
            json.dumps({"plan": plan, "state": "partial", "result": {}}), encoding="utf-8")
        session = Session(Mock(), self.root)
        with self.assertRaisesRegex(RuntimeError, "conflicts"):
            native_railway.execute_railway(session, plan, "conflict")
        with self.assertRaisesRegex(RuntimeError, "reconciliation"):
            native_railway.execute_railway(session, plan, "partial")

    def test_persist_writes_exact_json_and_syncs_file_and_directory(self):
        path = self.root / "nested" / "job.json"
        with patch.object(native_railway.os, "fsync") as sync:
            native_railway._persist(path, {"z": 1, "a": [2]})
        self.assertEqual(json.loads(path.read_text()), {"z": 1, "a": [2]})
        self.assertEqual(sync.call_count, 2)
        self.assertFalse(path.with_name("job.json.tmp").exists())

    def test_method_failure_keeps_pending_journal_and_partial_job_refuses_retry(self):
        admin = Mock()
        admin.copilot_identity.side_effect = [identity(), identity()]
        session = Session(admin, self.root)
        plan = self._plan()
        with patch.object(native_railway, "_quote",
                          return_value={"quote_success": True, "cost": 10}), \
             patch.object(native_railway.purchase, "snapshot",
                          return_value={"companies": [{"money": 10_000, "loan": 2_000}],
                                        "parts": [], "stations": [], "depots": []}):
            admin.copilot_build_single_rail.side_effect = RuntimeError("native send failed")
            with self.assertRaisesRegex(RuntimeError, "native send failed"):
                native_railway.execute_railway(session, plan, "failed")
        job = json.loads((self.root / "jobs" / "failed.json").read_text())
        self.assertEqual(job["state"], "partial")
        journal = Path(job["pending_journal"])
        self.assertEqual(json.loads(journal.read_text())["operation"]["state"], "pending")
        with self.assertRaisesRegex(RuntimeError, "reconciliation"):
            native_railway.execute_railway(session, plan, "failed")
        self.assertEqual(admin.copilot_build_single_rail.call_count, 1)


if __name__ == "__main__":
    unittest.main()
