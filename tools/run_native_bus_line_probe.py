#!/usr/bin/env python3
"""Prove a multi-town bus line or turn an existing two-town line into three."""

import argparse
import itertools
import json
from pathlib import Path
import time

import native_bus
from admin_transport import AdminTransportError
from native_bus_transport import BusBridge
from native_mutation_journal import normalize_position
from native_play_session import NativeSession
from native_railway import _identity
from run_environment_probe import require
from run_native_bus_probe import immutable, stable_assets
from run_control_probe import sha256_file


class ProbeSession(NativeSession):
    def __init__(self, *, town_density="normal", **kwargs):
        self.town_density = town_density
        super().__init__(**kwargs)
        self.manifest["probe_town_density"] = town_density

    def stage(self, profile, port, admin_port=None):
        config, metadata = super().stage(profile, port, admin_port)
        if self.town_density == "high" and admin_port is not None:
            text = config.read_text(encoding="utf-8")
            require("number_towns = 2" in text, "probe could not locate normal town-density setting")
            config.write_text(text.replace("number_towns = 2", "number_towns = 3"), encoding="utf-8")
            metadata["config_sha256"] = sha256_file(config)
        return config, metadata


def assets(observed):
    return {**stable_assets(observed),
            "orders": {str(bus["vehicle_id"]): bus["orders"] for bus in observed["buses"]}}


def nonmutating_rejection(session, planner):
    before = native_bus.inspect(session)
    try:
        planner()
    except RuntimeError as exc:
        require("above construction cap" in str(exc), f"unexpected cap refusal: {exc}")
    else:
        raise RuntimeError("one-unit bus line budget unexpectedly accepted")
    after = native_bus.inspect(session)
    require(assets(before) == assets(after), "planning changed bus assets/orders")
    require(normalize_position(before["identity"]) == normalize_position(after["identity"]),
            "planning changed operation position")
    require(before["identity"]["companies"][0]["loan"] == after["identity"]["companies"][0]["loan"],
            "planning changed loan")
    # A running existing bus can earn revenue or incur running expenses.
    if not before["buses"]:
        require(before["identity"]["companies"] == after["identity"]["companies"],
                "new-line planning changed finances")


def check_reload(session, result, records, initial_save, plan, job_id):
    before = assets(native_bus.inspect(session))
    position = _identity(session)
    session.deadline = time.monotonic() + 120
    session.start_world("bus-line-reload", save=result["completed_save"])
    require(before == assets(native_bus.inspect(session)), "reload changed line assets/orders")
    bridge = BusBridge(session.admin)
    for entry in records:
        wire = entry["wire"]
        retained = bridge.operation(result["world_id"], wire["operation_hi"], wire["operation_lo"])
        require(immutable(retained) == immutable(entry["outcome"]), "reload changed a retained line action")
        replay = bridge.mutate(**wire, timeout=session.remaining())
        require(immutable(replay) == immutable(retained), "exact line replay changed a retained action")
    require(normalize_position(position) == normalize_position(_identity(session)), "replay changed history")
    require(before == assets(native_bus.inspect(session)), "replay duplicated/edited line assets")
    session.check("all_line_outcomes_reload_replay", {"records": len(records), "position": _identity(session)})
    session.start_world("bus-line-older-save", save=initial_save)
    try:
        native_bus.execute_bus(session, plan, job_id)
    except RuntimeError as exc:
        require("loaded world/operation position" in str(exc), f"unexpected older-save refusal: {exc}")
    else:
        raise RuntimeError("older save inherited completed line work")
    session.check("line_older_save_refusal")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261024)
    parser.add_argument("--town-density", choices=("normal", "high"), default="normal",
                        help="explicit ordinary-map test setting; product default is unchanged")
    parser.add_argument("--towns", type=int, nargs=3,
                        help="ordered three-town search selection; insertion mode builds the first pair")
    parser.add_argument("--add-town", type=int)
    parser.add_argument("--existing-save", type=Path,
                        help="copy a prior two-town bus service for the insertion-only gate")
    parser.add_argument("--existing-job", type=Path,
                        help="the prior service's durable job JSON, paired with --existing-save")
    parser.add_argument("--line-only", action="store_true",
                        help="verify the new three-town line without requiring a fourth town")
    parser.add_argument("--insert-index", type=int, default=1)
    parser.add_argument("--deadline", type=float, default=900)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    session = ProbeSession(timeout=args.deadline, seed=args.seed, visible=args.show,
                           map_style="normal", town_density=args.town_density)
    failure = None
    try:
        require((args.existing_save is None) == (args.existing_job is None),
                "supply both --existing-save and --existing-job")
        initial = session.start_world("bus-line-initial", save=args.existing_save)
        initial_save = session.save("bus-line-initial")
        towns = native_bus.discover(session)
        session.manifest["towns"] = towns
        if args.existing_job is not None:
            base_record = json.loads(args.existing_job.read_text())
            result = base_record["result"]
            require(result["world_id"] == initial["world_id"], "existing job belongs to another world")
            require(normalize_position(base_record["outcomes"][-1]["outcome"]) == normalize_position(initial),
                    "existing save does not match the prior job's retained position")
            town_ids = [base_record["plan"]["source"]["town_id"], base_record["plan"]["destination"]["town_id"]]
            session.check("copied_existing_two_town_line", {
                "save": str(args.existing_save), "job": str(args.existing_job), "vehicle": result["vehicle"]})
        else:
            result, town_ids = build_initial_line(session, args, initial, towns)
        if args.line_only:
            require(args.existing_save is None, "--line-only cannot be combined with --existing-save")
            job = json.loads(Path(result["job_file"]).read_text())
            check_reload(session, result, job["outcomes"], initial_save, job["plan"], job["job_id"])
            return session.finish()
        before_edit = native_bus.inspect(session)
        original = next(bus for bus in before_edit["buses"] if bus["vehicle_id"] == result["vehicle"])
        selected_towns = [t for t in towns if t["town_id"] in town_ids]
        alternatives = sorted((t for t in towns if t["town_id"] not in town_ids),
                              key=lambda t: (min(native_bus.distance(t["tile"], a["tile"], initial["map_width"])
                                                for a in selected_towns), t["town_id"]))
        if args.add_town is not None:
            alternatives = [t for t in alternatives if t["town_id"] == args.add_town]
        session.manifest["insertion_planning_trials"] = []
        edit_plan = None
        for town in alternatives[:12]:
            try:
                candidate = native_bus.plan_bus_stops(
                    session, result["vehicle"], [town["town_id"]], args.insert_index, 50000, 10000, record=False)
            except AdminTransportError:
                raise
            except RuntimeError as exc:
                session.manifest["insertion_planning_trials"].append(
                    {"town_id": town["town_id"], "failure": str(exc), "construction_started": False})
                session.write()
                continue
            edit_plan, added_town = candidate, town["town_id"]
            break
        require(edit_plan is not None, "bounded new-stop search returned no plan; inspect retained trials")
        session.check("existing_line_read_only_plan", edit_plan)
        print(json.dumps({"existing_vehicle": result["vehicle"], "add_town": added_town,
                          "insert_index": args.insert_index, "quote": edit_plan["quoted_total"],
                          "operations": edit_plan["operation_count"]}), flush=True)
        nonmutating_rejection(session, lambda: native_bus.plan_bus_stops(
            session, result["vehicle"], [added_town], args.insert_index, 1, 10000, record=False))
        session.check("existing_line_cap_nonmutation")
        session.deadline = time.monotonic() + args.deadline
        edited = native_bus.execute_bus(session, edit_plan, "insert-line-stop")
        edited = native_bus.verify_bus(session, edited)
        after_edit = native_bus.inspect(session)
        require(edited["vehicle"] == result["vehicle"], "insertion replaced the original bus")
        require(stable_assets(before_edit)["buses"] == stable_assets(after_edit)["buses"],
                "insertion bought or replaced a bus")
        require(before_edit["bus_depots"] == after_edit["bus_depots"], "insertion changed depots")
        require(all(stop in after_edit["bus_stops"] for stop in before_edit["bus_stops"]),
                "insertion changed an old stop")
        vehicle = next(bus for bus in after_edit["buses"] if bus["vehicle_id"] == edited["vehicle"])
        remaining = vehicle["orders"][:args.insert_index] + vehicle["orders"][args.insert_index + 1:]
        require(remaining == original["orders"], "insertion replaced/reordered old orders")
        require(len(vehicle["orders"]) == len(original["orders"]) + 1, "insertion did not add exactly one stop")
        session.check("same_bus_expanded_passenger_service", edited)
        require(native_bus.execute_bus(session, edit_plan, "insert-line-stop") == edited,
                "duplicate insertion did not return its retained result")
        session.check("insertion_duplicate")
        records = list(base_record["outcomes"]) if args.existing_job is not None else (
            json.loads(Path(result["job_file"]).read_text())["outcomes"])
        records.extend(json.loads(Path(edited["job_file"]).read_text())["outcomes"])
        check_reload(session, edited, records, initial_save, edit_plan, "insert-line-stop")
    except Exception as exc:
        failure = exc
        if session.admin is not None and session.server is not None and session.server.poll() is None:
            try:
                session.deadline = time.monotonic() + 20
                session.manifest["failure_save"] = str(session.save("bus-line-failed"))
            except Exception as save_error:
                session.manifest["failure_save_error"] = f"{type(save_error).__name__}: {save_error}"
        session.write()
    return session.finish(failure)


def build_initial_line(session, args, initial, towns):
    triples = sorted(itertools.permutations(towns, 3), key=lambda ts: (
        sum(native_bus.distance(a["tile"], b["tile"], initial["map_width"])
            for a, b in zip(ts, ts[1:])), tuple(t["town_id"] for t in ts)))
    if args.towns:
        triples = [ts for ts in triples if [t["town_id"] for t in ts] == args.towns]
    session.manifest["line_planning_trials"] = []
    plan = None
    for source, via, destination in triples[:24]:
        ids = [source["town_id"], via["town_id"], destination["town_id"]]
        if not args.line_only:
            ids = ids[:2]
        try:
            candidate = native_bus.plan_bus(
                session, ids[0], ids[-1], 50000, 10000, via_town_ids=ids[1:-1], record=False)
        except AdminTransportError:
            raise
        except RuntimeError as exc:
            session.manifest["line_planning_trials"].append(
                {"town_ids": ids, "failure": str(exc), "construction_started": False})
            session.write()
            continue
        if not args.line_only and candidate["available_records"] - candidate["operation_count"] < 4:
            session.manifest["line_planning_trials"].append(
                {"town_ids": ids, "failure": "insufficient history left for the insertion gate",
                 "construction_started": False})
            session.write()
            continue
        plan, town_ids = candidate, ids
        break
    require(plan is not None, "bounded bus-line search returned no plan; inspect retained trials")
    label = "three_town" if args.line_only else "two_town_base"
    session.check(f"{label}_read_only_plan", plan)
    print(json.dumps({"artifact": str(session.artifacts), "town_ids": town_ids,
                      "quote": plan["quoted_total"], "operations": plan["operation_count"]}), flush=True)
    nonmutating_rejection(session, lambda: native_bus.plan_bus(
        session, town_ids[0], town_ids[-1], 1, 10000, via_town_ids=town_ids[1:-1], record=False))
    session.check(f"{label}_cap_nonmutation")
    session.deadline = time.monotonic() + args.deadline
    commissioned = native_bus.execute_bus(session, plan, "initial-bus-line")
    result = native_bus.verify_bus(session, commissioned)
    session.check(f"{label}_passenger_service", result)
    require(native_bus.execute_bus(session, plan, "initial-bus-line") == result,
            "duplicate initial line job did not return its retained result")
    session.check(f"{label}_duplicate")
    return result, town_ids


if __name__ == "__main__":
    raise SystemExit(main())
