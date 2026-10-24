#!/usr/bin/env python3
"""Exercise one bounded native railway between observed existing businesses."""

import argparse
import json

import native_railway
from native_play_session import NativeSession
from run_environment_probe import require
import run_native_train_purchase_probe as purchase
from run_native_train_configuration_probe import immutable_config
from run_native_train_orders_probe import read_orders


def immutable_outcome(record, kind):
    return immutable_config({
        "engine_id": 0xFFFF, "length": 0, "created_asset_id": 0xFFFFFFFF,
        **record, "kind": record.get("kind", record.get("infrastructure_kind", kind))})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=6)
    parser.add_argument("--deadline", type=float, default=900)
    parser.add_argument("--source", type=int)
    parser.add_argument("--destination", type=int)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    session = NativeSession(timeout=args.deadline, seed=args.seed, visible=args.show)
    failure = None
    try:
        identity = session.start_world("initial")
        session.save("native-initial")
        discovery = native_railway.discover(session.admin)
        session.manifest["discovery"] = discovery
        session.write()
        require(discovery["business_pairs"], "no existing coal business pair")
        pair = discovery["business_pairs"][0]
        source = pair["source_id"] if args.source is None else args.source
        destination = pair["destination_id"] if args.destination is None else args.destination
        print(json.dumps({"selected_source": source, "selected_destination": destination,
                          "nearest_pair": pair, "artifacts": str(session.artifacts)}), flush=True)
        before = purchase.snapshot(session, identity["world_id"])
        try:
            native_railway.plan_railway(session, source, destination, 1, 10000)
        except RuntimeError as exc:
            require("above construction cap" in str(exc), f"unexpected planning failure: {exc}")
            session.check("low_budget_rejected", str(exc))
        else:
            raise RuntimeError("one-unit construction cap unexpectedly accepted")
        require(purchase.snapshot(session, identity["world_id"]) == before,
                "planning/quotes/budget rejection changed assets or finances")
        session.check("planning_is_nonmutating")
        plan = native_railway.plan_railway(session, source, destination, 50000, 10000)
        session.check("whole_job_plan", {"cost": plan["quoted_total"],
                                       "operations": plan["operation_count"]})
        result = native_railway.execute_railway(session, plan, "native-probe")
        session.check("native_commissioned", result)
        result = native_railway.verify_service(session, result)
        session.check("two_native_deliveries", result["service_summary"])
        require(native_railway.execute_railway(session, plan, "native-probe") == result,
                "durable completed-job lookup differs")
        session.check("duplicate_job_no_mutation")
        retained = json.loads((session.artifacts / "jobs/native-probe.json").read_text())["outcomes"]
        before_reload = purchase.snapshot(session, identity["world_id"])
        session.start_world("reload", save=result["completed_save"])
        reloaded = purchase.snapshot(session, identity["world_id"])
        for key in ("world_id", "sequence", "head", "stations", "depots"):
            require(reloaded[key] == before_reload[key], f"reload changed {key}")
        part_keys = ("vehicle_id", "owner", "first_vehicle_id", "previous_vehicle_id",
                     "next_vehicle_id", "engine_id", "is_primary", "stopped",
                     "crashed", "cargo_type", "cargo_capacity")
        stable_parts = lambda snapshot: [
            {key: part[key] for key in part_keys} for part in snapshot["parts"]]
        require(stable_parts(reloaded) == stable_parts(before_reload), "reload changed consist")
        require(read_orders(session.admin, identity["world_id"], 0, result["vehicle"],
                            session.remaining)[0] == result["orders"], "reload changed orders")
        replies = []
        for entry in retained:
            wire = entry["wire"]
            status = session.admin.copilot_train_configuration_status(
                world_id=identity["world_id"], operation_hi=wire["operation_hi"],
                operation_lo=wire["operation_lo"], timeout=session.remaining())
            require(immutable_outcome(status, status["kind"]) ==
                    immutable_outcome(entry["outcome"], status["kind"]),
                    "reload changed retained command outcome")
            method = (session.admin.copilot_configure_train if "action" in wire else
                      session.admin.copilot_build_train if "depot_tile" in wire else
                      session.admin.copilot_build_infrastructure if "infrastructure_kind" in wire else
                      session.admin.copilot_build_single_rail)
            replay = method(**wire, timeout=session.remaining())
            require(immutable_outcome(replay, status["kind"]) == immutable_outcome(status, status["kind"]),
                    "replay changed original command outcome")
            replies.append(status)
        after_replay = purchase.snapshot(session, identity["world_id"])
        for key in ("world_id", "sequence", "head", "stations", "depots"):
            require(after_replay[key] == reloaded[key], f"replay mutated {key}")
        require(stable_parts(after_replay) == stable_parts(reloaded), "replay changed consist")
        require(after_replay["companies"][0]["loan"] == before_reload["companies"][0]["loan"],
                "reload/replay changed loan")
        session.check("reload_and_exact_replay", {"outcomes": replies, "snapshot": after_replay})
    except Exception as exc:
        failure = exc
    return session.finish(failure)


if __name__ == "__main__":
    raise SystemExit(main())
