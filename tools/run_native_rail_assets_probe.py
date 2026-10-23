#!/usr/bin/env python3
"""Verify bounded native rail station/depot asset pages on a copied save."""

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
DEFAULT_SERVICE_SAVE = (ROOT / "artifacts/vehicle-probe/20261022T181426Z-4ac68dab/service-final.sav")
ENGINE_SOURCE = mutation.ENGINE_SOURCE
ENGINE_FILES = ("src/network/network_admin.cpp", "src/network/network_admin.h")
PAGE_SIZE = 16


class Experiment(mutation.Experiment):
    probe_kind = "native-rail-assets-probe"


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


def read_all(admin, world_id: str, company_id: int, asset_kind: int, remaining) -> list[dict]:
    records: list[dict] = []
    start = 0
    key = "stations" if asset_kind == 0 else "depots"
    while True:
        page = admin.copilot_rail_assets(world_id, company_id, asset_kind, start,
                                        PAGE_SIZE, timeout=remaining())
        environment.require(page["start_index"] == start and
                            page["company_id"] == company_id and page["asset_kind"] == asset_kind,
                            "rail asset page lost its selector or offset")
        records.extend(page[key])
        if page["count"] < PAGE_SIZE:
            return records
        start += page["count"]


def record_state(stations: list[dict], depots: list[dict]) -> tuple[list[dict], list[dict]]:
    return ([dict(item) for item in stations], [dict(item) for item in depots])


def run(args: argparse.Namespace) -> int:
    source = args.save.expanduser().resolve()
    binary = args.binary.expanduser().resolve()
    environment.require(source.is_file() and source.suffix == ".sav", "source must be an existing .sav file")
    experiment = Experiment(binary, source, args.deadline, 3, base.DEFAULT_SEED)
    experiment.manifest["scope"] = "M2d bounded read-only native rail station/depot asset pages on copied save"
    experiment.manifest["engine_checkout"] = engine_provenance(binary, args.allow_dirty_engine)
    experiment.manifest["binary_sha256"] = base.sha256_file(binary)
    experiment.manifest["source_hashes"] = {
        name: base.sha256_file(ROOT / name) for name in (
            "tools/admin_transport.py", "tools/run_native_rail_assets_probe.py")
    }
    experiment.write()
    failure = None
    try:
        experiment.start("assets", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        before = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        world_id = before["world_id"]
        stations = read_all(experiment.admin, world_id, 0, 0, experiment.remaining)
        depots = read_all(experiment.admin, world_id, 0, 1, experiment.remaining)
        environment.require(all(set(item) == {"station_id", "base_tile", "platform_tile",
                                               "platform_width", "platform_height", "acceptance_mask"}
                                for item in stations), "station asset fields are incomplete")
        environment.require(all(set(item) == {"depot_id", "tile", "direction", "rail_type"}
                                for item in depots), "depot asset fields are incomplete")
        environment.require(len({item["station_id"] for item in stations}) == len(stations),
                            "duplicate station IDs")
        environment.require(len({item["depot_id"] for item in depots}) == len(depots),
                            "duplicate depot IDs")
        environment.require(len(stations) == 1 and stations[0]["station_id"] == 0 and
                            stations[0]["base_tile"] == 8257 and
                            stations[0]["platform_tile"] == 8257 and
                            stations[0]["platform_width"] == 2 and
                            stations[0]["platform_height"] == 1,
                            "known copied-save station 0 geometry did not match")
        environment.require(not depots, "copied control save unexpectedly has an owned rail depot")
        environment.require(all(item["platform_tile"] != 0xFFFFFFFF and
                                item["platform_width"] > 0 and item["platform_height"] > 0
                                for item in stations), "invalid train platform geometry")
        environment.require(all(item["direction"] in range(4) and item["rail_type"] < 64
                                for item in depots), "invalid depot geometry or rail type")
        try:
            experiment.admin.copilot_rail_assets("different-world", 0, 0, 0, PAGE_SIZE,
                                                 timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 5, "wrong-world rejection was not typed")
        else:
            raise base.ProbeError("wrong-world rail assets query was accepted")
        try:
            experiment.admin.copilot_rail_assets(world_id, 255, 0, 0, PAGE_SIZE,
                                                 timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 3, "missing-company rejection was not typed")
        else:
            raise base.ProbeError("missing-company rail assets query was accepted")
        ai_ids = [item["id"] for item in before["companies"] if item["is_ai"]]
        nonhuman_status = None
        if ai_ids:
            try:
                experiment.admin.copilot_rail_assets(world_id, ai_ids[0], 0, 0, PAGE_SIZE,
                                                     timeout=experiment.remaining())
            except CopilotBridgeError as exc:
                environment.require(exc.status == 6, "nonhuman-company rejection was not typed")
                nonhuman_status = exc.status
            else:
                raise base.ProbeError("nonhuman rail assets query was accepted")
        after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(before["sequence"] == after["sequence"] and
                            before["companies"] == after["companies"],
                            "read-only asset queries changed operation or company state")
        experiment.check("typed_rail_assets", {
            "stations": stations, "depots": depots, "before": before, "after": after,
            "wrong_world_status": 5, "missing_company_status": 3,
            "ai_company_ids": ai_ids, "nonhuman_status": nonhuman_status,
        })

        experiment.start("reload", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        reloaded = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        repeated_stations = read_all(experiment.admin, reloaded["world_id"], 0, 0, experiment.remaining)
        repeated_depots = read_all(experiment.admin, reloaded["world_id"], 0, 1, experiment.remaining)
        environment.require(reloaded["world_id"] == world_id and
                            record_state(repeated_stations, repeated_depots) == record_state(stations, depots),
                            "rail assets changed after copied-save reload")
        environment.require(reloaded["sequence"] == before["sequence"] and
                            reloaded["companies"] == before["companies"],
                            "save reload changed operation or company state")
        experiment.check("asset_reload", {"identity": reloaded, "stations": repeated_stations,
                                           "depots": repeated_depots})
        if args.service_save is not None:
            service_source = args.service_save.expanduser().resolve()
            environment.require(service_source.is_file() and service_source.suffix == ".sav",
                                "service source must be an existing .sav file")
            service_hash = base.sha256_file(service_source)
            experiment.start("service-assets", "Copilot Vehicle Probe",
                             [(ROOT / "game/copilot_vehicle", "copilot_vehicle")], service_source)
            service_before = experiment.admin.copilot_identity(company_id=0,
                                                                timeout=experiment.remaining())
            service_world = service_before["world_id"]
            service_stations = read_all(experiment.admin, service_world, 0, 0,
                                        experiment.remaining)
            service_depots = read_all(experiment.admin, service_world, 0, 1,
                                      experiment.remaining)
            environment.require({item["station_id"] for item in service_stations} >= {0, 1},
                                "service save lacks both rail stations")
            environment.require(any(item["tile"] == 3092 for item in service_depots),
                                "service save depot at tile 3092 was not observed")
            destination = next(item for item in service_stations if item["station_id"] == 1)
            environment.require(destination["acceptance_mask"] & (1 << 1),
                                "service destination did not report coal acceptance")
            service_after = experiment.admin.copilot_identity(company_id=0,
                                                               timeout=experiment.remaining())
            environment.require(service_before["world_id"] == service_after["world_id"] and
                                service_before["sequence"] == service_after["sequence"],
                                "read-only service asset query changed world or operation sequence")
            environment.require(base.sha256_file(service_source) == service_hash,
                                "original service save changed")
            experiment.check("service_asset_geometry", {
                "before": service_before, "after": service_after,
                "stations": service_stations, "depots": service_depots,
                "source_save": str(service_source), "source_sha256": service_hash,
            })
        environment.require(not experiment.errors, f"structured engine errors: {experiment.errors}")
    except Exception as exc:
        failure = exc
    return experiment.finish(failure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/openttd-m2a/openttd")
    parser.add_argument("--deadline", type=float, default=90)
    parser.add_argument("--service-save", type=Path, default=DEFAULT_SERVICE_SAVE,
                        help="optional copied service save with two rail stations and depot")
    parser.add_argument("--allow-dirty-engine", action="store_true",
                        help="allow a modified engine checkout for a local source-hashed gate")
    args = parser.parse_args()
    if args.deadline <= 0:
        parser.error("deadline must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
