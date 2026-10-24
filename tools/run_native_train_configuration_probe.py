#!/usr/bin/env python3
"""Probe native train consist, order, and explicit state configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from native_mutation_journal import Journal
import run_control_probe as base
import run_environment_probe as environment
import run_native_train_purchase_probe as purchase_probe
from run_native_train_orders_probe import read_orders

ROOT = base.REPO_ROOT
DEFAULT_SAVE = ROOT / "artifacts/native-train-purchase-probe/20261024T221240Z-89c4c574/train-purchase-final.sav"
ENGINE_SOURCE = purchase_probe.ENGINE_SOURCE
INVALID_ID = 0xFFFFFFFF


class Experiment(purchase_probe.Experiment):
    probe_kind = "native-train-configuration-probe"


def operation_parts(value: int) -> tuple[int, int]:
    return value >> 64, value & ((1 << 64) - 1)


def payload_hash(request: dict) -> tuple[int, int]:
    digest = hashlib.blake2b(
        json.dumps(request, sort_keys=True, separators=(",", ":")).encode(), digest_size=16
    ).digest()
    return int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:], "big")


def make_request(identity: dict, *, tile: int, action: int, vehicle_id: int,
                 target_id: int, order_index: int, policy: int, operation: int) -> tuple[dict, dict]:
    if action not in (4, 5, 6):
        raise ValueError("action must be 4, 5, or 6")
    if action == 4 and (target_id == INVALID_ID or order_index or policy):
        raise ValueError("invalid attach request")
    if action == 5 and (not 0 <= target_id < 0xFFFF or order_index not in (0, 1) or policy not in (0, 1)):
        raise ValueError("invalid order request")
    if action == 6 and (target_id != INVALID_ID or order_index or policy not in (0, 1)):
        raise ValueError("invalid state request")
    hi, lo = operation_parts(operation)
    request = {
        "world_id": identity["world_id"], "company_id": 0, "tile": tile,
        "action": action, "vehicle_id": vehicle_id, "target_id": target_id,
        "order_index": order_index, "policy": policy, "max_cost": 0,
        "expect_sequence": identity["sequence"], "expect_head": identity["head"],
        "operation": {"hi": hi, "lo": lo},
    }
    hash_hi, hash_lo = payload_hash(request)
    wire = {**{key: request[key] for key in (
        "world_id", "company_id", "tile", "action", "vehicle_id", "target_id",
        "order_index", "policy", "max_cost",
    )}, "expected_sequence": identity["sequence"],
        "expected_head_hi": identity["head_hi"], "expected_head_lo": identity["head_lo"],
        "operation_hi": hi, "operation_lo": lo,
        "payload_hash_hi": hash_hi, "payload_hash_lo": hash_lo}
    return request, wire


def immutable_config(record: dict) -> dict:
    fields = {key: record[key] for key in (
        "operation", "payload_hash", "company_id", "tile", "rail_type", "track",
        "max_cost", "actual_cost", "error", "frame", "state", "length",
        "created_asset_id", "engine_id",
    )}
    fields.update({
        "kind": record.get("kind", record.get("infrastructure_kind")),
        "vehicle_id": record.get("vehicle_id", INVALID_ID),
        "target_id": record.get("target_id", INVALID_ID),
        "order_index": record.get("order_index", 0),
        "policy": record.get("policy", 0),
    })
    return fields


def source_reference(save: Path) -> tuple[list[dict], dict]:
    manifest = save.parent / "manifest.json"
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
        records = value["checks"]["reload_retains_purchase"]["outcomes"]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise base.ProbeError("purchase reference manifest lacks reload outcomes") from exc
    environment.require(value["status"] == "success" and len(records) == 12,
                        "purchase reference must contain 12 successful-gate outcomes")
    environment.require(
        base.sha256_file(save) == value["checks"]["reload_retains_purchase"]["save"]["sha256"],
        "purchase source save hash does not match reload_retains_purchase.save.sha256",
    )
    return records, value


def retained_status(experiment, world_id, record):
    return experiment.admin.copilot_train_configuration_status(
        world_id=world_id, operation_hi=record["operation"]["hi"],
        operation_lo=record["operation"]["lo"], timeout=experiment.remaining())


def snapshot(experiment, world_id):
    result = purchase_probe.snapshot(experiment, world_id)
    result["orders"] = {
        str(part["vehicle_id"]): read_orders(
            experiment.admin, world_id, 0, part["vehicle_id"], experiment.remaining)[0]
        for part in result["parts"] if part["is_primary"]
    }
    return result


def require_consist(parts, original, primary_id, wagon_id, *, allow_movement=False):
    by_id = {part["vehicle_id"]: part for part in parts}
    old = {part["vehicle_id"]: part for part in original}
    environment.require(by_id.keys() == old.keys(), "configuration created or removed vehicles")
    primary, wagon = by_id[primary_id], by_id[wagon_id]
    environment.require(
        primary["first_vehicle_id"] == primary_id and primary["previous_vehicle_id"] == INVALID_ID
        and primary["next_vehicle_id"] == wagon_id and primary["is_primary"]
        and wagon["first_vehicle_id"] == primary_id and wagon["previous_vehicle_id"] == primary_id
        and wagon["next_vehicle_id"] == INVALID_ID and not wagon["is_primary"]
        and wagon["cargo_type"] == old[wagon_id]["cargo_type"] == 1
        and wagon["cargo_capacity"] == old[wagon_id]["cargo_capacity"] == 30
        and wagon["cargo_amount"] == old[wagon_id]["cargo_amount"] == 0,
        "independent consist links or default coal cargo/capacity do not match",
    )
    for vehicle_id, part in by_id.items():
        expected = old[vehicle_id]
        fields = ("owner", "engine_id", "cargo_type", "cargo_capacity", "cargo_amount")
        if not allow_movement:
            fields += ("tile", "in_depot")
        environment.require(all(part[key] == expected[key] for key in fields),
            "configuration changed vehicle identity, location, or cargo")
        if vehicle_id not in (primary_id, wagon_id):
            environment.require(part == expected, "configuration modified the spare locomotive")


def require_orders(orders, station_ids):
    environment.require(len(orders) == len(station_ids), "independent order count mismatch")
    for index, (order, station_id) in enumerate(zip(orders, station_ids)):
        environment.require(
            order["order_type"] == 1 and order["destination_id"] == station_id
            and order["load_type"] == (2 if index == 0 else 4)
            and order["unload_type"] == (4 if index == 0 else 0)
            and order["nonstop_flags"] == 0,
            "independent station order destination or policy mismatch",
        )


def without_cash(value):
    result = {**value}
    result["companies"] = [{key: entry for key, entry in company.items() if key != "money"}
                           for company in value["companies"]]
    return result


def configure(experiment: Experiment, identity: dict, *, tile: int, action: int,
              vehicle_id: int, target_id: int, order_index: int, policy: int, label: str,
              allow_running_cost: bool = False):
    request, wire = make_request(identity, tile=tile, action=action, vehicle_id=vehicle_id,
                                 target_id=target_id, order_index=order_index, policy=policy,
                                 operation=uuid.uuid4().int)
    journal = Journal.create(experiment.artifacts / f"journals/{label}.json", identity)
    environment.require(journal.record_pending(request), f"{label} was not journaled")
    reply = experiment.admin.copilot_configure_train(**wire, timeout=experiment.remaining())
    final = reply
    while final.get("state_name") == "pending":
        time.sleep(min(0.05, experiment.remaining()))
        final = experiment.admin.copilot_train_configuration_status(
            world_id=identity["world_id"], operation_hi=wire["operation_hi"],
            operation_lo=wire["operation_lo"], timeout=experiment.remaining())
    current = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    environment.require(journal.reconcile(current, final) in {"completed", "rejected"},
                        f"{label} did not reconcile")
    environment.require(final["actual_cost"] == 0
                        and without_cash(current)["companies"] == without_cash(identity)["companies"]
                        and (current["companies"] == identity["companies"] if not allow_running_cost else
                             current["companies"][0]["money"] <= identity["companies"][0]["money"]),
                        f"{label} changed loan/company metadata or unexpected cash")
    if final["state_name"] == "completed":
        environment.require(current["sequence"] == identity["sequence"] + 1
                            and current["head"] == final["operation"],
                            f"{label} did not advance successful sequence/head")
    else:
        environment.require(current["sequence"] == identity["sequence"]
                            and current["head"] == identity["head"],
                            f"{label} rejection advanced successful sequence/head")
    environment.require(final["sequence"] == current["sequence"] and final["head"] == current["head"],
                        f"{label} outcome lost current position")
    return request, wire, final, current, journal


def run(args: argparse.Namespace) -> int:
    source, binary = args.save.expanduser().resolve(), args.binary.expanduser().resolve()
    environment.require(source.is_file() and source.suffix == ".sav", f"missing save: {source}")
    environment.require(math.isfinite(args.deadline) and args.deadline > 0,
                        "deadline must be finite and positive")
    records, manifest = source_reference(source)
    experiment = Experiment(binary, source, args.deadline, 3, base.DEFAULT_SEED)
    experiment.manifest.update({
        "scope": "native train consist, order, and explicit state configuration",
        "binary_sha256": base.sha256_file(binary),
        "engine_checkout": purchase_probe.engine_provenance(binary, args.allow_dirty_engine),
        "source_save_sha256": base.sha256_file(source),
        "source_hashes": {name: base.sha256_file(ROOT / name) for name in (
            "tools/admin_transport.py", "tools/native_mutation_journal.py",
            "tools/run_native_train_configuration_probe.py",
            "tools/run_native_train_purchase_probe.py", "tools/run_native_train_orders_probe.py",
        )},
    })
    experiment.write()
    failure = None
    try:
        experiment.start("configuration", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        identity = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        reference = manifest["checks"]["reload_retains_purchase"]["snapshot"]
        world_id = identity["world_id"]
        initial = snapshot(experiment, world_id)
        environment.require({key: initial[key] for key in reference} == reference,
                            "schema-4 migration changed source world/assets/finances/position")
        prior_replies = [retained_status(experiment, world_id, record) for record in records]
        environment.require(all(immutable_config(actual) == immutable_config(expected)
                                for actual, expected in zip(prior_replies, records)),
                            "schema-4 migration changed prior immutable outcomes")
        experiment.check("schema4_migration", {
            "snapshot": initial, "outcomes": prior_replies,
            "reference_manifest_sha256": base.sha256_file(source.parent / "manifest.json"),
        })
        by_id = {part["vehicle_id"]: part for part in initial["parts"]}
        primary_id = manifest["checks"]["purchase_completed"]["locomotive"]["created_asset_id"]
        wagon_id = manifest["checks"]["purchase_completed"]["wagon"]["created_asset_id"]
        second_id = manifest["checks"]["purchase_completed"]["second_locomotive"]["created_asset_id"]
        environment.require(by_id[primary_id]["is_primary"] and not by_id[wagon_id]["is_primary"],
                            "retained purchase IDs did not identify primary and free wagon")
        stations = initial["stations"]
        environment.require(len(stations) >= 2, "fixture did not expose two owned stations")
        station_ids = [station["station_id"] for station in stations[:2]]
        environment.require(not initial["orders"][str(primary_id)]
                            and not initial["orders"][str(second_id)], "fixture already has orders")
        tile = by_id[primary_id]["tile"]
        outcomes, wires, journals = [], [], []

        def apply(label, action, vehicle_id=primary_id, target_id=INVALID_ID,
                  order_index=0, policy=0, rejected=False, allow_running_cost=False):
            nonlocal identity
            before = snapshot(experiment, world_id)
            observed_tile = next(part["tile"] for part in before["parts"]
                                 if part["vehicle_id"] == vehicle_id)
            _, wire, result, identity, journal = configure(
                experiment, identity, tile=observed_tile, action=action, vehicle_id=vehicle_id,
                target_id=target_id, order_index=order_index, policy=policy, label=label,
                allow_running_cost=allow_running_cost)
            environment.require(result["state_name"] == ("rejected" if rejected else "completed"),
                                f"{label} unexpected terminal state")
            outcomes.append(result)
            wires.append(wire)
            journals.append(journal)
            if rejected:
                actual = snapshot(experiment, world_id)
                environment.require((without_cash(actual) == without_cash(before) if allow_running_cost
                                     else actual == before),
                                    f"{label} rejection changed independent state")
            return wire, result

        apply("0000-invalid-source", 4, target_id=second_id, rejected=True)
        apply("0001-missing-station", 5, target_id=0xFFFE, rejected=True)
        apply("0002-wrong-index", 5, target_id=station_ids[0], order_index=1, rejected=True)
        apply("0003-start-without-orders", 6, policy=1, rejected=True)
        attach_wire, attach = apply("0004-attach", 4, vehicle_id=wagon_id, target_id=primary_id)
        attached = snapshot(experiment, world_id)
        require_consist(attached["parts"], initial["parts"], primary_id, wagon_id)
        duplicate_attach = experiment.admin.copilot_configure_train(
            **attach_wire, timeout=experiment.remaining())
        environment.require(immutable_config(duplicate_attach) == immutable_config(attach)
                            and snapshot(experiment, world_id) == attached,
                            "attach replay changed consist or original outcome")
        for index, station_id in enumerate(station_ids):
            apply(f"000{index + 5}-order", 5, target_id=station_id,
                  order_index=index, policy=index)
            require_orders(snapshot(experiment, world_id)["orders"][str(primary_id)], station_ids[:index + 1])
        before_noop = snapshot(experiment, world_id)
        apply("0007-already-stopped", 6)
        after_noop = snapshot(experiment, world_id)
        environment.require(all(after_noop[key] == before_noop[key]
                                for key in before_noop if key not in ("sequence", "head")),
                            "already-stopped action mutated assets/configuration/finances")
        start_wire, started = apply("0008-start", 6, policy=1, allow_running_cost=True)
        running = snapshot(experiment, world_id)
        environment.require(not next(p for p in running["parts"]
                                     if p["vehicle_id"] == primary_id)["stopped"],
                            "independent train part did not become running")
        apply("0009-already-running", 6, policy=1, allow_running_cost=True)
        still_running = snapshot(experiment, world_id)
        environment.require(not next(p for p in still_running["parts"]
                                     if p["vehicle_id"] == primary_id)["stopped"],
                            "already-running request toggled the train to stopped")
        apply("0010-running-order-refusal", 5, target_id=station_ids[1],
              order_index=1, policy=1, rejected=True, allow_running_cost=True)
        _, stopped = apply("0011-stop", 6, allow_running_cost=True)
        # Stock train running_ticks are charged at the next economy day, even after stopping.
        while experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())["frame"] < stopped["frame"] + 74:
            time.sleep(min(0.05, experiment.remaining()))
        after = snapshot(experiment, world_id)
        experiment.manifest["observed_configuration"] = {"running": running, "after": after}
        experiment.write()
        environment.require(next(p for p in after["parts"] if p["vehicle_id"] == primary_id)["stopped"],
                            "independent train part did not become stopped")
        require_consist(after["parts"], initial["parts"], primary_id, wagon_id, allow_movement=True)
        require_orders(after["orders"][str(primary_id)], station_ids)
        environment.require(without_cash(after)["companies"] == without_cash(initial)["companies"]
                            and after["companies"][0]["money"] <= initial["companies"][0]["money"]
                            and after["stations"] == initial["stations"]
                            and after["depots"] == initial["depots"]
                            and after["orders"][str(second_id)] == initial["orders"][str(second_id)],
                            "configuration changed finances, infrastructure, or spare orders")
        replay = experiment.admin.copilot_configure_train(**start_wire, timeout=experiment.remaining())
        environment.require(immutable_config(replay) == immutable_config(started)
                            and snapshot(experiment, world_id) == after,
                            "historical start replay changed original outcome or restarted train")
        for wire, key, value in ((attach_wire, "target_id", second_id),
                                 (attach_wire, "vehicle_id", second_id),
                                 (wires[5], "order_index", 1), (wires[5], "policy", 1)):
            purchase_probe.require_error(8, lambda w=wire, k=key, v=value: experiment.admin.copilot_configure_train(
                **{**w, k: v}, timeout=experiment.remaining()))
        purchase_probe.require_error(5, lambda: experiment.admin.copilot_configure_train(
            **{**attach_wire, "world_id": "wrong-world"}, timeout=experiment.remaining()))
        _, stale = make_request(
            {**identity, "sequence": initial["sequence"], "head": initial["head"],
             "head_hi": initial["head"]["hi"], "head_lo": initial["head"]["lo"]},
            tile=tile, action=6, vehicle_id=primary_id, target_id=INVALID_ID,
            order_index=0, policy=0, operation=uuid.uuid4().int)
        purchase_probe.require_error(11, lambda: experiment.admin.copilot_configure_train(
            **stale, timeout=experiment.remaining()))
        for method in (experiment.admin.copilot_operation_status,
                       experiment.admin.copilot_infrastructure_status,
                       experiment.admin.copilot_train_purchase_status):
            purchase_probe.require_error(2, lambda method=method: method(
                world_id=world_id, operation_hi=attach_wire["operation_hi"],
                operation_lo=attach_wire["operation_lo"], timeout=experiment.remaining()))
        environment.require(snapshot(experiment, world_id) == after,
                            "conflict/world/stale/old-status guard changed independent state")
        environment.require(Journal.open(journals[-1].path).classify_position(identity) == "current"
                            and Journal.open(journals[4].path).classify_position(identity) == "ahead"
                            and Journal.open(journals[-1].path).classify_position(
                                {**identity, "sequence": initial["sequence"], "head": initial["head"]}) == "older_save",
                            "configuration journals lost current/historical/older-save distinction")
        experiment.check("configuration_completed", {
            "source_manifest": str(source.parent / "manifest.json"),
            "before": initial, "after": after, "running": running, "still_running": still_running,
            "prior_outcomes": prior_replies, "admitted_outcomes": outcomes,
            "attach": attach, "start": started, "stop": stopped, "replay": replay,
            "command_cost_total": sum(record["actual_cost"] for record in outcomes),
            "running_balance_delta": after["companies"][0]["money"] - initial["companies"][0]["money"],
            "running_cost_settlement": {"stopped_frame": stopped["frame"], "minimum_wait_frames": 74},
            "guards": {"changed_target_same_hash": 8, "changed_source_same_hash": 8,
                       "changed_index_same_hash": 8, "changed_policy_same_hash": 8,
                       "wrong_world": 5, "stale": 11, "old_status": 2},
            "journals": [str(journal.path) for journal in journals],
        })
        saved = experiment.save_world("train-configuration-final")
        experiment.start("reload", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], saved)
        reloaded = snapshot(experiment, world_id)
        environment.require(reloaded == after, "reload changed assets/orders/finances/position/stopped state")
        reload_outcomes = [retained_status(experiment, world_id, record) for record in prior_replies + outcomes]
        environment.require(all(immutable_config(actual) == immutable_config(expected)
                                and actual["sequence"] == after["sequence"] and actual["head"] == after["head"]
                                for actual, expected in zip(reload_outcomes, prior_replies + outcomes)),
                            "reload changed immutable outcomes or current successful position")
        for wire, original in zip(wires, outcomes):
            duplicate = experiment.admin.copilot_configure_train(**wire, timeout=experiment.remaining())
            environment.require(immutable_config(duplicate) == immutable_config(original),
                                "reload replay changed original outcome")
        environment.require(snapshot(experiment, world_id) == after,
                            "reload replay mutated consist/orders/finances/stopped state")
        experiment.check("reload_retains_configuration", {
            "snapshot": reloaded, "outcomes": reload_outcomes, "save": environment.file_fingerprint(saved)})
        environment.require(not experiment.errors, f"structured engine errors: {experiment.errors}")
    except Exception as exc:
        failure = exc
    return experiment.finish(failure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/openttd-m2a/openttd")
    parser.add_argument("--deadline", type=float, default=120)
    parser.add_argument("--allow-dirty-engine", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.deadline) or args.deadline <= 0:
        parser.error("deadline must be finite and positive")
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
