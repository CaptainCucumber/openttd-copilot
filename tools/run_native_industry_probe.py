#!/usr/bin/env python3
"""Verify bounded native industry snapshots on an isolated copied save."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess

from admin_transport import CopilotBridgeError
import run_control_probe as base
import run_environment_probe as environment
import run_native_mutation_probe as mutation
from native_world_snapshot import read_tile_window
from native_industry_catalog import read_industries, require_cargo_pair

ROOT = base.REPO_ROOT
DEFAULT_SAVE = mutation.DEFAULT_SAVE
ENGINE_SOURCE = mutation.ENGINE_SOURCE
ENGINE_FILES = ("src/network/network_admin.cpp", "src/network/network_admin.h")
PAGE_SIZE = 16
DETAIL_PAGE_SIZE = 8


class Experiment(mutation.Experiment):
    probe_kind = "native-industry-probe"


def engine_provenance(binary: Path) -> dict:
    head = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "status", "--porcelain"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout
    environment.require(not dirty, "engine checkout must be clean")
    help_result = subprocess.run([str(binary), "-h"], capture_output=True,
                                 text=True, check=True, timeout=10)
    match = re.search(r"OpenTTD\s+(\S+)", help_result.stdout + help_result.stderr)
    environment.require(match is not None and f"g{head[:10]}" in match.group(1),
                        "binary revision does not name the clean engine checkout")
    return {"head": head, "clean": True, "revision": match.group(1),
            "source_hashes": {name: base.sha256_file(ENGINE_SOURCE / name)
                              for name in ENGINE_FILES}}


def read_all_industries(admin, world_id: str, remaining) -> list[dict]:
    industries: list[dict] = []
    start = 0
    while True:
        page = admin.copilot_industry_snapshot(world_id, start, PAGE_SIZE, timeout=remaining())
        environment.require(page["start_index"] == start, "industry page offset changed")
        industries.extend(page["industries"])
        if page["count"] < PAGE_SIZE:
            return industries
        start += page["count"]


def read_all_industry_details(admin, world_id: str, remaining) -> list[dict]:
    industries: list[dict] = []
    start = 0
    while True:
        page = admin.copilot_industry_details(
            world_id, start, DETAIL_PAGE_SIZE, timeout=remaining())
        environment.require(page["start_index"] == start, "industry detail page offset changed")
        industries.extend(page["industries"])
        if page["count"] < DETAIL_PAGE_SIZE:
            return industries
        start += page["count"]


def run(args: argparse.Namespace) -> int:
    source = args.save.expanduser().resolve()
    binary = args.binary.expanduser().resolve()
    environment.require(source.is_file() and source.suffix == ".sav",
                        "source must be an existing .sav file")
    experiment = Experiment(binary, source, args.deadline, 3, base.DEFAULT_SEED)
    experiment.manifest["scope"] = "M2d read-only industry names, bounds, cargo, and tile window on copied save"
    experiment.manifest["engine_checkout"] = engine_provenance(binary)
    experiment.manifest["binary_sha256"] = base.sha256_file(binary)
    experiment.manifest["source_hashes"] = {
        name: base.sha256_file(ROOT / name) for name in (
            "tools/admin_transport.py", "tools/run_native_industry_probe.py",
            "tools/native_world_snapshot.py", "tools/native_industry_catalog.py",
        )
    }
    experiment.write()
    failure = None
    try:
        experiment.start("snapshot", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        before = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        world_id = before["world_id"]
        page = experiment.admin.copilot_industry_snapshot(
            world_id, 0, PAGE_SIZE, timeout=experiment.remaining())
        environment.require(page["count"] > 0, "fixture returned no industries")
        environment.require(all(set(item) == {
            "industry_id", "industry_type", "tile", "produced_cargo", "accepted_cargo"
        } for item in page["industries"]), "industry record fields are incomplete")
        records = page["industries"]
        environment.require(len({item["industry_id"] for item in records}) == len(records),
                            "duplicate industry IDs in first page")
        environment.require(all(len(item["produced_cargo"]) <= 16 and
                                len(item["accepted_cargo"]) <= 16 for item in records),
                            "cargo lists exceed protocol bounds")
        try:
            experiment.admin.copilot_industry_snapshot(
                "different-world", 0, PAGE_SIZE, timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 5, "wrong-world rejection was not typed")
        else:
            raise base.ProbeError("wrong-world industry query was accepted")
        all_records = read_all_industries(experiment.admin, world_id, experiment.remaining)
        environment.require(len({item["industry_id"] for item in all_records}) == len(all_records),
                            "industry IDs repeat across pages")
        after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(before["sequence"] == after["sequence"] and
                            before["companies"] == after["companies"],
                            "read-only queries changed operation or company state")
        catalog = read_industries(experiment.admin)
        environment.require(catalog["industries"] == all_records,
                            "catalog reader disagreed with raw industry pages")
        details = read_all_industry_details(experiment.admin, world_id, experiment.remaining)
        environment.require(len(details) == len(all_records) and
                            len({item["industry_id"] for item in details}) == len(details),
                            "industry detail IDs were incomplete or repeated")
        basic_by_id = {item["industry_id"]: item for item in all_records}
        for item in details:
            basic = basic_by_id.get(item["industry_id"])
            environment.require(basic is not None and
                                (item["industry_type"], item["tile"],
                                 item["produced_cargo"], item["accepted_cargo"]) ==
                                (basic["industry_type"], basic["tile"],
                                 basic["produced_cargo"], basic["accepted_cargo"]),
                                "industry details disagreed with the existing catalog page")
            x, y = item["tile"] % before["map_width"], item["tile"] // before["map_width"]
            environment.require(bool(item["name"]) and item["location_width"] > 0 and
                                item["location_height"] > 0 and
                                x + item["location_width"] <= before["map_width"] and
                                y + item["location_height"] <= before["map_height"],
                                "industry name or location bounds were invalid")
        try:
            experiment.admin.copilot_industry_details(
                "different-world", 0, DETAIL_PAGE_SIZE, timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 5, "wrong-world industry details rejection was not typed")
        else:
            raise base.ProbeError("wrong-world industry details query was accepted")
        details_after = experiment.admin.copilot_identity(
            company_id=0, timeout=experiment.remaining())
        environment.require(details_after["sequence"] == before["sequence"] and
                            details_after["companies"] == before["companies"],
                            "industry details query changed operation or company state")
        source_industry, destination_industry = require_cargo_pair(
            catalog, source_id=0, destination_id=12, cargo_id=1)
        experiment.check("typed_industry_snapshot", {
            "first_page": page, "industries": all_records, "before": before,
            "after": after, "wrong_world_status": 5,
            "catalog": catalog, "coal_pair": {
                "source": source_industry, "destination": destination_industry,
                "cargo_id": 1,
            },
            "industry_details": details,
            "details_after": details_after,
        })
        window = read_tile_window(experiment.admin, x=62, y=64, width=35, height=2)
        environment.require(window["world_id"] == world_id and
                            window["sequence"] == before["sequence"] and
                            len(window["pages"]) == 4 and
                            [item["tile"] for item in window["rows"][0]] ==
                            list(range(8254, 8289)),
                            "tile window failed to preserve row and page coverage")
        environment.require(window["rows"][0][2]["tile_type"] == 1 and
                            window["rows"][0][3]["tile_type"] == 5,
                            "tile window missed known rail and station tiles")
        experiment.check("tile_window_sweep", window)
        experiment.start("reload", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        reloaded = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        repeated = read_all_industries(experiment.admin, reloaded["world_id"], experiment.remaining)
        repeated_details = read_all_industry_details(
            experiment.admin, reloaded["world_id"], experiment.remaining)
        environment.require(reloaded["world_id"] == world_id and repeated == all_records and
                            repeated_details == details,
                            "industry snapshot changed after saved-world reload")
        environment.require(reloaded["sequence"] == before["sequence"] and
                            reloaded["companies"] == before["companies"],
                            "save reload changed operation or company state")
        experiment.check("snapshot_reload", {"identity": reloaded, "industries": repeated,
                                              "industry_details": repeated_details})
        environment.require(not experiment.errors, f"structured engine errors: {experiment.errors}")
    except Exception as exc:
        failure = exc
    return experiment.finish(failure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/openttd-m2a/openttd")
    parser.add_argument("--deadline", type=float, default=90)
    args = parser.parse_args()
    if args.deadline <= 0:
        parser.error("deadline must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
