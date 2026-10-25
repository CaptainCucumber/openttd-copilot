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

    def test_find_path_uses_non_normal_station_tiles_only_when_explicit_anchors(self):
        records = {
            9: tile(9, tile_type=5, road_bits=5, owner=0, road_type=0, normal_road=False),
            10: tile(10, road_bits=5),
            11: tile(11, tile_type=5, road_bits=5, owner=0, road_type=0, normal_road=False),
        }
        with self.assertRaisesRegex(RuntimeError, "no bus route"):
            native_bus.find_path(records, 8, 8, [records[9]], [records[11]], max_expansions=20)
        result = native_bus.find_path(
            records, 8, 8, [records[9]], [records[11]],
            anchor_tiles={9, 11}, max_expansions=20,
        )
        self.assertEqual(result["path"], [9, 10, 11])
        self.assertFalse(records[9]["normal_road"])
        self.assertEqual(records[9]["tile_type"], 5)

    def test_find_path_can_traverse_third_explicit_old_line_stop_between_anchors(self):
        records = {
            9: tile(9, tile_type=5, road_bits=5, owner=0, road_type=0, normal_road=False),
            10: tile(10, road_bits=5),
            11: tile(11, tile_type=5, road_bits=5, owner=0, road_type=0, normal_road=False),
            12: tile(12, road_bits=5),
            13: tile(13, tile_type=5, road_bits=5, owner=0, road_type=0, normal_road=False),
        }
        with self.assertRaisesRegex(RuntimeError, "no bus route"):
            native_bus.find_path(
                records, 8, 8, [records[9]], [records[13]],
                anchor_tiles={9, 13}, max_expansions=20,
            )
        result = native_bus.find_path(
            records, 8, 8, [records[9]], [records[13]],
            anchor_tiles={9, 11, 13}, max_expansions=20,
        )
        self.assertEqual(result["path"], [9, 10, 11, 12, 13])
        self.assertEqual(native_bus.merge_road_steps(
            [result["path"]], records, 8, 8, protected={9, 11, 13}), [])

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

    def test_plan_multi_town_reuses_exact_intermediate_and_combines_job_counts(self):
        session = Session(self.root)
        towns = [
            {"town_id": 1, "name": "A", "tile": 9},
            {"town_id": 2, "name": "B", "tile": 11},
            {"town_id": 3, "name": "C", "tile": 13},
        ]
        first = {9: tile(9), 10: tile(10), 11: tile(11), 18: tile(18, tile_type=0)}
        second = {11: tile(11), 12: tile(12), 13: tile(13)}
        path_calls = []

        def path(records, width, height, sources, destinations):
            path_calls.append((sources, destinations))
            return {
                "path": [sources[0]["tile"], sources[0]["tile"] + 1, destinations[0]["tile"]],
                "source": sources[0], "destination": destinations[0], "expansions": 1,
            }

        quote = {
            "supported_profile": True, "quote_success": True, "cost": 10,
            "passenger_acceptance": 8, "passenger_production": 1,
            "operation_state": 0, "capacity": 100, "retained_count": 0, "error": "",
        }
        with patch.object(native_bus, "_identity", return_value=identity()), \
             patch.object(native_bus, "discover", return_value=towns), \
             patch.object(native_bus, "read_corridor", side_effect=[(first, [2, 3]), (second, [4, 5])]), \
             patch.object(native_bus, "candidate_stops",
                          side_effect=[[first[9]], [first[11]], [second[13]]]), \
             patch.object(native_bus, "find_path", side_effect=path), \
             patch.object(native_bus, "quote_step", return_value=quote), \
             patch.object(native_bus, "paged", return_value=[{
                 "engine_id": 3, "buildable": True, "default_cargo": 0,
                 "default_capacity": 20, "road_type": 0, "purchase_cost": 20,
             }]):
            plan = native_bus.plan_bus(session, 1, 3, 1_000, 0, via_town_ids=(2,))
        self.assertIs(path_calls[1][0][0], path_calls[0][1][0])
        self.assertEqual(plan["town_ids"], [1, 2, 3])
        self.assertEqual(plan["geometry"]["paths"], [[9, 10, 11], [11, 12, 13]])
        self.assertEqual(plan["observation_frame_span"], [2, 5])
        self.assertEqual(plan["operation_count"], len(plan["steps"]) + 5)
        self.assertEqual([step["town_id"] for step in plan["steps"] if step["kind"] == native_bus.STOP],
                         [1, 2, 3])

    def test_merge_road_steps_merges_masks_and_protects_selected_stops(self):
        records = {
            9: tile(9, road_bits=1),
            10: tile(10, road_bits=0, tile_type=0),
            18: tile(18, road_bits=0, tile_type=0),
        }
        steps = native_bus.merge_road_steps([[9, 10], [10, 18]], records, 8, 8)
        self.assertEqual({step["tile"]: step["road_bits"] for step in steps},
                         {9: 5, 10: 3, 18: 8})
        with self.assertRaisesRegex(RuntimeError, "station road bits"):
            native_bus.merge_road_steps([[9, 10]], {
                9: tile(9, road_bits=1), 10: tile(10, road_bits=0, tile_type=0),
            }, 8, 8, protected=[9])

    def _observed_existing_bus(self, *, orders_shared=False, crashed=False, stopped=False, orders=None):
        orders = orders or [
            {"order_type": 1, "destination_id": 10, "load_type": 0, "unload_type": 0, "non_stop": 0},
            {"order_type": 1, "destination_id": 20, "load_type": 0, "unload_type": 0, "non_stop": 0},
            {"order_type": 1, "destination_id": 40, "load_type": 0, "unload_type": 0, "non_stop": 0},
        ]
        vehicle = {
            "vehicle_id": 7, "owner": 0, "engine_id": 3, "cargo_type": 0,
            "cargo_capacity": 20, "orders_shared": orders_shared, "crashed": crashed,
            "stopped": stopped, "tile": 22, "orders": orders,
        }
        stops = [
            {"station_id": 10, "town_id": 1, "tile": 9, "road_bits": 5},
            {"station_id": 20, "town_id": 2, "tile": 11, "road_bits": 5},
            {"station_id": 40, "town_id": 4, "tile": 13, "road_bits": 5},
        ]
        return {"buses": [vehicle], "bus_stops": stops, "towns": [], "bus_engines": []}

    def test_existing_bus_validation_rejects_shared_nonordinary_crashed_and_stopped(self):
        cases = [
            (self._observed_existing_bus(orders_shared=True), "shared"),
            (self._observed_existing_bus(crashed=True), "crashed"),
            (self._observed_existing_bus(stopped=True), "stopped"),
            (self._observed_existing_bus(orders=[
                {"order_type": 2, "destination_id": 10, "load_type": 0, "unload_type": 0, "non_stop": 0},
                {"order_type": 1, "destination_id": 20, "load_type": 0, "unload_type": 0, "non_stop": 0},
            ]), "ordinary"),
        ]
        for observed, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(RuntimeError, message):
                native_bus._existing_bus(observed, 7)

    def test_existing_bus_accepts_exact_engine_stop_schema_plus_authoritative_town(self):
        observed = self._observed_existing_bus()
        observed["bus_stops"] = [
            {"station_id": station, "stop_id": index, "tile": tile_id,
             "orientation": 0, "owner": 0, "town_id": town}
            for index, (station, tile_id, town) in enumerate(
                ((10, 9, 1), (20, 11, 2), (40, 13, 4)))
        ]
        _, _, stops = native_bus._existing_bus(observed, 7)
        self.assertEqual(native_bus._stop_fingerprint(stops), [
            {"station_id": 10, "stop_id": 0, "tile": 9, "orientation": 0, "owner": 0, "town_id": 1},
            {"station_id": 20, "stop_id": 1, "tile": 11, "orientation": 0, "owner": 0, "town_id": 2},
            {"station_id": 40, "stop_id": 2, "tile": 13, "orientation": 0, "owner": 0, "town_id": 4},
        ])

    def test_plan_bus_stops_has_common_preview_shape_and_no_record_when_requested(self):
        observed = self._observed_existing_bus(orders=[
            {"order_type": 1, "destination_id": 10, "load_type": 0, "unload_type": 0, "non_stop": 0},
            {"order_type": 1, "destination_id": 40, "load_type": 0, "unload_type": 0, "non_stop": 0},
        ])
        observed["towns"] = [{"town_id": 3, "name": "C", "tile": 11}]
        observed["bus_engines"] = [{
            "engine_id": 3, "buildable": True, "default_cargo": 0,
            "default_capacity": 20, "road_type": 0, "purchase_cost": 100,
        }]
        first = {9: tile(9, tile_type=5, owner=0), 10: tile(10), 11: tile(11)}
        second = {11: tile(11), 12: tile(12), 13: tile(13, tile_type=5, owner=0)}
        chosen = {**first[11], "step": {
            "kind": native_bus.STOP, "tile": 11, "orientation": 0, "town_id": 3, "max_cost": 10,
        }}
        paths = [
            {"path": [9, 10, 11], "source": {**first[9], "tile_type": 2, "station_id": 10},
             "destination": chosen, "expansions": 1},
            {"path": [11, 12, 13], "source": chosen,
             "destination": {**second[13], "tile_type": 2, "station_id": 40}, "expansions": 1},
        ]
        session = Session(self.root)
        quote = {
            "supported_profile": True, "quote_success": True, "cost": 10,
            "passenger_acceptance": 8, "passenger_production": 1,
            "operation_state": 0, "capacity": 100, "retained_count": 0, "error": "",
        }
        with patch.object(native_bus, "_identity", return_value=identity()), \
             patch.object(native_bus, "inspect", return_value=observed), \
             patch.object(native_bus, "read_corridor", side_effect=[(first, [2, 3]), (second, [4, 5])]), \
             patch.object(native_bus, "candidate_stops", return_value=[first[11]]), \
             patch.object(native_bus, "find_path", side_effect=paths), \
             patch.object(native_bus, "road_steps", return_value=[]), \
             patch.object(native_bus, "quote_step", return_value=quote):
            plan = native_bus.plan_bus_stops(session, 7, [3], 1, 100, 5, record=False)
        self.assertEqual(plan["mode"], "add_stops")
        self.assertEqual(plan["vehicle_id"], 7)
        self.assertEqual(plan["town_ids"], [3])
        self.assertEqual(plan["insert_index"], 1)
        self.assertEqual(plan["quoted_total"], 10)
        self.assertEqual(plan["operation_count"], 4)
        self.assertEqual(plan["geometry"]["path"], [9, 10, 11, 12, 13])
        self.assertEqual(plan["observation_frame_span"], [2, 5])
        self.assertEqual(plan["engine"]["engine_id"], 3)
        self.assertEqual(session.writes, 0)
        self.assertEqual(session.manifest, {})

    def test_execute_add_stops_inserts_at_beginning_middle_and_end_without_purchase(self):
        class Executor:
            calls = []

            def __init__(self, session, plan, job_id, record, job_file, identity_value, operation):
                self.record = record

            def mutate(self, method, fields, cap, operation_id):
                self.calls.append(dict(fields))
                self.record["spent"] += cap
                return {"created_asset_id": 30, "outcome": identity()}

        for insertion in (0, 1, 3):
            with self.subTest(insertion=insertion):
                observed = self._observed_existing_bus()
                old_orders = native_bus._order_fingerprint(observed["buses"][0]["orders"])
                expected = list(old_orders)
                expected.insert(insertion, {
                    "order_type": 1, "destination_id": 30, "load_type": 0,
                    "unload_type": 0, "non_stop": 0,
                })
                running_after_build = json.loads(json.dumps(observed))
                running_after_build["bus_stops"].append(
                    {"station_id": 30, "town_id": 3, "tile": 12, "road_bits": 5})
                stopped = json.loads(json.dumps(running_after_build))
                stopped["buses"][0]["stopped"] = True
                configured = json.loads(json.dumps(stopped))
                configured["buses"][0]["orders"] = expected
                plan = {
                    "mode": "add_stops", "world_id": "world-1", "position": {"sequence": 0, "head": None},
                    "vehicle_id": 7, "vehicle_snapshot": native_bus._vehicle_snapshot(observed["buses"][0]),
                    "old_orders": old_orders, "old_order_fingerprint": old_orders,
                    "old_stops": observed["bus_stops"], "insert_index": insertion,
                    "town_ids": [3], "source": {"town_id": 3}, "destination": {"town_id": 3},
                    "steps": [{"kind": native_bus.STOP, "tile": 12, "town_id": 3, "max_cost": 10}],
                    "construction_cap": 100, "operating_reserve": 0,
                }
                session = Session(self.root)
                session.admin.copilot_vehicle_events.return_value = {
                    "epoch": 1, "gap": False, "events": [], "next_seq": 0,
                }
                Executor.calls = []
                job_id = f"insert-{insertion}"
                with patch.object(native_bus, "_identity", return_value=identity()), \
                     patch.object(native_bus, "inspect", side_effect=[
                         observed, running_after_build, stopped, stopped, configured,
                     ]), \
                     patch.object(native_bus, "quote_step", return_value={
                         "supported_profile": True, "quote_success": True, "cost": 10,
                         "passenger_acceptance": 8, "passenger_production": 1,
                         "operation_state": 0, "error": "",
                     }), \
                     patch.object(native_bus, "JournaledExecutor", Executor):
                    result = native_bus.execute_bus(session, plan, job_id)
                self.assertEqual(result["stations"], [order["destination_id"] for order in expected])
                self.assertEqual(result["vehicle"], 7)
                self.assertNotIn(native_bus.PURCHASE, [call["kind"] for call in Executor.calls])
                order_call = next(call for call in Executor.calls if call["kind"] == native_bus.ORDER)
                self.assertEqual(order_call["order_index"], insertion)

    def test_execute_adds_two_ordered_stops_at_exact_middle_indices_and_preserves_fingerprints(self):
        class Executor:
            calls = []
            stop_ids = iter((30, 31))

            def __init__(self, session, plan, job_id, record, job_file, identity_value, operation):
                self.record = record

            def mutate(self, method, fields, cap, operation_id):
                self.calls.append(dict(fields))
                self.record["spent"] += cap
                created = next(self.stop_ids) if fields["kind"] == native_bus.STOP else 0
                return {"created_asset_id": created, "outcome": identity()}

        observed = self._observed_existing_bus()
        old_orders = native_bus._order_fingerprint(observed["buses"][0]["orders"])
        old_stops = native_bus._stop_fingerprint(observed["bus_stops"])
        after_build = json.loads(json.dumps(observed))
        after_build["bus_stops"].extend([
            {"station_id": 30, "town_id": 3, "tile": 12},
            {"station_id": 31, "town_id": 5, "tile": 14},
        ])
        stopped = json.loads(json.dumps(after_build))
        stopped["buses"][0]["stopped"] = True
        after_first = json.loads(json.dumps(stopped))
        after_first["buses"][0]["orders"] = [
            old_orders[0],
            {"order_type": 1, "destination_id": 30, "load_type": 0, "unload_type": 0, "non_stop": 0},
            *old_orders[1:],
        ]
        final = json.loads(json.dumps(after_first))
        final["buses"][0]["orders"].insert(2, {
            "order_type": 1, "destination_id": 31, "load_type": 0, "unload_type": 0, "non_stop": 0,
        })
        plan = {
            "mode": "add_stops", "world_id": "world-1", "position": {"sequence": 0, "head": None},
            "vehicle_id": 7, "vehicle_snapshot": native_bus._vehicle_snapshot(observed["buses"][0]),
            "old_orders": old_orders, "old_order_fingerprint": old_orders,
            "old_stops": observed["bus_stops"], "old_stop_fingerprint": old_stops,
            "insert_index": 1, "town_ids": [3, 5],
            "steps": [
                {"kind": native_bus.STOP, "tile": 12, "town_id": 3, "max_cost": 10},
                {"kind": native_bus.STOP, "tile": 14, "town_id": 5, "max_cost": 10},
            ],
            "quoted_total": 20, "construction_cap": 100, "operating_reserve": 0,
        }
        session = Session(self.root)
        session.admin.copilot_vehicle_events.return_value = {
            "epoch": 1, "gap": False, "events": [], "next_seq": 0,
        }
        Executor.calls = []
        Executor.stop_ids = iter((30, 31))
        with patch.object(native_bus, "_identity", return_value=identity()), \
             patch.object(native_bus, "inspect", side_effect=[
                 observed, after_build, stopped, stopped, after_first, after_first, final,
             ]), \
             patch.object(native_bus, "quote_step", return_value={
                 "supported_profile": True, "quote_success": True, "cost": 10,
                 "passenger_acceptance": 8, "passenger_production": 1,
                 "operation_state": 0, "error": "",
             }), \
             patch.object(native_bus, "JournaledExecutor", Executor):
            result = native_bus.execute_bus(session, plan, "insert-two")
        self.assertEqual([order["destination_id"] for order in result["orders"]], [10, 30, 31, 20, 40])
        self.assertEqual(result["old_orders"], old_orders)
        self.assertEqual([call["order_index"] for call in Executor.calls
                          if call["kind"] == native_bus.ORDER], [1, 2])
        self.assertEqual(native_bus._order_fingerprint(observed["buses"][0]["orders"]), old_orders)
        self.assertEqual(native_bus._stop_fingerprint(observed["bus_stops"]), old_stops)

    def test_execute_add_stops_rejects_stale_orders_before_first_mutation(self):
        observed = self._observed_existing_bus()
        fingerprint = native_bus._order_fingerprint(observed["buses"][0]["orders"])
        plan = {
            "mode": "add_stops", "world_id": "world-1", "position": {"sequence": 0, "head": None},
            "vehicle_id": 7, "vehicle_snapshot": native_bus._vehicle_snapshot(observed["buses"][0]),
            "old_orders": fingerprint, "old_order_fingerprint": fingerprint,
            "old_stops": observed["bus_stops"], "insert_index": 1, "town_ids": [3],
            "steps": [], "quoted_total": 0, "construction_cap": 100, "operating_reserve": 0,
        }
        observed["buses"][0]["orders"][0], observed["buses"][0]["orders"][1] = (
            observed["buses"][0]["orders"][1], observed["buses"][0]["orders"][0])
        session = Session(self.root)
        with patch.object(native_bus, "_identity", return_value=identity()), \
             patch.object(native_bus, "inspect", return_value=observed), \
             self.assertRaisesRegex(RuntimeError, "orders changed"):
            native_bus.execute_bus(session, plan, "stale")
        session.admin.copilot_mutate.assert_not_called()

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

    def test_verify_requires_attributed_passengers_at_every_ordered_stop(self):
        session = Session(self.root)
        result = {
            "world_id": "world-1", "vehicle": 7, "source_station": 10,
            "destination_station": 30, "stations": [10, 20, 30],
            "epoch": 3, "cursor": 0, "initial": {"companies": [{"loan": 2_000}]},
            "job_file": str(self.root / "jobs" / "all-stops.json"),
        }
        session.admin.copilot_vehicle_events.return_value = {
            "epoch": 3, "gap": False, "next_seq": 3, "events": [
                {"kind": "delivery", "station": station, "vehicle": 7,
                 "company": 0, "cargo": 0, "amount": station // 10}
                for station in (10, 20, 30)
            ],
        }
        jobs = self.root / "jobs"
        jobs.mkdir()
        (jobs / "all-stops.json").write_text(json.dumps({"state": "commissioned"}), encoding="utf-8")
        with patch.object(native_bus, "_identity", return_value=identity()):
            verified = native_bus.verify_bus(session, result)
        self.assertEqual(verified["service_summary"]["passengers_delivered"],
                         {"10": 1, "20": 2, "30": 3})

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
