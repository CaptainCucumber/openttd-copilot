#!/usr/bin/env python3
"""Bounded M1 existing-save and single-GameScript-slot experiment.

The probe is observational: it never joins a company and never asks either
GameScript to mutate the world. A missing GameScript reply is a recorded,
bounded result; Admin ping must remain responsive afterward.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import uuid

from admin_transport import AdminClient
import run_control_probe as base
import run_lifecycle_probe as lifecycle


ROOT = base.REPO_ROOT
COPILOT_SOURCE = ROOT / "game/copilot_lifecycle"
FOREIGN_SOURCE = ROOT / "game/foreign_environment"


def require(condition, detail):
    if not condition:
        raise base.ProbeError(detail)


def file_fingerprint(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {"sha256": base.sha256_file(path), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def classify_script_reply(admin: AdminClient, timeout: float, label: str) -> dict[str, object]:
    """Return an explicit script identity; timeout is evidence, never an unbounded wait."""
    request = {"v": 1, "rid": f"environment-{label}-{uuid.uuid4().hex[:12]}", "cmd": "hello"}
    started = time.monotonic()
    try:
        reply = admin.request(request, timeout=timeout)
    except TimeoutError:
        return {"identity": "none", "result": "expected_timeout", "timeout_seconds": timeout,
                "elapsed_seconds": round(time.monotonic() - started, 3)}
    identity = "foreign" if reply.get("fixture") == "foreign" else "copilot" if (
        reply.get("v") == 1 and "seq" in reply and "human_found" in reply) else "unknown"
    return {"identity": identity, "result": "response", "reply": reply,
            "elapsed_seconds": round(time.monotonic() - started, 3)}


class Experiment:
    probe_kind = "environment-probe"

    def __init__(self, binary: Path, source_save: Path, deadline: float, response_timeout: float, seed: int):
        self.binary, self.source_save, self.seed = binary, source_save, seed
        self.response_timeout = response_timeout
        self.started = time.monotonic()
        self.deadline = self.started + deadline
        self.name, self.profile, self.artifacts = base.create_run(
            ROOT / ".runtime" / self.probe_kind, ROOT / "artifacts" / self.probe_kind)
        self.password = secrets.token_hex(16)
        self.process = self.pump = self.admin = None
        self.admins: list[AdminClient] = []
        self.secret_files: list[Path] = []
        self.events: list[dict] = []
        self.errors: list[str] = []
        self.source_before = file_fingerprint(source_save)
        self.manifest = {
            "schema": 1, "run": self.name, "status": "running", "seed": seed,
            "source_revision": base.git_revision(ROOT), "checks": {}, "phases": [],
            "source_save": str(source_save), "source_save_before": self.source_before,
            "before_normal_profile": lifecycle.normal_fingerprints(),
            "scope": "M1 non-mutating existing-save attachment and single-GameScript-slot experiment",
            "timeouts": {"experiment_seconds": deadline, "gamescript_response_seconds": response_timeout},
        }
        self.write()

    def write(self):
        (self.artifacts / "manifest.json").write_text(
            json.dumps(self.manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def remaining(self, limit=10.0):
        value = min(limit, self.deadline - time.monotonic())
        require(value > 0, "experiment deadline exceeded")
        return value

    def check(self, name, evidence):
        self.manifest["checks"][name] = evidence
        self.write()
        print(f"PASS {name}", flush=True)

    @staticmethod
    def _stage_script(profile: Path, source: Path, directory: str):
        destination = profile / "game" / directory
        require(not destination.exists(), f"refusing to replace staged script: {destination}")
        shutil.copytree(source, destination, symlinks=False)
        return destination

    def stage(self, label: str, selected_script: str, scripts: list[tuple[Path, str]]):
        profile = self.profile / label
        profile.mkdir()
        (profile / "save").mkdir()
        resources = base.stage_builtin_resources(profile, base.bundle_resources(self.binary))
        archive = base.stage_opengfx(base.find_opengfx_archive(), profile)
        port, admin_port = base.find_free_port(), base.find_free_port()
        require(port != admin_port, "ephemeral port collision; rerun fixture")
        config, private = base.write_config(profile, port, include_game_script=True, server=True)
        text = config.read_text(encoding="utf-8").replace(
            '"Copilot Control Probe"', f'"{selected_script}"')
        text = text.replace("server_admin_port = 0",
                            f"server_admin_port = {admin_port}\nallow_insecure_admin_login = true")
        config.write_text(text, encoding="utf-8")
        private.write_text(private.read_text(encoding="utf-8") +
                           "\n[server_bind_addresses]\n127.0.0.1 =\n", encoding="utf-8")
        staged = [self._stage_script(profile, source, directory) for source, directory in scripts]
        secret = profile / "secrets.cfg"
        fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.secret_files.append(secret)
        with os.fdopen(fd, "w") as stream:
            stream.write(f"[network]\nadmin_password = {self.password}\n")
        return profile, config, port, admin_port, {
            "config_sha256": base.sha256_file(config), "private_config_sha256": base.sha256_file(private),
            "content_sha256": base.sha256_file(archive), "resources": resources,
            "scripts": {path.name: base.sha256_tree(path) for path in staged},
        }

    def stop(self):
        if self.admin is not None:
            self.admin.close()
            self.admin = None
        if self.process is not None:
            base.terminate_process(self.process)
            self.process = None
        if self.pump is not None:
            self.pump.join()
            self.pump = None

    def start(self, label: str, selected_script: str, scripts: list[tuple[Path, str]], save: Path | None):
        self.stop()
        profile, config, port, admin_port, metadata = self.stage(label, selected_script, scripts)
        argv = base.build_server_argv(self.binary, config, port, self.seed)
        copied = None
        if save is not None:
            copied = profile / "save" / "loaded-copy.sav"
            shutil.copy2(save, copied)
            require(file_fingerprint(copied) == file_fingerprint(save), "staged save differs from source")
            argv += ["-g", str(copied)]
            require(str(save) not in argv, "original save path must never be passed to OpenTTD")
        argv += ["-d", "script=4,net=3,misc=1"]
        self.process = subprocess.Popen(argv, cwd=profile, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.pump = base.OutputPump(label, self.process.stdout, self.artifacts / f"{label}.log",
                                    self.events, self.errors)
        self.pump.start()
        base.wait_for_port(admin_port, time.monotonic() + self.remaining(20))
        listeners = subprocess.run(
            ["/usr/sbin/lsof", "-nP", "-a", "-p", str(self.process.pid), "-iTCP", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5, check=True).stdout
        lines = listeners.splitlines()[1:]
        require(lines and all("127.0.0.1:" in line for line in lines), "unexpected non-loopback listener")
        self.admin = AdminClient(admin_port, self.password, timeout=self.remaining()).connect()
        self.admins.append(self.admin)
        pong_value = int(time.monotonic_ns() & 0xFFFFFFFF)
        require(self.admin.ping(pong_value, timeout=self.remaining()) == pong_value, "Admin ping mismatch")
        phase = {"label": label, "selected_script": selected_script, "argv": base.redact_argv(argv),
                 "config": str(config),
                 "listeners": listeners, "initial_ping": pong_value, "staged_save": str(copied) if copied else None,
                 **metadata}
        self.manifest["phases"].append(phase)
        self.write()
        return phase

    def save_world(self, name: str):
        target = self.artifacts / f"{name}.sav"
        base.send_console(self.process, f'save "{target.with_suffix("")}"')
        require(base.wait_for_save(self.pump, target, time.monotonic() + self.remaining(20)), "save failed")
        return target

    def run(self):
        self.manifest["binary_sha256"] = base.sha256_file(self.binary)
        sources = [Path(__file__), ROOT / "tools/admin_transport.py",
                   ROOT / "tools/run_control_probe.py", ROOT / "tools/run_lifecycle_probe.py",
                   COPILOT_SOURCE / "info.nut", COPILOT_SOURCE / "main.nut",
                   FOREIGN_SOURCE / "info.nut", FOREIGN_SOURCE / "main.nut"]
        self.manifest["source_hashes"] = {str(path.relative_to(ROOT)): base.sha256_file(path) for path in sources}

        existing = self.start("existing-copy", "Copilot Lifecycle Probe",
                              [(COPILOT_SOURCE, "copilot_lifecycle")], self.source_save)
        self.manifest["engine_version"] = base.run_version(
            self.binary, Path(existing["config"]), self.artifacts / "version.log")
        attachment = classify_script_reply(self.admin, min(self.response_timeout, self.remaining()), "existing")
        require(attachment["identity"] in {"none", "copilot", "foreign"},
                f"unrecognized GameScript response on existing save: {attachment}")
        pong = int(time.monotonic_ns() & 0xFFFFFFFF)
        require(self.admin.ping(pong, timeout=self.remaining()) == pong, "Admin stopped responding after script probe")
        require(file_fingerprint(self.source_save) == self.source_before, "original save changed during copied load")
        self.check("existing_save_loaded_without_source_mutation", {
            "attachment": attachment, "post_probe_ping": pong, "listeners": existing["listeners"],
            "original": self.source_before, "copy": file_fingerprint(Path(existing["staged_save"])),
            "mutation_requests": 0,
        })

        self.start("foreign-create", "Foreign Environment Fixture",
                   [(FOREIGN_SOURCE, "foreign_environment")], None)
        foreign_new = classify_script_reply(self.admin, min(8.0, self.remaining()), "foreign-new")
        require(foreign_new["identity"] == "foreign", f"foreign fixture did not start: {foreign_new}")
        require(foreign_new["reply"].get("loaded") is False, "fresh foreign fixture reported reload")
        foreign_save = self.save_world("foreign-source")
        foreign_before = file_fingerprint(foreign_save)
        self.check("foreign_world_saved", {"identity": foreign_new, "save": foreign_before})

        coexist = self.start("foreign-reload", "Copilot Lifecycle Probe",
                             [(FOREIGN_SOURCE, "foreign_environment"),
                              (COPILOT_SOURCE, "copilot_lifecycle")], foreign_save)
        resumed = classify_script_reply(self.admin, min(8.0, self.remaining()), "foreign-reload")
        require(resumed["identity"] == "foreign", f"saved foreign script did not retain slot: {resumed}")
        require(resumed["reply"].get("loaded") is True, "foreign script did not report saved-state load")
        require(resumed["reply"].get("marker") == "foreign-environment-v1", "foreign marker changed")
        require(resumed["reply"].get("mutation_count") == 0, "foreign fixture reported mutation")
        require(file_fingerprint(foreign_save) == foreign_before, "generated foreign source save changed")
        self.check("saved_foreign_script_retains_single_slot", {
            "configured_script": coexist["selected_script"], "active_response": resumed,
            "copilot_control_response": False, "staged_scripts": sorted(coexist["scripts"]),
            "mutation_requests": 0,
        })
        require(not self.errors, f"structured log errors: {self.errors}")

    def finish(self, failure=None):
        self.stop()
        for secret in self.secret_files:
            secret.unlink(missing_ok=True)
        source_after = file_fingerprint(self.source_save)
        after_normal = lifecycle.normal_fingerprints()
        self.manifest.update({
            "status": "failed" if failure else "success",
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            "source_save_after": source_after,
            "source_save_unchanged": source_after == self.source_before,
            "after_normal_profile": after_normal,
            "normal_profile_unchanged": after_normal == self.manifest["before_normal_profile"],
            "secret_files_removed": all(not path.exists() for path in self.secret_files),
            "transport_events": [event for admin in self.admins for event in admin.events],
            "log_errors": self.errors,
        })
        if failure:
            self.manifest["failure"] = f"{type(failure).__name__}: {failure}".replace(self.password, "<redacted>")
        if not self.manifest["source_save_unchanged"] or not self.manifest["normal_profile_unchanged"]:
            self.manifest["status"] = "failed"
            self.manifest["failure"] = "source save or normal profile fingerprint changed"
        self.write()
        text = (self.artifacts / "manifest.json").read_text(encoding="utf-8")
        require(self.password not in text, "Admin password leaked into manifest")
        print(f"environment probe {self.manifest['status']}: {self.artifacts}")
        if self.manifest["status"] != "success":
            print(self.manifest.get("failure", "unknown failure"), file=sys.stderr)
            return 2
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", required=True, type=Path, help="existing .sav to copy; the original is never loaded")
    parser.add_argument("--binary", default=str(base.DEFAULT_BINARY))
    parser.add_argument("--deadline", type=float, default=90)
    parser.add_argument("--response-timeout", type=float, default=3)
    parser.add_argument("--seed", type=int, default=base.DEFAULT_SEED)
    args = parser.parse_args()
    source = args.save.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".sav":
        parser.error("--save must name an existing .sav file")
    if (not math.isfinite(args.deadline) or args.deadline <= 0 or
            not math.isfinite(args.response_timeout) or args.response_timeout <= 0 or
            not 0 <= args.seed < 0xFFFFFFFE):
        parser.error("positive finite timeouts and seed between 0 and 4294967293 required")
    experiment = Experiment(Path(args.binary).resolve(), source, args.deadline, args.response_timeout, args.seed)
    error = None
    try:
        experiment.run()
    except Exception as exc:
        error = exc
    return experiment.finish(error)


if __name__ == "__main__":
    raise SystemExit(main())
