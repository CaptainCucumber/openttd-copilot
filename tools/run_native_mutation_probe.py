#!/usr/bin/env python3
"""Exercise one capped native rail mutation on an isolated copied save."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

from native_mutation_journal import Journal
import run_control_probe as base
import run_environment_probe as environment
import run_native_bridge_probe as native


ROOT = base.REPO_ROOT
DEFAULT_SAVE = ROOT / "artifacts/control-probe/20261021T180450Z-f8fc9132/control-probe-final.sav"
ENGINE_COMMIT = "8b8f3d7bad64fb01fc2a216b35e8070be95f51d8"
ENGINE_SOURCE = ROOT / "vendor/openttd-copilot-engine"
ENGINE_FILES = (
    "src/copilot_cmd.cpp", "src/copilot_cmd.h", "src/network/network_admin.cpp",
    "src/network/network_command.cpp", "src/saveload/copilot_sl.cpp",
)


def inspect_engine(binary: Path) -> dict:
    head = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(ENGINE_SOURCE), "status", "--porcelain"],
        capture_output=True, text=True, check=True, timeout=10).stdout
    environment.require(head == ENGINE_COMMIT, f"engine checkout differs: {head}")
    environment.require(not dirty, "engine checkout has uncommitted changes")
    help_result = subprocess.run(
        [str(binary), "-h"], capture_output=True, text=True, timeout=10)
    environment.require(help_result.returncode == 0, "engine version check failed")
    match = re.search(r"OpenTTD\s+(\S+)", help_result.stdout + help_result.stderr)
    environment.require(match is not None and f"g{ENGINE_COMMIT[:10]}" in match.group(1),
                        "binary revision does not name committed M2b engine")
    return {"head": head, "clean": True, "revision": match.group(1),
            "source_hashes": {name: base.sha256_file(ENGINE_SOURCE / name)
                              for name in ENGINE_FILES}}


class Experiment(environment.Experiment):
    probe_kind = "native-mutation-probe"

    def stage(self, label, selected_script, scripts):
        custom_binary = self.binary
        self.binary = base.DEFAULT_BINARY
        try:
            return super().stage(label, selected_script, scripts)
        finally:
            self.binary = custom_binary


def run(args: argparse.Namespace) -> int:
    source = args.save.expanduser().resolve()
    binary = args.binary.expanduser().resolve()
    if not source.is_file() or source.suffix != ".sav":
        raise base.ProbeError("source must be an existing .sav file")
    experiment = Experiment(binary, source, args.deadline, 3, base.DEFAULT_SEED)
    experiment.manifest["scope"] = "M2b one capped native rail mutation on copied save"
    experiment.manifest["tile"] = args.tile
    experiment.manifest["max_cost"] = args.max_cost
    experiment.manifest["binary_sha256"] = base.sha256_file(binary)
    experiment.manifest["engine_checkout"] = inspect_engine(binary)
    experiment.manifest["source_hashes"] = {
        name: base.sha256_file(ROOT / name) for name in (
            "tools/admin_transport.py", "tools/native_mutation_journal.py",
            "tools/run_native_mutation_probe.py")
    }
    experiment.write()
    failure = None
    try:
        experiment.start("cap-reject", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        capped_identity = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        capped_before = capped_identity["companies"][0]
        capped_operation = uuid.uuid4().int
        capped_hi, capped_lo = capped_operation >> 64, capped_operation & ((1 << 64) - 1)
        capped = experiment.admin.copilot_build_single_rail(
            world_id=capped_identity["world_id"], company_id=0, tile=args.tile,
            rail_type=0, track=1, max_cost=0, expected_sequence=0,
            expected_head_hi=0, expected_head_lo=0, operation_hi=capped_hi,
            operation_lo=capped_lo, payload_hash_hi=1, payload_hash_lo=1,
            timeout=experiment.remaining())
        while capped["state_name"] == "pending":
            time.sleep(0.05)
            capped = experiment.admin.copilot_operation_status(
                world_id=capped_identity["world_id"], operation_hi=capped_hi,
                operation_lo=capped_lo, timeout=experiment.remaining())
        capped_after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(capped["state_name"] == "rejected", "zero cap did not reject")
        environment.require(capped["actual_cost"] == 0 and capped_after["sequence"] == 0,
                            "capped rejection advanced cost or sequence")
        environment.require(not capped["readback"]["has_rail"], "capped rejection built rail")
        environment.require(capped_after["companies"][0]["money"] == capped_before["money"],
                            "capped rejection changed cash")
        environment.require(capped_after["companies"][0]["loan"] == capped_before["loan"],
                            "capped rejection changed loan")
        experiment.check("native_cost_cap_rejection", {
            "before": capped_identity, "outcome": capped, "after": capped_after,
        })

        phase = experiment.start("build", "Copilot Control Probe",
                                 [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        first = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(first["version"] == 2 and first["world_id"],
                            "native protocol or world identity missing")
        company = native.select_human_company(first["companies"], 0)
        before_money, before_loan = company["money"], company["loan"]
        operation = uuid.uuid4().int
        op_hi, op_lo = operation >> 64, operation & ((1 << 64) - 1)
        request = {
            "world_id": first["world_id"], "expect_sequence": first["sequence"],
            "expect_head": first["head"], "operation": {"hi": op_hi, "lo": op_lo},
            "company_id": 0, "tile": args.tile, "rail_type": 0, "track": 1,
            "max_cost": args.max_cost,
        }
        digest = hashlib.blake2b(json.dumps(request, sort_keys=True).encode(), digest_size=16).digest()
        hash_hi = int.from_bytes(digest[:8], "big")
        hash_lo = int.from_bytes(digest[8:], "big")
        journal = Journal.create(experiment.artifacts / "mutation-journal.json", first)
        environment.require(journal.record_pending(request), "operation intent was not recorded")
        kwargs = {
            "world_id": first["world_id"], "company_id": 0, "tile": args.tile,
            "rail_type": 0, "track": 1, "max_cost": args.max_cost,
            "expected_sequence": first["sequence"],
            "expected_head_hi": first["head_hi"], "expected_head_lo": first["head_lo"],
            "operation_hi": op_hi, "operation_lo": op_lo,
            "payload_hash_hi": hash_hi, "payload_hash_lo": hash_lo,
        }
        accepted = experiment.admin.copilot_build_single_rail(**kwargs, timeout=experiment.remaining())
        final = accepted
        while final["state_name"] == "pending":
            time.sleep(0.05)
            final = experiment.admin.copilot_operation_status(
                world_id=first["world_id"], operation_hi=op_hi, operation_lo=op_lo,
                timeout=experiment.remaining())
        after = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        result = journal.reconcile(after, final)
        environment.require(result == "completed", f"rail command ended {result}: {final}")
        environment.require(final["readback"]["has_rail"], "rail readback absent")
        environment.require(final["readback"]["owner"] == 0, "rail owner differs from human company")
        environment.require(final["readback"]["track_bits"] & (1 << 1), "expected track bit absent")
        environment.require(final["actual_cost"] > 0, "no authoritative construction cost")
        environment.require(final["actual_cost"] <= args.max_cost, "construction cap exceeded")
        environment.require(after["companies"][0]["loan"] == before_loan, "loan changed")
        environment.require(before_money - after["companies"][0]["money"] == final["actual_cost"],
                            "cash and command cost differ in isolated fixture")
        duplicate = experiment.admin.copilot_build_single_rail(**kwargs, timeout=experiment.remaining())
        environment.require(duplicate["state_name"] == "completed", "duplicate changed operation state")
        environment.require(duplicate["sequence"] == final["sequence"], "duplicate advanced sequence")
        saved = experiment.save_world("completed-native-mutation")
        experiment.check("native_mutation_completed", {
            "before": first, "accepted": accepted, "final": final, "after": after,
            "duplicate": duplicate, "save": environment.file_fingerprint(saved),
            "phase": phase, "journal": str(journal.path),
        })
        experiment.start("reload", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], saved)
        reloaded = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        replay = experiment.admin.copilot_operation_status(
            world_id=first["world_id"], operation_hi=op_hi, operation_lo=op_lo,
            timeout=experiment.remaining())
        environment.require(reloaded["world_id"] == first["world_id"], "world identity changed on reload")
        environment.require(reloaded["sequence"] == final["sequence"], "journal sequence lost on reload")
        environment.require(replay["state_name"] == "completed", "completed outcome lost on reload")
        environment.require(replay["readback"]["has_rail"], "rail lost on reload")
        environment.require(journal.classify_position(reloaded) == "current", "external journal differs on reload")
        replay_duplicate = experiment.admin.copilot_build_single_rail(
            **kwargs, timeout=experiment.remaining())
        environment.require(replay_duplicate["state_name"] == "completed" and
                            replay_duplicate["money"] == replay["money"],
                            "reload duplicate changed outcome or cash")
        experiment.check("native_mutation_reload", {
            "identity": reloaded, "operation": replay, "duplicate": replay_duplicate})

        experiment.start("older", "Copilot Control Probe",
                         [(ROOT / "game/copilot_probe", "copilot_probe")], source)
        older = experiment.admin.copilot_identity(company_id=0, timeout=experiment.remaining())
        environment.require(journal.classify_position(older) == "older_save",
                            "older save was not classified")
        experiment.check("older_save_detected", {"identity": older,
                         "journal_position": journal.data["position"]})
    except Exception as exc:
        failure = exc
    return experiment.finish(failure)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, default=DEFAULT_SAVE)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/openttd-m2a/openttd")
    parser.add_argument("--tile", type=int, default=8255)
    parser.add_argument("--max-cost", type=int, default=1000)
    parser.add_argument("--deadline", type=float, default=90)
    args = parser.parse_args()
    if args.tile <= 0 or args.max_cost <= 0 or args.deadline <= 0:
        parser.error("tile, max cost, and deadline must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
