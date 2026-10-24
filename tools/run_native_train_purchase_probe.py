#!/usr/bin/env python3
"""Bounded native locomotive and wagon purchase probe on a copied save."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import time
import uuid

from native_mutation_journal import Journal
from admin_transport import CopilotBridgeError
import run_control_probe as base
import run_environment_probe as environment
import run_native_mutation_probe as mutation
import run_native_bridge_probe as native

ROOT = base.REPO_ROOT
DEFAULT_SAVE = ROOT / "artifacts/native-infrastructure-probe/20261023T215235Z-f535454c/infrastructure-final.sav"
ENGINE_SOURCE = mutation.ENGINE_SOURCE
INVALID_ID = 0xFFFFFFFF
INVALID_ENGINE = 0xFFFF
PAGE_SIZE = 16


class Experiment(mutation.Experiment):
    probe_kind = "native-train-purchase-probe"


def engine_provenance(binary: Path, allow_dirty: bool) -> dict:
    head = subprocess.run(["git", "-C", str(ENGINE_SOURCE), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(ENGINE_SOURCE), "status", "--porcelain"],
                           capture_output=True, text=True, check=True, timeout=10).stdout
    environment.require(allow_dirty or not dirty, "engine checkout must be clean; pass --allow-dirty-engine")
    result = subprocess.run([str(binary), "-h"], capture_output=True, text=True, check=True, timeout=10)
    match = re.search(r"OpenTTD\s+(\S+)", result.stdout + result.stderr)
    marker = "m" if dirty else "g"
    environment.require(match is not None and f"{marker}{head[:10]}" in match.group(1),
                        "binary revision does not match engine checkout state")
    files = (
        "src/command_type.h", "src/copilot_cmd.cpp", "src/copilot_cmd.h",
        "src/network/network_admin.cpp", "src/network/network_admin.h",
        "src/network/network_command.cpp",
        "src/saveload/copilot_sl.cpp",
    )
    return {"head": head, "clean": not bool(dirty), "revision": match.group(1),
            "source_hashes": {name: base.sha256_file(ENGINE_SOURCE / name) for name in files}}


def read_catalog(admin, world_id: str, company_id: int, remaining) -> tuple[list[dict], list[dict]]:
    records: list[dict] = []
    pages: list[dict] = []
    start = 0
    for _ in range(256):
        page = admin.copilot_rail_catalog(
            world_id, company_id, start, PAGE_SIZE, timeout=remaining()
        )
        environment.require(page["start_index"] == start and page["count"] == len(page["engines"]),
                            "catalog page range mismatch")
        records.extend(page["engines"])
        pages.append(page)
        if page["count"] < PAGE_SIZE:
            return records, pages
        environment.require(page["count"] > 0, "catalog page did not terminate")
        start += page["count"]
    raise base.ProbeError("rail catalog exceeded bounded page limit")


def read_parts(admin, world_id: str, company_id: int, remaining) -> tuple[list[dict], list[dict]]:
    parts: list[dict] = []
    pages: list[dict] = []
    cursor = INVALID_ID
    for _ in range(64):
        page = admin.copilot_train_parts(world_id, company_id, cursor, 16, 256, timeout=remaining())
        parts.extend(page["parts"])
        pages.append(page)
        if page["complete"]:
            return parts, pages
        environment.require(page["next_after_id"] != cursor, "train-part cursor did not advance")
        cursor = page["next_after_id"]
    raise base.ProbeError("train-part scan exceeded bounded page limit")


def read_depots(admin, world_id: str, company_id: int, remaining) -> list[dict]:
    records: list[dict] = []
    start = 0
    for _ in range(4096):
        page = admin.copilot_rail_assets(world_id, company_id, 1, start, PAGE_SIZE, timeout=remaining())
        records.extend(page["depots"])
        if page["count"] < PAGE_SIZE:
            return records
        start += page["count"]
    raise base.ProbeError("depot scan exceeded bounded page limit")


def read_stations(admin, world_id: str, company_id: int, remaining) -> list[dict]:
    records: list[dict] = []
    start = 0
    for _ in range(4096):
        page = admin.copilot_rail_assets(world_id, company_id, 0, start, PAGE_SIZE, timeout=remaining())
        records.extend(page["stations"])
        if page["count"] < PAGE_SIZE:
            return records
        start += page["count"]
    raise base.ProbeError("station scan exceeded bounded page limit")


def choose_engines(catalog: list[dict], depot_railtypes: int, cargo_id: int = 1) -> tuple[dict, dict]:
    buildable = [e for e in catalog if e["buildable"] and e["engine_id"] != INVALID_ENGINE]
    locomotives = [e for e in buildable if e["railveh_type"] == 0 and e["railtypes"] & depot_railtypes]
    wagons = [e for e in buildable if e["railveh_type"] == 2 and e["default_cargo"] == cargo_id
              and e["default_capacity"] > 0 and e["railtypes"] & depot_railtypes]
    if not locomotives:
        raise base.ProbeError("live catalog has no buildable locomotive")
    if not wagons:
        raise base.ProbeError("live catalog has no buildable default coal wagon")
    return min(locomotives, key=lambda e: (e["purchase_cost"], e["engine_id"])), \
        min(wagons, key=lambda e: (e["purchase_cost"], e["engine_id"]))


def operation_parts(value: int) -> tuple[int, int]:
    return value >> 64, value & ((1 << 64) - 1)


def payload_hash(request: dict) -> tuple[int, int]:
    digest = hashlib.blake2b(json.dumps(request, sort_keys=True, separators=(",", ":")).encode(),
                             digest_size=16).digest()
    return int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:], "big")


def make_request(identity: dict, depot_tile: int, engine_id: int, max_cost: int,
                 operation: int) -> tuple[dict, dict]:
    hi, lo = operation_parts(operation)
    request = {
        "world_id": identity["world_id"], "company_id": 0, "depot_tile": depot_tile,
        "engine_id": engine_id, "max_cost": max_cost, "expect_sequence": identity["sequence"],
        "expect_head": identity["head"], "operation": {"hi": hi, "lo": lo},
    }
    hash_hi, hash_lo = payload_hash(request)
    return request, {
        "world_id": identity["world_id"], "company_id": 0, "depot_tile": depot_tile,
        "engine_id": engine_id, "max_cost": max_cost,
        "expected_sequence": identity["sequence"],
        "expected_head_hi": identity["head_hi"], "expected_head_lo": identity["head_lo"],
        "operation_hi": hi, "operation_lo": lo,
        "payload_hash_hi": hash_hi, "payload_hash_lo": hash_lo,
    }


def purchase(experiment: Experiment, identity: dict, depot_tile: int, engine_id: int,
             max_cost: int, label: str):
    request, wire = make_request(identity, depot_tile, engine_id, max_cost, uuid.uuid4().int)
    journal = Journal.create(experiment.artifacts / f"journals/{label}.json", identity)
    environment.require(journal.record_pending(request), f"{label} was not journaled")
    reply = experiment.admin.copilot_build_train(**wire, timeout=experiment.remaining())
    final = reply
    while final.get("state_name") == "pending":
        time.sleep(min(0.05, experiment.remaining()))
        final = experiment.admin.copilot_train_purchase_status(
            world_id=identity["world_id"], operation_hi=wire["operation_hi"],
            operation_lo=wire["operation_lo"], timeout=experiment.remaining())
    environment.require(journal.reconcile(
        experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining()), final
    ) in {"completed", "rejected"}, f"{label} did not reconcile")
    return request, wire, final, journal


def immutable(record: dict) -> dict:
    return {key: record[key] for key in (
        "operation", "payload_hash", "company_id", "tile", "rail_type", "track",
        "max_cost", "actual_cost", "error", "frame", "state", "infrastructure_kind",
        "length", "created_asset_id", "engine_id",
    )}


def source_outcomes(source: Path) -> tuple[dict, list[dict]]:
    manifest = source.parent / "manifest.json"
    try:
        reference = json.loads(manifest.read_text(encoding="utf-8"))
        outcomes = reference["checks"]["reload_retains_created_assets"]["admitted_outcomes"]
        identity = reference["checks"]["reload_retains_created_assets"]["identity"]
        saved_hash = reference["checks"]["station_depot_completed"]["save"]["sha256"]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        raise base.ProbeError("required schema-3 source manifest is missing or malformed") from exc
    environment.require(reference["status"] == "success" and len(outcomes) == 4
                        and base.sha256_file(source) == saved_hash,
                        "source does not match the four-outcome schema-3 fixture")
    return identity, [{**record, "engine_id": INVALID_ENGINE} for record in outcomes]


def retained_status(experiment, world_id, record):
    return experiment.admin.copilot_train_purchase_status(
        world_id=world_id, operation_hi=record["operation_hi"],
        operation_lo=record["operation_lo"], timeout=experiment.remaining())


def snapshot(experiment, world_id):
    identity = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    parts, _ = read_parts(experiment.admin, world_id, 0, experiment.remaining)
    return {
        "world_id": identity["world_id"], "sequence": identity["sequence"], "head": identity["head"],
        "companies": identity["companies"], "parts": parts,
        "stations": read_stations(experiment.admin, world_id, 0, experiment.remaining),
        "depots": read_depots(experiment.admin, world_id, 0, experiment.remaining),
    }


def require_success(previous, current, outcome, max_cost):
    environment.require(
        outcome["state_name"] == "completed" and 0 < outcome["actual_cost"] <= max_cost
        and current["sequence"] == previous["sequence"] + 1
        and current["head"] == outcome["operation"]
        and outcome["sequence"] == current["sequence"] and outcome["head"] == current["head"]
        and current["companies"][0]["money"] == previous["companies"][0]["money"] - outcome["actual_cost"]
        and current["companies"][0]["loan"] == previous["companies"][0]["loan"],
        "purchase cost, finances, or successful sequence/head did not match",
    )


def require_error(status, action):
    try:
        action()
    except CopilotBridgeError as exc:
        environment.require(exc.status == status, f"expected bridge rejection {status}, got {exc.status}")
    else:
        raise base.ProbeError(f"expected bridge rejection {status}, request succeeded")


def run(args: argparse.Namespace) -> int:
    source = args.save.expanduser().resolve()
    binary = args.binary.expanduser().resolve()
    environment.require(source.is_file() and source.suffix == ".sav", f"source must be an existing .sav file: {source}")
    environment.require(math.isfinite(args.deadline) and args.deadline > 0, "deadline must be finite and positive")
    experiment = Experiment(binary, source, args.deadline, 3, base.DEFAULT_SEED)
    experiment.manifest.update({
        "scope": "bounded native locomotive and wagon purchase with retained identity",
        "binary_sha256": base.sha256_file(binary),
        "engine_checkout": engine_provenance(binary, args.allow_dirty_engine),
        "source_save_sha256": base.sha256_file(source),
        "source_hashes": {name: base.sha256_file(ROOT / name) for name in (
            "tools/admin_transport.py", "tools/native_mutation_journal.py",
            "tools/run_native_train_purchase_probe.py")},
    })
    experiment.write()
    failure = None
    try:
        experiment.start("purchase", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        identity = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        native.select_human_company(identity["companies"], requested=0)
        reference_identity, prior_outcomes = source_outcomes(source)
        environment.require(
            identity["world_id"] == reference_identity["world_id"]
            and identity["sequence"] == reference_identity["sequence"]
            and identity["head"] == reference_identity["head"],
            "schema-3 source position changed during migration",
        )
        prior_replies = [retained_status(experiment, identity["world_id"], record) for record in prior_outcomes]
        environment.require(all(immutable(actual) == immutable(expected)
                                for actual, expected in zip(prior_replies, prior_outcomes)),
                            "schema-3 migration changed retained infrastructure outcomes")
        experiment.check("schema3_migration", {
            "identity": identity, "outcomes": prior_replies,
            "reference_manifest_sha256": base.sha256_file(source.parent / "manifest.json"),
        })
        original_position = identity
        before = identity["companies"][0]
        depots = read_depots(experiment.admin, identity["world_id"], 0, experiment.remaining)
        environment.require(depots, "source save has no owned depot")
        depot = depots[0]
        stations_before = read_stations(experiment.admin, identity["world_id"], 0, experiment.remaining)
        environment.require(stations_before, "source save has no owned station")
        invalid_depot_tile = stations_before[0]["base_tile"]
        catalog, catalog_pages = read_catalog(experiment.admin, identity["world_id"], 0, experiment.remaining)
        environment.require(identity["landscape"] == 0, "purchase fixture must be standard temperate")
        loco, wagon = choose_engines(catalog, 1 << depot["rail_type"])
        parts_before, part_pages_before = read_parts(experiment.admin, identity["world_id"], 0, experiment.remaining)

        initial_snapshot = snapshot(experiment, identity["world_id"])
        zero_request, zero_wire, zero_outcome, zero_journal = purchase(
            experiment, identity, depot["tile"], loco["engine_id"], 0, "0000-zero-cap",
        )
        environment.require(zero_outcome["state_name"] == "rejected"
                            and zero_outcome["actual_cost"] == 0,
                            "zero-cap purchase was not retained as a rejection")
        zero_after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        parts_zero, _ = read_parts(experiment.admin, identity["world_id"], 0, experiment.remaining)
        environment.require(zero_after["companies"] == identity["companies"]
                            and zero_after["sequence"] == identity["sequence"]
                            and parts_zero == parts_before,
                            "zero-cap purchase changed state")
        environment.require(snapshot(experiment, identity["world_id"]) == initial_snapshot,
                            "zero cap changed assets, cash/loan, or successful head")

        invalid_request, invalid_wire, invalid_outcome, invalid_journal = purchase(
            experiment, identity, invalid_depot_tile, loco["engine_id"], args.max_cost,
            "0001-invalid-depot")
        environment.require(invalid_outcome["state_name"] == "rejected"
                            and invalid_outcome["actual_cost"] == 0,
                            "purchase on an owned station tile was not rejected")
        invalid_after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(invalid_after["companies"] == identity["companies"]
                            and invalid_after["sequence"] == identity["sequence"],
                            "invalid-depot rejection changed finances unexpectedly")
        environment.require(snapshot(experiment, identity["world_id"]) == initial_snapshot,
                            "invalid depot changed assets or position")

        loco_req, loco_wire, loco_outcome, loco_journal = purchase(
            experiment, invalid_after, depot["tile"], loco["engine_id"], args.max_cost, "0002-locomotive")
        environment.require(loco_outcome["state_name"] == "completed"
                            and loco_outcome["created_asset_id"] != INVALID_ID
                            and 0 < loco_outcome["actual_cost"] <= args.max_cost
                            and loco_outcome["engine_id"] == loco["engine_id"],
                            "locomotive purchase outcome was not authoritative")
        after_loco = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        require_success(invalid_after, after_loco, loco_outcome, args.max_cost)
        parts_loco, _ = read_parts(experiment.admin, identity["world_id"], 0, experiment.remaining)
        loco_part = next((p for p in parts_loco if p["vehicle_id"] == loco_outcome["created_asset_id"]), None)
        environment.require(loco_part is not None and loco_part["engine_id"] == loco["engine_id"]
                            and loco_part["owner"] == 0 and loco_part["tile"] == depot["tile"]
                            and loco_part["stopped"] and loco_part["in_depot"]
                            and loco_part["is_primary"] and loco_part["first_vehicle_id"] == loco_part["vehicle_id"],
                            "purchased locomotive was not independently read back")

        identity = after_loco
        wagon_req, wagon_wire, wagon_outcome, wagon_journal = purchase(
            experiment, after_loco, depot["tile"], wagon["engine_id"], args.max_cost, "0003-wagon")
        environment.require(wagon_outcome["state_name"] == "completed"
                            and wagon_outcome["created_asset_id"] != INVALID_ID
                            and 0 < wagon_outcome["actual_cost"] <= args.max_cost
                            and wagon_outcome["engine_id"] == wagon["engine_id"],
                            "wagon purchase outcome was not authoritative")
        after_wagon = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        require_success(after_loco, after_wagon, wagon_outcome, args.max_cost)
        parts_after_wagon, _ = read_parts(experiment.admin, identity["world_id"], 0, experiment.remaining)
        wagon_part_before_second = next(
            p for p in parts_after_wagon if p["vehicle_id"] == wagon_outcome["created_asset_id"]
        )
        environment.require(
            wagon_part_before_second["engine_id"] == wagon["engine_id"]
            and wagon_part_before_second["owner"] == 0
            and wagon_part_before_second["tile"] == depot["tile"]
            and wagon_part_before_second["in_depot"] and not wagon_part_before_second["is_primary"]
            and wagon_part_before_second["cargo_type"] == wagon["default_cargo"]
            and wagon_part_before_second["cargo_capacity"] == wagon["default_capacity"]
            and wagon_part_before_second["cargo_amount"] == 0
            and wagon_part_before_second["first_vehicle_id"] == wagon_part_before_second["vehicle_id"]
            and wagon_part_before_second["previous_vehicle_id"] == INVALID_ID
            and wagon_part_before_second["next_vehicle_id"] == INVALID_ID,
            "purchased default coal wagon does not match independent parts",
        )
        second_req, second_wire, second_outcome, second_journal = purchase(
            experiment, after_wagon, depot["tile"], loco["engine_id"],
            loco_outcome["actual_cost"], "0004-locomotive")
        environment.require(second_outcome["state_name"] == "completed"
                            and second_outcome["created_asset_id"] != INVALID_ID
                            and second_outcome["created_asset_id"] != loco_outcome["created_asset_id"]
                            and second_outcome["engine_id"] == loco["engine_id"],
                            "second locomotive purchase did not return a distinct authoritative ID")
        after_second = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        require_success(after_wagon, after_second, second_outcome, loco_outcome["actual_cost"])
        parts_after_second, _ = read_parts(experiment.admin, identity["world_id"], 0, experiment.remaining)
        second_part = next((p for p in parts_after_second
                            if p["vehicle_id"] == second_outcome["created_asset_id"]), None)
        wagon_part_after_second = next(
            p for p in parts_after_second if p["vehicle_id"] == wagon_outcome["created_asset_id"]
        )
        environment.require(second_part is not None and second_part["engine_id"] == loco["engine_id"]
                            and second_part["owner"] == 0 and second_part["tile"] == depot["tile"]
                            and second_part["stopped"] and second_part["in_depot"]
                            and wagon_part_after_second == wagon_part_before_second
                            and second_part["first_vehicle_id"] != wagon_part_after_second["first_vehicle_id"],
                            "second locomotive was implicitly joined to the free wagon chain")

        before_repeat = snapshot(experiment, identity["world_id"])
        repeat_wagon_req, repeat_wagon_wire, repeat_wagon_outcome, repeat_wagon_journal = purchase(
            experiment, after_second, depot["tile"], wagon["engine_id"], args.max_cost,
            "0005-wagon-repeat")
        environment.require(repeat_wagon_outcome["state_name"] == "rejected"
                            and repeat_wagon_outcome["actual_cost"] == 0,
                            "same-type free wagon purchase was not rejected")
        after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(snapshot(experiment, identity["world_id"]) == before_repeat,
                            "same-wagon refusal mutated existing parts/assets or finances")
        parts_after, part_pages_after = read_parts(experiment.admin, identity["world_id"], 0, experiment.remaining)
        ids_before = {p["vehicle_id"] for p in parts_before}
        new_parts = [p for p in parts_after if p["vehicle_id"] not in ids_before]
        environment.require({p["vehicle_id"] for p in new_parts}
                            == {loco_outcome["created_asset_id"], wagon_outcome["created_asset_id"],
                                second_outcome["created_asset_id"]},
                            "purchase created unexpected or missing vehicle IDs")
        environment.require([p for p in parts_after if p["vehicle_id"] in ids_before] == parts_before
                            and read_stations(experiment.admin, identity["world_id"], 0,
                                              experiment.remaining) == stations_before
                            and read_depots(experiment.admin, identity["world_id"], 0,
                                            experiment.remaining) == depots,
                            "purchase changed pre-existing vehicles or infrastructure")
        for part in new_parts:
            environment.require(
                part["first_vehicle_id"] == part["vehicle_id"]
                and part["previous_vehicle_id"] == INVALID_ID and part["next_vehicle_id"] == INVALID_ID,
                "purchase unexpectedly assembled or adopted a vehicle chain",
            )
        environment.require(after["companies"][0]["money"] == before["money"]
                            - loco_outcome["actual_cost"] - wagon_outcome["actual_cost"]
                            - second_outcome["actual_cost"]
                            and after["companies"][0]["loan"] == before["loan"],
                            "cash/loan accounting does not match purchase costs")

        duplicate = experiment.admin.copilot_build_train(**loco_wire, timeout=experiment.remaining())
        duplicate_after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(immutable(duplicate) == immutable(loco_outcome)
                            and duplicate_after["companies"] == after["companies"]
                            and duplicate_after["sequence"] == after["sequence"],
                            "exact purchase replay mutated state")
        environment.require(snapshot(experiment, identity["world_id"]) == before_repeat,
                            "purchase replay changed assets or successful head")

        conflict = {**loco_wire, "engine_id": wagon["engine_id"]}
        require_error(8, lambda: experiment.admin.copilot_build_train(
            **conflict, timeout=experiment.remaining()))
        require_error(5, lambda: experiment.admin.copilot_build_train(
            **{**loco_wire, "world_id": "wrong-world"}, timeout=experiment.remaining()))
        _, stale = make_request(original_position, depot["tile"], loco["engine_id"],
                                args.max_cost, uuid.uuid4().int)
        require_error(11, lambda: experiment.admin.copilot_build_train(**stale, timeout=experiment.remaining()))
        for status_method in (experiment.admin.copilot_operation_status,
                              experiment.admin.copilot_infrastructure_status):
            require_error(2, lambda method=status_method: method(
                world_id=identity["world_id"], operation_hi=loco_wire["operation_hi"],
                operation_lo=loco_wire["operation_lo"], timeout=experiment.remaining()))
        rail_conflict = {key: value for key, value in loco_wire.items()
                         if key not in ("engine_id", "depot_tile")}
        rail_conflict.update(tile=depot["tile"], rail_type=0, track=0)
        require_error(8, lambda: experiment.admin.copilot_build_single_rail(
            **rail_conflict, timeout=experiment.remaining()))
        infra_conflict = {key: value for key, value in rail_conflict.items() if key != "track"}
        infra_conflict.update(orientation=0, infrastructure_kind=2, length=1)
        require_error(8, lambda: experiment.admin.copilot_build_infrastructure(
            **infra_conflict, timeout=experiment.remaining()))
        _, _, below_cap_outcome, _ = purchase(
            experiment, after, depot["tile"], loco["engine_id"],
            loco_outcome["actual_cost"] - 1, "0006-below-cap")
        environment.require(below_cap_outcome["state_name"] == "rejected"
                            and below_cap_outcome["actual_cost"] == 0,
                            "one-unit-below observed purchase cap did not reject")
        unavailable = next((engine for engine in catalog if not engine["buildable"]), None)
        unavailable_outcome = None
        if unavailable is not None:
            _, _, unavailable_outcome, _ = purchase(
                experiment, after, depot["tile"], unavailable["engine_id"],
                args.max_cost, "0007-unavailable")
            environment.require(unavailable_outcome["state_name"] == "rejected"
                                and unavailable_outcome["actual_cost"] == 0,
                                "unavailable engine did not reject")
        environment.require(snapshot(experiment, identity["world_id"]) == before_repeat,
                            "guards or unavailable-engine rejection mutated state")
        environment.require(
            Journal.open(second_journal.path).classify_position(after) == "current"
            and Journal.open(loco_journal.path).classify_position(after) == "ahead"
            and Journal.open(second_journal.path).classify_position(original_position) == "older_save",
            "retained journals did not distinguish current/historical/older-save position",
        )
        outcomes = [zero_outcome, invalid_outcome, loco_outcome, wagon_outcome,
                    second_outcome, repeat_wagon_outcome, below_cap_outcome]
        if unavailable_outcome is not None:
            outcomes.append(unavailable_outcome)
        experiment.check("purchase_completed", {
            "before": before, "after": after, "catalog": catalog,
            "catalog_pages": catalog_pages, "selected": {"locomotive": loco, "wagon": wagon},
            "depots": depots, "parts_before": parts_before, "parts_after": parts_after,
            "part_pages_before": part_pages_before, "part_pages_after": part_pages_after,
            "locomotive": loco_outcome, "wagon": wagon_outcome, "second_locomotive": second_outcome,
            "invalid_depot": invalid_outcome, "same_wagon_rejection": repeat_wagon_outcome,
            "duplicate": duplicate,
            "zero_cap": zero_outcome, "below_cap": below_cap_outcome,
            "unavailable_engine": unavailable_outcome,
            "guards": {"changed_engine_same_hash": 8, "wrong_world": 5, "stale": 11,
                       "old_rail_status": 2, "old_infra_status": 2,
                       "old_rail_build": 8, "old_infra_build": 8},
            "admitted_outcomes": outcomes,
            "journals": [str(loco_journal.path), str(wagon_journal.path), str(second_journal.path),
                         str(invalid_journal.path), str(repeat_wagon_journal.path),
                         str(zero_journal.path)],
        })
        saved = experiment.save_world("train-purchase-final")
        experiment.start("reload", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], saved)
        reloaded = snapshot(experiment, identity["world_id"])
        environment.require(reloaded == before_repeat, "reload changed built parts/assets/finances/position")
        reload_outcomes = [retained_status(experiment, identity["world_id"], record)
                           for record in prior_outcomes + outcomes]
        environment.require(
            all(immutable(actual) == immutable(expected)
                for actual, expected in zip(reload_outcomes, prior_outcomes + outcomes))
            and all(record["sequence"] == after["sequence"] and record["head"] == after["head"]
                    for record in reload_outcomes),
            "reload changed original immutable outcomes or current successful position",
        )
        reload_duplicate = experiment.admin.copilot_build_train(**loco_wire, timeout=experiment.remaining())
        environment.require(immutable(reload_duplicate) == immutable(loco_outcome)
                            and snapshot(experiment, identity["world_id"]) == before_repeat,
                            "reload replay charged or created another purchase")
        experiment.check("reload_retains_purchase", {
            "snapshot": reloaded, "outcomes": reload_outcomes, "duplicate": reload_duplicate,
            "save": environment.file_fingerprint(saved),
        })
    except Exception as exc:
        failure = exc
    return experiment.finish(failure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/openttd-m2a/openttd")
    parser.add_argument("--deadline", type=float, default=120)
    parser.add_argument("--max-cost", type=int, default=100000)
    parser.add_argument("--allow-dirty-engine", action="store_true")
    args = parser.parse_args()
    if args.max_cost <= 0 or not math.isfinite(args.deadline) or args.deadline <= 0:
        parser.error("max-cost and deadline must be finite and positive")
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
