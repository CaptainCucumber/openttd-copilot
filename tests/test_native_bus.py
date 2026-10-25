from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import native_bus  # noqa: E402


def tile(tile, *, tile_type=2, road_bits=5, one_way=False, owner=16,
         slope=0, valid=True, road_type=0, normal_road=True):
    return {
        "tile": tile,
        "valid": valid,
        "tile_type": tile_type,
        "road_bits": road_bits,
        "one_way": one_way,
        "owner": owner,
        "slope": slope,
        "road_type": road_type,
        "normal_road": normal_road,
    }


def identity(*, sequence=0, head=None, money=10_000, loan=2_000):
    return {
        "world_id": "world-1",
        "sequence": sequence,
        "head": head,
        "head_hi": 0 if head is None else head["hi"],
        "head_lo": 0 if head is None else head["lo"],
        "frame": 10,
        "map_width": 8,
        "map_height": 8,
        "companies": [{"money": money, "loan": loan}],
    }


class Session:
    def __init__(self, root: Path, admin=None):
        self.admin = admin or Mock()
        self.artifacts = root
        self.manifest = {}
        self.writes = 0

    def remaining(self):
        return 1.0

    def write(self):
        self.writes += 1

    def save(self, name):
        return self.artifacts / f"{name}.sav"


class NativeBusTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / ".native-bus-test-artifacts"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def test_usable_accepts_owned_clearings_and_rejects_invalid_or_unsafe_tiles(self):
        self.assertTrue(native_bus.usable(tile(1, tile_type=2, road_bits=5)))
        self.assertTrue(native_bus.usable(tile(2, tile_type=0, owner=16)))
        self.assertTrue(native_bus.usable(tile(3, tile_type=4, owner=16)))
        for record in (
            None,
            tile(4, valid=False),
            tile(5, tile_type=2, road_type=1),
            tile(6, tile_type=2, one_way=True),
            tile(6, tile_type=2, normal_road=False),
            tile(7, tile_type=0, owner=0),
            tile(8, tile_type=4, owner=0),
        ):
            with self.subTest(record=record):
                self.assertFalse(native_bus.usable(record))

    def test_candidate_stops_requires_straight_zero_slope_roads_near_town(self):
        records = {
            9: tile(9, road_bits=5),
            10: tile(10, road_bits=10),
            11: tile(11, road_bits=15),
            12: tile(12, road_bits=5, slope=1),
            13: tile(13, road_bits=5, tile_type=0),
            14: tile(14, road_bits=5, one_way=True),
        }
        result = native_bus.candidate_stops(records, {"tile": 9}, 8)
        self.assertEqual([record["tile"] for record in result], [9, 10])

    def test_find_path_prefers_existing_roads_over_new_clearings(self):
        records = {
            9: tile(9, road_bits=5),
            10: tile(10, road_bits=5),
            11: tile(11, road_bits=5),
            17: tile(17, tile_type=0),
            18: tile(18, tile_type=0),
            19: tile(19, tile_type=0),
        }
        result = native_bus.find_path(
            records, 8, 8, [{"tile": 9}], [{"tile": 11}], max_expansions=100,
        )
        self.assertEqual(result["path"], [9, 10, 11])

    def test_find_path_preserves_direction_and_reciprocal_connection(self):
        records = {
            9: tile(9, road_bits=5),
            10: tile(10, road_bits=5),
            11: tile(11, road_bits=5),
        }
        result = native_bus.find_path(
            records, 8, 8, [{"tile": 9}], [{"tile": 11}], max_expansions=100,
        )
        self.assertEqual(result["path"], [9, 10, 11])
        steps = native_bus.road_steps(result["path"], records, 8, 8)
        self.assertEqual(steps, [])

    def test_road_steps_emits_only_missing_bits_for_all_new_road_masks(self):
        records = {
            9: tile(9, road_bits=1),
            10: tile(10, road_bits=0, tile_type=0),
            11: tile(11, road_bits=4),
        }
        steps = native_bus.road_steps([9, 10, 11], records, 8, 8)
        self.assertEqual(
            {step["tile"]: step["road_bits"] for step in steps},
            {9: 5, 10: 5, 11: 5},
        )

    def test_road_steps_emits_reciprocal_bits_for_a_new_corner(self):
        records = {
            9: tile(9, road_bits=0, tile_type=0),
            10: tile(10, road_bits=0, tile_type=0),
            18: tile(18, road_bits=0, tile_type=0),
        }
        steps = native_bus.road_steps([9, 10, 18], records, 8, 8)
        self.assertEqual(
            {step["tile"]: step["road_bits"] for step in steps},
            {9: 4, 10: 3, 18: 8},
        )

    def test_find_path_rejects_water_houses_oneways_and_unowned_clearings(self):
        records = {
            9: tile(9, road_bits=5),
            10: tile(10, tile_type=3),
            11: tile(11, tile_type=0, owner=0),
            12: tile(12, tile_type=2, one_way=True),
            13: tile(13, tile_type=0, owner=16),
        }
        with self.assertRaisesRegex(RuntimeError, "no bus route"):
            native_bus.find_path(
                records, 8, 8, [{"tile": 9}], [{"tile": 13}],
                max_expansions=20,
            )

    def test_neighbour_and_find_path_respect_map_boundaries(self):
        self.assertIsNone(native_bus.neighbour(0, 0, 8, 8))
        self.assertIsNone(native_bus.neighbour(7, 2, 8, 8))
        self.assertIsNone(native_bus.neighbour(56, 1, 8, 8))
        self.assertIsNone(native_bus.neighbour(63, 1, 8, 8))
        records = {0: tile(0, road_bits=5), 1: tile(1, road_bits=10)}
        with self.assertRaisesRegex(RuntimeError, "no bus route"):
            native_bus.find_path(records, 8, 8, [{"tile": 0}], [{"tile": 7}])

    def test_paged_rejects_wrong_world_and_nonadvancing_pages(self):
        bridge = Mock()
        bridge.towns.side_effect = [
            {"world_id": "other", "towns": [], "complete": True},
        ]
        with self.assertRaisesRegex(RuntimeError, "world mismatch"):
            native_bus.paged(bridge, "towns", "world-1", "towns")
        bridge.towns.side_effect = [
            {"world_id": "world-1", "towns": [], "complete": False, "next_start": 0},
        ]
        with self.assertRaisesRegex(RuntimeError, "did not advance"):
            native_bus.paged(bridge, "towns", "world-1", "towns")

    def _plan_patches(self, *, cost=100, money=10_000, reserve=0, writes=True,
                      source_tile=9, destination_tile=11):
        source = {"town_id": 1, "name": "A", "tile": source_tile}
        destination = {"town_id": 2, "name": "B", "tile": destination_tile}
        records = {
            source_tile: tile(source_tile, road_bits=5),
            10: tile(10, road_bits=5),
            destination_tile: tile(destination_tile, road_bits=5),
            18: tile(18, tile_type=0, owner=16),
        }
        session = Session(self.root)
        session.admin = Mock()
        patches = [
            patch.object(native_bus, "_identity", return_value=identity(money=money)),
            patch.object(native_bus, "discover", return_value=[source, destination]),
            patch.object(native_bus, "read_corridor", return_value=(records, [1, 1])),
            patch.object(native_bus, "candidate_stops",
                         side_effect=[[records[source_tile]], [records[destination_tile]]]),
            patch.object(native_bus, "find_path",
                         return_value={"path": [source_tile, 10, destination_tile],
                                       "source": {**records[source_tile], "step": {
                                           "kind": native_bus.STOP, "tile": source_tile,
                                           "orientation": 0, "town_id": 1,
                                       }},
                                       "destination": {**records[destination_tile], "step": {
                                           "kind": native_bus.STOP, "tile": destination_tile,
                                           "orientation": 0, "town_id": 2,
                                       }},
                                       "expansions": 1}),
            patch.object(native_bus, "road_steps", return_value=[]),
            patch.object(native_bus, "quote_step",
                         side_effect=lambda bridge, world, step: {
                             "supported_profile": True, "quote_success": True,
                             "cost": cost, "passenger_acceptance": 8,
                             "passenger_production": 1, "operation_state": 0,
                             "capacity": 100, "retained_count": 0, "error": "",
                         }),
            patch.object(native_bus, "paged", return_value=[
                {"engine_id": 3, "buildable": True, "default_cargo": 0,
                 "default_capacity": 20, "road_type": 0, "purchase_cost": cost},
            ]),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return session

    def test_plan_quotes_whole_job_and_reserve_before_recording(self):
        session = self._plan_patches(cost=100, money=10_000, reserve=500)
        plan = native_bus.plan_bus(session, 1, 2, 1_000, 500)
        self.assertEqual(plan["quoted_total"], 500)
        self.assertEqual(plan["operating_reserve"], 500)
        self.assertEqual(plan["construction_cap"], 1_000)
        self.assertGreaterEqual(session.writes, 1)

    def test_plan_rejects_whole_job_budget_and_reserve_without_writes(self):
        for cap, reserve, message in (
            (399, 0, "above construction cap"),
            (1_000, 9_701, "insufficient cash"),
        ):
            session = self._plan_patches(cost=100, money=10_000)
            with self.subTest(cap=cap, reserve=reserve), self.assertRaisesRegex(RuntimeError, message):
                native_bus.plan_bus(session, 1, 2, cap, reserve)
            self.assertEqual(session.writes, 0)

    def test_plan_record_false_does_not_write_manifest_or_history(self):
        session = self._plan_patches(cost=100)
        result = native_bus.plan_bus(session, 1, 2, 1_000, 0, record=False)
        self.assertEqual(result["quoted_total"], 500)
        self.assertEqual(session.writes, 0)
        self.assertEqual(session.manifest, {})

    def test_plan_rejects_invalid_ids_and_same_town_before_observation(self):
        session = Session(self.root)
        with self.assertRaises(ValueError):
            native_bus.plan_bus(session, True, 2, 100, 0)
        with self.assertRaisesRegex(RuntimeError, "different towns"):
            native_bus.plan_bus(session, 1, 1, 100, 0)
        session.admin.copilot_identity.assert_not_called()

    def test_plan_does_not_allow_same_candidate_endpoint_for_both_towns(self):
        session = self._plan_patches(cost=100)
        shared = tile(9, road_bits=5)
        with patch.object(native_bus, "candidate_stops", side_effect=[[shared], [shared]]):
            with self.assertRaisesRegex(RuntimeError, "route|endpoint|stop"):
                native_bus.plan_bus(session, 1, 2, 1_000, 0)

    def _execution_plan(self, *, sequence=0, head=None):
        return {
            "world_id": "world-1",
            "position": {"sequence": sequence, "head": head},
            "source": {"town_id": 1}, "destination": {"town_id": 2},
            "quoted_total": 100, "construction_cap": 1_000,
            "operating_reserve": 0,
            "steps": [{"kind": native_bus.STOP, "tile": 9, "max_cost": 50},
                      {"kind": native_bus.STOP, "tile": 11, "max_cost": 50}],
            "geometry": {"depot": {"tile": 10}},
            "engine": {"engine_id": 3, "purchase_cost": 0, "default_capacity": 20},
        }

    def test_execute_rejects_wrong_world_or_position_before_mutation(self):
        for current, message in (
            (identity(sequence=1), "differs from approved"),
            ({**identity(), "world_id": "other"}, "differs from approved"),
        ):
            session = Session(self.root)
            with patch.object(native_bus, "_identity", return_value=current), \
                 self.assertRaisesRegex(RuntimeError, message):
                native_bus.execute_bus(session, self._execution_plan(), "job")
            session.admin.copilot_mutate.assert_not_called()

    def test_execute_quote_failure_causes_zero_mutations_and_persists_partial_job(self):
        session = Session(self.root)
        plan = self._execution_plan()
        with patch.object(native_bus, "_identity", return_value=identity()), \
             patch.object(native_bus, "inspect", return_value={"buses": []}), \
             patch.object(native_bus, "quote_step",
                          return_value={"supported_profile": True, "quote_success": False,
                                        "cost": 0, "operation_state": 0, "error": "blocked"}), \
             self.assertRaisesRegex(RuntimeError, "rejected"):
            native_bus.execute_bus(session, plan, "failed")
        self.assertEqual(session.admin.copilot_mutate.call_count, 0)
        record = json.loads((self.root / "jobs" / "failed.json").read_text())
        self.assertEqual(record["state"], "partial")

    def test_execute_refuses_partial_job_retry(self):
        plan = self._execution_plan()
        jobs = self.root / "jobs"
        jobs.mkdir()
        (jobs / "partial.json").write_text(
            json.dumps({"plan": plan, "state": "partial", "outcomes": []}),
            encoding="utf-8",
        )
        session = Session(self.root)
        with patch.object(native_bus, "_identity", return_value=identity()), \
             self.assertRaisesRegex(RuntimeError, "reconciliation"):
            native_bus.execute_bus(session, plan, "partial")
        session.admin.copilot_mutate.assert_not_called()

    def test_execute_replays_completed_job_without_writes_or_mutation(self):
        plan = self._execution_plan()
        jobs = self.root / "jobs"
        jobs.mkdir()
        result = {"job_id": "done", "vehicle": 8}
        (jobs / "done.json").write_text(json.dumps({
            "plan": plan, "state": "commissioned", "outcomes": [{"outcome": identity()}],
            "result": result,
        }), encoding="utf-8")
        session = Session(self.root)
        with patch.object(native_bus, "_identity", return_value=identity()):
            self.assertEqual(native_bus.execute_bus(session, plan, "done"), result)
        session.admin.copilot_mutate.assert_not_called()
        self.assertEqual(session.writes, 0)

    def test_verify_counts_only_correct_vehicle_company_cargo_and_two_stops(self):
        session = Session(self.root)
        result = {
            "world_id": "world-1", "vehicle": 7, "source_station": 10,
            "destination_station": 20, "epoch": 3, "cursor": 0,
            "initial": {"companies": [{"loan": 2_000}]},
            "job_file": str(self.root / "jobs" / "verify.json"),
        }
        events = [
            {"kind": "delivery", "station": 10, "vehicle": 7, "company": 0, "cargo": 0, "amount": 2},
            {"kind": "delivery", "station": 20, "vehicle": 7, "company": 0, "cargo": 0, "amount": 3},
            {"kind": "delivery", "station": 10, "vehicle": 8, "company": 0, "cargo": 0, "amount": 99},
            {"kind": "delivery", "station": 20, "vehicle": 7, "company": 1, "cargo": 0, "amount": 99},
            {"kind": "delivery", "station": 20, "vehicle": 7, "company": 0, "cargo": 1, "amount": 99},
            {"kind": "delivery", "station": 20, "vehicle": 99, "company": 0, "cargo": 0, "amount": 99},
        ]
        session.admin.copilot_vehicle_events.side_effect = [
            {"epoch": 3, "gap": False, "events": events, "next_seq": 6},
        ]
        jobs = self.root / "jobs"
        jobs.mkdir()
        (jobs / "verify.json").write_text(json.dumps({"state": "commissioned"}), encoding="utf-8")
        with patch.object(native_bus, "_identity", return_value=identity()):
            verified = native_bus.verify_bus(session, result)
        self.assertEqual(verified["service_summary"]["passengers_delivered"], {"10": 2, "20": 3})
        self.assertEqual(json.loads((jobs / "verify.json").read_text())["result"], verified)
        self.assertEqual(verified["vehicle"], 7)

    def test_verify_rejects_wrong_epoch_or_event_gap(self):
        for page in (
            {"epoch": 4, "gap": False, "events": [], "next_seq": 0},
            {"epoch": 3, "gap": True, "events": [], "next_seq": 0},
        ):
            session = Session(self.root)
            session.admin.copilot_vehicle_events.return_value = page
            with self.subTest(page=page), self.assertRaisesRegex(RuntimeError, "gap/world reload"):
                native_bus.verify_bus(session, {
                    "world_id": "world-1", "vehicle": 7,
                    "source_station": 10, "destination_station": 20,
                    "epoch": 3, "cursor": 0,
                })


if __name__ == "__main__":
    unittest.main()
