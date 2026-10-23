#!/usr/bin/env python3
"""Verify bounded native rail catalog pages on an isolated copied save."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess

from admin_transport import CopilotBridgeError
import run_control_probe as base
import run_environment_probe as environment
import run_native_mutation_probe as mutation
from native_rail_catalog import read_rail_catalog


ROOT = base.REPO_ROOT
DEFAULT_SAVE = mutation.DEFAULT_SAVE
ENGINE_SOURCE = mutation.ENGINE_SOURCE
ENGINE_FILES = ("src/network/network_admin.cpp", "src/network/network_admin.h")
PAGE_SIZE = 16
RECORD_FIELDS = {
    "engine_id", "buildable", "railveh_type", "railtypes", "default_cargo",
    "default_capacity", "refit_mask", "purchase_cost", "running_cost",
    "max_speed", "power", "weight", "shorten_factor",
}


class Experiment(mutation.Experiment):
    probe_kind = "native-rail-catalog-probe"


def engine_provenance(binary: Path, allow_dirty: bool) -> dict:
    head = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "status", "--porcelain"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout
    is_dirty = bool(dirty)
    environment.require(allow_dirty or not is_dirty,
                        "engine checkout must be clean; use --allow-dirty-engine only for a local source probe")
    help_result = subprocess.run([str(binary), "-h"], capture_output=True,
                                 text=True, check=True, timeout=10)
    version_text = help_result.stdout + help_result.stderr
    match = re.search(r"OpenTTD\s+(\S+)", version_text)
    revision_prefix = "m" if is_dirty else "g"
    environment.require(match is not None and f"{revision_prefix}{head[:10]}" in match.group(1),
                        "binary revision does not match the engine checkout state")
    return {
        "head": head,
        "clean": not is_dirty,
        "revision": match.group(1),
        "source_hashes": {name: base.sha256_file(ENGINE_SOURCE / name)
                          for name in ENGINE_FILES},
    }


def read_all_catalog(admin, world_id: str, company_id: int, remaining) -> list[dict]:
    engines: list[dict] = []
    start = 0
    while True:
        page = admin.copilot_rail_catalog(
            world_id, company_id, start, PAGE_SIZE, timeout=remaining())
        environment.require(page["start_index"] == start and
                            page["company_id"] == company_id,
                            "catalog page lost its company or offset")
        engines.extend(page["engines"])
        if page["count"] < PAGE_SIZE:
            return engines
        start += page["count"]


def catalog_state(records: list[dict]) -> list[dict]:
    return [{key: item[key] for key in sorted(RECORD_FIELDS)} for item in records]


def run(args: argparse.Namespace) -> int:
    source = args.save.expanduser().resolve()
    binary = args.binary.expanduser().resolve()
    environment.require(source.is_file() and source.suffix == ".sav",
                        "source must be an existing .sav file")
    experiment = Experiment(binary, source, args.deadline, 3, base.DEFAULT_SEED)
    experiment.manifest["scope"] = "M2d bounded read-only native rail catalog on copied save"
    experiment.manifest["engine_checkout"] = engine_provenance(binary, args.allow_dirty_engine)
    experiment.manifest["binary_sha256"] = base.sha256_file(binary)
    experiment.manifest["source_hashes"] = {
        name: base.sha256_file(ROOT / name) for name in (
            "tools/admin_transport.py", "tools/run_native_rail_catalog_probe.py",
            "tools/native_rail_catalog.py",
        )
    }
    experiment.write()
    failure = None
    try:
        experiment.start("catalog", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        before = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        world_id = before["world_id"]
        first_page = experiment.admin.copilot_rail_catalog(
            world_id, 0, 0, PAGE_SIZE, timeout=experiment.remaining())
        environment.require(first_page["count"] > 0, "fixture returned no train engines")
        environment.require(all(set(item) == RECORD_FIELDS for item in first_page["engines"]),
                            "rail catalog record fields are incomplete")
        all_engines = read_all_catalog(experiment.admin, world_id, 0, experiment.remaining)
        collected = read_rail_catalog(experiment.admin, company_id=0)
        environment.require(collected["engines"] == all_engines and
                            collected["company_railtypes"] == first_page["company_railtypes"],
                            "guarded catalog reader disagreed with raw pages")
        ids = [item["engine_id"] for item in all_engines]
        environment.require(ids == sorted(ids) and len(set(ids)) == len(ids),
                            "engine IDs are not unique and ordered")
        environment.require(all(item["railveh_type"] in (0, 1, 2) for item in all_engines),
                            "unknown rail vehicle class returned")
        environment.require(any(item["buildable"] for item in all_engines),
                            "fixture has no buildable rail vehicles")
        environment.require(all(item["default_cargo"] == 255 or
                                item["default_cargo"] < 64 for item in all_engines),
                            "catalog returned an invalid default cargo")
        try:
            experiment.admin.copilot_rail_catalog(
                "different-world", 0, 0, PAGE_SIZE, timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 5, "wrong-world rejection was not typed")
        else:
            raise base.ProbeError("wrong-world catalog query was accepted")
        try:
            experiment.admin.copilot_rail_catalog(
                world_id, 255, 0, PAGE_SIZE, timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 3, "invalid-company rejection was not typed")
        else:
            raise base.ProbeError("invalid-company catalog query was accepted")
        after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(before["sequence"] == after["sequence"] and
                            before["companies"] == after["companies"],
                            "read-only catalog queries changed operation or company state")
        experiment.check("typed_rail_catalog", {
            "first_page": first_page, "engines": all_engines,
            "collected": collected,
            "before": before, "after": after,
            "wrong_world_status": 5, "invalid_company_status": 3,
        })

        experiment.start("reload", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        reloaded = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        repeated = read_all_catalog(experiment.admin, reloaded["world_id"], 0,
                                    experiment.remaining)
        environment.require(reloaded["world_id"] == world_id and
                            catalog_state(repeated) == catalog_state(all_engines),
                            "rail catalog changed after saved-world reload")
        environment.require(reloaded["sequence"] == before["sequence"] and
                            reloaded["companies"] == before["companies"],
                            "save reload changed operation or company state")
        experiment.check("catalog_reload", {"identity": reloaded, "engines": repeated})
        environment.require(not experiment.errors,
                            f"structured engine errors: {experiment.errors}")
    except Exception as exc:
        failure = exc
    return experiment.finish(failure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE)
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
