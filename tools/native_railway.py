"""Deterministic, budgeted native construction for the first isolated coal line."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from native_mutation_journal import Journal, normalize_position
from native_world_snapshot import read_tile_window
import native_route_plan as planner
import run_native_train_purchase_probe as purchase
from run_native_train_orders_probe import read_orders
from run_vehicle_probe import validate_native_service_events
from run_environment_probe import require


def discover(admin):
    identity = admin.copilot_identity(company_id=0)
    industries = []
    for start in range(0, 4096, 8):
        page = admin.copilot_industry_details(identity["world_id"], start, 8)
        industries.extend(page["industries"])
        if page["count"] < 8:
            break
    else:
        raise RuntimeError("industry discovery exceeded its bounded record scan")
    width = identity["map_width"]
    producers = [i for i in industries if 1 in i["produced_cargo"]]
    acceptors = [i for i in industries if 1 in i["accepted_cargo"]]
    pairs = sorted(
        ({"source_id": s["industry_id"], "destination_id": d["industry_id"],
          "source": s["name"], "destination": d["name"],
          "distance": abs(s["tile"] % width - d["tile"] % width)
                      + abs(s["tile"] // width - d["tile"] // width)}
         for s in producers for d in acceptors if s["industry_id"] != d["industry_id"]),
        key=lambda pair: (pair["distance"], pair["source_id"], pair["destination_id"]),
    )
    after = admin.copilot_identity(company_id=0)
    require(normalize_position(after) == normalize_position(identity), "world changed during industry discovery")
    return {"world_id": identity["world_id"], "sequence": identity["sequence"],
            "industries": industries, "business_pairs": pairs, "atomic": False}


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _identity(session):
    return session.admin.copilot_identity(company_id=0, timeout=session.remaining())


def _quote(session, world_id, step, industry_id=0xFFFF):
    return session.admin.copilot_construction_quote(
        world_id=world_id, company_id=0, tile=step["tile"], rail_type=step.get("rail_type", 0),
        orientation=step.get("track", step.get("axis", step.get("orientation", 0))),
        kind=step["kind"], length=step.get("length", 0),
        industry_id=industry_id, cargo_id=1, timeout=session.remaining())


def plan_railway(session, source_id, destination_id, cap, reserve, *, record=True):
    for value, name, minimum in ((source_id, "source_id", 0), (destination_id, "destination_id", 0),
                                 (cap, "construction_cap", 1), (reserve, "operating_reserve", 0)):
        _integer(value, name, minimum)
    require(source_id != destination_id, "source and destination must differ")
    identity = _identity(session)
    require(identity["map_width"] <= 128 and identity["map_height"] <= 128,
            "alpha planning is bounded to maps no larger than 128x128")
    businesses = discover(session.admin)
    by_id = {i["industry_id"]: i for i in businesses["industries"]}
    require(source_id in by_id and destination_id in by_id, "selected business is not present")
    source, destination = by_id[source_id], by_id[destination_id]
    require(1 in source["produced_cargo"] and 1 in destination["accepted_cargo"],
            "selected businesses do not produce/accept standard coal")
    if record:
        session.manifest["job_state"] = "planning"
        session.write()
    window = read_tile_window(session.admin, x=0, y=0, width=identity["map_width"],
                              height=identity["map_height"], max_tiles=128 * 128)
    tiles = {t["tile"]: t for row in window["rows"] for t in row}
    candidates = []
    candidate_quotes = {}
    for industry, is_source in ((source, True), (destination, False)):
        proposed = planner.station_candidates(
            tiles, identity["map_width"], identity["map_height"], industry)
        admitted = []
        for candidate in proposed:
            step = {**candidate, "kind": 1}
            quote = _quote(session, identity["world_id"], step, industry["industry_id"])
            require(quote["supported_profile"], "only standard temperate without gameplay NewGRFs is supported")
            if (quote["quote_success"] and (quote["covers_producer"] if is_source else
                                           quote["industry_acceptance"] >= 8)):
                admitted.append(candidate)
                candidate_quotes[(candidate["tile"], candidate["axis"], industry["industry_id"])] = quote
        require(admitted, f"no supported clear level station site covering industry {industry['industry_id']}")
        candidates.append(admitted)
    geometry = planner.find_route(tiles, identity["map_width"], identity["map_height"],
                                  candidates[0], candidates[1])
    steps = [{**geometry["source_station"], "kind": 1},
             {**geometry["destination_station"], "kind": 1},
             {**geometry["depot"], "kind": 2, "length": 1}]
    steps += [{**rail, "kind": 0, "length": 0} for rail in geometry["rails"]]
    quotes = []
    for step in steps:
        quote = _quote(session, identity["world_id"], step)
        require(quote["quote_success"], f"normal construction test rejected tile {step['tile']}: {quote['error']}")
        require(quote["operation_state"] not in (1, 4), "pending/uncertain world operation blocks planning")
        step["max_cost"] = quote["cost"]
        step["rail_type"] = 0
        quotes.append(quote)
    catalog, _ = purchase.read_catalog(session.admin, identity["world_id"], 0, session.remaining)
    loco, wagon = purchase.choose_engines(catalog, 1)
    # This first runtime profile proves standard single-head plus one default coal wagon.
    require(loco["railveh_type"] == 0 and wagon["default_capacity"] > 0, "unsupported consist")
    total = sum(step["max_cost"] for step in steps) + loco["purchase_cost"] + wagon["purchase_cost"]
    after = _identity(session)
    require(normalize_position(after) == normalize_position(identity), "world/operation position changed while planning")
    available = quotes[-1]["capacity"] - quotes[-1]["retained_count"]
    operation_count = len(steps) + 6  # engine, wagon, attachment, two orders, start
    require(operation_count <= available, f"route needs {operation_count} retained records, only {available} available")
    require(total <= cap, f"whole railway costs {total}, above construction cap {cap}; nothing built")
    require(after["companies"][0]["money"] >= total + reserve,
            f"whole railway costs {total} plus operating reserve {reserve}; insufficient cash; nothing built")
    result = {
        "world_id": identity["world_id"], "position": {"sequence": identity["sequence"], "head": identity["head"]},
        "company_id": 0, "source": source, "destination": destination, "cargo_id": 1,
        "construction_cap": cap, "operating_reserve": reserve, "quoted_total": total,
        "operation_count": operation_count, "available_records": available,
        "geometry": geometry, "steps": steps, "locomotive": loco, "wagon": wagon,
        "catchment_quotes": [candidate_quotes[(site["tile"], site["axis"], industry["industry_id"])]
                             for site, industry in zip((geometry["source_station"], geometry["destination_station"]),
                                                       (source, destination))],
        "quotes": quotes, "observation_frame_span": [window["frame_min"], window["frame_max"]],
        "scope": "flat clear isolated standard coal line; no terraform, signals, refit or existing rail reuse",
    }
    if record:
        session.manifest["plan"] = result
        session.write()
    return result


def inspect_game(session):
    """Collect live bounded observations, without inferring profit or route health."""
    before = _identity(session)
    world_id = before["world_id"]
    businesses = discover(session.admin)
    assets = purchase.snapshot(session, world_id)
    catalog, catalog_pages = purchase.read_catalog(session.admin, world_id, 0, session.remaining)
    primary_parts = [part for part in assets["parts"] if part["is_primary"]]
    require(len(primary_parts) <= 16, "inspection supports at most 16 primary trains")
    trains = []
    frames = [before["frame"], *(page["frame"] for page in catalog_pages)]
    for primary in primary_parts:
        vehicle_id = primary["vehicle_id"]
        parts = [part for part in assets["parts"] if part["first_vehicle_id"] == vehicle_id]
        orders, order_pages = read_orders(session.admin, world_id, 0, vehicle_id, session.remaining)
        frames.extend(page["frame"] for page in order_pages)
        events, cursor, epoch, gap, complete = [], 0, None, False, False
        for _ in range(4):
            page = session.admin.copilot_vehicle_events(
                world_id=world_id, company_id=0, vehicle_id=vehicle_id,
                cursor=cursor, timeout=session.remaining())
            require(epoch is None or page["epoch"] == epoch,
                    "event observation epoch changed during inspection")
            epoch = page["epoch"]
            gap |= page["gap"]
            events.extend(page["events"])
            frames.append(page["frame"])
            require(page["next_seq"] >= cursor, "event cursor moved backwards")
            cursor = page["next_seq"]
            if len(page["events"]) < 16:
                complete = True
                break
        trains.append({
            "vehicle_id": vehicle_id, "parts": parts, "orders": orders,
            "recent_events": {"epoch": epoch, "gap": gap, "complete": complete,
                              "next_cursor": cursor, "events": events},
        })
    after = _identity(session)
    require(normalize_position(before) == normalize_position(after),
            "world/operation position changed during live inspection")
    require(businesses["world_id"] == world_id and assets["world_id"] == world_id,
            "inspection observations belong to a different world")
    frames.append(after["frame"])
    return {
        "world_id": world_id, "position": {"sequence": after["sequence"], "head": after["head"]},
        "company_id": 0, "identity": after, "industries": businesses["industries"],
        "business_pairs": businesses["business_pairs"],
        "stations": assets["stations"], "depots": assets["depots"],
        "train_parts": assets["parts"], "trains": trains,
        "buildable_rail_engines": [engine for engine in catalog if engine["buildable"]],
        "atomic": False, "observation_frame_span": [min(frames), max(frames)],
        "units": {"money": "integral engine money units, not formatted GUI currency",
                  "catalog": "engine-native values; max_speed is not a measured train speed"},
        "limitations": [
            "Pages are live observations, not an atomic snapshot.",
            "The current bridge does not expose per-train profit, actual speed, station waiting "
            "cargo, industry production rate, reliability or whole-company income breakdown.",
            "Historical delivery evidence is not proof that the current edited route is healthy.",
            "Empty departures are not emitted. Missing events do not prove inactivity.",
            "Business pairs are cargo-compatible observations, not confirmed buildable routes.",
            "Coal railway jobs require flat-clear standard coal routes of at most 50 rail tiles; "
            "all transport jobs share the world's 64 retained operation records.",
        ],
    }


def _persist(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class JournaledExecutor:
    """Shared sequential send boundary for railway and bus construction."""

    def __init__(self, session, plan, job_id, record, job_file, identity, poll):
        self.session, self.plan, self.job_id = session, plan, job_id
        self.record, self.job_file, self.identity = record, job_file, identity
        self.remaining_cost, self.poll = plan["quoted_total"], poll

    def mutate(self, method, fields, bound, label):
        session, plan, record = self.session, self.plan, self.record
        current = _identity(session)
        require(normalize_position(current) == normalize_position(self.identity), "world/position changed; construction stopped")
        require(current["companies"][0]["loan"] == record["initial"]["companies"][0]["loan"], "loan changed during job")
        require(record["spent"] + self.remaining_cost <= plan["construction_cap"], "remaining construction exceeds cap")
        require(current["companies"][0]["money"] >= self.remaining_cost + plan["operating_reserve"],
                "cash no longer covers remaining construction and reserve; partial work retained")
        operation = uuid.uuid4().int
        hi, lo = operation >> 64, operation & ((1 << 64) - 1)
        request = {"world_id": plan["world_id"], "company_id": 0, **fields, "max_cost": bound,
                   "expect_sequence": current["sequence"], "expect_head": current["head"],
                   "operation": {"hi": hi, "lo": lo}}
        digest = hashlib.blake2b(json.dumps(request, sort_keys=True).encode(), digest_size=16).digest()
        wire = {key: value for key, value in request.items()
                if key not in ("expect_sequence", "expect_head", "operation")}
        wire.update(expected_sequence=current["sequence"], expected_head_hi=current["head_hi"],
                    expected_head_lo=current["head_lo"], operation_hi=hi, operation_lo=lo,
                    payload_hash_hi=int.from_bytes(digest[:8], "big"),
                    payload_hash_lo=int.from_bytes(digest[8:], "big"))
        journal_path = session.artifacts / "journals" / self.job_id / f"{len(record['outcomes']):04d}-{label}.json"
        journal = Journal.create(journal_path, current)
        require(journal.record_pending(request), "intent was not durably recorded")
        record["pending_journal"] = str(journal_path)
        _persist(self.job_file, record)
        outcome = method(**wire, timeout=session.remaining())
        while outcome["state_name"] == "pending":
            time.sleep(min(0.05, session.remaining()))
            outcome = self.poll(world_id=plan["world_id"], operation_hi=hi, operation_lo=lo,
                                timeout=session.remaining())
        self.identity = _identity(session)
        state = journal.reconcile(self.identity, outcome)
        record["outcomes"].append({"label": label, "wire": wire, "outcome": outcome,
                                   "journal": str(journal_path)})
        record["pending_journal"] = None
        record["spent"] += outcome["actual_cost"]
        self.remaining_cost -= bound
        _persist(self.job_file, record)
        session.manifest["completed_operations"] = len(record["outcomes"])
        session.manifest["spent"] = record["spent"]
        session.write()
        require(state == "completed", f"{label} ended {state}; existing partial work retained: {journal_path}")
        require(0 <= outcome["actual_cost"] <= bound, f"{label} command cost exceeded bound")
        return outcome


def execute_railway(session, plan, job_id):
    if not isinstance(job_id, str) or not job_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in job_id):
        raise ValueError("job_id must be a nonempty alphanumeric/hyphen/underscore identifier")
    job_file = session.artifacts / "jobs" / f"{job_id}.json"
    if job_file.exists():
        old = json.loads(job_file.read_text(encoding="utf-8"))
        require(old["plan"] == plan, "job ID conflicts with its durable plan")
        require(old["state"] in ("commissioned", "operating"), "existing partial/pending job requires reconciliation; never retried")
        require(old.get("outcomes"), "durable job has no retained outcome position; reconciliation required")
        require(normalize_position(_identity(session)) == normalize_position(old["outcomes"][-1]["outcome"]),
                "durable job differs from loaded world/operation position; reconciliation required")
        return old["result"]
    identity = _identity(session)
    require(identity["world_id"] == plan["world_id"] and
            {"sequence": identity["sequence"], "head": identity["head"]} == plan["position"],
            "world/operation position differs from the approved plan")
    initial = purchase.snapshot(session, plan["world_id"])
    record = {"job_id": job_id, "state": "building", "plan": plan, "outcomes": [], "spent": 0,
              "initial": initial}
    _persist(job_file, record)
    session.manifest["job_state"] = "building"
    session.manifest["job_file"] = str(job_file)
    session.write()
    executor = JournaledExecutor(session, plan, job_id, record, job_file, identity,
                                 session.admin.copilot_train_configuration_status)
    mutate = executor.mutate

    try:
        built = []
        for index, step in enumerate(plan["steps"]):
            quote = _quote(session, plan["world_id"], step)
            require(quote["quote_success"] and quote["cost"] <= step["max_cost"],
                    f"tile {step['tile']} changed or price rose; partial work retained")
            if step["kind"] == 0:
                method = session.admin.copilot_build_single_rail
                fields = {key: step[key] for key in ("tile", "rail_type", "track")}
            else:
                method = session.admin.copilot_build_infrastructure
                fields = {"tile": step["tile"], "rail_type": step["rail_type"],
                          "orientation": step.get("axis", step.get("orientation", 0)),
                          "infrastructure_kind": step["kind"], "length": step["length"]}
            outcome = mutate(method, fields, step["max_cost"], f"build-{index}")
            built.append(outcome)
            if step["kind"] == 0:
                require(outcome["readback"]["has_rail"] and outcome["readback"]["owner"] == 0
                        and outcome["readback"]["track_bits"] == 1 << step["track"],
                        "independent rail geometry/ownership mismatch")
        source_station, destination_station = built[0]["created_asset_id"], built[1]["created_asset_id"]
        stations = purchase.read_stations(session.admin, plan["world_id"], 0, session.remaining)
        require(next(s for s in stations if s["station_id"] == destination_station)["acceptance_mask"] & 2,
                "built destination does not accept coal")
        depot_tile = plan["geometry"]["depot"]["tile"]
        vehicles = []
        for label in ("locomotive", "wagon"):
            engine = plan[label]
            catalog, _ = purchase.read_catalog(session.admin, plan["world_id"], 0, session.remaining)
            live = next(e for e in catalog if e["engine_id"] == engine["engine_id"])
            require(live["buildable"] and live["purchase_cost"] <= engine["purchase_cost"],
                    "engine no longer available at planned price")
            vehicles.append(mutate(session.admin.copilot_build_train,
                                   {"depot_tile": depot_tile, "engine_id": engine["engine_id"]},
                                   engine["purchase_cost"], label)["created_asset_id"])
        primary, wagon_id = vehicles
        common = {"tile": depot_tile, "order_index": 0, "policy": 0}
        mutate(session.admin.copilot_configure_train,
               {**common, "action": 4, "vehicle_id": wagon_id, "target_id": primary}, 0, "attach")
        for index, station in enumerate((source_station, destination_station)):
            mutate(session.admin.copilot_configure_train,
                   {**common, "action": 5, "vehicle_id": primary, "target_id": station,
                    "order_index": index, "policy": index}, 0, f"order-{index}")
        parts, _ = purchase.read_parts(session.admin, plan["world_id"], 0, session.remaining)
        by_id = {p["vehicle_id"]: p for p in parts}
        require(by_id[primary]["next_vehicle_id"] == wagon_id
                and by_id[wagon_id]["first_vehicle_id"] == primary
                and by_id[wagon_id]["previous_vehicle_id"] == primary
                and by_id[wagon_id]["cargo_type"] == 1
                and by_id[wagon_id]["cargo_capacity"] == plan["wagon"]["default_capacity"],
                "purchased consist independent identity/cargo/link check failed")
        orders, _ = read_orders(session.admin, plan["world_id"], 0, primary, session.remaining)
        require(orders == [
            {"order_type": 1, "destination_id": source_station, "load_type": 2, "unload_type": 4, "nonstop_flags": 0},
            {"order_type": 1, "destination_id": destination_station, "load_type": 4, "unload_type": 0, "nonstop_flags": 0}],
            "independent station orders do not match intent")
        page = session.admin.copilot_vehicle_events(world_id=plan["world_id"], company_id=0,
                                                   vehicle_id=primary, cursor=0, timeout=session.remaining())
        require(not page["gap"], "observation ring has a gap before start")
        mutate(session.admin.copilot_configure_train,
               {**common, "action": 6, "vehicle_id": primary, "target_id": 0xFFFFFFFF, "policy": 1}, 0, "start")
        result = {"job_id": job_id, "world_id": plan["world_id"], "company": 0, "cargo": 1,
                  "source_station": source_station, "destination_station": destination_station,
                  "source_industry": plan["source"]["industry_id"],
                  "destination_industry": plan["destination"]["industry_id"], "vehicle": primary,
                  "wagon": wagon_id, "spent": record["spent"], "construction_cap": plan["construction_cap"],
                  "operating_reserve": plan["operating_reserve"], "epoch": page["epoch"],
                  "cursor": page["next_seq"], "job_file": str(job_file),
                  "initial": initial, "parts": parts, "orders": orders}
        result["commissioned_save"] = str(session.save("native-commissioned"))
        record.update(state="commissioned", result=result)
        _persist(job_file, record)
        session.manifest.update(job_state="verifying", result=result)
        session.write()
        return result
    except Exception as exc:
        record["state"] = "partial"
        record["failure"] = f"{type(exc).__name__}: {exc}"
        _persist(job_file, record)
        session.manifest.update(job_state="partial", failure=record["failure"])
        session.write()
        raise


def verify_service(session, result):
    session.manifest["job_state"] = "verifying"
    cursor, events = result["cursor"], []
    while True:
        page = session.admin.copilot_vehicle_events(
            world_id=result["world_id"], company_id=0, vehicle_id=result["vehicle"],
            cursor=cursor, timeout=session.remaining())
        require(page["epoch"] == result["epoch"] and not page["gap"],
                "telemetry gap/world reload; service is unverified")
        events.extend(page["events"])
        cursor = page["next_seq"]
        session.manifest.update(native_events=events, last_native_telemetry=page)
        session.write()
        source_departures = [e for e in events if e["kind"] == "departure" and e["station"] == result["source_station"]]
        deliveries = [e for e in events if e["kind"] == "delivery" and e["industry"] == result["destination_industry"]]
        # Empty departures are not emitted; the third loaded departure proves two returns.
        if len(source_departures) >= 3 and len(deliveries) >= 2:
            summary = validate_native_service_events(events, result, result["vehicle"])
            current = _identity(session)
            require(current["companies"][0]["loan"] == result["initial"]["companies"][0]["loan"], "service changed loan")
            result = {**result, "service_summary": summary, "events": events,
                      "completed_save": str(session.save("native-service-final")),
                      "final_identity": current}
            job_file = Path(result["job_file"])
            record = json.loads(job_file.read_text(encoding="utf-8"))
            record.update(state="operating", result=result)
            _persist(job_file, record)
            session.manifest.update(job_state="operating", result=result)
            session.write()
            return result
        time.sleep(min(0.5, session.remaining()))
