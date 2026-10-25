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


def find_path(records, width, height, sources, destinations, *, max_expansions=100000):
    """Bounded multi-source A*: prefer existing roads, never clear buildings."""
    goals = {site["tile"]: site for site in destinations}
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
            if not usable(target):
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


def plan_bus(session, source_id, destination_id, cap, reserve, *, record=True):
    for value, name, minimum in ((source_id, "source_town_id", 0), (destination_id, "destination_town_id", 0),
                                 (cap, "construction_cap", 1), (reserve, "operating_reserve", 0)):
        _integer(value, name, minimum)
    require(source_id != destination_id, "bus endpoints must be different towns")
    identity, bridge = _identity(session), BusBridge(session.admin)
    world = identity["world_id"]
    towns = {t["town_id"]: t for t in discover(session)}
    require(source_id in towns and destination_id in towns, "select observed town IDs")
    source, destination = towns[source_id], towns[destination_id]
    records, frames = read_corridor(session, bridge, identity, source, destination)
    stations = []
    for town in (source, destination):
        admitted = []
        for candidate in candidate_stops(records, town, identity["map_width"]):
            step = {"kind": STOP, "tile": candidate["tile"],
                    "orientation": 0 if candidate["road_bits"] == 5 else 1, "town_id": town["town_id"]}
            quote = quote_step(bridge, world, step)
            if (quote["supported_profile"] and quote["quote_success"] and
                    quote["passenger_acceptance"] >= 8 and quote["passenger_production"] > 0):
                admitted.append({**candidate, "step": {**step, "max_cost": quote["cost"]}})
                if len(admitted) >= 12:
                    break
        require(admitted, f"no supported roadside bus stop accepting/producing passengers in {town['name']}")
        stations.append(admitted)
    require(any(a["tile"] != b["tile"] for a in stations[0] for b in stations[1]),
            "no distinct bus stop endpoints for the two towns")
    geometry = find_path(records, identity["map_width"], identity["map_height"], *stations)
    require(geometry["source"]["tile"] != geometry["destination"]["tile"],
            "bus stops for different towns must be distinct; overlapping endpoints are unsupported")
    steps = road_steps(geometry["path"], records, identity["map_width"], identity["map_height"])
    selected_depot = None
    for road_tile in geometry["path"]:
        for direction in range(4):
            depot_tile = neighbour(road_tile, direction, identity["map_width"], identity["map_height"])
            site = records.get(depot_tile)
            if (depot_tile in geometry["path"] or not usable(site) or site["tile_type"] not in (0, 4)
                    or site["slope"] != 0):
                continue
            step = {"kind": DEPOT, "tile": depot_tile, "orientation": (direction + 2) % 4}
            quote = quote_step(bridge, world, step)
            if not quote["quote_success"] or not quote["supported_profile"]:
                continue
            # Add only a branch on a road tile, never rebuild a drive-through stop.
            if road_tile in (geometry["source"]["tile"], geometry["destination"]["tile"]):
                continue
            existing = next((s for s in steps if s["tile"] == road_tile), None)
            mask = (existing["road_bits"] if existing else records[road_tile]["road_bits"]) | (1 << direction)
            connection = {"kind": ROAD, "tile": road_tile, "road_bits": mask}
            connection_quote = quote_step(bridge, world, connection)
            if not connection_quote["quote_success"]:
                continue
            if existing:
                existing["road_bits"] = mask
            elif mask != records[road_tile]["road_bits"]:
                steps.append(connection)
            selected_depot = step
            break
        if selected_depot:
            break
    require(selected_depot, "no supported connected roadside depot site in the observed corridor")
    # Secure authority-sensitive stops before any disclosed tree clearing.
    steps = [geometry["source"]["step"], geometry["destination"]["step"], selected_depot] + steps
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
    operation_count = len(steps) + 4
    available = quotes[-1]["capacity"] - quotes[-1]["retained_count"]
    require(operation_count <= available,
            f"bus service needs {operation_count} retained records, only {available} available; nothing built")
    require(total <= cap, f"whole bus service costs {total}, above construction cap {cap}; nothing built")
    require(after["companies"][0]["money"] >= total + reserve,
            f"bus service costs {total} plus reserve {reserve}; insufficient cash; nothing built")
    result = {"world_id": world, "position": {"sequence": identity["sequence"], "head": identity["head"]},
              "company_id": 0, "source": source, "destination": destination, "cargo_id": 0,
              "construction_cap": cap, "operating_reserve": reserve, "quoted_total": total,
              "operation_count": operation_count, "available_records": available,
              "geometry": {"path": geometry["path"], "depot": selected_depot},
              "steps": steps, "quotes": quotes, "engine": engine, "observation_frame_span": frames,
              "road_tiles_to_build": sum(s["kind"] == ROAD for s in steps),
              "scope": "one ordinary passenger bus; existing two-way roads plus bounded new road/tree clearing; no demolition, bridges or terraforming"}
    if record:
        session.manifest.update(job_state="planning", plan=result)
        session.write()
    return result


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
        require(len(orders) == 2 and [o["destination_id"] for o in orders] == stops
                and all(o["order_type"] == 1 and o["load_type"] == 0 and o["unload_type"] == 0 for o in orders),
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
                  "destination_station": stops[1], "spent": record["spent"], "orders": orders,
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
        delivered = {station: sum(e["amount"] for e in events if e["kind"] == "delivery"
                                 and e["station"] == station and e["vehicle"] == result["vehicle"]
                                 and e["company"] == 0 and e["cargo"] == 0)
                     for station in (result["source_station"], result["destination_station"])}
        if all(amount > 0 for amount in delivered.values()):
            current = _identity(session)
            require(current["companies"][0]["loan"] == result["initial"]["companies"][0]["loan"], "bus service changed loan")
            summary = {"scope": "vehicle-tagged passenger acceptance at both stops",
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
