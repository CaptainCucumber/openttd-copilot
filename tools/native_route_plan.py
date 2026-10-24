"""Pure, deterministic flat-clear rail route planning.

This module deliberately knows nothing about OpenTTD commands.  It consumes an
already resolved tile observation and industry records, and returns a bounded
proposal for the parent executor to quote and revalidate.
"""

from __future__ import annotations

from heapq import heappop, heappush
from typing import Any, Mapping, Sequence


_DIRECTIONS = ((-1, 0), (0, 1), (1, 0), (0, -1))
_TRACKS = {
    frozenset((0, 2)): 0,
    frozenset((1, 3)): 1,
    frozenset((3, 0)): 2,
    frozenset((2, 1)): 3,
    frozenset((3, 2)): 4,
    frozenset((0, 1)): 5,
}
_TRACK_CROSSES = (0, 1, 2, 2, 3, 3)


def _forbidden_90(previous: int, current: int) -> bool:
    """Conservative equivalent of OpenTTD's default no-90-degree rule."""
    categories = {_TRACK_CROSSES[previous], _TRACK_CROSSES[current]}
    return previous != current and categories in ({0, 1}, {2, 3})


class RouteSearchError(RuntimeError):
    """A route was not returned; ``kind`` distinguishes a bounded search."""

    def __init__(self, message: str, *, kind: str = "no_route") -> None:
        super().__init__(message)
        self.kind = kind


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _normalise_tiles(
    tiles: Mapping[Any, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    map_width: int,
    map_height: int,
) -> dict[int, dict[str, Any]]:
    """Normalize a tile-record mapping or list.

    Lists must contain ``tile``; mappings may use the tile ID as the key.  Each
    record is copied and receives deterministic ``tile``, ``x``, and ``y``
    fields.  A native snapshot's ``rows`` is intentionally not accepted here:
    callers should flatten that observation explicitly at the API boundary.
    """
    result: dict[int, dict[str, Any]] = {}
    records = tiles.items() if isinstance(tiles, Mapping) else ((None, raw) for raw in tiles)
    for key, raw in records:
        if not isinstance(raw, Mapping):
            raise ValueError("each tile record must be a mapping")
        record = dict(raw)
        if key is None and "tile" not in record:
            raise ValueError("tile record must include tile")
        tile_value = record.get("tile", key)
        tile = _int(tile_value, "tile")
        if key is not None and not isinstance(key, bool) and isinstance(key, int) and tile != key:
            raise ValueError("tile record key and tile disagree")
        if tile < 0 or tile >= map_width * map_height:
            raise ValueError("tile is outside the map")
        if tile in result:
            raise ValueError(f"duplicate tile record {tile}")
        record["tile"] = tile
        record["x"] = tile % map_width
        record["y"] = tile // map_width
        result[tile] = record
    return result


def _flat_clear(record: Mapping[str, Any], height: int | None = None) -> bool:
    valid = record.get("valid_tile", record.get("valid"))
    tile_type = record.get("tile_type", record.get("type"))
    owner = record.get("owner")
    slope = record.get("slope")
    actual_height = record.get("base_height", record.get("height"))
    if (type(valid) is not bool or valid is not True
            or any(type(value) is not int for value in (tile_type, owner, slope, actual_height))
            or tile_type != 0 or owner != 16 or slope != 0):
        return False
    return height is None or actual_height == height


def _industry_rect(industry: Mapping[str, Any], width: int, height: int) -> tuple[int, int, int, int]:
    tile = industry.get("tile")
    if isinstance(tile, Mapping):
        x, y = _int(tile["x"], "industry tile x"), _int(tile["y"], "industry tile y")
    else:
        tile_id = _int(tile, "industry tile")
        x, y = tile_id % width, tile_id // width
    iw = _int(industry.get("width", industry.get("location_width", 1)), "industry width")
    ih = _int(industry.get("height", industry.get("location_height", 1)), "industry height")
    if iw < 1 or ih < 1 or x < 0 or y < 0 or x + iw > width or y + ih > height:
        raise ValueError("industry rectangle is outside the map")
    return x, y, iw, ih


def _distance_to_rect(x: int, y: int, rect: tuple[int, int, int, int]) -> int:
    rx, ry, rw, rh = rect
    dx = max(rx - x, 0, x - (rx + rw - 1))
    dy = max(ry - y, 0, y - (ry + rh - 1))
    return dx + dy


def station_candidates(
    tiles: Mapping[Any, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    map_width: int,
    map_height: int,
    industry: Mapping[str, Any],
    max_candidates: int = 32,
) -> list[dict[str, Any]]:
    """Return sorted, flat-clear two-tile station proposals within catchment 4.

    ``axis`` is 0 for the increasing-x pair and 1 for increasing-y.  ``tile``
    is the lower/left tile and ``footprint`` is the ordered pair of tile IDs.
    Catchment is only a geometric proposal; the executor must quote coverage.
    """
    map_width, map_height = _int(map_width, "map_width"), _int(map_height, "map_height")
    if map_width < 2 or map_height < 2:
        raise ValueError("map dimensions must be at least 2")
    max_candidates = _int(max_candidates, "max_candidates")
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    records = _normalise_tiles(tiles, map_width, map_height)
    rect = _industry_rect(industry, map_width, map_height)
    candidates: list[tuple[int, int, int, dict[str, Any]]] = []
    for tile, record in records.items():
        x, y = record["x"], record["y"]
        for axis in (0, 1):
            nx, ny = (x + 1, y) if axis == 0 else (x, y + 1)
            if nx >= map_width or ny >= map_height:
                continue
            other = ny * map_width + nx
            if other not in records or not _flat_clear(record):
                continue
            if not _flat_clear(records[other], record.get("base_height", record.get("height"))):
                continue
            distance = min(_distance_to_rect(x, y, rect), _distance_to_rect(nx, ny, rect))
            if distance > 4:
                continue
            candidate = {
                "tile": tile,
                "axis": axis,
                "length": 2,
                "footprint": [tile, other],
            }
            candidates.append((distance, tile, axis, candidate))
    candidates.sort(key=lambda item: item[:3])
    return [candidate for _, _, _, candidate in candidates[:max_candidates]]


def _candidate_geometry(
    candidate: Mapping[str, Any],
    records: Mapping[int, Mapping[str, Any]],
    width: int,
    height: int,
) -> tuple[int, int, tuple[int, int]]:
    tile = _int(candidate["tile"], "station tile")
    axis = _int(candidate["axis"], "station axis")
    if axis not in (0, 1) or candidate.get("length", 2) != 2:
        raise ValueError("stations must be length two on axis 0 or 1")
    if "footprint" not in candidate:
        footprint = (tile, tile + (1 if axis == 0 else width))
    else:
        footprint = tuple(candidate["footprint"])
    if len(footprint) != 2:
        raise ValueError("station footprint must contain two tiles")
    footprint = tuple(_int(value, "station footprint tile") for value in footprint)
    if tile != footprint[0]:
        raise ValueError("station tile must equal footprint[0]")
    if any(value < 0 or value >= width * height for value in footprint):
        raise ValueError("station footprint is outside the map")
    missing = [value for value in footprint if value not in records]
    if missing:
        raise ValueError(f"station footprint tile {missing[0]} was not observed")
    first = records[footprint[0]]
    second = records[footprint[1]]
    if axis == 0 and (second.get("x") != first.get("x", 0) + 1
                      or second.get("y") != first.get("y", 0)):
        raise ValueError("station footprint must increase along its axis")
    if axis == 1 and (second.get("y") != first.get("y", 0) + 1
                      or second.get("x") != first.get("x", 0)):
        raise ValueError("station footprint must increase along its axis")
    if any(not _flat_clear(records[value]) for value in footprint):
        raise ValueError("station candidate is not flat, clear, valid, and unowned")
    heights = {records[value].get("base_height", records[value].get("height")) for value in footprint}
    if len(heights) != 1:
        raise ValueError("station footprint heights differ")
    return tile, axis, footprint


def _tile(x: int, y: int, width: int, height: int) -> int | None:
    if x < 0 or y < 0 or x >= width or y >= height:
        return None
    return y * width + x


def _neighbour(tile: int, direction: int, width: int, height: int) -> int | None:
    x, y = tile % width, tile // width
    dx, dy = _DIRECTIONS[direction]
    return _tile(x + dx, y + dy, width, height)


def _search_pair(
    records: Mapping[int, Mapping[str, Any]],
    width: int,
    height: int,
    source: Mapping[str, Any],
    destination: Mapping[str, Any],
    max_rail_tiles: int,
    max_expansions: int,
    budget: dict[str, int],
) -> tuple[list[dict[str, int]], dict[str, Any], dict[str, Any]] | None:
    source_tile, source_axis, source_fp = _candidate_geometry(source, records, width, height)
    dest_tile, dest_axis, dest_fp = _candidate_geometry(destination, records, width, height)
    if set(source_fp) & set(dest_fp):
        return None
    reserved = set(source_fp) | set(dest_fp)
    source_height = records[source_fp[0]].get("base_height", records[source_fp[0]].get("height"))
    dest_height = records[dest_fp[0]].get("base_height", records[dest_fp[0]].get("height"))
    if source_height != dest_height:
        return None

    positive_source = (2, 1)[source_axis]
    for forward in (positive_source, (positive_source + 2) % 4):
        source_first = source_fp[0] if forward == positive_source else source_fp[1]
        depot = _neighbour(source_first, (forward + 2) % 4, width, height)
        exit_tile = _neighbour(source_fp[1] if forward == positive_source else source_fp[0],
                                forward, width, height)
        if depot is None or exit_tile is None or depot in reserved or exit_tile in reserved:
            continue
        if depot not in records or exit_tile not in records:
            continue
        if not _flat_clear(records[depot], source_height) or not _flat_clear(records[exit_tile], source_height):
            continue
        if depot == exit_tile:
            continue

        positive_destination = (2, 1)[dest_axis]
        for inward in (positive_destination, (positive_destination + 2) % 4):
            dest_first = dest_fp[0] if inward == positive_destination else dest_fp[1]
            initial_entry = (forward + 2) % 4
            # (estimated cost, cost, turns, tile, entry, previous exit, path)
            initial_track = source_axis
            queue: list[tuple[int, int, int, int, int, int, int | None,
                             tuple[tuple[int, int], ...]]] = []
            heappush(queue, (0, 0, 0, exit_tile, initial_entry, initial_track, None, ()))
            best: dict[tuple[int, int, int], tuple[int, int, tuple[tuple[int, int], ...]]] = {}
            while queue:
                _, cost, turns, current, entry, previous_track, previous_exit, path = heappop(queue)
                if len(path) >= max_rail_tiles:
                    continue
                key = (current, entry, previous_track)
                prior = best.get(key)
                score = (cost, turns, path)
                if prior is not None and prior <= score:
                    continue
                best[key] = score
                budget["expansions"] += 1
                if budget["expansions"] > max_expansions:
                    raise RouteSearchError("route search expansion bound exceeded", kind="search_bound")
                for exit_direction in range(4):
                    if exit_direction == entry:
                        continue
                    track = _TRACKS[frozenset((entry, exit_direction))]
                    next_tile = _neighbour(current, exit_direction, width, height)
                    if exit_direction == inward and next_tile == dest_first:
                        if _forbidden_90(previous_track, track) or _forbidden_90(track, dest_axis):
                            continue
                        rails = [{"tile": tile, "track": piece} for tile, piece in path]
                        rails.append({"tile": current, "track": track})
                        if len({item["tile"] for item in rails}) == len(rails):
                            return rails, {
                                **dict(source),
                                "footprint": tuple(source_fp),
                                "forward": forward,
                            }, {
                                **dict(destination),
                                "footprint": tuple(dest_fp),
                                "inward": inward,
                            }
                    if next_tile is None or next_tile in reserved or next_tile == depot:
                        continue
                    if _forbidden_90(previous_track, track):
                        continue
                    if next_tile not in records or not _flat_clear(records[next_tile], source_height):
                        continue
                    if any(item[0] == next_tile for item in path) or next_tile == current:
                        continue
                    next_entry = (exit_direction + 2) % 4
                    next_cost = cost + 1
                    next_turns = turns + (1 if previous_exit is not None and previous_exit != exit_direction else 0)
                    if next_cost >= max_rail_tiles:
                        continue
                    heuristic = abs((next_tile % width) - (dest_first % width)) + abs(
                        (next_tile // width) - (dest_first // width)
                    )
                    next_path = path + ((current, track),)
                    heappush(queue, (
                        next_cost + heuristic + next_turns,
                        next_cost,
                        next_turns,
                        next_tile,
                        next_entry,
                        track,
                        exit_direction,
                        next_path,
                    ))
    return None


def find_route(
    tiles: Mapping[Any, Mapping[str, Any]] | Sequence[Mapping[str, Any]],
    map_width: int,
    map_height: int,
    source_candidates: Sequence[Mapping[str, Any]],
    destination_candidates: Sequence[Mapping[str, Any]],
    max_rail_tiles: int = 50,
    max_expansions: int = 100_000,
    max_pairs: int = 128,
    rail_type: int = 0,
) -> dict[str, Any]:
    """Find a deterministic source-to-destination flat-clear route proposal."""
    width, height = _int(map_width, "map_width"), _int(map_height, "map_height")
    max_rail_tiles, max_expansions, max_pairs = (
        _int(max_rail_tiles, "max_rail_tiles"),
        _int(max_expansions, "max_expansions"),
        _int(max_pairs, "max_pairs"),
    )
    if min(width, height, max_rail_tiles, max_expansions, max_pairs) < 1:
        raise ValueError("route bounds and map dimensions must be positive")
    records = _normalise_tiles(tiles, width, height)
    source_candidates = [
        {**candidate, "footprint": list(_candidate_geometry(candidate, records, width, height)[2])}
        for candidate in source_candidates
    ]
    destination_candidates = [
        {**candidate, "footprint": list(_candidate_geometry(candidate, records, width, height)[2])}
        for candidate in destination_candidates
    ]
    pair_list = [
        (source, destination)
        for source in source_candidates
        for destination in destination_candidates
    ]

    def pair_key(pair: tuple[Mapping[str, Any], Mapping[str, Any]]) -> tuple[Any, ...]:
        source, destination = pair
        source_fp = tuple(source.get("footprint", (source["tile"],)))
        dest_fp = tuple(destination.get("footprint", (destination["tile"],)))
        distance = min(abs(a % width - b % width) + abs(a // width - b // width)
                       for a in source_fp for b in dest_fp)
        return (distance, source["tile"], source["axis"], destination["tile"], destination["axis"])

    pair_list.sort(key=pair_key)
    if pair_list:
        minimum_rails = max(0, pair_key(pair_list[0])[0] - 1)
        if minimum_rails > max_rail_tiles:
            raise RouteSearchError(
                f"Selected station candidates require at least {minimum_rails} rail tiles; "
                f"this alpha supports at most {max_rail_tiles}. Choose a closer business pair.",
                kind="route_length_limit")
        pair_list = [pair for pair in pair_list if pair_key(pair)[0] - 1 <= max_rail_tiles]
    budget = {"expansions": 0}
    for pairs, (source, destination) in enumerate(pair_list, 1):
        if pairs > max_pairs:
            raise RouteSearchError("route pair search bound exceeded", kind="search_bound")
        found = _search_pair(records, width, height, source, destination,
                             max_rail_tiles, max_expansions, budget)
        if found is None:
            continue
        rails, source_site, destination_site = found
        stations = [source_site, destination_site]
        positive_source = (2, 1)[source_site["axis"]]
        source_first = (source_site["footprint"][0]
                        if source_site["forward"] == positive_source
                        else source_site["footprint"][1])
        depot_tile = _neighbour(
                source_first,
                (source_site["forward"] + 2) % 4, width, height,
            )
        if depot_tile is None:
            continue
        footprint = tuple(
                [depot_tile]
                + [tile for station in stations for tile in station["footprint"]]
                + [item["tile"] for item in rails]
            )
        if len(set(footprint)) != len(footprint):
            continue
        depot = {"tile": depot_tile, "orientation": source_site["forward"]}
        return {
                "source_station": {**source_site, "footprint": list(source_site["footprint"])},
                "destination_station": {**destination_site, "footprint": list(destination_site["footprint"])},
                "stations": [{**station, "footprint": list(station["footprint"])}
                             for station in stations],
                "depot": depot,
                "rails": rails,
                "rail_type": rail_type,
                "operation_count": len(rails) + 9,
                "footprint": list(footprint),
            }
    raise RouteSearchError("no supported flat-clear route found", kind="no_route")
