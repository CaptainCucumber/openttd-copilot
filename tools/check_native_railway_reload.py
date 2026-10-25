#!/usr/bin/env python3
"""Check retained native railway identity against copied older/latest saves."""

import argparse
import json
from pathlib import Path
import shutil

import native_railway
from native_play_session import NativeSession
from run_environment_probe import require
import run_native_train_purchase_probe as purchase
from run_native_railway_probe import immutable_outcome
from run_native_train_orders_probe import read_orders
import run_control_probe as base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    source = args.run.resolve()
    record = json.loads((source / "jobs/native-probe.json").read_text())
    require(record["state"] == "operating", "reference job did not verify service")
    plan, result = record["plan"], record["result"]
    session = NativeSession(timeout=120)
    failure = None
    try:
        session.manifest["reference"] = {
            "path": str(source), "manifest_sha256": base.sha256_file(source / "manifest.json"),
            "job_sha256": base.sha256_file(source / "jobs/native-probe.json")}
        target = session.artifacts / "jobs/native-probe.json"
        target.parent.mkdir()
        shutil.copy2(source / "jobs/native-probe.json", target)
        loaded = session.start_world("older", save=source / "native-initial.sav")
        old = purchase.snapshot(session, result["world_id"])
        source_site = {**plan["geometry"]["source_station"], "kind": 1}
        destination_site = {**plan["geometry"]["destination_station"], "kind": 1}
        source_quote = native_railway._quote(session, result["world_id"], source_site,
                                            result["source_industry"])
        destination_quote = native_railway._quote(session, result["world_id"], destination_site,
                                                 result["destination_industry"])
        other_producers = [industry for industry in native_railway.discover(session.admin)["industries"]
                           if 1 in industry["produced_cargo"] and
                           industry["industry_id"] != result["source_industry"]]
        require(other_producers, "quote regression requires a second naturally generated coal producer")
        width = loaded["map_width"]
        other_producer = max(other_producers, key=lambda industry:
                             abs(industry["tile"] % width - source_site["tile"] % width) +
                             abs(industry["tile"] // width - source_site["tile"] // width))
        wrong_producer = native_railway._quote(session, result["world_id"], source_site,
                                              other_producer["industry_id"])
        wrong_acceptor = native_railway._quote(session, result["world_id"], destination_site,
                                              result["source_industry"])
        require(source_quote["quote_success"] and source_quote["covers_producer"] and
                destination_quote["quote_success"] and destination_quote["industry_acceptance"] >= 8,
                "selected-industry prospective catchment did not match")
        require(not wrong_producer["covers_producer"] and wrong_acceptor["industry_acceptance"] == 0,
                "prospective quote counted an unrelated industry")
        purchase.require_error(5, lambda: native_railway._quote(session, "wrong-world", source_site))
        require(purchase.snapshot(session, result["world_id"]) == old, "quote requests mutated world")
        session.check("selected_industry_quotes_nonmutating", {
            "source": source_quote, "destination": destination_quote,
            "wrong_producer": wrong_producer, "wrong_acceptor": wrong_acceptor})
        try:
            native_railway.execute_railway(session, plan, "native-probe")
        except RuntimeError as exc:
            require("loaded world/operation position" in str(exc), str(exc))
        else:
            raise RuntimeError("older world incorrectly reported completed railway")
        require(purchase.snapshot(session, result["world_id"]) == old, "older save guard mutated world")
        session.check("older_save_not_false_completion")
        session.start_world("latest", save=result["completed_save"])
        before = purchase.snapshot(session, result["world_id"])
        stations = {station["station_id"]: station for station in before["stations"]}
        for site, station_id in zip(plan["geometry"]["stations"],
                                    (result["source_station"], result["destination_station"])):
            station = stations[station_id]
            require(station["platform_tile"] == site["tile"] and
                    station["platform_width"] == (2 if site["axis"] == 0 else 1) and
                    station["platform_height"] == (1 if site["axis"] == 0 else 2),
                    "reloaded platform geometry differs from planned footprint")
        require(any(depot["tile"] == plan["geometry"]["depot"]["tile"] and
                    depot["direction"] == plan["geometry"]["depot"]["orientation"] and
                    depot["rail_type"] == 0 for depot in before["depots"]),
                "reloaded depot geometry differs")
        require(native_railway.execute_railway(session, plan, "native-probe") == result,
                "latest durable job lookup differs")
        replies = []
        for entry in record["outcomes"]:
            wire = entry["wire"]
            status = session.admin.copilot_train_configuration_status(
                world_id=result["world_id"], operation_hi=wire["operation_hi"],
                operation_lo=wire["operation_lo"], timeout=session.remaining())
            require(immutable_outcome(status, status["kind"]) ==
                    immutable_outcome(entry["outcome"], status["kind"]), "retained outcome changed")
            if status["kind"] == 0:
                require(status["readback"]["has_rail"] and status["readback"]["owner"] == 0 and
                        status["readback"]["track_bits"] == 1 << wire["track"],
                        "independent reloaded rail geometry/ownership differs")
            method = (session.admin.copilot_configure_train if "action" in wire else
                      session.admin.copilot_build_train if "depot_tile" in wire else
                      session.admin.copilot_build_infrastructure if "infrastructure_kind" in wire else
                      session.admin.copilot_build_single_rail)
            replay = method(**wire, timeout=session.remaining())
            require(immutable_outcome(replay, status["kind"]) == immutable_outcome(status, status["kind"]),
                    "replay changed retained outcome")
            replies.append(status)
        after = purchase.snapshot(session, result["world_id"])
        for key in ("world_id", "sequence", "head", "stations", "depots"):
            require(after[key] == before[key], f"replay changed {key}")
        stable = lambda snapshot: [{key: part[key] for key in (
            "vehicle_id", "owner", "first_vehicle_id", "previous_vehicle_id", "next_vehicle_id",
            "engine_id", "is_primary", "stopped", "crashed", "cargo_type", "cargo_capacity")}
            for part in snapshot["parts"]]
        require(stable(after) == stable(before), "replay changed consist/running state")
        require(after["companies"][0]["loan"] == result["initial"]["companies"][0]["loan"],
                "reload/replay changed loan")
        require(read_orders(session.admin, result["world_id"], 0, result["vehicle"], session.remaining)[0]
                == result["orders"], "reload/replay changed orders")
        session.check("all_outcomes_reloaded_and_replayed", {"outcomes": replies, "snapshot": after})
        migrated_save = session.save("latest-migrated")
        session.start_world("resaved-latest", save=migrated_save)
        resaved = purchase.snapshot(session, result["world_id"])
        for key in ("world_id", "sequence", "head", "stations", "depots"):
            require(resaved[key] == after[key], f"resaved legacy world changed {key}")
        require(stable(resaved) == stable(after), "resaved legacy world changed consist")
        for entry in record["outcomes"]:
            wire = entry["wire"]
            status = session.admin.copilot_train_configuration_status(
                world_id=result["world_id"], operation_hi=wire["operation_hi"],
                operation_lo=wire["operation_lo"], timeout=session.remaining())
            require(immutable_outcome(status, status["kind"]) ==
                    immutable_outcome(entry["outcome"], status["kind"]),
                    "legacy outcome changed after saving/reloading current schema")
        session.check("legacy_saved_and_reloaded", {"records": len(record["outcomes"]), "snapshot": resaved})
    except Exception as exc:
        failure = exc
    return session.finish(failure)


if __name__ == "__main__":
    raise SystemExit(main())
