#!/usr/bin/env python3
"""Prove a bounded passenger bus service on an ordinary generated world."""

import argparse
import json
from pathlib import Path

import native_bus
from admin_transport import AdminTransportError, CopilotBridgeError
from native_bus_transport import BusBridge
from native_mutation_journal import normalize_position
from native_play_session import NativeSession
from native_railway import _identity
from run_environment_probe import require


def stable_assets(value):
    return {
        "stops": value["bus_stops"], "depots": value["bus_depots"],
        "buses": [{k: bus[k] for k in ("vehicle_id", "engine_id", "owner", "cargo_type", "cargo_capacity")}
                  for bus in value["buses"]],
    }


def immutable(value):
    fields = ("operation", "payload_hash", "state_name", "kind", "tile", "company_id",
              "orientation", "road_bits", "max_cost", "actual_cost", "error",
              "operation_sequence", "created_asset_id", "engine_id",
              "vehicle_id", "target_id", "order_index", "policy", "completed_frame")
    return {key: value[key] for key in fields if key in value}


def check_guards(session, plan):
    identity, bridge = _identity(session), BusBridge(session.admin)
    step = next(s for s in plan["steps"] if s["kind"] == native_bus.STOP)
    fields = {k: v for k, v in step.items() if k not in ("max_cost", "town_id")}
    quote = native_bus.quote_step(bridge, plan["world_id"], step)
    native_bus.require_quote(quote, stop=True)
    require(quote["cost"] > 0, "cap guard requires a positive normal stop quote")
    bound = quote["cost"] - 1
    guard_plan = {**plan, "quoted_total": bound, "construction_cap": bound}
    initial = native_bus.inspect(session)
    for index, changed in enumerate(({"road_bits": 1}, {"engine_id": 116}, {"policy": 1})):
        job_id = f"invalid-bus-shape-{index}"
        path = session.artifacts / "jobs" / f"{job_id}.json"
        record = {"initial": initial["identity"], "outcomes": [], "spent": 0}
        executor = native_bus.JournaledExecutor(
            session, guard_plan, job_id, record, path, identity, bridge.operation)
        try:
            executor.mutate(bridge.mutate, {**fields, **changed}, bound, job_id)
        except CopilotBridgeError as exc:
            require("invalid Copilot argument" in str(exc), f"unexpected shape rejection: {exc}")
        else:
            raise RuntimeError("invalid bus command shape was admitted")
        require(quote["retained_count"] == native_bus.quote_step(
            bridge, plan["world_id"], step)["retained_count"], "invalid shape consumed retained history")
        require(normalize_position(identity) == normalize_position(_identity(session)),
                "invalid shape changed operation position")
    session.check("bus_invalid_shape_nonadmission")
    path = session.artifacts / "jobs" / "bus-cap-guard.json"
    record = {"initial": initial["identity"], "outcomes": [], "spent": 0}
    executor = native_bus.JournaledExecutor(
        session, guard_plan, "bus-cap-guard", record, path, identity, bridge.operation)
    try:
        executor.mutate(bridge.mutate, fields, bound, "below-cap-stop")
    except RuntimeError as exc:
        require("ended rejected" in str(exc), f"unexpected capped-stop failure: {exc}")
    else:
        raise RuntimeError("below-cap bus stop unexpectedly completed")
    entry = record["outcomes"][0]
    require(entry["outcome"]["actual_cost"] == 0, "capped rejection charged money")
    require(initial["identity"]["companies"] == _identity(session)["companies"], "guards changed finances")
    require(stable_assets(initial) == stable_assets(native_bus.inspect(session)), "guards changed assets")
    require(normalize_position(identity) == normalize_position(_identity(session)), "guards changed successful head")
    saved = session.save("bus-cap-rejected")
    session.start_world("bus-cap-rejected-reload", save=saved)
    reply = BusBridge(session.admin).mutate(**entry["wire"], timeout=session.remaining())
    require(immutable(reply) == immutable(entry["outcome"]), "rejected bus record changed on reload/replay")
    session.check("bus_cap_rejection_reload_replay", entry["outcome"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261024)
    parser.add_argument("--source", type=int)
    parser.add_argument("--destination", type=int)
    parser.add_argument("--deadline", type=float, default=900)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    session = NativeSession(timeout=args.deadline, seed=args.seed, visible=args.show, map_style="normal")
    failure = None
    try:
        initial = session.start_world("bus-initial")
        initial_save = session.save("bus-initial")
        towns = native_bus.discover(session)
        session.manifest["towns"] = towns
        sample = []
        for start in range(0, initial["map_width"] * initial["map_height"], 512):
            sample.extend(session.admin.copilot_tile_snapshot(initial["world_id"], start, 32)["tiles"])
        types = {t["tile_type"] for t in sample if t["valid"]}
        require({2, 3, 4, 6}.issubset(types) and any(t["slope"] for t in sample),
                "normal-map gate requires actual roads, houses, trees, water and slopes")
        session.check("normal_map_generation", {
            "width": initial["map_width"], "height": initial["map_height"], "towns": len(towns),
            "sample_tiles": len(sample), "sample_tile_types": sorted(types),
            "sample_sloped_tiles": sum(bool(t["slope"]) for t in sample)})
        pairs = sorted(
            ((native_bus.distance(a["tile"], b["tile"], initial["map_width"]), a, b)
             for a in towns for b in towns if a["town_id"] < b["town_id"]),
            key=lambda item: (item[0], item[1]["town_id"], item[2]["town_id"]))
        if args.source is not None or args.destination is not None:
            require(args.source is not None and args.destination is not None, "supply both source and destination")
            pairs = [p for p in pairs if {p[1]["town_id"], p[2]["town_id"]} == {args.source, args.destination}]
        require(pairs, "no distinct observed town pair")
        session.manifest["planning_trials"] = []
        plan = None
        for _, a, b in pairs[:12]:
            try:
                candidate = native_bus.plan_bus(session, a["town_id"], b["town_id"], 50000, 10000, record=False)
            except AdminTransportError:
                raise
            except RuntimeError as exc:
                session.manifest["planning_trials"].append(
                    {"source": a, "destination": b, "failure": str(exc), "construction_started": False})
                session.write()
                continue
            plan = candidate
            break
        require(plan is not None, "bounded nearby-town trials returned no supported bus plan; inspect retained failures")
        session.check("normal_map_bus_plan", plan)
        print(json.dumps({"artifact": str(session.artifacts), "source": plan["source"],
                          "destination": plan["destination"], "quote": plan["quoted_total"],
                          "roads": plan["road_tiles_to_build"], "operations": plan["operation_count"]}), flush=True)
        observed = native_bus.inspect(session)
        position = _identity(session)
        try:
            native_bus.plan_bus(session, plan["source"]["town_id"], plan["destination"]["town_id"], 1, 10000)
        except RuntimeError as exc:
            require("above construction cap" in str(exc), f"unexpected low-budget rejection: {exc}")
        else:
            raise RuntimeError("one-unit bus budget unexpectedly accepted")
        require(normalize_position(position) == normalize_position(_identity(session)), "planning changed history")
        require(stable_assets(observed) == stable_assets(native_bus.inspect(session)), "planning changed bus assets")
        require(position["companies"] == _identity(session)["companies"], "planning changed finances")
        session.check("bus_low_budget_nonmutation")
        result = native_bus.execute_bus(session, plan, "bus-probe")
        session.check("bus_independent_commissioning", result)
        result = native_bus.verify_bus(session, result)
        session.check("passenger_deliveries_both_towns", result["service_summary"])
        require(native_bus.execute_bus(session, plan, "bus-probe") == result, "duplicate bus job lookup differs")
        session.check("duplicate_bus_no_mutation")
        records = json.loads(Path(result["job_file"]).read_text())["outcomes"]
        before = native_bus.inspect(session)
        before_identity = _identity(session)
        session.start_world("bus-reload", save=result["completed_save"])
        require(stable_assets(before) == stable_assets(native_bus.inspect(session)), "reload changed bus assets")
        bridge = BusBridge(session.admin)
        for entry in records:
            wire = entry["wire"]
            reply = bridge.operation(result["world_id"], wire["operation_hi"], wire["operation_lo"])
            require(immutable(reply) == immutable(entry["outcome"]), "reload changed retained bus outcome")
            replay = bridge.mutate(**wire, timeout=session.remaining())
            require(immutable(replay) == immutable(reply), "exact bus replay changed retained outcome")
        require(normalize_position(before_identity) == normalize_position(_identity(session)), "replay changed history")
        require(stable_assets(before) == stable_assets(native_bus.inspect(session)), "replay duplicated bus assets")
        session.check("bus_retained_reload_replay", {"records": len(records), "position": _identity(session)})
        session.start_world("bus-older-save", save=initial_save)
        try:
            native_bus.execute_bus(session, plan, "bus-probe")
        except RuntimeError as exc:
            require("loaded world/operation position" in str(exc), f"unexpected older-save failure: {exc}")
        else:
            raise RuntimeError("older save inherited completed bus job")
        session.check("bus_older_save_refuses_false_completion")
        check_guards(session, plan)
    except Exception as exc:
        failure = exc
        session.manifest["failure_process_state"] = {
            "server_returncode": session.server.poll() if session.server is not None else None,
            "client_returncode": session.client.poll() if session.client is not None else None}
        if session.admin is not None and session.server is not None and session.server.poll() is None:
            try:
                session.manifest["failure_save"] = str(session.save("bus-failed"))
            except Exception as save_error:
                session.manifest["failure_save_error"] = f"{type(save_error).__name__}: {save_error}"
        session.write()
    return session.finish(failure)


if __name__ == "__main__":
    raise SystemExit(main())
