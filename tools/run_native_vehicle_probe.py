#!/usr/bin/env python3
"""Reproduce the isolated two-cycle service gate with native vehicle events."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import subprocess

import run_control_probe as base
from run_vehicle_probe import VehicleExperiment


ROOT = base.REPO_ROOT
ENGINE_SOURCE = ROOT / "vendor/openttd-copilot-engine"
ENGINE_FILES = (
    "src/network/network_admin.cpp", "src/network/network_admin.h",
    "src/vehicle.cpp", "src/economy.cpp", "src/copilot_observation.cpp",
    "src/copilot_observation.h",
)


class NativeVehicleExperiment(VehicleExperiment):
    probe_kind = "native-vehicle-probe"


def inspect_engine(binary: Path) -> dict:
    head = subprocess.run(["git", "-C", str(ENGINE_SOURCE), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(ENGINE_SOURCE), "status", "--porcelain"],
                           check=True, capture_output=True, text=True, timeout=10).stdout
    if dirty:
        raise base.ProbeError("engine checkout has uncommitted changes")
    version = subprocess.run([str(binary), "-h"], capture_output=True, text=True, timeout=10)
    match = re.search(r"OpenTTD\s+(\S+)", version.stdout + version.stderr)
    if version.returncode != 0 or match is None or f"g{head[:10]}" not in match.group(1):
        raise base.ProbeError("native binary revision differs from clean engine checkout")
    return {"head": head, "clean": True, "revision": match.group(1),
            "source_hashes": {name: base.sha256_file(ENGINE_SOURCE / name) for name in ENGINE_FILES}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/openttd-m2a/openttd")
    parser.add_argument("--deadline", type=float, default=600)
    parser.add_argument("--seed", type=int, default=base.DEFAULT_SEED)
    args = parser.parse_args()
    if not math.isfinite(args.deadline) or args.deadline <= 0 or not 0 <= args.seed < 0xFFFFFFFE:
        parser.error("positive finite deadline and seed between 0 and 4294967293 required")
    binary = args.binary.expanduser().resolve()
    experiment = NativeVehicleExperiment(binary, args.deadline, args.seed,
                                         native_telemetry=True, resource_binary=base.DEFAULT_BINARY)
    experiment.manifest["scope"] = (
        "M2c vehicle-tagged native observation of the isolated stock-script service fixture; "
        "the native bridge does not yet build the complete route"
    )
    failure = None
    try:
        experiment.manifest["engine_checkout"] = inspect_engine(binary)
        experiment.write()
        experiment.run()
    except Exception as exc:
        failure = exc
    return experiment.finish(failure)


if __name__ == "__main__":
    raise SystemExit(main())
