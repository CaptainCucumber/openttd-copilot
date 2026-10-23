#!/usr/bin/env python3
"""Verify bounded native train consist-part pages on copied saves."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess

from admin_transport import CopilotBridgeError
import run_control_probe as base
import run_environment_probe as environment
import run_native_mutation_probe as mutation


ROOT = base.REPO_ROOT
DEFAULT_SAVE = mutation.DEFAULT_SAVE
DEFAULT_SERVICE_SAVE = (ROOT / "artifacts/native-vehicle-probe/20261023T172550Z-485cd1fd/service-final.sav")
ENGINE_SOURCE = mutation.ENGINE_SOURCE
ENGINE_FILES = ("src/network/network_admin.cpp", "src/network/network_admin.h")
PAGE_SIZE = 16
SCAN_BUDGET = 64
INVALID_ID = 0xFFFFFFFF


class Experiment(mutation.Experiment):
    probe_kind = "native-train-parts-probe"


def engine_provenance(binary: Path, allow_dirty: bool) -> dict:
    head = subprocess.run(["git", "-C", str(ENGINE_SOURCE), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(ENGINE_SOURCE), "status", "--porcelain"],
                           capture_output=True, text=True, check=True, timeout=10).stdout
    environment.require(allow_dirty or not dirty,
                        "engine checkout must be clean; pass --allow-dirty-engine for local source gate")
    help_result = subprocess.run([str(binary), "-h"], capture_output=True,
                                 text=True, check=True, timeout=10)
    match = re.search(r"OpenTTD\s+(\S+)", help_result.stdout + help_result.stderr)
    marker = "m" if dirty else "g"
    environment.require(match is not None and f"{marker}{head[:10]}" in match.group(1),
                        "binary revision does not match engine checkout state")
    return {"head": head, "clean": not bool(dirty), "revision": match.group(1),
            "source_hashes": {name: base.sha256_file(ENGINE_SOURCE / name) for name in ENGINE_FILES}}


def read_all(admin, world_id: str, company_id: int, remaining) -> tuple[list[dict], list[dict]]:
    records: list[dict] = []
    pages: list[dict] = []
    cursor = INVALID_ID
    previous_frame = None
    for _ in range(64):
        page = admin.copilot_train_parts(world_id, company_id, cursor, PAGE_SIZE,
                                         SCAN_BUDGET, timeout=remaining())
        environment.require(page["company_id"] == company_id and page["after_vehicle_id"] == cursor,
                            "train part page lost its company or cursor")
        if previous_frame is not None:
            environment.require(page["frame"] == previous_frame,
                                "world advanced while train part pages were collected")
        previous_frame = page["frame"]
        records.extend(page["parts"])
        pages.append(page)
        if page["complete"]:
            return records, pages
        environment.require(page["next_after_id"] != cursor,
                            "incomplete train part page did not advance")
        cursor = page["next_after_id"]
    raise base.ProbeError("train part scan exceeded 64 bounded pages")


def validate_chains(parts: list[dict]) -> dict:
    by_id = {part["vehicle_id"]: part for part in parts}
    environment.require(len(by_id) == len(parts), "duplicate vehicle IDs in train part scan")
    roots = [part for part in parts if part["is_primary"]]
    for part in parts:
        environment.require(part["owner"] == 0, "foreign-company train part was returned")
        root = by_id.get(part["first_vehicle_id"])
        environment.require(root is not None and root["is_primary"],
                            "train part does not resolve to a returned primary root")
        if part["previous_vehicle_id"] != INVALID_ID:
            previous = by_id.get(part["previous_vehicle_id"])
            environment.require(previous is not None and previous["next_vehicle_id"] == part["vehicle_id"],
                                "previous/next consist links disagree")
        if part["next_vehicle_id"] != INVALID_ID:
            following = by_id.get(part["next_vehicle_id"])
            environment.require(following is not None and following["previous_vehicle_id"] == part["vehicle_id"],
                                "next/previous consist links disagree")
        seen: set[int] = set()
        current = root
        while current["next_vehicle_id"] != INVALID_ID:
            environment.require(current["vehicle_id"] not in seen, "cycle in consist links")
            seen.add(current["vehicle_id"])
            current = by_id.get(current["next_vehicle_id"])
            environment.require(current is not None and current["first_vehicle_id"] == root["vehicle_id"],
                                "consist chain is incomplete or changes root")
        environment.require(current["vehicle_id"] == part["vehicle_id"] or part["vehicle_id"] in seen,
                            "train part is detached from its root chain")
    return {"primary_count": len(roots), "part_count": len(parts),
            "chains": [{"root_vehicle_id": root["vehicle_id"],
                        "parts": [part["vehicle_id"] for part in parts
                                  if part["first_vehicle_id"] == root["vehicle_id"]]}
                       for root in roots]}


def scan_save(experiment: Experiment, label: str, source: Path, scripts, require_train: bool) -> None:
    source_hash = base.sha256_file(source)
    experiment.start(label, "Copilot Vehicle Probe" if require_train else "Copilot Control Probe",
                     scripts, source)
    before = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    parts, pages = read_all(experiment.admin, before["world_id"], 0, experiment.remaining)
    chain_summary = validate_chains(parts)
    if require_train:
        environment.require(chain_summary["primary_count"] == 1 and chain_summary["part_count"] >= 2,
                            "service save did not return exactly one train with engine/wagon parts")
        environment.require(any(part["is_primary"] for part in parts) and
                            any(not part["is_primary"] for part in parts),
                            "service save did not distinguish primary engine and wagon parts")
    else:
        environment.require(not parts and chain_summary["primary_count"] == 0,
                            "control save unexpectedly has an owned train")
    try:
        experiment.admin.copilot_train_parts("different-world", 0, timeout=experiment.remaining())
    except CopilotBridgeError as exc:
        environment.require(exc.status == 5, "wrong-world rejection was not typed")
    else:
        raise base.ProbeError("wrong-world train parts query was accepted")
    try:
        experiment.admin.copilot_train_parts(before["world_id"], 255,
                                             timeout=experiment.remaining())
    except CopilotBridgeError as exc:
        environment.require(exc.status == 3, "missing-company rejection was not typed")
    else:
        raise base.ProbeError("missing-company train parts query was accepted")
    after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
    environment.require(before["world_id"] == after["world_id"] and
                        before["sequence"] == after["sequence"],
                        "read-only train part query changed world or operation sequence")
    if not require_train:
        environment.require(before["companies"] == after["companies"],
                            "control company state changed during read-only query")
    environment.require(base.sha256_file(source) == source_hash,
                        "original source save changed")
    experiment.check(label + "_train_parts", {
        "before": before, "after": after, "parts": parts, "pages": pages,
        "chain_summary": chain_summary, "source_save": str(source),
        "source_sha256": source_hash,
    })


def run(args: argparse.Namespace) -> int:
    control_source = args.save.expanduser().resolve()
    service_source = args.service_save.expanduser().resolve()
    binary = args.binary.expanduser().resolve()
    for source in (control_source, service_source):
        environment.require(source.is_file() and source.suffix == ".sav",
                            f"source must be an existing .sav file: {source}")
    experiment = Experiment(binary, control_source, args.deadline, 3, base.DEFAULT_SEED)
    experiment.manifest["scope"] = "M2d bounded read-only native train consist-part pages on copied saves"
    experiment.manifest["engine_checkout"] = engine_provenance(binary, args.allow_dirty_engine)
    experiment.manifest["binary_sha256"] = base.sha256_file(binary)
    experiment.manifest["source_hashes"] = {
        name: base.sha256_file(ROOT / name) for name in (
            "tools/admin_transport.py", "tools/run_native_train_parts_probe.py")
    }
    experiment.write()
    failure = None
    try:
        scan_save(experiment, "control-empty", control_source,
                  [(ROOT / "game/copilot_probe", "copilot_probe")], False)
        scan_save(experiment, "service-consist", service_source,
                  [(ROOT / "game/copilot_vehicle", "copilot_vehicle")], True)
        environment.require(not experiment.errors,
                            f"structured engine errors: {experiment.errors}")
    except Exception as exc:
        failure = exc
    return experiment.finish(failure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE)
    parser.add_argument("--service-save", type=Path, default=DEFAULT_SERVICE_SAVE)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/openttd-m2a/openttd")
    parser.add_argument("--deadline", type=float, default=90)
    parser.add_argument("--allow-dirty-engine", action="store_true",
                        help="allow a modified engine checkout for a local source-hashed probe")
    args = parser.parse_args()
    if args.deadline <= 0:
        parser.error("deadline must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
