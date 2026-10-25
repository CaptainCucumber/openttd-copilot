"""Deterministic passenger bus services using observed towns and normal roads."""

from __future__ import annotations

import heapq
import itertools
import json
from pathlib import Path
import time

from native_bus_transport import BusBridge
from admin_transport import AdminProtocolError, AdminTransportError
from native_mutation_journal import normalize_position
from native_railway import JournaledExecutor, _identity, _integer, _persist
from run_environment_probe import require


DIRECTIONS = ((-1, 0), (0, 1), (1, 0), (0, -1))
ROAD, STOP, DEPOT, PURCHASE, ORDER, RUNNING = range(7, 13)
MAX_WINDOW = 192
MAX_PATH = 160
MAX_STOPS = 8


def paged(bridge, method, world, key, **kwargs):
    records, start = [], 0
    for _ in range(512):
        page = getattr(bridge, method)(world, start=start, count=8, **kwargs)
        require(page["world_id"] == world, "bus observation world mismatch")
        records.extend(page[key])
        if page["complete"]:
            return records
        require(page["next_start"] > start, "bus page did not advance")
        start = page["next_start"]
    raise RuntimeError(f"bus {method} exceeded bounded observation scan")


def discover(session):
    before = _identity(session)
    towns = paged(BusBridge(session.admin), "towns", before["world_id"], "towns")
    require(normalize_position(before) == normalize_position(_identity(session)),
            "world/operation position changed while reading towns")
    return towns


def inspect(session):
    before = _identity(session)
    bridge, world = BusBridge(session.admin), before["world_id"]
    result = {"towns": paged(bridge, "towns", world, "towns")}
    result["bus_engines"] = [
        engine for engine in paged(bridge, "catalog", world, "engines")
        if engine["buildable"] and engine["default_cargo"] == 0 and engine["road_type"] == 0]
    result["bus_catalog_scope"] = "currently buildable standard passenger road engines only"
    for kind in ("vehicles", "stops", "depots"):
        result["buses" if kind == "vehicles" else "bus_" + kind] = paged(
            bridge, "assets", world, kind, kind=kind)
    for vehicle in result["buses"]:
        vehicle["orders"] = bridge.orders(world, vehicle["vehicle_id"])["orders"]
    after = _identity(session)
    require(normalize_position(before) == normalize_position(after),
            "world/operation position changed during bus inspection")
    return {**result, "world_id": world, "atomic": False,
            "position": {"sequence": after["sequence"], "head": after["head"]}, "identity": after,
            "observation_frame_span": [before["frame"], after["frame"]]}


def neighbour(tile, direction, width, height):
    x, y = tile % width, tile // width
    dx, dy = DIRECTIONS[direction]
    return (y + dy) * width + x + dx if 0 <= x + dx < width and 0 <= y + dy < height else None


def distance(a, b, width):
    return abs(a % width - b % width) + abs(a // width - b // width)


def usable(record):
    if not record or not record["valid"]:
        return False
    if record["tile_type"] == 2:
        return record["normal_road"] and record["road_type"] == 0 and not record["one_way"]
    return record["tile_type"] in (0, 4) and record["owner"] == 16


def candidate_stops(records, town, width):
    sites = [record for record in records.values()
             if usable(record) and record["tile_type"] == 2 and record["road_bits"] in (5, 10)
             and record["slope"] == 0 and distance(record["tile"], town["tile"], width) <= 16]
    return sorted(sites, key=lambda r: (distance(r["tile"], town["tile"], width), r["tile"]))[:32]


def find_path(records, width, height, sources, destinations, *, max_expansions=100000,
              anchor_tiles=()):
    """Bounded multi-source A*: prefer existing roads, never clear buildings."""
    goals = {site["tile"]: site for site in destinations}
    anchor_tiles = set(anchor_tiles)

    def path_usable(record):
        return (record is not None and record["tile"] in anchor_tiles
                and record["valid"] and record["tile_type"] == 5
                and record["owner"] == 0 and record["road_type"] == 0
                and record["road_bits"] in (5, 10)) or usable(record)

    queue, best, previous, origin = [], {}, {}, {}
    counter = itertools.count()
    for site in sources:
        state = (site["tile"], -1)
        best[state], origin[state] = 0, site
        h = min(distance(site["tile"], goal, width) for goal in goals)
        heapq.heappush(queue, (h, 0, next(counter), state, 1))
    expansions = 0
    while queue:
        _, cost, _, state, length = heapq.heappop(queue)
        if cost != best[state]:
            continue
        tile, entry = state
        if (tile in goals and entry >= 0 and tile != origin[state]["tile"]
                and records[tile]["road_bits"] & (1 << entry)):
            path = [tile]
            end = state
            while state in previous:
                state = previous[state]
                path.append(state[0])
            path.reverse()
            return {"path": path, "source": origin[end], "destination": goals[tile],
                    "expansions": expansions}
        expansions += 1
        require(expansions <= max_expansions, "bus road search expansion limit exceeded; feasibility unknown")
        if length >= MAX_PATH:
            continue
        record = records[tile]
        for direction in range(4):
            if direction == entry:
                continue
            other = neighbour(tile, direction, width, height)
            target = records.get(other)
            if not path_usable(target):
                continue
            # Both selected drive-through stops must retain their straight axis.
            if (entry == -1 or tile in goals) and not record["road_bits"] & (1 << direction):
                continue
            mask = 1 << direction | (1 << entry if entry >= 0 else 0)
            old = record["road_bits"] if record["tile_type"] == 2 else 0
            new_bits = mask & ~old
            if new_bits and record["slope"] != 0:
                continue
            incoming = (direction + 2) % 4
            if target["slope"] and (target["tile_type"] != 2 or not target["road_bits"] & (1 << incoming)):
                continue
            step = 1 if not new_bits else 5 + (2 if record["tile_type"] == 4 else 0)
            next_state, total = (other, incoming), cost + step
            if total >= best.get(next_state, float("inf")):
                continue
            best[next_state], previous[next_state], origin[next_state] = total, state, origin[state]
            heuristic = min(distance(other, goal, width) for goal in goals)
            heapq.heappush(queue, (total + heuristic, total, next(counter), next_state, length + 1))
    raise RuntimeError("no bus route found within the observed corridor/160-tile bound; feasibility unknown")


def road_steps(path, records, width, height):
    additions = {}
    for a, b in zip(path, path[1:]):
        direction = next(d for d in range(4) if neighbour(a, d, width, height) == b)
        for tile, side in ((a, direction), (b, (direction + 2) % 4)):
            additions[tile] = additions.get(tile, 0) | (1 << side)
    return [{"kind": ROAD, "tile": tile, "road_bits": mask | records[tile]["road_bits"]}
            for tile, mask in additions.items() if mask & ~records[tile]["road_bits"]]


def merge_road_steps(paths, records, width, height, protected=()):
    masks = {}
    protected = set(protected)
    for path in paths:
        for step in road_steps(path, records, width, height):
            require(step["tile"] not in protected,
                    "bus route would require changing selected station road bits")
            masks[step["tile"]] = masks.get(step["tile"], records[step["tile"]]["road_bits"]) | step["road_bits"]
            records[step["tile"]] = {**records[step["tile"]], "road_bits": masks[step["tile"]]}
    return [{"kind": ROAD, "tile": tile, "road_bits": mask} for tile, mask in sorted(masks.items())]


def _ordinary_order(order):
    return (order.get("order_type") == 1 and order.get("load_type") == 0
            and order.get("unload_type") == 0 and order.get("non_stop", 0) == 0)


def _order_fingerprint(orders):
    keys = ("order_type", "destination_id", "load_type", "unload_type", "non_stop")
    return [{key: order.get(key, 0) for key in keys} for order in orders]


def _stop_fingerprint(stops):
    keys = ("station_id", "stop_id", "tile", "orientation", "owner", "town_id")
    return [{key: stop.get(key) for key in keys} for stop in stops]


def _vehicle_snapshot(vehicle):
    keys = ("vehicle_id", "owner", "engine_id", "cargo_type", "cargo_capacity",
            "orders_shared", "crashed", "stopped")
    result = {key: vehicle.get(key) for key in keys}
    result["owner"] = vehicle.get("owner", vehicle.get("company_id"))
    return result


def _frame_span(spans):
    values = [value for span in spans for value in span]
    return [min(values), max(values)]


def read_corridor(session, bridge, identity, source, destination):
    width, height = identity["map_width"], identity["map_height"]
    xs = (source["tile"] % width, destination["tile"] % width)
    ys = (source["tile"] // width, destination["tile"] // width)
    x0, x1 = max(1, min(xs) - 20), min(width - 2, max(xs) + 20)
    y0, y1 = max(1, min(ys) - 20), min(height - 2, max(ys) + 20)
    require(x1 - x0 < MAX_WINDOW and y1 - y0 < MAX_WINDOW,
            "town pair exceeds the 192x192 bounded bus planning corridor")
    records, frames = {}, []
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1, 8):
            page = bridge.tiles(identity["world_id"], y * width + x, min(8, x1 - x + 1))
            require(page["world_id"] == identity["world_id"], "bus tile observation world mismatch")
            frames.append(page["frame"])
            records.update((r["tile"], r) for r in page["tiles"])
    return records, [min(frames), max(frames)]


def quote_step(bridge, world, step):
    try:
        return bridge.quote(world, **{k: v for k, v in step.items() if k != "max_cost"})
    except AdminTransportError as exc:
        raise AdminProtocolError(f"bus quote kind={step['kind']} tile={step['tile']}: {exc}") from exc


def require_quote(quote, *, stop=False):
    require(quote["supported_profile"], "bus construction requires standard temperate content")
    require(quote["operation_state"] not in (1, 4), "pending/uncertain operation blocks bus construction")
    require(quote["quote_success"], f"normal bus construction test rejected: {quote['error']}")
    require(quote["cost"] >= 0, "bus quote returned a negative cost")
    if stop:
        require(quote["passenger_acceptance"] >= 8 and quote["passenger_production"] > 0,
                "bus stop no longer accepts/produces passengers from the selected town")


def plan_bus(session, source_id, destination_id, cap, reserve, *, record=True, via_town_ids=()):
    for value, name, minimum in ((source_id, "source_town_id", 0), (destination_id, "destination_town_id", 0),
                                 (cap, "construction_cap", 1), (reserve, "operating_reserve", 0)):
        _integer(value, name, minimum)
    require(isinstance(via_town_ids, (list, tuple)), "via_town_ids must be an ordered list of town IDs")
    for town_id in via_town_ids:
        _integer(town_id, "via_town_id", 0)
    town_ids = [source_id, *via_town_ids, destination_id]
    require(2 <= len(town_ids) <= MAX_STOPS, f"bus service requires 2..{MAX_STOPS} towns")
    require(len(set(town_ids)) == len(town_ids), "bus endpoints/via towns must be different towns")
    identity, bridge = _identity(session), BusBridge(session.admin)
    world = identity["world_id"]
    towns = {t["town_id"]: t for t in discover(session)}
    require(all(town_id in towns for town_id in town_ids), "select observed town IDs")
    ordered_towns = [towns[town_id] for town_id in town_ids]
    records, original_records, spans, paths, selected = {}, {}, [], [], []
    previous = None
    for leg, (left, right) in enumerate(zip(ordered_towns, ordered_towns[1:])):
        leg_records, frame_span = read_corridor(session, bridge, identity, left, right)
        original_records.update({tile_id: dict(record) for tile_id, record in leg_records.items()})
        for tile_id, planned in records.items():
            if tile_id in leg_records:
                leg_records[tile_id] = {**leg_records[tile_id], "road_bits": planned["road_bits"]}
        records.update(leg_records)
        spans.append(frame_span)

        def admitted(town):
            choices = []
            for candidate in candidate_stops(leg_records, town, identity["map_width"]):
                if candidate["tile"] in {site["tile"] for site in selected}:
                    continue
                step = {"kind": STOP, "tile": candidate["tile"],
                        "orientation": 0 if candidate["road_bits"] == 5 else 1, "town_id": town["town_id"]}
                quote = quote_step(bridge, world, step)
                if (quote["supported_profile"] and quote["quote_success"] and
                        quote["passenger_acceptance"] >= 8 and quote["passenger_production"] > 0):
                    choices.append({**candidate, "step": {**step, "max_cost": quote["cost"]}})
                    if len(choices) >= 12:
                        break
            require(choices, f"no supported roadside bus stop accepting/producing passengers in {town['name']}")
            return choices

        sources = [previous] if previous else admitted(left)
        destinations = admitted(right)
        require(any(source_site["tile"] != destination_site["tile"]
                    for source_site in sources for destination_site in destinations),
                "no distinct bus stop endpoints for adjacent towns")
        geometry = find_path(leg_records, identity["map_width"], identity["map_height"], sources, destinations)
        require(geometry["source"]["tile"] != geometry["destination"]["tile"],
                "bus stops for different towns must be distinct; overlapping endpoints are unsupported")
        if previous is None:
            selected.append(geometry["source"])
        selected.append(geometry["destination"])
        previous = geometry["destination"]
        paths.append(geometry["path"])
        for step in road_steps(geometry["path"], leg_records, identity["map_width"], identity["map_height"]):
            leg_records[step["tile"]] = {**leg_records[step["tile"]], "road_bits": step["road_bits"]}
            records[step["tile"]] = leg_records[step["tile"]]
    protected = [site["tile"] for site in selected]
    steps = merge_road_steps(paths, original_records, identity["map_width"], identity["map_height"], protected)
    selected_depot = None
    route_tiles = list(dict.fromkeys(tile_id for path in paths for tile_id in path))
    for road_tile in route_tiles:
        for direction in range(4):
            depot_tile = neighbour(road_tile, direction, identity["map_width"], identity["map_height"])
            site = original_records.get(depot_tile)
            if (depot_tile in route_tiles or not usable(site) or site["tile_type"] not in (0, 4)
                    or site["slope"] != 0):
                continue
            step = {"kind": DEPOT, "tile": depot_tile, "orientation": (direction + 2) % 4}
            quote = quote_step(bridge, world, step)
            if not quote["quote_success"] or not quote["supported_profile"]:
                continue
            # Add only a branch on a road tile, never rebuild a drive-through stop.
            if road_tile in protected:
                continue
            existing = next((s for s in steps if s["tile"] == road_tile), None)
            mask = (existing["road_bits"] if existing else original_records[road_tile]["road_bits"]) | (1 << direction)
            connection = {"kind": ROAD, "tile": road_tile, "road_bits": mask}
            connection_quote = quote_step(bridge, world, connection)
            if not connection_quote["quote_success"]:
                continue
            if existing:
                existing["road_bits"] = mask
            elif mask != original_records[road_tile]["road_bits"]:
                steps.append(connection)
            selected_depot = step
            break
        if selected_depot:
            break
    require(selected_depot, "no supported connected roadside depot site in the observed corridor")
    # Secure authority-sensitive stops before any disclosed tree clearing.
    steps = [site["step"] for site in selected] + [selected_depot] + steps
    quotes = []
    for step in steps:
        quote = quote_step(bridge, world, step)
        require_quote(quote, stop=step["kind"] == STOP)
        step["max_cost"] = quote["cost"]
        quotes.append(quote)
    engines = paged(bridge, "catalog", world, "engines")
    choices = [e for e in engines if e["buildable"] and e["default_cargo"] == 0
               and e["default_capacity"] > 0 and e["road_type"] == 0]
    require(choices, "no supported standard passenger bus currently available")
    engine = min(choices, key=lambda e: (e["purchase_cost"], e["engine_id"]))
    total = sum(s["max_cost"] for s in steps) + engine["purchase_cost"]
    after = _identity(session)
    require(normalize_position(after) == normalize_position(identity), "world/operation position changed during bus planning")
    operation_count = len(steps) + 1 + len(selected) + 1
    available = quotes[-1]["capacity"] - quotes[-1]["retained_count"]
    require(operation_count <= available,
            f"bus service needs {operation_count} retained records, only {available} available; nothing built")
    require(total <= cap, f"whole bus service costs {total}, above construction cap {cap}; nothing built")
    require(after["companies"][0]["money"] >= total + reserve,
            f"bus service costs {total} plus reserve {reserve}; insufficient cash; nothing built")
    result = {"world_id": world, "position": {"sequence": identity["sequence"], "head": identity["head"]},
              "company_id": 0, "source": ordered_towns[0], "destination": ordered_towns[-1],
              "towns": ordered_towns, "town_ids": town_ids, "cargo_id": 0,
              "construction_cap": cap, "operating_reserve": reserve, "quoted_total": total,
              "operation_count": operation_count, "available_records": available,
              "geometry": {"path": [tile_id for path in paths for tile_id in path[:-1]] + [paths[-1][-1]],
                           "paths": paths, "depot": selected_depot},
              "steps": steps, "quotes": quotes, "engine": engine,
              "observation_frame_span": _frame_span(spans),
              "road_tiles_to_build": sum(s["kind"] == ROAD for s in steps),
              "scope": "one ordinary passenger bus; existing two-way roads plus bounded new road/tree clearing; no demolition, bridges or terraforming"}
    if record:
        session.manifest.update(job_state="planning", plan=result)
        session.write()
    return result


def _existing_bus(observed, vehicle_id):
    vehicle = next((item for item in observed["buses"] if item["vehicle_id"] == vehicle_id), None)
    require(vehicle is not None, "select an observed owned bus")
    require(vehicle.get("owner", vehicle.get("company_id")) == 0, "existing bus must be owned by company 0")
    require(not vehicle.get("crashed", False), "crashed buses cannot be expanded")
    require(not vehicle.get("orders_shared", False), "shared bus orders cannot be expanded")
    require(not vehicle.get("stopped", False),
            "stopped existing buses are not yet supported for stop insertion; start it first")
    require(vehicle.get("cargo_type") == 0 and vehicle.get("cargo_capacity", 0) > 0,
            "existing vehicle must be a standard passenger bus")
    orders = vehicle.get("orders", [])
    require(2 <= len(orders) <= 7, "existing bus must have 2..7 orders")
    require(all(_ordinary_order(order) for order in orders),
            "existing bus must have only ordinary exact passenger station orders")
    require(len({order["destination_id"] for order in orders}) == len(orders),
            "existing bus orders must reference distinct stations")
    stops = []
    by_station = {stop["station_id"]: stop for stop in observed["bus_stops"]}
    for order in orders:
        require(order["destination_id"] in by_station, "existing bus order station is not observed")
        stops.append(by_station[order["destination_id"]])
    return vehicle, orders, stops


def plan_bus_stops(session, vehicle_id, town_ids, insert_index, cap, reserve, *, record=True):
    for value, name, minimum in ((vehicle_id, "vehicle_id", 0), (insert_index, "insert_index", 0),
                                 (cap, "construction_cap", 1), (reserve, "operating_reserve", 0)):
        _integer(value, name, minimum)
    require(isinstance(town_ids, (list, tuple)) and town_ids, "town_ids must contain ordered new town IDs")
    for town_id in town_ids:
        _integer(town_id, "town_id", 0)
    require(len(set(town_ids)) == len(town_ids), "new town IDs must be distinct")
    identity, bridge = _identity(session), BusBridge(session.admin)
    world = identity["world_id"]
    observed = inspect(session)
    vehicle, orders, old_stops = _existing_bus(observed, vehicle_id)
    require(insert_index <= len(orders), "insert_index must be at most the existing order count")
    require(len(orders) + len(town_ids) <= MAX_STOPS, f"expanded bus order list exceeds {MAX_STOPS} stops")
    towns = {town["town_id"]: town for town in observed["towns"]}
    require(all(town_id in towns for town_id in town_ids), "select observed town IDs")
    old_town_ids = [stop.get("town_id") for stop in old_stops]
    require(all(town_id is not None for town_id in old_town_ids),
            "existing bus stops must have observed town associations")
    require(not set(town_ids) & set(old_town_ids), "new town IDs must not repeat existing bus towns")
    engine = next((item for item in observed["bus_engines"] if item["engine_id"] == vehicle["engine_id"]), None)
    require(engine is not None and engine["default_cargo"] == 0 and engine["road_type"] == 0
            and engine["default_capacity"] == vehicle["cargo_capacity"],
            "existing bus engine/capacity is outside the supported standard profile")

    predecessor = old_stops[insert_index - 1] if insert_index else old_stops[-1]
    successor = old_stops[insert_index] if insert_index < len(old_stops) else old_stops[0]
    anchors = [predecessor, *[towns[town_id] for town_id in town_ids], successor]
    selected, paths, combined, base_records, spans = [], [], {}, {}, []
    previous = None
    for leg, (left, right) in enumerate(zip(anchors, anchors[1:])):
        leg_records, span = read_corridor(session, bridge, identity, left, right)
        base_records.update({tile_id: dict(record) for tile_id, record in leg_records.items()})
        spans.append(span)
        for tile_id, planned in combined.items():
            if tile_id in leg_records:
                leg_records[tile_id] = {**leg_records[tile_id], "road_bits": planned["road_bits"]}
        for anchor in (left, right):
            if "station_id" in anchor:
                record_at_anchor = leg_records.get(anchor["tile"])
                require(record_at_anchor and record_at_anchor["tile_type"] == 5
                        and record_at_anchor["owner"] == 0
                        and record_at_anchor["road_type"] == 0
                        and record_at_anchor["road_bits"] in (5, 10),
                        "existing bus stop geometry is not an exact straight drive-through station")
        combined.update(leg_records)

        def new_sites(town):
            choices = []
            for candidate in candidate_stops(leg_records, town, identity["map_width"]):
                if candidate["tile"] in {item["tile"] for item in selected}:
                    continue
                step = {"kind": STOP, "tile": candidate["tile"],
                        "orientation": 0 if candidate["road_bits"] == 5 else 1, "town_id": town["town_id"]}
                quote = quote_step(bridge, world, step)
                if (quote["supported_profile"] and quote["quote_success"] and
                        quote["passenger_acceptance"] >= 8 and quote["passenger_production"] > 0):
                    choices.append({**candidate, "step": {**step, "max_cost": quote["cost"]}})
                    if len(choices) >= 12:
                        break
            require(choices, f"no supported roadside bus stop accepting/producing passengers in {town['name']}")
            return choices

        if previous is None:
            previous = {**leg_records[predecessor["tile"]], "station_id": predecessor["station_id"]}
        sources = [previous]
        if "station_id" in right:
            destinations = [{**leg_records[right["tile"]], "station_id": right["station_id"]}]
        else:
            destinations = new_sites(right)
        geometry = find_path(
            leg_records, identity["map_width"], identity["map_height"], sources, destinations,
            anchor_tiles={stop["tile"] for stop in old_stops},
        )
        previous = geometry["destination"]
        if "station_id" not in right:
            selected.append(previous)
        paths.append(geometry["path"])
        for step in road_steps(geometry["path"], leg_records, identity["map_width"], identity["map_height"]):
            leg_records[step["tile"]] = {**leg_records[step["tile"]], "road_bits": step["road_bits"]}
            combined[step["tile"]] = leg_records[step["tile"]]

    protected = [stop["tile"] for stop in old_stops] + [site["tile"] for site in selected]
    road = merge_road_steps(paths, base_records, identity["map_width"], identity["map_height"], protected)
    anchor_geometry = []
    for stop in old_stops:
        station_record = base_records.get(stop["tile"])
        if station_record is None:
            page = bridge.tiles(world, stop["tile"], 1)
            require(page["world_id"] == world and len(page["tiles"]) == 1,
                    "existing line stop geometry observation failed")
            spans.append([page["frame"], page["frame"]])
            station_record = page["tiles"][0]
        require(station_record["tile_type"] == 5 and station_record["owner"] == 0
                and station_record["road_type"] == 0 and station_record["road_bits"] in (5, 10),
                "existing line contains a non-drive-through or unsupported bus stop")
        anchor_geometry.append({
            "station_id": stop["station_id"], "tile": stop["tile"],
            "tile_type": station_record["tile_type"], "road_bits": station_record["road_bits"],
        })
    steps = [site["step"] for site in selected] + road
    quotes = []
    for step in steps:
        quote = quote_step(bridge, world, step)
        require_quote(quote, stop=step["kind"] == STOP)
        step["max_cost"] = quote["cost"]
        quotes.append(quote)
    total = sum(step["max_cost"] for step in steps)
    after = _identity(session)
    require(normalize_position(after) == normalize_position(identity),
            "world/operation position changed during bus stop planning")
    operation_count = len(steps) + len(town_ids) + 2
    available = quotes[-1]["capacity"] - quotes[-1]["retained_count"]
    require(operation_count <= available,
            f"bus expansion needs {operation_count} retained records, only {available} available; nothing built")
    require(total <= cap, f"whole bus expansion costs {total}, above construction cap {cap}; nothing built")
    require(after["companies"][0]["money"] >= total + reserve,
            f"bus expansion costs {total} plus reserve {reserve}; insufficient cash; nothing built")
    result = {
        "mode": "add_stops", "world_id": world,
        "position": {"sequence": identity["sequence"], "head": identity["head"]},
        "company_id": 0, "cargo_id": 0, "vehicle_id": vehicle_id,
        "vehicle_snapshot": _vehicle_snapshot(vehicle), "engine": engine,
        "old_orders": _order_fingerprint(orders), "old_order_fingerprint": _order_fingerprint(orders),
        "old_stops": old_stops, "old_stop_fingerprint": _stop_fingerprint(old_stops),
        "anchor_geometry": anchor_geometry, "insert_index": insert_index,
        "towns": [towns[town_id] for town_id in town_ids], "town_ids": list(town_ids),
        "source": towns[town_ids[0]], "destination": towns[town_ids[-1]],
        "construction_cap": cap, "operating_reserve": reserve, "quoted_total": total,
        "operation_count": operation_count, "available_records": available,
        "geometry": {"path": [tile_id for path in paths for tile_id in path[:-1]] + [paths[-1][-1]],
                     "paths": paths, "predecessor_station": predecessor["station_id"],
                     "successor_station": successor["station_id"]},
        "steps": steps, "quotes": quotes, "observation_frame_span": _frame_span(spans),
        "road_tiles_to_build": sum(step["kind"] == ROAD for step in steps),
        "scope": "insert new ordinary stops into one running unshared standard passenger bus; no replacement bus or depot",
    }
    if record:
        session.manifest.update(job_state="planning", plan=result)
        session.write()
    return result


def _revalidate_expansion(observed, plan, *, stopped=None):
    vehicle, orders, stops = _existing_bus(observed, plan["vehicle_id"])
    if stopped is not None:
        require(bool(vehicle.get("stopped", False)) == stopped, "existing bus running state changed")
    require(_vehicle_snapshot(vehicle) == plan["vehicle_snapshot"], "existing bus identity/profile changed")
    require(_order_fingerprint(orders) == plan["old_order_fingerprint"], "existing bus orders changed")
    expected = plan.get("old_stop_fingerprint", _stop_fingerprint(plan["old_stops"]))
    require(_stop_fingerprint(stops) == expected, "existing bus stop associations changed")
    return vehicle, orders, stops


def _revalidate_anchor_geometry(bridge, plan):
    for expected in plan.get("anchor_geometry", []):
        page = bridge.tiles(plan["world_id"], expected["tile"], 1)
        require(page["world_id"] == plan["world_id"] and len(page["tiles"]) == 1,
                "existing bus station geometry observation failed")
        actual = page["tiles"][0]
        require(actual["tile"] == expected["tile"] and actual["tile_type"] == 5
                and actual["road_bits"] == expected["road_bits"]
                and actual["road_bits"] in (5, 10),
                "existing bus station geometry changed")


def execute_bus(session, plan, job_id):
    require(isinstance(job_id, str) and job_id and all(c.isascii() and (c.isalnum() or c in "-_") for c in job_id),
            "invalid bus job ID")
    job_file = session.artifacts / "jobs" / f"{job_id}.json"
    identity, bridge = _identity(session), BusBridge(session.admin)
    if job_file.exists():
        old = json.loads(job_file.read_text())
        require(old["plan"] == plan, "bus job conflicts with durable plan")
        require(old["state"] in ("commissioned", "operating"), "partial bus job requires reconciliation; never retried")
        require(old["outcomes"] and normalize_position(identity) == normalize_position(old["outcomes"][-1]["outcome"]),
                "bus job differs from loaded world/operation position; reconciliation required")
        return old["result"]
    require(identity["world_id"] == plan["world_id"] and
            {"sequence": identity["sequence"], "head": identity["head"]} == plan["position"],
            "world/operation position differs from approved bus plan")
    initial = {**identity, **inspect(session)}
    record = {"job_id": job_id, "state": "building", "plan": plan, "outcomes": [], "spent": 0, "initial": initial}
    _persist(job_file, record)
    session.manifest.update(job_state="building", job_file=str(job_file))
    session.write()
    executor = JournaledExecutor(session, plan, job_id, record, job_file, identity, bridge.operation)
    try:
        if plan.get("mode") == "add_stops":
            _revalidate_expansion(initial, plan, stopped=False)
            _revalidate_anchor_geometry(bridge, plan)
            created = []
            for index, step in enumerate(plan["steps"]):
                quote = quote_step(bridge, plan["world_id"], step)
                require_quote(quote, stop=step["kind"] == STOP)
                require(quote["cost"] <= step["max_cost"], "bus expansion price rose; partial work retained")
                fields = {key: value for key, value in step.items() if key not in ("max_cost", "town_id")}
                outcome = executor.mutate(bridge.mutate, fields, step["max_cost"], f"bus-expand-build-{index}")
                if step["kind"] == STOP:
                    created.append(outcome["created_asset_id"])
            before_edit = inspect(session)
            live, _, _ = _revalidate_expansion(before_edit, plan, stopped=False)
            _revalidate_anchor_geometry(bridge, plan)
            executor.mutate(
                bridge.mutate,
                {"kind": RUNNING, "tile": live["tile"], "vehicle_id": plan["vehicle_id"],
                 "target_id": 0xFFFFFFFF, "policy": 0},
                0, "bus-expand-stop",
            )
            stopped_observed = inspect(session)
            stopped_bus = next((item for item in stopped_observed["buses"]
                                if item["vehicle_id"] == plan["vehicle_id"]), None)
            require(stopped_bus is not None and stopped_bus.get("stopped", False),
                    "bus did not stop before order editing")
            stopped_snapshot = _vehicle_snapshot(stopped_bus)
            require(all(stopped_snapshot[key] == plan["vehicle_snapshot"][key]
                        for key in ("vehicle_id", "owner", "engine_id", "cargo_type",
                                    "cargo_capacity", "orders_shared", "crashed")),
                    "existing bus identity/profile changed while stopping")
            require(_order_fingerprint(stopped_bus["orders"]) == plan["old_order_fingerprint"],
                    "existing bus orders changed while stopping")
            observed_old = {stop["station_id"]: stop for stop in stopped_observed["bus_stops"]}
            stopped_old = [observed_old.get(station["station_id"]) for station in plan["old_stops"]]
            require(None not in stopped_old
                    and _stop_fingerprint(stopped_old)
                    == plan.get("old_stop_fingerprint", _stop_fingerprint(plan["old_stops"])),
                    "existing bus stop associations changed while stopping")
            expected = list(plan["old_order_fingerprint"])
            configured = stopped_observed
            for offset, station_id in enumerate(created):
                before_insert = inspect(session)
                editing_bus = next(item for item in before_insert["buses"]
                                   if item["vehicle_id"] == plan["vehicle_id"])
                require(editing_bus.get("stopped", False)
                        and _order_fingerprint(editing_bus["orders"]) == expected,
                        "bus orders changed immediately before insertion")
                executor.mutate(
                    bridge.mutate,
                    {"kind": ORDER, "tile": editing_bus["tile"], "vehicle_id": plan["vehicle_id"],
                     "target_id": station_id, "order_index": plan["insert_index"] + offset, "policy": 0},
                    0, f"bus-expand-order-{offset}",
                )
                expected.insert(
                    plan["insert_index"] + offset,
                    {"order_type": 1, "destination_id": station_id, "load_type": 0,
                     "unload_type": 0, "non_stop": 0},
                )
                configured = inspect(session)
                inserted_bus = next(item for item in configured["buses"]
                                    if item["vehicle_id"] == plan["vehicle_id"])
                require(inserted_bus.get("stopped", False)
                        and _order_fingerprint(inserted_bus["orders"]) == expected,
                        "bus order insertion did not produce the exact requested list")
            configured_bus = next(item for item in configured["buses"]
                                  if item["vehicle_id"] == plan["vehicle_id"])
            require(_order_fingerprint(configured_bus["orders"]) == expected,
                    "expanded bus order list does not exactly match the approved insertion")
            for step, station_id in zip((item for item in plan["steps"] if item["kind"] == STOP), created):
                require(any(stop["station_id"] == station_id and stop["tile"] == step["tile"]
                            for stop in configured["bus_stops"]),
                        "new bus stop independent identity/readback mismatch")
            page = session.admin.copilot_vehicle_events(
                plan["world_id"], 0, plan["vehicle_id"], timeout=session.remaining())
            require(not page["gap"], "bus event history gap before restart")
            executor.mutate(
                bridge.mutate,
                {"kind": RUNNING, "tile": configured_bus["tile"], "vehicle_id": plan["vehicle_id"],
                 "target_id": 0xFFFFFFFF, "policy": 1},
                0, "bus-expand-start",
            )
            station_ids = [order["destination_id"] for order in expected]
            old_towns = [stop["town_id"] for stop in plan["old_stops"]]
            expanded_towns = list(old_towns)
            expanded_towns[plan["insert_index"]:plan["insert_index"]] = plan["town_ids"]
            result = {
                "mode": "add_stops", "job_id": job_id, "world_id": plan["world_id"],
                "company": 0, "cargo": 0, "vehicle": plan["vehicle_id"],
                "source_town": expanded_towns[0], "destination_town": expanded_towns[-1],
                "town_ids": expanded_towns, "source_station": station_ids[0],
                "destination_station": station_ids[-1], "stations": station_ids,
                "spent": record["spent"], "orders": configured_bus["orders"], "initial": initial,
                "epoch": page["epoch"], "cursor": page["next_seq"],
                "construction_cap": plan["construction_cap"],
                "operating_reserve": plan["operating_reserve"], "job_file": str(job_file),
                "commissioned_save": str(session.save("bus-expanded-commissioned")),
                "vehicle_snapshot": plan["vehicle_snapshot"], "old_orders": plan["old_orders"],
                "insert_index": plan["insert_index"],
            }
            record.update(state="commissioned", result=result)
            _persist(job_file, record)
            session.manifest.update(job_state="verifying", result=result)
            session.write()
            return result
        stops = []
        for index, step in enumerate(plan["steps"]):
            quote = quote_step(bridge, plan["world_id"], step)
            require_quote(quote, stop=step["kind"] == STOP)
            require(quote["cost"] <= step["max_cost"], "bus construction price rose; partial work retained")
            fields = {k: v for k, v in step.items() if k not in ("max_cost", "town_id")}
            outcome = executor.mutate(bridge.mutate, fields, step["max_cost"], f"bus-build-{index}")
            if step["kind"] == STOP:
                stops.append(outcome["created_asset_id"])
        depot_tile = plan["geometry"]["depot"]["tile"]
        engine = plan["engine"]
        live_engines = paged(bridge, "catalog", plan["world_id"], "engines")
        live = next(e for e in live_engines if e["engine_id"] == engine["engine_id"])
        require(live["buildable"] and live["purchase_cost"] <= engine["purchase_cost"], "bus became unavailable or price rose")
        bus = executor.mutate(bridge.mutate, {"kind": PURCHASE, "tile": depot_tile, "engine_id": engine["engine_id"]},
                              engine["purchase_cost"], "bus-purchase")["created_asset_id"]
        for index, stop in enumerate(stops):
            executor.mutate(bridge.mutate, {"kind": ORDER, "tile": depot_tile, "vehicle_id": bus,
                                           "target_id": stop, "order_index": index, "policy": 0}, 0, f"bus-order-{index}")
        observed = inspect(session)
        vehicle = next(v for v in observed["buses"] if v["vehicle_id"] == bus)
        require(vehicle["engine_id"] == engine["engine_id"] and vehicle["cargo_type"] == 0
                and vehicle["cargo_capacity"] == engine["default_capacity"], "bus independent purchase/capacity mismatch")
        orders = vehicle["orders"]
        require(len(orders) == len(stops) and [o["destination_id"] for o in orders] == stops
                and all(_ordinary_order(o) for o in orders),
                "bus orders do not match ordinary passenger service")
        for step, stop in zip((s for s in plan["steps"] if s["kind"] == STOP), stops):
            require(any(s["station_id"] == stop and s["tile"] == step["tile"] for s in observed["bus_stops"]),
                    "bus stop independent identity/readback mismatch")
        page = session.admin.copilot_vehicle_events(plan["world_id"], 0, bus, timeout=session.remaining())
        require(not page["gap"], "bus event history gap before start")
        executor.mutate(bridge.mutate, {"kind": RUNNING, "tile": depot_tile, "vehicle_id": bus,
                                       "target_id": 0xFFFFFFFF, "policy": 1}, 0, "bus-start")
        result = {"job_id": job_id, "world_id": plan["world_id"], "company": 0, "cargo": 0,
                  "vehicle": bus, "source_town": plan["source"]["town_id"],
                  "destination_town": plan["destination"]["town_id"], "source_station": stops[0],
                  "destination_station": stops[-1], "stations": stops,
                  "town_ids": plan.get("town_ids", [plan["source"]["town_id"], plan["destination"]["town_id"]]),
                  "spent": record["spent"], "orders": orders,
                  "initial": initial, "epoch": page["epoch"], "cursor": page["next_seq"],
                  "construction_cap": plan["construction_cap"], "operating_reserve": plan["operating_reserve"],
                  "job_file": str(job_file), "commissioned_save": str(session.save("bus-commissioned"))}
        record.update(state="commissioned", result=result)
        _persist(job_file, record)
        session.manifest.update(job_state="verifying", result=result)
        session.write()
        return result
    except Exception as exc:
        record.update(state="partial", failure=f"{type(exc).__name__}: {exc}")
        _persist(job_file, record)
        session.manifest.update(job_state="partial", failure=record["failure"])
        session.write()
        raise


def verify_bus(session, result):
    cursor, events = result["cursor"], []
    while True:
        page = session.admin.copilot_vehicle_events(result["world_id"], 0, result["vehicle"],
                                                   cursor=cursor, timeout=session.remaining())
        require(page["epoch"] == result["epoch"] and not page["gap"],
                "bus event gap/world reload; passenger service is unverified")
        events.extend(page["events"])
        cursor = page["next_seq"]
        session.manifest.update(native_bus_events=events, last_native_telemetry=page)
        session.write()
        station_ids = result.get("stations", [result["source_station"], result["destination_station"]])
        delivered = {station: sum(e["amount"] for e in events if e["kind"] == "delivery"
                                 and e["station"] == station and e["vehicle"] == result["vehicle"]
                                 and e["company"] == 0 and e["cargo"] == 0)
                     for station in station_ids}
        if all(amount > 0 for amount in delivered.values()):
            current = _identity(session)
            require(current["companies"][0]["loan"] == result["initial"]["companies"][0]["loan"], "bus service changed loan")
            summary = {"scope": "vehicle-tagged passenger acceptance at all ordered stops",
                       "passengers_delivered": {str(station): amount for station, amount in delivered.items()},
                       "vehicle": result["vehicle"]}
            result = {**result, "service_summary": summary, "events": events,
                      "final_identity": current, "completed_save": str(session.save("bus-service-final"))}
            path = Path(result["job_file"])
            record = json.loads(path.read_text())
            record.update(state="operating", result=result)
            _persist(path, record)
            session.manifest.update(job_state="operating", result=result)
            session.write()
            return result
        session.remaining()
        time.sleep(min(0.5, session.remaining()))
