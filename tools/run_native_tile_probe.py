#!/usr/bin/env python3
"""Verify bounded native tile observations on an isolated copied save."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

from admin_transport import CopilotBridgeError
import run_control_probe as base
import run_environment_probe as environment
import run_native_mutation_probe as mutation


ROOT = base.REPO_ROOT
DEFAULT_SAVE = mutation.DEFAULT_SAVE
ENGINE_SOURCE = mutation.ENGINE_SOURCE
ENGINE_COMMIT = "bf789a968cdf47ac54237a917402821d24e6dff6"
ENGINE_FILES = (
    "src/network/network_admin.cpp",
    "src/network/network_admin.h",
)


class Experiment(mutation.Experiment):
    probe_kind = "native-tile-probe"


def engine_provenance(binary: Path) -> dict:
    head = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "status", "--porcelain"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout
    environment.require(head == ENGINE_COMMIT, "engine checkout differs from the tested tile commit")
    environment.require(not dirty, "engine checkout must be clean")
    help_result = subprocess.run([str(binary), "-h"], capture_output=True,
                                 text=True, check=True, timeout=10)
    environment.require(f"g{head[:10]}" in help_result.stdout + help_result.stderr,
                        "binary revision does not name the clean engine commit")
    return {"head": head, "clean": True, "revision_output":
            (help_result.stdout + help_result.stderr).splitlines()[0],
            "source_hashes": {name: base.sha256_file(ENGINE_SOURCE / name)
                              for name in ENGINE_FILES}}


def run(args: argparse.Namespace) -> int:
    source = args.save.expanduser().resolve()
    binary = args.binary.expanduser().resolve()
    environment.require(source.is_file() and source.suffix == ".sav",
                        "source must be an existing .sav file")
    experiment = Experiment(binary, source, args.deadline, 3, base.DEFAULT_SEED)
    experiment.manifest["scope"] = "M2d read-only tile snapshot seam on copied save"
    experiment.manifest["engine_checkout"] = engine_provenance(binary)
    experiment.manifest["binary_sha256"] = base.sha256_file(binary)
    experiment.manifest["source_hashes"] = {
        name: base.sha256_file(ROOT / name) for name in (
            "tools/admin_transport.py", "tools/run_native_tile_probe.py",
            "tools/run_environment_probe.py", "tools/run_native_mutation_probe.py",
        )
    }
    experiment.write()
    failure = None
    try:
        experiment.start("snapshot", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        before = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        world_id = before["world_id"]
        page = experiment.admin.copilot_tile_snapshot(
            world_id, 8255, 4, timeout=experiment.remaining())
        tiles = page["tiles"]
        environment.require([item["tile"] for item in tiles] == [8255, 8256, 8257, 8258],
                            "tile page is not contiguous")
        environment.require(tiles[1]["valid"] and tiles[1]["tile_type"] == 1 and
                            tiles[1]["owner"] == 0 and tiles[1]["track_bits"] != 0,
                            "known rail piece not observed")
        environment.require(all(item["valid"] and item["tile_type"] == 5 and
                                item["owner"] == 0 for item in tiles[2:]),
                            "known station tiles not observed")
        void = experiment.admin.copilot_tile_snapshot(
            world_id, 127, 2, timeout=experiment.remaining())
        environment.require(void["tiles"][0]["valid"] is False and
                            void["tiles"][0]["tile_type"] == 7,
                            "void-border tile was not marked invalid")
        try:
            experiment.admin.copilot_tile_snapshot("different-world", 8255, 4,
                                                   timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 5, "wrong-world rejection was not typed")
        else:
            raise base.ProbeError("wrong-world tile query was accepted")
        after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(before["sequence"] == after["sequence"] and
                            before["companies"] == after["companies"],
                            "read-only queries changed operation or company state")
        experiment.check("typed_tile_snapshot", {"page": page, "void_page": void,
                                                 "before": before, "after": after,
                                                 "wrong_world_status": 5})
        experiment.start("reload", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        reloaded = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        repeat = experiment.admin.copilot_tile_snapshot(
            reloaded["world_id"], 8255, 4, timeout=experiment.remaining())
        environment.require(reloaded["world_id"] == world_id and repeat["tiles"] == tiles,
                            "saved-world tile snapshot changed after reload")
        environment.require(reloaded["sequence"] == before["sequence"] and
                            reloaded["companies"] == before["companies"],
                            "save reload changed operation or company state")
        experiment.check("snapshot_reload", {"identity": reloaded, "page": repeat})
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
