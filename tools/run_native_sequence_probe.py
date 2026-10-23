#!/usr/bin/env python3
"""Exercise the retained native operation journal on an isolated copied save.

This is deliberately a bounded regression probe.  It records every admitted
request in a separate external journal before sending it, and never retries a
request whose final outcome was not reconciled.
"""

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
    "src/copilot_cmd.cpp",
    "src/copilot_cmd.h",
    "src/saveload/copilot_sl.cpp",
    "src/network/network_admin.cpp",
    "src/network/network_admin.h",
)
MAX_RECORDS = 64
OWNER_NONE = 0x10


class Experiment(mutation.Experiment):
    probe_kind = "native-sequence-probe"


def engine_provenance(binary: Path, allow_dirty: bool) -> dict:
    """Bind evidence to the engine checkout and all directly relevant sources."""
    head = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "status", "--porcelain"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout
    environment.require(
        allow_dirty or not dirty,
        "engine checkout must be clean; pass --allow-dirty-engine for local source gate",
    )
    version = subprocess.run(
        [str(binary), "-h"], capture_output=True, text=True, check=True, timeout=10,
    )
    match = re.search(r"OpenTTD\s+(\S+)", version.stdout + version.stderr)
    marker = "m" if dirty else "g"
    environment.require(
        match is not None and f"{marker}{head[:10]}" in match.group(1),
        "binary revision does not match engine checkout state",
    )
    return {
        "head": head,
        "clean": not bool(dirty),
        "revision": match.group(1),
        "source_hashes": {
            name: base.sha256_file(ENGINE_SOURCE / name) for name in ENGINE_FILES
        },
    }


def operation_parts(value: int) -> tuple[int, int]:
    return value >> 64, value & ((1 << 64) - 1)


def payload_hash(request: dict) -> tuple[int, int]:
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.blake2b(encoded, digest_size=16).digest()
    return int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:], "big")


def clear_flat_tiles(admin, world_id: str, first_tile: int, remaining):
    """Return observed clear/flat/unoccupied tiles near the known first tile."""
    start = max(0, first_tile - 16)
    observed: list[dict] = []
    for offset in range(0, 128, 32):
        page = admin.copilot_tile_snapshot(
            world_id, start + offset, 32, timeout=remaining(),
        )
        observed.extend(page["tiles"])
    candidates = [
        tile for tile in observed
        if tile["valid"] and tile["tile_type"] == 0 and tile["slope"] == 0
        and tile["track_bits"] == 0 and tile["owner"] == OWNER_NONE
    ]
    candidates.sort(key=lambda tile: (abs(tile["tile"] - first_tile), tile["tile"]))
    return candidates


def wait_for_terminal(experiment: Experiment, world_id: str, operation: tuple[int, int], reply: dict) -> dict:
    final = reply
    while final.get("state_name") == "pending":
        time.sleep(min(0.05, experiment.remaining()))
        final = experiment.admin.copilot_operation_status(
            world_id=world_id, operation_hi=operation[0], operation_lo=operation[1],
            timeout=experiment.remaining(),
        )
    return final


def make_request(identity: dict, tile: int, max_cost: int, operation: int) -> tuple[dict, dict]:
    op_hi, op_lo = operation_parts(operation)
    request = {
        "world_id": identity["world_id"],
        "expect_sequence": identity["sequence"],
        "expect_head": identity["head"],
        "operation": {"hi": op_hi, "lo": op_lo},
        "company_id": 0,
        "tile": tile,
        "rail_type": 0,
        "track": 1,
        "max_cost": max_cost,
    }
    hash_hi, hash_lo = payload_hash(request)
    wire = {
        "world_id": identity["world_id"],
        "company_id": 0,
        "tile": tile,
        "rail_type": 0,
        "track": 1,
        "max_cost": max_cost,
        "expected_sequence": identity["sequence"],
        "expected_head_hi": identity["head_hi"],
        "expected_head_lo": identity["head_lo"],
        "operation_hi": op_hi,
        "operation_lo": op_lo,
        "payload_hash_hi": hash_hi,
        "payload_hash_lo": hash_lo,
    }
    return request, wire


def admitted_request(experiment: Experiment, identity: dict, tile: int, max_cost: int,
                     operation: int, label: str) -> tuple[dict, dict, dict, Journal]:
    request, wire = make_request(identity, tile, max_cost, operation)
    journal = Journal.create(
        experiment.artifacts / f"journals/{label}.json", identity,
    )
    environment.require(journal.record_pending(request), f"{label} was not journaled")
    reply = experiment.admin.copilot_build_single_rail(
        **wire, timeout=experiment.remaining(),
    )
    final = wait_for_terminal(
        experiment, identity["world_id"], operation_parts(operation), reply,
    )
    current = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    environment.require(
        journal.reconcile(current, final) in {"completed", "rejected"},
        f"{label} did not reconcile: {final}",
    )
    return request, wire, final, journal


def expect_status(experiment: Experiment, identity: dict, wire: dict, status: int, label: str):
    try:
        experiment.admin.copilot_build_single_rail(**wire, timeout=experiment.remaining())
    except CopilotBridgeError as exc:
        environment.require(exc.status == status, f"{label} returned status {exc.status}, expected {status}")
        return {"status": exc.status}
    raise base.ProbeError(f"{label} was accepted")


def legacy_operation_from_manifest(save: Path) -> dict | None:
    manifest = save.parent / "manifest.json"
    if not manifest.is_file():
        return None
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
        completed = value["checks"]["native_mutation_completed"]
        record = completed["final"]
        if record.get("state_name") != "completed":
            return None
        return {
            key: record[key] for key in (
                "operation_hi", "operation_lo", "payload_hash_hi", "payload_hash_lo",
                "company_id", "tile", "rail_type", "track", "max_cost",
                "actual_cost", "frame",
            )
        }
    except (OSError, KeyError, TypeError, ValueError):
        return None


def verify_reload_journal_positions(journals: list[Journal], identity: dict) -> dict[str, str]:
    """Require historical journals to be ahead and current journals to match exactly."""
    remote_sequence = identity["sequence"]
    remote_head = identity["head"]
    classifications: dict[str, str] = {}
    for journal in journals:
        classification = journal.classify_position(identity)
        local_sequence = journal.position[1]
        local_head = journal.position[2]
        normalized_remote_head = (
            None if remote_head is None else (remote_head["hi"], remote_head["lo"])
        )
        if local_sequence < remote_sequence:
            expected = "ahead"
        elif local_sequence == remote_sequence:
            environment.require(
                local_head == normalized_remote_head, "reload journal head diverged",
            )
            expected = "current"
        else:
            raise base.ProbeError("reload is older than a retained journal")
        environment.require(
            classification == expected,
            f"unexpected reload classification for {journal.path}: "
            f"{classification}, expected {expected}",
        )
        classifications[str(journal.path)] = classification
    environment.require(
        any(value == "current" for value in classifications.values()),
        "no latest journal classified current after reload",
    )
    return classifications


def run_legacy_gate(experiment: Experiment, legacy_save: Path, args: argparse.Namespace) -> None:
    environment.require(legacy_save.is_file(), f"required schema-1 save not present: {legacy_save}")
    legacy_before = environment.file_fingerprint(legacy_save)
    operation = legacy_operation_from_manifest(legacy_save)
    environment.require(operation is not None, "legacy save manifest lacks its M2b operation")
    experiment.start(
        "legacy-schema1", "Copilot Control Probe",
        [(ROOT / "game/copilot_probe", "copilot_probe")], legacy_save,
    )
    identity = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    environment.require(identity["sequence"] == 1 and identity["head"] == {
        "hi": operation["operation_hi"], "lo": operation["operation_lo"],
    }, "schema-1 completed save did not migrate its existing head")
    before_replay = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    replay = experiment.admin.copilot_operation_status(
        world_id=identity["world_id"], operation_hi=operation["operation_hi"],
        operation_lo=operation["operation_lo"], timeout=experiment.remaining(),
    )
    after_replay = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    environment.require(
        replay["state_name"] == "completed"
        and replay["operation_hi"] == operation["operation_hi"]
        and replay["operation_lo"] == operation["operation_lo"]
        and replay["payload_hash_hi"] == operation["payload_hash_hi"]
        and replay["payload_hash_lo"] == operation["payload_hash_lo"]
        and replay["company_id"] == operation["company_id"]
        and replay["tile"] == operation["tile"]
        and replay["rail_type"] == operation["rail_type"]
        and replay["track"] == operation["track"]
        and replay["max_cost"] == operation["max_cost"]
        and replay["actual_cost"] == operation["actual_cost"]
        and replay["frame"] == operation["frame"],
        "schema-1 completed operation did not replay its immutable record after migration",
    )
    environment.require(
        replay["sequence"] == identity["sequence"]
        and replay["head"] == identity["head"]
        and replay["readback"]["money"] == before_replay["companies"][0]["money"]
        and replay["readback"]["loan"] == before_replay["companies"][0]["loan"]
        and before_replay["companies"] == after_replay["companies"]
        and before_replay["sequence"] == after_replay["sequence"]
        and before_replay["head"] == after_replay["head"],
        "schema-1 replay changed current global or company state",
    )
    candidates = clear_flat_tiles(
        experiment.admin, identity["world_id"], args.tile, experiment.remaining,
    )
    candidate = next(
        (tile for tile in candidates if tile["tile"] != args.tile
         and abs(tile["tile"] - args.tile) == 1),
        None,
    )
    environment.require(candidate is not None, "legacy migration gate found no adjacent clear tile")
    _, _, outcome, journal = admitted_request(
        experiment, identity, candidate["tile"], args.max_cost, uuid.uuid4().int,
        "legacy-0002-new",
    )
    environment.require(outcome["state_name"] == "completed" and outcome["sequence"] == 2,
                        "new operation after schema-1 migration did not advance to sequence two")
    saved = experiment.save_world("legacy-schema1-final")
    experiment.start(
        "legacy-schema1-reload", "Copilot Control Probe",
        [(ROOT / "game/copilot_probe", "copilot_probe")], saved,
    )
    reloaded = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    replay_new = experiment.admin.copilot_operation_status(
        world_id=reloaded["world_id"], operation_hi=outcome["operation_hi"],
        operation_lo=outcome["operation_lo"], timeout=experiment.remaining(),
    )
    environment.require(
        reloaded["sequence"] == 2 and replay_new["state_name"] == "completed"
        and journal.classify_position(reloaded) == "current",
        "schema-1 migrated journal did not survive new operation reload",
    )
    old_duplicate = experiment.admin.copilot_build_single_rail(
        world_id=reloaded["world_id"], company_id=operation["company_id"],
        tile=operation["tile"], rail_type=operation["rail_type"], track=operation["track"],
        max_cost=operation["max_cost"], expected_sequence=0,
        expected_head_hi=0, expected_head_lo=0,
        operation_hi=operation["operation_hi"], operation_lo=operation["operation_lo"],
        payload_hash_hi=operation["payload_hash_hi"], payload_hash_lo=operation["payload_hash_lo"],
        timeout=experiment.remaining(),
    )
    after_duplicate = experiment.admin.copilot_identity(
        company_id=0, timeout=experiment.remaining(),
    )
    environment.require(
        all(old_duplicate[key] == value for key, value in operation.items())
        and old_duplicate["state_name"] == "completed"
        and old_duplicate["sequence"] == reloaded["sequence"]
        and old_duplicate["head"] == reloaded["head"]
        and after_duplicate["companies"] == reloaded["companies"]
        and after_duplicate["sequence"] == reloaded["sequence"]
        and after_duplicate["head"] == reloaded["head"],
        "migrated old operation did not replay safely after reload",
    )
    legacy_after = environment.file_fingerprint(legacy_save)
    environment.require(legacy_before == legacy_after, "original schema-1 source save changed")
    experiment.check("legacy_schema1_migration", {
        "save": str(legacy_save), "record": operation, "replay": replay,
        "new_operation": outcome,
        "reload_identity": reloaded, "reload_replay": replay_new,
        "old_duplicate_after_reload": old_duplicate,
        "journal": str(journal.path),
        "source_before": legacy_before, "source_after": legacy_after,
    })


def run(args: argparse.Namespace) -> int:
    source = args.save.expanduser().resolve()
    binary = args.binary.expanduser().resolve()
    environment.require(source.is_file() and source.suffix == ".sav",
                        f"source must be an existing .sav file: {source}")
    experiment = Experiment(binary, source, args.deadline, 3, base.DEFAULT_SEED)
    experiment.manifest["scope"] = (
        "M2d retained native operation journal regression: 64 admitted records, "
        "immutable replay, rejection, reload, and older-save gates"
    )
    experiment.manifest["max_records"] = MAX_RECORDS
    experiment.manifest["binary_sha256"] = base.sha256_file(binary)
    experiment.manifest["engine_checkout"] = engine_provenance(binary, args.allow_dirty_engine)
    experiment.manifest["source_hashes"] = {
        name: base.sha256_file(ROOT / name) for name in (
            "tools/admin_transport.py",
            "tools/native_mutation_journal.py",
            "tools/run_native_mutation_probe.py",
            "tools/run_native_sequence_probe.py",
        )
    }
    experiment.write()
    failure = None
    try:
        experiment.start(
            "sequence", "Copilot Control Probe",
            [(ROOT / "game/copilot_probe", "copilot_probe")], source,
        )
        identity0 = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(
            identity0["sequence"] == 0 and identity0["head"] is None,
            "schema-1 save did not migrate to empty retained journal",
        )
        company0 = native.select_human_company(identity0["companies"], 0)
        before_money, before_loan = company0["money"], company0["loan"]
        candidates = clear_flat_tiles(
            experiment.admin, identity0["world_id"], args.tile, experiment.remaining,
        )
        first_tile = next((tile for tile in candidates if tile["tile"] == args.tile), None)
        environment.require(first_tile is not None, "known first tile was not observed clear and flat")
        second = next(
            (tile for tile in candidates if tile["tile"] != args.tile
             and abs(tile["tile"] - args.tile) == 1),
            None,
        )
        environment.require(
            second is not None,
            "no adjacent clear flat tile was observed; refusing to invent buildability",
        )
        second_tile = second["tile"]
        spare = next(tile for tile in candidates if tile["tile"] not in {args.tile, second_tile})

        first_request, first_wire, first, first_journal = admitted_request(
            experiment, identity0, args.tile, args.max_cost, uuid.uuid4().int, "0001-first",
        )
        environment.require(first["state_name"] == "completed", f"first build failed: {first}")
        environment.require(
            first["readback"]["has_rail"] and first["readback"]["owner"] == 0
            and first["readback"]["track_bits"] == 2,
            "first build did not read back the expected owned track",
        )
        environment.require(0 < first["actual_cost"] <= args.max_cost, "first cost exceeded cap")
        identity1 = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(identity1["sequence"] == 1, "first success did not advance sequence to one")
        environment.require(identity1["companies"][0]["loan"] == before_loan, "first build changed loan")
        environment.require(
            before_money - identity1["companies"][0]["money"] == first["actual_cost"],
            "first cash delta did not equal authoritative cost",
        )
        experiment.check("first_success", {
            "request": first_request, "outcome": first, "identity": identity1,
            "journal": str(first_journal.path),
        })

        second_request, second_wire, second_outcome, second_journal = admitted_request(
            experiment, identity1, second_tile, args.max_cost, uuid.uuid4().int, "0002-second",
        )
        environment.require(second_outcome["state_name"] == "completed", f"second build failed: {second_outcome}")
        environment.require(
            second_outcome["readback"]["has_rail"]
            and second_outcome["readback"]["owner"] == 0
            and second_outcome["readback"]["track_bits"] == 2,
            "second build did not read back the expected owned track",
        )
        environment.require(0 < second_outcome["actual_cost"] <= args.max_cost, "second cost exceeded cap")
        identity2 = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(identity2["sequence"] == 2, "second success did not advance sequence to two")
        environment.require(identity2["companies"][0]["loan"] == before_loan, "second build changed loan")
        environment.require(
            before_money - identity2["companies"][0]["money"]
            == first["actual_cost"] + second_outcome["actual_cost"],
            "cash did not equal the two authoritative costs",
        )
        duplicate_before = experiment.admin.copilot_identity(
            company_id=0, timeout=experiment.remaining(),
        )
        duplicate = experiment.admin.copilot_build_single_rail(
            **first_wire, timeout=experiment.remaining(),
        )
        duplicate_after = experiment.admin.copilot_identity(
            company_id=0, timeout=experiment.remaining(),
        )
        environment.require(
            duplicate["state_name"] == "completed"
            and duplicate["actual_cost"] == first["actual_cost"]
            and duplicate["sequence"] == identity2["sequence"]
            and duplicate["head"] == identity2["head"]
            and duplicate_before["companies"] == duplicate_after["companies"],
            "first duplicate did not replay without mutation",
        )
        experiment.check("second_success", {
            "request": second_request, "outcome": second_outcome, "identity": identity2,
            "journal": str(second_journal.path), "duplicate": duplicate,
        })

        replay = experiment.admin.copilot_operation_status(
            world_id=identity2["world_id"],
            operation_hi=first["operation_hi"], operation_lo=first["operation_lo"],
            timeout=experiment.remaining(),
        )
        replay_before = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(
            replay["state_name"] == "completed"
            and replay["actual_cost"] == first["actual_cost"]
            and replay["frame"] == first["frame"]
            and replay["sequence"] == identity2["sequence"]
            and replay["head"] == identity2["head"],
            "first immutable outcome did not replay with current global position",
        )
        replay_after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(
            replay["tile"] == args.tile
            and replay["company_id"] == first["company_id"]
            and replay["operation"] == first["operation"]
            and replay["payload_hash"] == first["payload_hash"]
            and replay["readback"]["money"] == replay_before["companies"][0]["money"]
            and replay["readback"]["loan"] == replay_before["companies"][0]["loan"]
            and replay_before["sequence"] == replay_after["sequence"]
            and replay_before["companies"] == replay_after["companies"],
            "replay changed immutable payload, returned stale readback, or mutated state",
        )
        experiment.check("historical_replay_after_second", {
            "replay": replay, "before": replay_before, "after": replay_after,
        })

        changed_request = dict(first_request)
        changed_request["tile"] = second_tile
        changed_hash = payload_hash(changed_request)
        changed_wire = dict(first_wire)
        changed_wire.update({
            "tile": second_tile,
            "expected_sequence": identity2["sequence"],
            "expected_head_hi": identity2["head_hi"],
            "expected_head_lo": identity2["head_lo"],
            "payload_hash_hi": changed_hash[0],
            "payload_hash_lo": changed_hash[1],
        })
        conflict = expect_status(experiment, identity2, changed_wire, 8, "changed payload")
        stale_operation = uuid.uuid4().int
        stale_hi, stale_lo = operation_parts(stale_operation)
        stale_wire = dict(second_wire)
        stale_wire.update({
            "operation_hi": stale_hi,
            "operation_lo": stale_lo,
            "expected_sequence": 0,
            "expected_head_hi": 0,
            "expected_head_lo": 0,
        })
        stale = expect_status(experiment, identity2, stale_wire, 11, "stale position")
        experiment.check("conflict_and_stale_guards", {"conflict": conflict, "stale": stale})

        rejected_request, rejected_wire, rejected, rejected_journal = admitted_request(
            experiment, identity2, spare["tile"], 0, uuid.uuid4().int, "0003-rejected",
        )
        environment.require(
            rejected["state_name"] == "rejected" and rejected["actual_cost"] == 0
            and not rejected["readback"]["has_rail"],
            "zero-cap request did not retain a zero-cost rejection",
        )
        identity_after_rejection = experiment.admin.copilot_identity(
            company_id=0, timeout=experiment.remaining(),
        )
        environment.require(
            identity_after_rejection["sequence"] == 2
            and identity_after_rejection["head"] == identity2["head"]
            and identity_after_rejection["companies"] == identity2["companies"],
            "rejection changed global head or company state",
        )
        _, _, second_rejection, second_rejection_journal = admitted_request(
            experiment, identity_after_rejection, spare["tile"], 0, uuid.uuid4().int, "0004-rejected",
        )
        environment.require(second_rejection["state_name"] == "rejected",
                            "second zero-cap request did not reject")
        experiment.check("rejection_does_not_poison_head", {
            "first": {"request": rejected_request, "outcome": rejected,
                      "journal": str(rejected_journal.path)},
            "second": {"outcome": second_rejection,
                       "journal": str(second_rejection_journal.path)},
            "identity": identity_after_rejection,
        })

        journals = [first_journal, second_journal, rejected_journal, second_rejection_journal]
        if args.capacity_gate:
            for index in range(len(journals), MAX_RECORDS):
                identity = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
                _, _, outcome, journal = admitted_request(
                    experiment, identity, spare["tile"], 0, uuid.uuid4().int,
                    f"{index + 1:04d}-rejected",
                )
                environment.require(outcome["state_name"] == "rejected",
                                    f"capacity fill record {index + 1} was not rejected")
                journals.append(journal)
            environment.require(len(journals) == MAX_RECORDS, "capacity fill count was not exact")
            full_identity = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
            full_op = uuid.uuid4().int
            _, full_wire = make_request(full_identity, spare["tile"], 0, full_op)
            full = expect_status(experiment, full_identity, full_wire, 12, "journal capacity")
            full_after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
            environment.require(
                full_after["sequence"] == full_identity["sequence"]
                and full_after["companies"] == full_identity["companies"],
                "journal-full request mutated state",
            )
            experiment.check("journal_capacity", {
                "records": len(journals), "expected": MAX_RECORDS, "rejection": full,
                "identity": full_after,
            })

        saved = experiment.save_world("sequence-final")
        experiment.start(
            "reload", "Copilot Control Probe",
            [(ROOT / "game/copilot_probe", "copilot_probe")], saved,
        )
        reloaded = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        reloaded_replay = experiment.admin.copilot_operation_status(
            world_id=reloaded["world_id"], operation_hi=first["operation_hi"],
            operation_lo=first["operation_lo"], timeout=experiment.remaining(),
        )
        reload_duplicate_before = experiment.admin.copilot_identity(
            company_id=0, timeout=experiment.remaining(),
        )
        reload_duplicate = experiment.admin.copilot_build_single_rail(
            **first_wire, timeout=experiment.remaining(),
        )
        reload_duplicate_after = experiment.admin.copilot_identity(
            company_id=0, timeout=experiment.remaining(),
        )
        environment.require(
            reloaded["sequence"] == identity_after_rejection["sequence"]
            and reloaded_replay["actual_cost"] == first["actual_cost"]
            and reloaded_replay["state_name"] == "completed"
            and reload_duplicate["state_name"] == "completed"
            and reload_duplicate["sequence"] == reloaded["sequence"]
            and reload_duplicate["head"] == reloaded["head"]
            and reload_duplicate_before["companies"] == reload_duplicate_after["companies"]
            and reload_duplicate_before["sequence"] == reload_duplicate_after["sequence"]
            and reload_duplicate_before["head"] == reload_duplicate_after["head"],
            "retained records did not survive save/reload",
        )
        classifications = verify_reload_journal_positions(journals, reloaded)
        retained = []
        for journal in journals:
            persisted = Journal.open(journal.path)
            operation = persisted.operation
            record = operation["reply"]
            current = experiment.admin.copilot_operation_status(
                world_id=reloaded["world_id"], operation_hi=record["operation_hi"],
                operation_lo=record["operation_lo"], timeout=experiment.remaining(),
            )
            immutable_fields = (
                "operation", "payload_hash", "company_id", "tile", "rail_type", "track",
                "max_cost", "actual_cost", "error", "frame", "state",
            )
            environment.require(
                all(current[key] == record[key] for key in immutable_fields)
                and current["sequence"] == reloaded["sequence"]
                and current["head"] == reloaded["head"],
                f"saved outcome was lost or changed: {journal.path}",
            )
            retained.append(current)
        experiment.check("reload_retains_records", {
            "identity": reloaded, "replay": reloaded_replay, "duplicate": reload_duplicate,
            "journal_count": len(journals), "journal_classifications": classifications,
            "save": environment.file_fingerprint(saved),
            "retained_outcomes": retained,
        })

        run_legacy_gate(
            experiment, args.legacy_save.expanduser().resolve(), args,
        )
        experiment.start(
            "older", "Copilot Control Probe",
            [(ROOT / "game/copilot_probe", "copilot_probe")], source,
        )
        older = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(
            all(journal.classify_position(older) == "older_save" for journal in journals),
            "original schema-1 save was not classified as older than retained journals",
        )
        experiment.check("older_save_detected", {
            "identity": older, "journal_count": len(journals),
            "classification": "older_save",
        })
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
    parser.add_argument(
        "--legacy-save", type=Path,
        default=ROOT / "artifacts/native-mutation-probe/20261023T163704Z-fb8cb770/"
                "completed-native-mutation.sav",
        help="required old M2b schema-1 save and adjacent manifest for migration gate",
    )
    parser.add_argument("--tile", type=int, default=8255)
    parser.add_argument("--max-cost", type=int, default=1000)
    parser.add_argument("--no-capacity-gate", dest="capacity_gate", action="store_false")
    args = parser.parse_args()
    if not math.isfinite(args.deadline) or args.deadline <= 0 or args.tile < 0 or args.max_cost <= 0:
        parser.error("deadline and max-cost must be positive; tile must be non-negative")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
