#!/usr/bin/env python3
"""Verify bounded native train-order pages on an isolated copied service save."""

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
DEFAULT_SERVICE_SAVE = ROOT / "artifacts/native-vehicle-probe/20261023T172550Z-485cd1fd/service-final.sav"
ENGINE_SOURCE = mutation.ENGINE_SOURCE
ENGINE_FILES = ("src/network/network_admin.cpp", "src/network/network_admin.h")
PAGE_SIZE = 16


class Experiment(mutation.Experiment):
    probe_kind = "native-train-orders-probe"


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


def read_orders(admin, world_id: str, company_id: int, vehicle_id: int, remaining) -> tuple[list[dict], list[dict]]:
    start = 0
    orders: list[dict] = []
    pages: list[dict] = []
    total: int | None = None
    for _ in range(32):
        page = admin.copilot_train_orders(world_id, company_id, vehicle_id,
                                          start, PAGE_SIZE, timeout=remaining())
        environment.require(page["company_id"] == company_id and
                            page["vehicle_id"] == vehicle_id and
                            page["start_index"] == start and page["count"] == len(page["orders"]),
                            "train order page lost its selector or range")
        if total is None:
            total = page["total_orders"]
        environment.require(total == page["total_orders"],
                            "train order count changed while pages were collected")
        orders.extend(page["orders"])
        pages.append({"start_index": start, "count": page["count"], "frame": page["frame"]})
        if start + page["count"] >= total:
            return orders, pages
        environment.require(page["count"] > 0, "incomplete train order page was empty")
        start += page["count"]
    raise base.ProbeError("train order scan exceeded 32 bounded pages")


def run(args: argparse.Namespace) -> int:
    source = args.service_save.expanduser().resolve()
    binary = args.binary.expanduser().resolve()
    environment.require(source.is_file() and source.suffix == ".sav",
                        f"service source must be an existing .sav file: {source}")
    experiment = Experiment(binary, source, args.deadline, 3, base.DEFAULT_SEED)
    experiment.manifest["scope"] = "M2d bounded read-only native train-order pages on a copied service save"
    experiment.manifest["engine_checkout"] = engine_provenance(binary, args.allow_dirty_engine)
    experiment.manifest["binary_sha256"] = base.sha256_file(binary)
    experiment.manifest["source_hashes"] = {
        name: base.sha256_file(ROOT / name) for name in (
            "tools/admin_transport.py", "tools/run_native_train_orders_probe.py")
    }
    experiment.write()
    source_hash = base.sha256_file(source)
    failure = None
    try:
        experiment.start("service-orders", "Copilot Vehicle Probe",
                         [(ROOT / "game/copilot_vehicle", "copilot_vehicle")], source)
        before = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        parts = experiment.admin.copilot_train_parts(before["world_id"], 0,
                                                     timeout=experiment.remaining())
        primaries = [part for part in parts["parts"] if part["is_primary"]]
        environment.require(len(primaries) == 1 and primaries[0]["vehicle_id"] == 2,
                            "service save did not return its expected primary train")
        orders, pages = read_orders(experiment.admin, before["world_id"], 0, 2,
                                    experiment.remaining)
        environment.require(len(orders) == 2 and
                            orders[0]["order_type"] == 1 and orders[0]["destination_id"] == 0 and
                            orders[0]["load_type"] == 2,
                            "source order did not target station 0 with full-load policy")
        environment.require(orders[1]["order_type"] == 1 and
                            orders[1]["destination_id"] == 1 and
                            orders[1]["load_type"] == 4 and orders[1]["unload_type"] == 1,
                            "destination order did not target station 1 with no-load/unload policy")
        try:
            experiment.admin.copilot_train_orders("different-world", 0, 2,
                                                  timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 5, "wrong-world rejection was not typed")
        else:
            raise base.ProbeError("wrong-world train orders query was accepted")
        try:
            experiment.admin.copilot_train_orders(before["world_id"], 255, 2,
                                                  timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 3, "missing-company rejection was not typed")
        else:
            raise base.ProbeError("missing-company train orders query was accepted")
        try:
            experiment.admin.copilot_train_orders(before["world_id"], 0, 123456,
                                                  timeout=experiment.remaining())
        except CopilotBridgeError as exc:
            environment.require(exc.status == 7, "missing-train rejection was not typed")
        else:
            raise base.ProbeError("missing-train orders query was accepted")
        after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(before["world_id"] == after["world_id"] and
                            before["sequence"] == after["sequence"] and
                            before["companies"] == after["companies"],
                            "read-only orders query changed world, sequence, or company state")
        environment.require(base.sha256_file(source) == source_hash,
                            "original service save changed")
        experiment.check("service_train_orders", {
            "before": before, "after": after, "vehicle_id": 2,
            "orders": orders, "pages": pages, "source_save": str(source),
            "source_sha256": source_hash,
        })

        experiment.start("service-orders-reload", "Copilot Vehicle Probe",
                         [(ROOT / "game/copilot_vehicle", "copilot_vehicle")], source)
        reloaded = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        reloaded_orders, reloaded_pages = read_orders(
            experiment.admin, reloaded["world_id"], 0, 2, experiment.remaining)
        environment.require(reloaded["world_id"] == before["world_id"] and
                            reloaded["sequence"] == before["sequence"] and
                            reloaded_orders == orders,
                            "train orders changed across copied-save reload")
        experiment.check("train_orders_reload", {
            "identity": reloaded, "orders": reloaded_orders, "pages": reloaded_pages,
        })
        environment.require(not experiment.errors,
                            f"structured engine errors: {experiment.errors}")
    except Exception as exc:
        failure = exc
    return experiment.finish(failure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
