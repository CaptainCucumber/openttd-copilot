#!/usr/bin/env python3
"""Run the bounded M2a native-bridge read-only gate.

The probe loads only a copied existing save, stages the non-mutating foreign
GameScript, and asks the native bridge for identity twice.  It deliberately
does not send a gameplay mutation or a save command.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import uuid

import run_control_probe as base
import run_environment_probe as environment
from admin_transport import CopilotBridgeError


ROOT = base.REPO_ROOT
FOREIGN_SOURCE = ROOT / "game/foreign_environment"
DEFAULT_BINARY = ROOT / "build/openttd-m2a/openttd"
BRIDGE_PROTOCOL_VERSION = 1
ENGINE_UPSTREAM_REVISION = "14ec60f248547d4d062a1160f0fc26d742319888"
ENGINE_COMMIT = "2850af59a5df2fe32aaff718b8e3dbb01808ecdd"
ENGINE_FILES = (
    "src/network/core/tcp_admin.cpp",
    "src/network/core/tcp_admin.h",
    "src/network/network_admin.cpp",
    "src/network/network_admin.h",
)


def run_engine_revision(binary: Path, config: Path, output: Path) -> str:
    """Require the runtime revision string to name the committed M2a engine."""
    completed = subprocess.run(
        [str(binary), "-X", "-x", "-c", str(config), "-h"],
        cwd=config.parent, capture_output=True, text=True, timeout=10,
    )
    text = completed.stdout + completed.stderr
    output.write_text(text, encoding="utf-8")
    require(completed.returncode == 0,
            f"OpenTTD help/version probe failed with exit code {completed.returncode}")
    match = re.search(r"OpenTTD\s+(\S+)", text)
    require(match is not None, "OpenTTD help/version output did not contain a revision")
    revision = match.group(1)
    require(f"g{ENGINE_COMMIT[:10]}" in revision,
            f"custom engine revision does not name {ENGINE_COMMIT[:10]}: {revision}")
    return revision


def inspect_engine_checkout(source: Path) -> dict:
    """Require and fingerprint the clean engine commit used for the build."""
    head = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=10, check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain"],
        capture_output=True, text=True, timeout=10, check=True,
    ).stdout
    require(head == ENGINE_COMMIT, f"engine checkout is {head}, expected {ENGINE_COMMIT}")
    require(not dirty, "engine checkout has uncommitted changes")
    return {
        "head": head,
        "clean": True,
        "source_hashes": {name: base.sha256_file(source / name) for name in ENGINE_FILES},
    }


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise base.ProbeError(detail)


def _company_id(company: dict) -> int | None:
    value = company.get("company_id", company.get("id"))
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _is_human(company: dict) -> bool:
    if company.get("is_human") is True or company.get("human") is True or company.get("is_ai") is False:
        return True
    return str(company.get("type", company.get("owner", ""))).lower() in {"human", "player"}


def select_human_company(companies: object, requested: int | None = None) -> dict:
    """Select one company deterministically; never resolve by display name."""
    require(isinstance(companies, list), "native identity companies must be a list")
    entries = [item for item in companies if isinstance(item, dict)]
    require(len(entries) == len(companies), "native identity contains a malformed company")
    if requested is not None:
        matches = [item for item in entries if _company_id(item) == requested]
        require(len(matches) == 1, f"requested company id {requested} was not returned exactly once")
        require(_is_human(matches[0]), f"requested company id {requested} is not human-owned")
        return matches[0]
    human = [item for item in entries if _is_human(item)]
    require(len(human) == 1, f"expected exactly one human company, found {len(human)}")
    require(_company_id(human[0]) is not None, "human company has no numeric id")
    return human[0]


def validate_identity(reply: object) -> dict:
    require(isinstance(reply, dict), "native identity response must be an object")
    require(reply.get("version") == BRIDGE_PROTOCOL_VERSION, "native bridge protocol version mismatch")
    require(reply.get("request_kind") in {0, "copilot_identity"},
            "unexpected native bridge request kind")
    require(isinstance(reply.get("request_id"), int) and not isinstance(reply["request_id"], bool),
            "native identity response has no numeric request id")
    for key in ("frame", "seed", "calendar_date", "map_width", "map_height", "landscape"):
        require(key in reply, f"native identity response missing {key}")
    require(isinstance(reply["seed"], int) and not isinstance(reply["seed"], bool),
            "native identity seed must be an integer")
    require(isinstance(reply["map_width"], int) and reply["map_width"] > 0,
            "native identity map width must be positive")
    require(isinstance(reply["map_height"], int) and reply["map_height"] > 0,
            "native identity map height must be positive")
    companies = reply.get("companies")
    require(isinstance(companies, list), "native identity companies must be a list")
    require(all(isinstance(item, dict) and _company_id(item) is not None for item in companies),
            "native identity contains a malformed company")
    return reply


def foreign_running(before: dict, after: dict) -> bool:
    """Require both responses from the saved foreign script to remain benign."""
    for label, reply in (("before", before), ("after", after)):
        require(reply.get("identity") == "foreign", f"foreign script did not answer {label} native query")
        payload = reply.get("reply", {})
        require(payload.get("fixture") == "foreign", f"foreign marker missing {label} native query")
        require(payload.get("marker") == "foreign-environment-v1", "foreign marker changed")
        require(payload.get("loaded") is True, "copied save did not restore foreign GameScript")
        require(payload.get("mutation_count") == 0, "foreign GameScript reported a mutation")
        require(isinstance(payload.get("tick"), int) and not isinstance(payload.get("tick"), bool),
                f"foreign GameScript tick missing {label} native query")
    require(after["reply"]["tick"] > before["reply"]["tick"],
            "foreign GameScript did not advance across native queries")
    return True


class Experiment(environment.Experiment):
    probe_kind = "native-bridge-probe"

    def __init__(self, binary: Path, source_save: Path, deadline: float, response_timeout: float,
                 seed: int, company_id: int | None = None, resource_binary: Path = base.DEFAULT_BINARY,
                 engine_source: Path = ROOT / "vendor/openttd-copilot-engine"):
        super().__init__(binary, source_save, deadline, response_timeout, seed)
        self.company_id = company_id
        self.resource_binary = resource_binary
        self.engine_source = engine_source
        self.manifest.update({
            "schema": 1,
            "scope": "M2a native bridge read-only copied-save attachment with foreign GameScript",
            "bridge_protocol_version": BRIDGE_PROTOCOL_VERSION,
            "requested_company_id": company_id,
            "mutation_requests": 0,
            "fixture_save_commands": 1,
        })
        self.write()

    def stage(self, label: str, selected_script: str, scripts: list[tuple[Path, str]]):
        """Stage data from the installed app while executing the custom binary."""
        custom_binary = self.binary
        self.binary = self.resource_binary
        try:
            return super().stage(label, selected_script, scripts)
        finally:
            self.binary = custom_binary

    def run(self):
        require(self.binary.name == "openttd", "native probe binary must be an openttd executable")
        sources = [Path(__file__), ROOT / "tools/admin_transport.py", ROOT / "tools/run_control_probe.py",
                   ROOT / "tools/run_environment_probe.py", FOREIGN_SOURCE / "info.nut",
                   FOREIGN_SOURCE / "main.nut"]
        self.manifest["source_hashes"] = {
            str(path.relative_to(ROOT)): base.sha256_file(path) for path in sources
        }
        self.manifest.update({
            "binary": str(self.binary),
            "binary_sha256": base.sha256_file(self.binary),
            "resource_binary": str(self.resource_binary),
            "resource_binary_sha256": base.sha256_file(self.resource_binary),
            "engine_upstream_revision": ENGINE_UPSTREAM_REVISION,
            "engine_commit": ENGINE_COMMIT,
            "engine_checkout": inspect_engine_checkout(self.engine_source),
            "platform": sys.platform,
            "machine": platform.machine(),
        })
        phase = self.start("existing-copy", "Foreign Environment Fixture",
                           [(FOREIGN_SOURCE, "foreign_environment")], self.source_save)
        self.manifest["engine_version"] = "15.3"
        self.manifest["engine_revision_string"] = run_engine_revision(
            self.binary, Path(phase["config"]), self.artifacts / "version.log")
        try:
            self.admin.copilot_identity(
                company_id=255, protocol_version=BRIDGE_PROTOCOL_VERSION + 1,
                request_id=int(uuid.uuid4().int & 0xFFFFFFFF), timeout=self.remaining())
        except CopilotBridgeError as exc:
            require(exc.status == 1, f"unexpected version-negotiation status {exc.status}")
        else:
            raise base.ProbeError("native bridge accepted an unsupported protocol version")
        first = validate_identity(self.admin.copilot_identity(
            company_id=255, protocol_version=BRIDGE_PROTOCOL_VERSION,
            request_id=int(uuid.uuid4().int & 0xFFFFFFFF), timeout=self.remaining()))
        selected = select_human_company(first["companies"], self.company_id)
        second = validate_identity(self.admin.copilot_identity(
            company_id=_company_id(selected), protocol_version=BRIDGE_PROTOCOL_VERSION,
            request_id=int(uuid.uuid4().int & 0xFFFFFFFF), timeout=self.remaining()))
        require(first["seed"] == second["seed"], "world seed changed between native identity queries")
        require(first["map_width"] == second["map_width"] and first["map_height"] == second["map_height"],
                "world dimensions changed between native identity queries")
        require(first["landscape"] == second["landscape"], "landscape changed between native identity queries")
        selected_again = select_human_company(second["companies"], _company_id(selected))
        require(_company_id(selected) == _company_id(selected_again), "human company identity changed")
        pong = int(time.monotonic_ns() & 0xFFFFFFFF)
        require(self.admin.ping(pong, timeout=self.remaining()) == pong,
                "Admin stopped responding after native identity queries")
        self.check("read_only_identity_on_copied_save", {
            "first_identity": first, "second_identity": second,
            "selected_company": selected, "post_probe_ping": pong,
            "staged_save": phase["staged_save"], "listeners": phase["listeners"],
            "unsupported_version_rejected": True, "mutation_requests": 0,
        })

        self.start("foreign-create", "Foreign Environment Fixture",
                   [(FOREIGN_SOURCE, "foreign_environment")], None)
        created = environment.classify_script_reply(
            self.admin, min(self.response_timeout, self.remaining()), "foreign-create")
        require(created.get("identity") == "foreign", "foreign fixture did not start")
        require(created.get("reply", {}).get("loaded") is False,
                "new foreign fixture unexpectedly reported loaded state")
        foreign_save = self.save_world("foreign-source")
        foreign_before = environment.file_fingerprint(foreign_save)

        coexist = self.start("foreign-reload", "Foreign Environment Fixture",
                             [(FOREIGN_SOURCE, "foreign_environment")], foreign_save)
        before = environment.classify_script_reply(
            self.admin, min(self.response_timeout, self.remaining()), "foreign-before-identity")
        foreign_first = validate_identity(self.admin.copilot_identity(
            company_id=255, protocol_version=BRIDGE_PROTOCOL_VERSION,
            request_id=int(uuid.uuid4().int & 0xFFFFFFFF), timeout=self.remaining()))
        foreign_second = validate_identity(self.admin.copilot_identity(
            company_id=255, protocol_version=BRIDGE_PROTOCOL_VERSION,
            request_id=int(uuid.uuid4().int & 0xFFFFFFFF), timeout=self.remaining()))
        after = environment.classify_script_reply(
            self.admin, min(self.response_timeout, self.remaining()), "foreign-after-identity")
        foreign_running(before, after)
        require(foreign_first["seed"] == foreign_second["seed"],
                "foreign world seed changed between native identity queries")
        require(environment.file_fingerprint(foreign_save) == foreign_before,
                "generated foreign source save changed")
        pong = int(time.monotonic_ns() & 0xFFFFFFFF)
        require(self.admin.ping(pong, timeout=self.remaining()) == pong,
                "Admin stopped responding after foreign coexistence queries")
        self.check("native_bridge_coexists_with_saved_foreign_gamescript", {
            "before_foreign": before, "after_foreign": after,
            "first_identity": foreign_first, "second_identity": foreign_second,
            "post_probe_ping": pong, "staged_save": coexist["staged_save"],
            "listeners": coexist["listeners"], "mutation_requests": 0,
        })
        require(not self.errors, f"structured log errors: {self.errors}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", required=True, type=Path,
                        help="existing .sav to copy; the original is never loaded")
    parser.add_argument("--binary", default=str(DEFAULT_BINARY))
    parser.add_argument("--resource-binary", default=str(base.DEFAULT_BINARY),
                        help="installed OpenTTD app binary whose adjacent resources are staged")
    parser.add_argument("--engine-source", default=str(ROOT / "vendor/openttd-copilot-engine"),
                        help="clean committed engine checkout used to build --binary")
    parser.add_argument("--company-id", type=int, default=None)
    parser.add_argument("--deadline", type=float, default=90)
    parser.add_argument("--response-timeout", type=float, default=3)
    parser.add_argument("--seed", type=int, default=base.DEFAULT_SEED)
    args = parser.parse_args()
    source = args.save.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".sav":
        parser.error("--save must name an existing .sav file")
    if (not math.isfinite(args.deadline) or args.deadline <= 0 or
            not math.isfinite(args.response_timeout) or args.response_timeout <= 0 or
            not 0 <= args.seed < 0xFFFFFFFE or
            (args.company_id is not None and not 0 <= args.company_id < 255)):
        parser.error("positive finite timeouts and seed between 0 and 4294967293 required")
    experiment = Experiment(Path(args.binary).expanduser().resolve(), source, args.deadline,
                            args.response_timeout, args.seed, args.company_id,
                            Path(args.resource_binary).expanduser().resolve(),
                            Path(args.engine_source).expanduser().resolve())
    error = None
    try:
        experiment.run()
    except Exception as exc:
        error = exc
    return experiment.finish(error)


if __name__ == "__main__":
    raise SystemExit(main())
