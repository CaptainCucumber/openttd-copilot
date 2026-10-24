from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from tools.native_route_plan import (
    RouteSearchError, _forbidden_90, find_route, station_candidates,
)


def grid(width: int, height: int, *, blocked=(), heights=None):
    blocked = set(blocked)
    heights = heights or {}
    return [
        {"tile": y * width + x, "valid": True, "tile_type": 0, "owner": 16,
         "slope": 0, "base_height": heights.get((x, y), 0),
         **({"tile_type": 1} if y * width + x in blocked else {})}
        for y in range(height) for x in range(width)
    ]


TRACK_EDGES = {
    0: {0, 2}, 1: {1, 3}, 2: {3, 0},
    3: {2, 1}, 4: {3, 2}, 5: {0, 1},
}


class NativeRoutePlanTests(unittest.TestCase):
    def test_station_candidates_axes_and_flat_height(self):
        tiles = grid(8, 8, heights={(2, 1): 1})
        candidates = station_candidates(tiles, 8, 8,
                                        {"tile": 2 * 8 + 2, "width": 1, "height": 1})
        self.assertTrue(any(c["axis"] == 0 for c in candidates))
        self.assertTrue(any(c["axis"] == 1 for c in candidates))
        self.assertTrue(all(len(c["footprint"]) == 2 for c in candidates))
        self.assertFalse(any(c["tile"] == 2 * 8 + 2 - 8 and c["axis"] in (0, 1)
                             for c in candidates))

    def test_routes_with_curves_and_all_source_directions(self):
        tiles = grid(12, 8)
        source = station_candidates(tiles, 12, 8, {"tile": 2 * 12 + 1, "width": 1, "height": 1})
        dest = station_candidates(tiles, 12, 8, {"tile": 5 * 12 + 9, "width": 1, "height": 1})
        plan = find_route(tiles, 12, 8, source[:8], dest[:8], max_rail_tiles=40)
        self.assertGreaterEqual(len(plan["rails"]), 1)
        self.assertEqual(plan["operation_count"], len(plan["rails"]) + 9)
        self.assertEqual(len(plan["footprint"]), len(set(plan["footprint"])))
        json.dumps(plan)
        for rail in plan["rails"]:
            self.assertIn(rail["track"], range(6))

    def test_avoids_blocked_tiles_and_border_wrap(self):
        tiles = grid(10, 10, blocked={55})
        source = station_candidates(tiles, 10, 10, {"tile": 11, "location_width": 1,
                                                    "location_height": 1})
        dest = station_candidates(tiles, 10, 10, {"tile": 77, "location_width": 1,
                                                  "location_height": 1})
        plan = find_route(tiles, 10, 10, source[:8], dest[:8], max_rail_tiles=40)
        self.assertNotIn(55, plan["footprint"])
        for tile in plan["footprint"]:
            self.assertGreaterEqual(tile % 10, 0)
            self.assertLess(tile % 10, 10)

    def test_respects_capacity_and_search_bounds(self):
        tiles = grid(10, 10)
        source = [{"tile": 11, "axis": 1, "length": 2, "footprint": (11, 21)}]
        dest = [{"tile": 67, "axis": 1, "length": 2, "footprint": (67, 77)}]
        with self.assertRaisesRegex(RouteSearchError, "at most 2"):
            find_route(tiles, 10, 10, source, dest, max_rail_tiles=2)
        with self.assertRaisesRegex(RouteSearchError, "expansion bound"):
            find_route(tiles, 10, 10, source, dest, max_expansions=1)

    def test_distant_candidates_reject_before_search_with_length_bound(self):
        source = [{"tile": 37, "axis": 0, "length": 2, "footprint": [37, 38]}]
        destination = [{"tile": 99, "axis": 0, "length": 2, "footprint": [99, 100]}]
        with patch("tools.native_route_plan._search_pair") as search:
            with self.assertRaises(RouteSearchError) as error:
                find_route(grid(12, 12), 12, 12, source, destination, max_rail_tiles=2)
        search.assert_not_called()
        self.assertEqual(error.exception.kind, "route_length_limit")
        self.assertIn("at least 5 rail tiles", str(error.exception))
        self.assertIn("at most 2", str(error.exception))

    def test_exact_lower_bound_is_not_rejected(self):
        source = [{"tile": 31, "axis": 0, "length": 2, "footprint": [31, 32]}]
        destination = [{"tile": 37, "axis": 0, "length": 2, "footprint": [37, 38]}]
        plan = find_route(grid(10, 10), 10, 10, source, destination, max_rail_tiles=4)
        self.assertEqual(len(plan["rails"]), 4)

    def test_deterministic_and_rejects_owned_or_sloped_station(self):
        tiles = grid(8, 8)
        tiles[0]["owner"] = 0
        tiles[1]["slope"] = 1
        source = [{"tile": 0, "axis": 0, "length": 2, "footprint": (0, 1)}]
        dest = [{"tile": 54, "axis": 0, "length": 2, "footprint": (54, 55)}]
        with self.assertRaises(ValueError):
            find_route(tiles, 8, 8, source, dest)
        clean = grid(8, 8)
        candidates = station_candidates(clean, 8, 8, {"tile": 8 + 1, "width": 1, "height": 1})
        a = station_candidates(clean, 8, 8, {"tile": 8 + 1, "width": 1, "height": 1})
        self.assertEqual(candidates, a)

    def test_axis_headings_depot_edge_and_json_native_output(self):
        tiles = grid(12, 12)
        for axis, source_fp, destination_fp, expected_heading in (
            (0, [37, 38], [99, 100], 2),
            (1, [37, 49], [99, 111], 1),
        ):
            source = [{"tile": source_fp[0], "axis": axis, "length": 2,
                       "footprint": source_fp}]
            destination = [{"tile": destination_fp[0], "axis": axis, "length": 2,
                            "footprint": destination_fp}]
            plan = find_route(tiles, 12, 12, source, destination, max_rail_tiles=50)
            self.assertEqual(plan["depot"]["orientation"], expected_heading)
            self.assertEqual(plan["source_station"]["forward"], expected_heading)
            self.assertIsInstance(plan["footprint"], list)
            self.assertIsInstance(plan["source_station"]["footprint"], list)
            json.dumps(plan)

    def test_curves_have_reciprocal_edges_and_destination_approach(self):
        tiles = grid(12, 12)
        source = [{"tile": 37, "axis": 0, "length": 2, "footprint": [37, 38]}]
        destination = [{"tile": 99, "axis": 1, "length": 2, "footprint": [99, 111]}]
        plan = find_route(tiles, 12, 12, source, destination, max_rail_tiles=50)
        rail_by_tile = {piece["tile"]: piece["track"] for piece in plan["rails"]}
        self.assertTrue(any(len(TRACK_EDGES[piece["track"]]) == 2
                            and piece["track"] in (2, 3, 4, 5)
                            for piece in plan["rails"]))
        for tile, track in rail_by_tile.items():
            x, y = tile % 12, tile // 12
            for edge in TRACK_EDGES[track]:
                dx, dy = ((-1, 0), (0, 1), (1, 0), (0, -1))[edge]
                neighbour = (x + dx, y + dy)
                neighbour_tile = neighbour[1] * 12 + neighbour[0]
                if neighbour_tile in rail_by_tile:
                    opposite = (edge + 2) % 4
                    self.assertIn(opposite, TRACK_EDGES[rail_by_tile[neighbour_tile]])
        inward = plan["destination_station"]["inward"]
        first = plan["destination_station"]["footprint"][0 if inward == 2 or inward == 1 else 1]
        self.assertIn(first, {
            y * 12 + x
            for piece in plan["rails"]
            for edge in TRACK_EDGES[piece["track"]]
            for x, y in [(piece["tile"] % 12 + ((-1, 0), (0, 1), (1, 0), (0, -1))[edge][0],
                         piece["tile"] // 12 + ((-1, 0), (0, 1), (1, 0), (0, -1))[edge][1])]
        })

    def test_track_sequence_never_uses_forbidden_ninety_degree_transition(self):
        tiles = grid(12, 12)
        source = [{"tile": 37, "axis": 0, "length": 2, "footprint": [37, 38]}]
        destination = [{"tile": 99, "axis": 0, "length": 2, "footprint": [99, 100]}]
        plan = find_route(tiles, 12, 12, source, destination, max_rail_tiles=50)
        sequence = [0] + [piece["track"] for piece in plan["rails"]] + [0]
        self.assertFalse(any(_forbidden_90(previous, current)
                             for previous, current in zip(sequence, sequence[1:])))
        self.assertFalse(any((previous, current) in ((2, 5), (5, 2))
                             for previous, current in zip(sequence, sequence[1:])))
        self.assertEqual(len(plan["rails"]), len({piece["tile"] for piece in plan["rails"]}))

    def test_rejects_missing_or_malformed_observation_and_station_tiles(self):
        malformed = grid(6, 6)
        for field in ("valid", "tile_type", "owner", "slope", "base_height"):
            tiles = [dict(record) for record in malformed]
            for tile in tiles:
                del tile[field]
            candidates = station_candidates(tiles, 6, 6, {"tile": 7, "width": 1, "height": 1})
            self.assertEqual(candidates, [], field)
        with self.assertRaisesRegex(ValueError, "must include tile"):
            station_candidates([{"valid": True}], 6, 6,
                               {"tile": 7, "width": 1, "height": 1})
        with self.assertRaisesRegex(ValueError, "must equal footprint"):
            find_route(grid(8, 8), 8, 8,
                       [{"tile": 1, "axis": 0, "length": 2, "footprint": [2, 3]}],
                       [{"tile": 60, "axis": 0, "length": 2, "footprint": [60, 61]}])
        with self.assertRaisesRegex(ValueError, "was not observed"):
            observed = [tile for tile in grid(8, 8) if tile["tile"] != 61]
            find_route(observed, 8, 8,
                       [{"tile": 1, "axis": 0, "length": 2, "footprint": [1, 2]}],
                       [{"tile": 60, "axis": 0, "length": 2, "footprint": [60, 61]}])


if __name__ == "__main__":
    unittest.main()
