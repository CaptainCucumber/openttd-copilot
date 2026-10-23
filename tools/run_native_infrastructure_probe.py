#!/usr/bin/env python3
"""Bounded native station/depot construction probe on a copied save."""

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

from admin_transport import CopilotBridgeError
from native_mutation_journal import Journal
import run_control_probe as base
import run_environment_probe as environment
import run_native_mutation_probe as mutation
import run_native_bridge_probe as native


ROOT = base.REPO_ROOT
DEFAULT_SAVE = mutation.DEFAULT_SAVE
ENGINE_SOURCE = mutation.ENGINE_SOURCE
ENGINE_FILES = (
    "src/copilot_cmd.cpp", "src/copilot_cmd.h", "src/network/network_admin.cpp",
    "src/network/network_admin.h", "src/network/network_command.cpp",
    "src/command_type.h", "src/saveload/copilot_sl.cpp",
)
OWNER_NONE = 0x10
ASSET_ABSENT = 0xFFFFFFFF


class Experiment(mutation.Experiment):
    probe_kind = "native-infrastructure-probe"


def engine_provenance(binary: Path, allow_dirty: bool) -> dict:
    head = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "status", "--porcelain"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout
    environment.require(allow_dirty or not dirty, "engine checkout must be clean; pass --allow-dirty-engine")
    version = subprocess.run([str(binary), "-h"], capture_output=True, text=True, check=True, timeout=10)
    match = re.search(r"OpenTTD\s+(\S+)", version.stdout + version.stderr)
    marker = "m" if dirty else "g"
    environment.require(match is not None and f"{marker}{head[:10]}" in match.group(1),
                        "binary revision does not match engine checkout state")
    return {"head": head, "clean": not bool(dirty), "revision": match.group(1),
            "source_hashes": {name: base.sha256_file(ENGINE_SOURCE / name) for name in ENGINE_FILES}}


def operation_parts(value: int) -> tuple[int, int]:
    return value >> 64, value & ((1 << 64) - 1)


def payload_hash(request: dict) -> tuple[int, int]:
    digest = hashlib.blake2b(
        json.dumps(request, sort_keys=True, separators=(",", ":")).encode(), digest_size=16
    ).digest()
    return int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:], "big")


def clear_flat_tiles(admin, world_id: str, first_tile: int, remaining):
    identity = admin.copilot_identity(timeout=remaining())
    map_width, map_height = identity["map_width"], identity["map_height"]
    observed = []
    first_x, first_y = first_tile % map_width, first_tile // map_width
    for y in range(max(0, first_y - 1), min(map_height, first_y + 2)):
        start_x, end_x = max(0, first_x - 32), min(map_width, first_x + 64)
        for x in range(start_x, end_x, 32):
            observed.extend(admin.copilot_tile_snapshot(
                world_id, y * map_width + x, min(32, end_x - x), timeout=remaining()
            )["tiles"])
    return sorted(
        (tile for tile in observed if tile["valid"] and tile["tile_type"] == 0
         and tile["slope"] == 0 and tile["track_bits"] == 0 and tile["owner"] == OWNER_NONE
         and 0 <= tile["tile"] < map_width * map_height),
        key=lambda tile: (abs(tile["tile"] - first_tile), tile["tile"]),
    )


def select_infrastructure_sites(
    tiles: list[dict], first_tile: int, map_width: int, map_height: int, axis: int = 0,
) -> tuple[dict, dict]:
    """Select a two-tile station footprint and a separate depot tile."""
    if axis not in (0, 1):
        raise ValueError("station axis must be 0 or 1")
    tiles = sorted(tiles, key=lambda tile: (abs(tile["tile"] - first_tile), tile["tile"]))
    by_id = {tile["tile"]: tile for tile in tiles}
    delta = 1 if axis == 0 else map_width
    station = next(
        (tile for tile in tiles
         if tile["tile"] + delta in by_id
         and tile["height"] == by_id[tile["tile"] + delta]["height"]
         and (axis == 1 or tile["tile"] % map_width < map_width - 1)
         and (axis == 0 or tile["tile"] // map_width < map_height - 1)),
        None,
    )
    if station is None:
        raise base.ProbeError("no adjacent clear flat station footprint was observed")
    depot = next(
        (tile for tile in tiles if tile["tile"] not in {station["tile"], station["tile"] + delta}
         and abs(tile["tile"] % map_width - station["tile"] % map_width)
         + abs(tile["tile"] // map_width - station["tile"] // map_width) > 2),
        None,
    )
    if depot is None:
        raise base.ProbeError("no separated clear flat depot site was observed")
    return station, depot


def make_request(identity: dict, tile: int, kind: int, orientation: int,
                 length: int, max_cost: int, operation: int) -> tuple[dict, dict]:
    op_hi, op_lo = operation_parts(operation)
    request = {
        "world_id": identity["world_id"], "expect_sequence": identity["sequence"],
        "expect_head": identity["head"], "operation": {"hi": op_hi, "lo": op_lo},
        "company_id": 0, "tile": tile, "rail_type": 0, "orientation": orientation,
        "infrastructure_kind": kind, "length": length, "max_cost": max_cost,
    }
    hash_hi, hash_lo = payload_hash(request)
    wire = {**{key: request[key] for key in (
        "world_id", "company_id", "tile", "rail_type", "orientation",
        "infrastructure_kind", "length", "max_cost",
    )}, "expected_sequence": identity["sequence"],
             "expected_head_hi": identity["head_hi"], "expected_head_lo": identity["head_lo"],
             "operation_hi": op_hi, "operation_lo": op_lo,
             "payload_hash_hi": hash_hi, "payload_hash_lo": hash_lo}
    return request, wire


def wait_for_terminal(experiment: Experiment, world_id: str, operation: tuple[int, int], reply: dict) -> dict:
    final = reply
    while final.get("state_name") == "pending":
        time.sleep(min(0.05, experiment.remaining()))
        final = experiment.admin.copilot_infrastructure_status(
            world_id=world_id, operation_hi=operation[0], operation_lo=operation[1],
            timeout=experiment.remaining())
    return final


def read_assets(admin, world_id: str, kind: int, timeout: float):
    deadline = time.monotonic() + timeout
    assets = []
    for start in range(0, 65536, 16):
        remaining = deadline - time.monotonic()
        environment.require(remaining > 0, "asset scan deadline exceeded")
        page = admin.copilot_rail_assets(
            world_id, 0, 0 if kind == 1 else 1, start, 16, timeout=remaining,
        )
        assets.extend(page["stations" if kind == 1 else "depots"])
        if page["count"] < 16:
            return assets
    raise base.ProbeError("asset scan exceeded bounded station/depot pool")


def admitted_request(experiment, identity, tile, kind, orientation, length, max_cost, label):
    request, wire = make_request(identity, tile, kind, orientation, length, max_cost, uuid.uuid4().int)
    journal = Journal.create(experiment.artifacts / f"journals/{label}.json", identity)
    environment.require(journal.record_pending(request), f"{label} was not journaled")
    reply = experiment.admin.copilot_build_infrastructure(**wire, timeout=experiment.remaining())
    final = wait_for_terminal(experiment, identity["world_id"],
                              (wire["operation_hi"], wire["operation_lo"]), reply)
    current = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    environment.require(journal.reconcile(current, final) in {"completed", "rejected"},
                        f"{label} did not reconcile")
    return request, wire, final, journal


def legacy_sequence_records(save: Path) -> list[dict]:
    manifest = save.parent / "manifest.json"
    environment.require(manifest.is_file(), f"required schema-2 manifest is missing: {manifest}")
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
        records = value["checks"]["reload_retains_records"]["retained_outcomes"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise base.ProbeError("schema-2 manifest lacks retained reload outcomes") from exc
    environment.require(isinstance(records, list) and len(records) == 64,
                        "schema-2 manifest must contain exactly 64 retained outcomes")
    environment.require(all(isinstance(record, dict) for record in records),
                        "schema-2 retained outcomes are malformed")
    return records


def immutable_operation_fields(record: dict) -> dict:
    return {key: record[key] for key in (
        "operation", "payload_hash", "company_id", "tile", "rail_type", "track",
        "max_cost", "actual_cost", "error", "frame", "state",
    )}


def immutable_infrastructure_fields(record: dict) -> dict:
    return {key: record[key] for key in (
        "operation", "payload_hash", "company_id", "tile", "rail_type",
        "orientation", "infrastructure_kind", "length", "max_cost",
        "actual_cost", "error", "frame", "state", "created_asset_id",
    )}


def run_schema2_history_migration(experiment: Experiment, args: argparse.Namespace) -> None:
    legacy_save = args.legacy_sequence_save.expanduser().resolve()
    environment.require(legacy_save.is_file(), f"required schema-2 save is missing: {legacy_save}")
    records = legacy_sequence_records(legacy_save)
    source_before = environment.file_fingerprint(legacy_save)
    experiment.start(
        "schema2-history", "Copilot Control Probe",
        [(ROOT / "game/copilot_probe", "copilot_probe")], legacy_save,
    )
    identity = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    native.select_human_company(identity["companies"], requested=0)
    environment.require(identity["sequence"] == records[-1]["sequence"]
                        and identity["head"] == records[-1]["head"],
                        "schema-2 history position did not migrate")
    before_company = identity["companies"][0]
    for record in records:
        replay = experiment.admin.copilot_operation_status(
            world_id=identity["world_id"], operation_hi=record["operation_hi"],
            operation_lo=record["operation_lo"], timeout=experiment.remaining(),
        )
        environment.require(immutable_operation_fields(replay)
                            == immutable_operation_fields(record),
                            "schema-2 immutable rail outcome changed during migration")
        environment.require(replay["sequence"] == identity["sequence"]
                            and replay["head"] == identity["head"],
                            "schema-2 replay changed current journal position")
    rail = experiment.admin.copilot_infrastructure_status(
        world_id=identity["world_id"], operation_hi=records[0]["operation_hi"],
        operation_lo=records[0]["operation_lo"], timeout=experiment.remaining(),
    )
    environment.require(
        (rail["infrastructure_kind"], rail["length"], rail["created_asset_id"])
        == (0, 0, ASSET_ABSENT),
        "status12 did not expose the legacy rail extension",
    )
    full_operation = uuid.uuid4().int
    _, full_wire = make_request(identity, records[0]["tile"], 1, 0, 1, args.max_cost, full_operation)
    try:
        experiment.admin.copilot_build_infrastructure(**full_wire, timeout=experiment.remaining())
    except CopilotBridgeError as exc:
        environment.require(exc.status == 12, "full schema-2 journal did not refuse infrastructure admission")
    else:
        raise base.ProbeError("full schema-2 journal accepted infrastructure admission")
    after_full = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    environment.require(after_full["sequence"] == identity["sequence"]
                        and after_full["head"] == identity["head"]
                        and after_full["companies"] == identity["companies"],
                        "full journal refusal changed current state")
    migrated = experiment.save_world("schema2-history-migrated")
    experiment.start(
        "schema2-history-reload", "Copilot Control Probe",
        [(ROOT / "game/copilot_probe", "copilot_probe")], migrated,
    )
    reloaded = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    environment.require(
        reloaded["world_id"] == identity["world_id"]
        and reloaded["sequence"] == identity["sequence"]
        and reloaded["head"] == identity["head"]
        and reloaded["companies"][0]["money"] == before_company["money"]
        and reloaded["companies"][0]["loan"] == before_company["loan"],
        "schema-2 migration reload changed identity or company finances",
    )
    for record in records:
        replay = experiment.admin.copilot_operation_status(
            world_id=reloaded["world_id"], operation_hi=record["operation_hi"],
            operation_lo=record["operation_lo"], timeout=experiment.remaining(),
        )
        environment.require(immutable_operation_fields(replay)
                            == immutable_operation_fields(record),
                            "schema-3 reload changed retained schema-2 outcome")
    source_after = environment.file_fingerprint(legacy_save)
    environment.require(source_after == source_before, "schema-2 source save changed")
    experiment.check("schema2_history_migration", {
        "source": str(legacy_save), "source_before": source_before,
        "source_after": source_after, "records": len(records),
        "before": identity, "after_reload": reloaded,
        "rail_status12": rail, "migrated_save": environment.file_fingerprint(migrated),
    })


def run(args: argparse.Namespace) -> int:
    source, binary = args.save.expanduser().resolve(), args.binary.expanduser().resolve()
    environment.require(
        isinstance(args.deadline, (int, float)) and not isinstance(args.deadline, bool)
        and math.isfinite(args.deadline) and args.deadline > 0,
        "deadline must be a finite positive number",
    )
    environment.require(source.is_file() and source.suffix == ".sav", f"source must be an existing .sav file: {source}")
    experiment = Experiment(binary, source, args.deadline, 3, base.DEFAULT_SEED)
    experiment.manifest.update({
        "scope": "M2d bounded native station/depot construction and retained identity probe",
        "binary_sha256": base.sha256_file(binary),
        "engine_checkout": engine_provenance(binary, args.allow_dirty_engine),
        "source_hashes": {name: base.sha256_file(ROOT / name) for name in (
            "tools/admin_transport.py", "tools/native_mutation_journal.py",
            "tools/run_native_infrastructure_probe.py")},
    })
    experiment.write()
    failure = None
    try:
        run_schema2_history_migration(experiment, args)
        experiment.start("infrastructure", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        identity = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        native.select_human_company(identity["companies"], requested=0)
        environment.require(identity["sequence"] == 0 and identity["head"] is None,
                            "construction fixture must start with an empty native journal")
        tiles = clear_flat_tiles(experiment.admin, identity["world_id"], args.tile, experiment.remaining)
        station, depot = select_infrastructure_sites(
            tiles, args.tile, identity["map_width"], identity["map_height"], args.station_axis,
        )
        before = identity["companies"][0]
        original_stations = read_assets(experiment.admin, identity["world_id"], 1, experiment.remaining())
        original_depots = read_assets(experiment.admin, identity["world_id"], 2, experiment.remaining())

        # A zero cap is a retained rejection and must not consume the site.
        cap_before = identity
        station_cap_request, station_cap_wire, rejected, station_cap_journal = admitted_request(
            experiment, identity, station["tile"], 1, args.station_axis, 2, 0, "0000-station-cap")
        environment.require(rejected["state_name"] == "rejected" and rejected["actual_cost"] == 0,
                            "station zero-cap request did not reject")
        cap_after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(
            cap_after["sequence"] == cap_before["sequence"]
            and cap_after["head"] == cap_before["head"]
            and cap_after["companies"] == cap_before["companies"]
            and read_assets(experiment.admin, cap_after["world_id"], 1, experiment.remaining()) == original_stations
            and read_assets(experiment.admin, cap_after["world_id"], 2, experiment.remaining()) == original_depots,
            "station cap rejection changed journal, finances, or assets",
        )
        identity = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        station_request, station_wire, station_outcome, station_journal = admitted_request(
            experiment, identity, station["tile"], 1, args.station_axis, 2, args.max_cost, "0001-station")
        environment.require(station_outcome["state_name"] == "completed"
                            and station_outcome["created_asset_id"] != ASSET_ABSENT
                            and station_outcome["actual_cost"] > 0
                            and station_outcome["actual_cost"] <= args.max_cost
                            and station_outcome["sequence"] == identity["sequence"] + 1
                            and station_outcome["head"] == station_outcome["operation"],
                            f"station build failed: {station_outcome}")
        station_assets = read_assets(experiment.admin, identity["world_id"], 1, experiment.remaining())
        environment.require(len(station_assets) == len(original_stations) + 1,
                            "station build merged with or removed an existing station")
        created_station = next((item for item in station_assets
                                if item["station_id"] == station_outcome["created_asset_id"]), None)
        environment.require(created_station is not None, "created station absent from asset readback")
        expected_width, expected_height = (2, 1) if args.station_axis == 0 else (1, 2)
        delta = 1 if args.station_axis == 0 else identity["map_width"]
        environment.require(
            created_station["base_tile"] == station["tile"]
            and created_station["platform_tile"] in {station["tile"], station["tile"] + delta}
            and created_station["platform_width"] == expected_width
            and created_station["platform_height"] == expected_height,
            "created station geometry does not match requested footprint",
        )
        environment.require(
            Journal.open(station_journal.path).classify_position(station_outcome) == "current",
            "reopened station journal did not match its completed position",
        )

        identity_after_station = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        depot_cap_before = identity_after_station
        depot_cap_request, depot_cap_wire, depot_rejected, depot_cap_journal = admitted_request(
            experiment, identity_after_station, depot["tile"], 2, args.depot_direction, 1, 0, "0002-depot-cap")
        environment.require(depot_rejected["state_name"] == "rejected"
                            and depot_rejected["actual_cost"] == 0,
                            "depot zero-cap request did not reject")
        depot_cap_after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(
            depot_cap_after["sequence"] == depot_cap_before["sequence"]
            and depot_cap_after["head"] == depot_cap_before["head"]
            and depot_cap_after["companies"] == depot_cap_before["companies"]
            and read_assets(experiment.admin, depot_cap_after["world_id"], 1, experiment.remaining()) == station_assets
            and read_assets(experiment.admin, depot_cap_after["world_id"], 2, experiment.remaining()) == original_depots,
            "depot cap rejection changed journal, finances, or assets",
        )
        identity_after_station = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        _, depot_wire, depot_outcome, depot_journal = admitted_request(
            experiment, identity_after_station, depot["tile"], 2, args.depot_direction, 1, args.max_cost, "0003-depot")
        environment.require(depot_outcome["state_name"] == "completed"
                            and depot_outcome["created_asset_id"] != ASSET_ABSENT
                            and depot_outcome["actual_cost"] > 0
                            and depot_outcome["actual_cost"] <= args.max_cost
                            and depot_outcome["sequence"] == identity_after_station["sequence"] + 1
                            and depot_outcome["head"] == depot_outcome["operation"],
                            f"depot build failed: {depot_outcome}")
        depot_assets = read_assets(experiment.admin, identity_after_station["world_id"], 2, experiment.remaining())
        environment.require(len(depot_assets) == len(original_depots) + 1,
                            "depot build merged with or removed an existing depot")
        created_depot = next((item for item in depot_assets
                              if item["depot_id"] == depot_outcome["created_asset_id"]), None)
        environment.require(
            created_depot is not None
            and created_depot["tile"] == depot["tile"]
            and created_depot["direction"] == args.depot_direction
            and created_depot["rail_type"] == 0,
            "created depot geometry does not match requested site",
        )
        environment.require(
            Journal.open(depot_journal.path).classify_position(depot_outcome) == "current"
            and Journal.open(station_journal.path).classify_position(depot_outcome) == "ahead",
            "reopened journals did not classify current and historical positions",
        )
        after_build = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        built_tiles = []
        for tile, tile_type in ((station["tile"], 5), (station["tile"] + delta, 5), (depot["tile"], 1)):
            observed = experiment.admin.copilot_tile_snapshot(
                identity["world_id"], tile, 1, timeout=experiment.remaining())["tiles"][0]
            environment.require(observed["valid"] and observed["owner"] == 0
                                and observed["tile_type"] == tile_type,
                                "built infrastructure tile type or ownership does not match")
            built_tiles.append(observed)
        environment.require(
            after_build["companies"][0]["loan"] == before["loan"]
            and before["money"] - after_build["companies"][0]["money"]
            == station_outcome["actual_cost"] + depot_outcome["actual_cost"],
            "cash or loan does not match authoritative infrastructure costs",
        )
        environment.require(
            [item for item in station_assets if item["station_id"] in {x["station_id"] for x in original_stations}]
            == original_stations
            and [item for item in depot_assets if item["depot_id"] in {x["depot_id"] for x in original_depots}]
            == original_depots,
            "pre-existing station or depot records changed",
        )

        duplicate_before = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        duplicate = experiment.admin.copilot_build_infrastructure(**station_wire, timeout=experiment.remaining())
        duplicate_after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(
            duplicate["state_name"] == "completed"
            and duplicate["created_asset_id"] == station_outcome["created_asset_id"]
            and duplicate["actual_cost"] == station_outcome["actual_cost"]
            and duplicate["frame"] == station_outcome["frame"]
            and duplicate["payload_hash"] == station_outcome["payload_hash"]
            and duplicate["infrastructure_kind"] == station_outcome["infrastructure_kind"]
            and duplicate["length"] == station_outcome["length"]
            and duplicate_before["companies"] == duplicate_after["companies"]
            and duplicate_before["sequence"] == duplicate_after["sequence"]
            and duplicate_before["head"] == duplicate_after["head"]
            and read_assets(experiment.admin, duplicate_after["world_id"], 1, experiment.remaining()) == station_assets
            and read_assets(experiment.admin, duplicate_after["world_id"], 2, experiment.remaining()) == depot_assets,
            "duplicate infrastructure request mutated state or changed created ID")

        conflict = dict(station_wire)
        conflict["tile"] = depot["tile"]
        changed_request = dict(station_request)
        changed_request["tile"] = depot["tile"]
        changed_hash = payload_hash(changed_request)
        conflict["payload_hash_hi"], conflict["payload_hash_lo"] = changed_hash
        try:
            experiment.admin.copilot_build_infrastructure(**conflict, timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 8, "changed infrastructure ID did not conflict")
        else:
            raise base.ProbeError("changed infrastructure ID was accepted")
        rail_conflict = {
            "world_id": identity["world_id"], "company_id": 0, "tile": station["tile"],
            "rail_type": 0, "track": 1, "max_cost": args.max_cost,
            "expected_sequence": duplicate_after["sequence"],
            "expected_head_hi": duplicate_after["head_hi"],
            "expected_head_lo": duplicate_after["head_lo"],
            "operation_hi": station_wire["operation_hi"],
            "operation_lo": station_wire["operation_lo"],
            "payload_hash_hi": 0, "payload_hash_lo": 1,
        }
        try:
            experiment.admin.copilot_build_single_rail(**rail_conflict, timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 8, "rail request did not conflict with infrastructure operation ID")
        else:
            raise base.ProbeError("rail request reused an infrastructure operation ID")
        wrong_world = dict(station_wire)
        wrong_world["world_id"] = "wrong-world"
        try:
            experiment.admin.copilot_build_infrastructure(**wrong_world, timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 5, "wrong-world infrastructure request did not reject")
        else:
            raise base.ProbeError("wrong-world infrastructure request was accepted")

        try:
            experiment.admin.copilot_operation_status(
                world_id=identity["world_id"], operation_hi=station_wire["operation_hi"],
                operation_lo=station_wire["operation_lo"], timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 2, "old status request did not reject infrastructure")
        else:
            raise base.ProbeError("old rail status request accepted infrastructure")
        stale = dict(depot_wire)
        stale["operation_hi"], stale["operation_lo"] = operation_parts(uuid.uuid4().int)
        stale["expected_sequence"] = 0
        stale["expected_head_hi"] = 0
        stale["expected_head_lo"] = 0
        try:
            experiment.admin.copilot_build_infrastructure(**stale, timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 11, "stale infrastructure request did not reject")
        else:
            raise base.ProbeError("stale infrastructure request was accepted")
        after_guards = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(
            after_guards["companies"] == after_build["companies"]
            and after_guards["sequence"] == after_build["sequence"]
            and after_guards["head"] == after_build["head"]
            and read_assets(experiment.admin, after_guards["world_id"], 1, experiment.remaining()) == station_assets
            and read_assets(experiment.admin, after_guards["world_id"], 2, experiment.remaining()) == depot_assets,
            "conflict, world, or stale guard mutated state",
        )
        saved = experiment.save_world("infrastructure-final")
        experiment.check("station_depot_completed", {
            "before": before, "station": station_outcome, "depot": depot_outcome,
            "station_assets": station_assets, "depot_assets": depot_assets,
            "duplicate": duplicate, "journals": [str(station_journal.path), str(depot_journal.path)],
            "original_stations": original_stations, "original_depots": original_depots,
            "after": after_guards, "built_tiles": built_tiles,
            "guards": {"changed_payload": 8, "old_rail_id_reuse": 8, "wrong_world": 5,
                       "old_status": 2, "stale_position": 11},
            "cap_rejections": [rejected, depot_rejected],
            "save": environment.file_fingerprint(saved),
        })
        experiment.start("reload", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], saved)
        reloaded = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(
            reloaded["world_id"] == after_build["world_id"]
            and reloaded["companies"] == after_build["companies"]
            and reloaded["sequence"] == after_build["sequence"]
            and reloaded["head"] == after_build["head"],
            "save/reload changed world, journal position, cash, or loan",
        )
        reload_outcomes = []
        for wire in (station_cap_wire, station_wire, depot_cap_wire, depot_wire):
            reload_outcomes.append(experiment.admin.copilot_infrastructure_status(
                world_id=reloaded["world_id"], operation_hi=wire["operation_hi"],
                operation_lo=wire["operation_lo"], timeout=experiment.remaining()))
        expected_reload = [rejected, station_outcome, depot_rejected, depot_outcome]
        environment.require(
            all(immutable_infrastructure_fields(actual)
                == immutable_infrastructure_fields(expected)
                for actual, expected in zip(reload_outcomes, expected_reload)),
            "save/reload changed an admitted infrastructure outcome",
        )
        station_replay = experiment.admin.copilot_infrastructure_status(
            world_id=reloaded["world_id"], operation_hi=station_wire["operation_hi"],
            operation_lo=station_wire["operation_lo"], timeout=experiment.remaining())
        depot_replay = experiment.admin.copilot_infrastructure_status(
            world_id=reloaded["world_id"], operation_hi=depot_wire["operation_hi"],
            operation_lo=depot_wire["operation_lo"], timeout=experiment.remaining())
        reload_duplicate = experiment.admin.copilot_build_infrastructure(
            **station_wire, timeout=experiment.remaining())
        environment.require(
            station_replay["created_asset_id"] == station_outcome["created_asset_id"]
            and depot_replay["created_asset_id"] == depot_outcome["created_asset_id"]
            and reload_duplicate["created_asset_id"] == station_outcome["created_asset_id"]
            and reload_duplicate["sequence"] == reloaded["sequence"],
            "infrastructure identity or duplicate was not retained after reload",
        )
        reload_after_duplicate = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(
            immutable_infrastructure_fields(reload_duplicate) == immutable_infrastructure_fields(station_outcome)
            and reload_after_duplicate["companies"] == reloaded["companies"]
            and reload_after_duplicate["sequence"] == reloaded["sequence"]
            and reload_after_duplicate["head"] == reloaded["head"]
            and reload_duplicate["head"] == reloaded["head"],
            "reload duplicate changed immutable outcome, cash, loan, or journal position",
        )
        for expected in built_tiles:
            actual = experiment.admin.copilot_tile_snapshot(
                reloaded["world_id"], expected["tile"], 1, timeout=experiment.remaining())["tiles"][0]
            environment.require(actual == expected, "built tile changed after reload/replay")
        environment.require(
            read_assets(experiment.admin, reloaded["world_id"], 1, experiment.remaining()) == station_assets
            and read_assets(experiment.admin, reloaded["world_id"], 2, experiment.remaining()) == depot_assets,
            "save/reload changed built station or depot records",
        )
        experiment.check("reload_retains_created_assets", {
            "identity": reloaded, "station": station_replay, "depot": depot_replay,
            "duplicate": reload_duplicate,
            "admitted_outcomes": reload_outcomes,
            "stations": read_assets(experiment.admin, reloaded["world_id"], 1, experiment.remaining()),
            "depots": read_assets(experiment.admin, reloaded["world_id"], 2, experiment.remaining()),
        })
    except Exception as exc:
        failure = exc
    return experiment.finish(failure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/openttd-m2a/openttd")
    parser.add_argument("--deadline", type=float, default=120)
    parser.add_argument("--allow-dirty-engine", action="store_true")
    parser.add_argument("--tile", type=int, default=8255)
    parser.add_argument("--max-cost", type=int, default=10000)
    parser.add_argument("--station-axis", type=int, choices=(0, 1), default=0)
    parser.add_argument("--depot-direction", type=int, choices=(0, 1, 2, 3), default=0)
    parser.add_argument(
        "--legacy-sequence-save", type=Path,
        default=ROOT / "artifacts/native-sequence-probe/20261023T213034Z-f2d4546a/sequence-final.sav",
    )
    args = parser.parse_args()
    if args.tile < 0 or args.max_cost <= 0 or not math.isfinite(args.deadline) or args.deadline <= 0:
        parser.error("tile must be non-negative; max-cost and deadline must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
