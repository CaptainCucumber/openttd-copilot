#!/usr/bin/env python3
"""S3a real-engine transport/recovery experiment in disposable OpenTTD profiles."""
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
from lifecycle_journal import Journal
import run_control_probe as base

ROOT = base.REPO_ROOT
SOURCE = ROOT / "game/copilot_lifecycle"


def require(condition, detail):
    if not condition:
        raise base.ProbeError(detail)


def normal_fingerprints():
    profile = Path.home() / "Documents/OpenTTD"
    paths = [profile / "openttd.cfg", *sorted((profile / "save").rglob("*.sav"))]
    return {str(p): {"sha256": base.sha256_file(p), "mtime_ns": p.stat().st_mtime_ns}
            for p in paths if p.is_file()}


class Experiment:
    probe_kind = "lifecycle-probe"
    script_source = SOURCE
    script_name = "Copilot Lifecycle Probe"

    def __init__(self, binary: Path, timeout: float, seed: int):
        self.binary, self.seed = binary, seed
        self.started = time.monotonic()
        self.deadline = self.started + timeout
        self.name, self.profile, self.artifacts = base.create_run(
            ROOT / ".runtime" / self.probe_kind, ROOT / "artifacts" / self.probe_kind)
        self.password = secrets.token_hex(16)
        # A reloaded company's allow-list recognizes the original client key.
        # Reuse one disposable identity throughout this run, never the user's.
        self.client_secret = secrets.token_hex(32)
        self.processes = []
        self.pumps = []
        self.admins = []
        self.secret_files = []
        self.events, self.errors = [], []
        self.server = self.server_pump = self.admin = None
        self.visible_client = False
        self.counter = 0
        self.manifest = {
            "schema": 1, "run": self.name, "status": "running", "seed": seed,
            "engine_source_revision": "14ec60f248547d4d062a1160f0fc26d742319888",
            "source_revision": base.git_revision(ROOT), "checks": {}, "phases": [],
            "before_normal_profile": normal_fingerprints(),
            "limits": {"tiles_per_scan": 32, "rows_per_page": 4, "journal_operations": 32,
                       "json_bytes": 1449, "construction_cap": 10000, "reserve": 10000},
            "scope": "S3a rail-only lifecycle fixture; no vehicle/crash-gap/exactly-once proof",
        }
        self.write()

    def write(self):
        (self.artifacts / "manifest.json").write_text(json.dumps(self.manifest, indent=2, sort_keys=True) + "\n")

    def remaining(self, limit=8):
        remaining = min(limit, self.deadline - time.monotonic())
        require(remaining > 0, "experiment deadline exceeded")
        return remaining

    def check(self, name, evidence=True):
        self.manifest["checks"][name] = evidence
        self.write()
        print(f"PASS {name}", flush=True)

    def launch_process(self, argv, cwd, label, console=False):
        process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE if console else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.processes.append(process)
        pump = base.OutputPump(label, process.stdout, self.artifacts / f"{label}.log", self.events, self.errors)
        pump.start()
        self.pumps.append(pump)
        return process, pump

    def stage(self, profile, port, admin_port=None):
        profile.mkdir()
        (profile / "save").mkdir()
        resources = base.stage_builtin_resources(profile, base.bundle_resources(self.binary))
        archive = base.stage_opengfx(base.find_opengfx_archive(), profile)
        config, private = base.write_config(profile, port, include_game_script=admin_port is not None,
                                            server=admin_port is not None)
        text = config.read_text().replace('"Copilot Control Probe"', '"' + self.script_name + '"')
        if admin_port is not None:
            text = text.replace("server_admin_port = 0", f"server_admin_port = {admin_port}\nallow_insecure_admin_login = true")
            private.write_text(private.read_text() + "\n[server_bind_addresses]\n127.0.0.1 =\n")
            base.stage_game_script(profile, self.script_source)
        secret = profile / "secrets.cfg"
        fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.secret_files.append(secret)
        with os.fdopen(fd, "w") as stream:
            setting = (f"admin_password = {self.password}" if admin_port is not None
                       else f"client_secret_key = {self.client_secret}")
            stream.write(f"[network]\n{setting}\n")
        config.write_text(text)
        return config, {"config_sha256": base.sha256_file(config),
                        "private_config_sha256": base.sha256_file(private),
                        "content_sha256": base.sha256_file(archive), "resources": resources}

    def connect(self):
        admin = AdminClient(self.admin_port, self.password, timeout=self.remaining())
        self.admins.append(admin)
        admin.connect()
        self.admin = admin
        return admin

    def start_world(self, label, save=None, seed=None):
        self.stop_world()
        server_profile, client_profile = self.profile / f"{label}-server", self.profile / f"{label}-client"
        self.port, self.admin_port = base.find_free_port(), base.find_free_port()
        require(self.port != self.admin_port, "ephemeral port collision; rerun fixture")
        config, metadata = self.stage(server_profile, self.port, self.admin_port)
        client_config, client_metadata = self.stage(client_profile, self.port)
        argv = base.build_server_argv(self.binary, config, self.port, seed if seed is not None else self.seed)
        original_hash = None
        if save is not None:
            original_hash = base.sha256_file(save)
            copied = server_profile / "save/loaded-copy.sav"
            shutil.copy2(save, copied)
            argv += ["-g", str(copied)]
        argv += ["-d", "script=4,net=3,misc=1"]
        self.server, self.server_pump = self.launch_process(argv, server_profile, label + "-server", True)
        base.wait_for_port(self.admin_port, time.monotonic() + self.remaining(20))
        listeners = subprocess.run(["/usr/sbin/lsof", "-nP", "-a", "-p", str(self.server.pid), "-iTCP", "-sTCP:LISTEN"],
                                   capture_output=True, text=True, timeout=5, check=True).stdout
        require(f"127.0.0.1:{self.admin_port} (LISTEN)" in listeners, "Admin listener not loopback")
        require(all("127.0.0.1:" in line for line in listeners.splitlines()[1:]), "unexpected non-loopback listener")
        client_argv = base.build_client_argv(self.binary, client_config, self.port, self.visible_client)
        if save is not None:
            client_argv[-1] += "#1"
        self.client, _ = self.launch_process(client_argv, client_profile, label + "-client")
        self.connect()
        stop = time.monotonic() + self.remaining(15)
        while True:
            hello = self.call("hello")
            if hello.get("company") == 0:
                break
            require(time.monotonic() < stop, f"human company was not associated: {hello}")
            time.sleep(0.05)
        if save is not None:
            require(base.sha256_file(save) == original_hash, "source save modified")
        self.manifest["phases"].append({"label": label, "server": metadata, "client": client_metadata,
                                         "argv": argv, "listeners": listeners, "hello": hello,
                                         "loaded_source_sha256": original_hash})
        return hello

    def stop_world(self):
        if self.admin is not None:
            self.admin.close()
            self.admin = None
        for process in self.processes:
            if process.poll() is None:
                base.terminate_process(process)
        for pump in self.pumps:
            pump.join()
        self.server = None

    def call(self, cmd, expect_ok=True, **fields):
        self.counter += 1
        payload = {"v": 1, "rid": f"r{self.counter}", "cmd": cmd, **fields}
        reply = self.admin.request(payload, timeout=self.remaining())
        require(reply.get("ok") is expect_ok, f"unexpected {cmd} reply: {reply}")
        return reply

    def save(self, name):
        target = self.artifacts / f"{name}.sav"
        base.send_console(self.server, f'save "{target.with_suffix("")}"')
        require(base.wait_for_save(self.server_pump, target, time.monotonic() + self.remaining(15)), "save failed")
        self.manifest.setdefault("saves", {})[name] = {"path": str(target), "sha256": base.sha256_file(target)}
        return target

    def snapshot(self, world, start, count):
        scan = uuid.uuid4().hex
        capture = self.call("scan", world=world, scan=scan, start=start, count=count)
        pages = [self.call("page", world=world, scan=scan, index=i) for i in range((count + 3) // 4)]
        again = self.call("page", world=world, scan=scan, index=0)
        require(again["rows"] == pages[0]["rows"], "snapshot page changed")
        rows = [row for page in pages for row in page["rows"]]
        require([row[0] for row in rows] == list(range(start, start + count)), "paging skipped/repeated tiles")
        return rows, {"capture": capture, "pages": pages}

    def run(self):
        self.manifest["binary_sha256"] = base.sha256_file(self.binary)
        sources = [Path(__file__), ROOT / "tools/admin_transport.py", ROOT / "tools/lifecycle_journal.py",
                   ROOT / "tools/run_control_probe.py", SOURCE / "main.nut", SOURCE / "info.nut"]
        self.manifest["source_hashes"] = {str(p.relative_to(ROOT)): base.sha256_file(p) for p in sources}
        hello = self.start_world("initial")
        self.manifest["engine_version"] = base.run_version(self.binary, self.profile / "initial-server/openttd.cfg",
                                                           self.artifacts / "version.log")
        world, session = uuid.uuid4().hex, uuid.uuid4().hex
        initialized = self.call("init", world=world)
        self.call("bind", world=world, session=session)
        ledger = Journal(self.artifacts / "external-journal.json", initialized)
        self.check("human_company", hello)
        self.check("versioned_round_trip", initialized)
        _, paging = self.snapshot(world, 8000, 17)
        self.check("paged_capture", paging)
        invalid = self.admin.request({"v": 99, "rid": "bad-version", "cmd": "hello"})
        require(invalid.get("ok") is False, "unknown version accepted")
        self.check("invalid_version_rejected", invalid)
        baseline = self.save("baseline-seq0")
        candidate = self.call("candidate", world=world)
        fields = {key: candidate[key] for key in ("company", "tile", "track", "rail_type")}
        request = {"v": 1, "rid": "lost-response", "cmd": "build", "world": world, "session": session,
                   "op": uuid.uuid4().hex, "cap": 10000, "expect_seq": 0, **fields}
        rejected = self.call("build", expect_ok=False, **{k: v for k, v in request.items() if k not in ("v", "rid", "cmd", "session")}, session="stale")
        require(self.call("hello")["seq"] == 0, "stale session mutated world")
        self.check("stale_session_rejected", rejected)
        ledger.pending(request)
        self.admin.send_request(request)
        # Deliberately close without consuming any reply. Reconnect and ask status,
        # never resend the construction command to discover whether it executed.
        self.admin.close()
        self.connect()
        stop = time.monotonic() + self.remaining()
        while True:
            recovered = self.call("status", world=world, op=request["op"])
            outcome = recovered.get("outcome", {})
            if outcome.get("state") == "completed":
                break
            require(time.monotonic() < stop, f"lost response unresolved: {recovered}")
            time.sleep(0.05)
        ledger = Journal(self.artifacts / "external-journal.json")
        ledger.complete(request["op"], recovered, outcome)
        rows, readback = self.snapshot(world, fields["tile"], 1)
        require(rows[0][1] == fields["company"] and rows[0][2] & fields["track"], "built rail readback mismatch")
        require(outcome["cost"] == candidate["quote"] > 0, "command cost differs from engine quote")
        require(outcome["loan"] == hello["loan"], "loan changed")
        self.check("lost_reply_reconciled", {"status": recovered, "readback": readback})
        duplicate = self.admin.request({**request, "rid": "repeat"})
        require(duplicate.get("ok") is True and duplicate["seq"] == 1, "duplicate did not resolve to stored outcome")
        require(duplicate["outcome"] == outcome, "duplicate outcome changed")
        conflict = self.admin.request({**request, "rid": "conflict", "cap": 9999})
        require(conflict.get("ok") is False and conflict.get("error") == "id_conflict", "changed operation accepted")
        require(self.call("hello")["cash"] == outcome["cash"], "duplicate/conflict changed cash")
        self.check("duplicate_and_conflict", {"duplicate": duplicate, "conflict": conflict})
        # A second real mutation establishes an unambiguous newer journal position.
        candidate2 = self.call("candidate", world=world)
        request2 = {**request, **{k: candidate2[k] for k in fields}, "rid": "second", "op": uuid.uuid4().hex, "expect_seq": 1}
        ledger.pending(request2)
        second = self.admin.request(request2)
        require(second.get("ok") is True, f"second build failed: {second}")
        ledger.complete(request2["op"], second, second["outcome"])
        self.check("second_build", second)
        candidate3 = self.call("candidate", world=world)
        base.send_console(self.server, "pause")
        stop = time.monotonic() + self.remaining()
        while not (paused := self.call("hello"))["paused"]:
            require(time.monotonic() < stop, "pause not observed")
        pong = self.admin.ping(12345)
        paused_build = self.admin.request({**request2, **{k: candidate3[k] for k in fields}, "rid": "paused-build", "op": "paused-op", "expect_seq": 2})
        require(paused_build.get("ok") is False and paused_build.get("error") == "paused", f"paused build not refused: {paused_build}")
        base.send_console(self.server, "unpause")
        while (unpaused := self.call("hello"))["paused"]:
            require(time.monotonic() < stop, "unpause not observed")
        require(unpaused["seq"] == 2, "paused request executed later")
        self.check("pause_queries_and_mutation_refusal", {"paused": paused, "pong": pong, "refusal": paused_build, "unpaused": unpaused})
        latest = self.save("latest-seq2")
        reloaded = self.start_world("latest-reload", latest)
        require(ledger.classify(reloaded) == "current" and reloaded["session"] is None, "latest reload position/session wrong")
        blocked = self.admin.request({**request, "rid": "old-session"})
        require(blocked.get("ok") is False, "pre-load session still permits commands")
        known = self.call("status", world=world, op=request["op"])
        require(known["outcome"] == outcome, "save lost operation outcome")
        rows, reload_readback = self.snapshot(world, fields["tile"], 1)
        require(rows[0][1] == fields["company"] and rows[0][2] & fields["track"], "reload rail changed")
        fresh_session = uuid.uuid4().hex
        self.call("bind", world=world, session=fresh_session)
        replay = self.admin.request({**request, "rid": "reload-replay", "session": fresh_session})
        require(replay.get("ok") is True and replay.get("duplicate") is True
                and replay.get("outcome") == outcome, "saved operation replay was not deduplicated")
        after_replay = self.call("hello")
        require((after_replay["seq"], after_replay["cash"], after_replay["loan"])
                == (reloaded["seq"], reloaded["cash"], reloaded["loan"]), "reload replay changed company/journal")
        require(self.call("hello")["seq"] == 2, "bind mutated journal")
        self.check("latest_save_reload", {"hello": reloaded, "status": known, "blocked": blocked,
                                          "readback": reload_readback, "replay": replay, "after_replay": after_replay})
        older = self.start_world("older-reload", baseline)
        require(ledger.classify(older) == "older_save", "older save not detected")
        unknown = self.call("status", world=world, op=request["op"])
        require(unknown.get("outcome", {}).get("state") == "unknown", "older save unexpectedly knows later operation")
        rows, older_readback = self.snapshot(world, fields["tile"], 1)
        require(rows[0][1] != fields["company"], "older world contains later rail")
        # No bind and no replay into this older world.
        self.check("older_save_stopped", {"hello": older, "status": unknown, "readback": older_readback})
        changed = self.start_world("changed-world", seed=self.seed + 1)
        require(changed["world"] is None, "new world reused saved identity")
        other = self.call("init", world=uuid.uuid4().hex)
        require(ledger.classify(other) == "changed_world", "changed world not detected")
        mismatch = self.call("status", expect_ok=False, world=world, op=request["op"])
        self.check("changed_world_stopped", {"hello": other, "rejection": mismatch})
        require(not self.errors, f"structured log errors: {self.errors}")

    def finish(self, failure=None):
        self.stop_world()
        # Per-run secret is ephemeral and is never copied into evidence.
        for secret in self.secret_files:
            secret.unlink(missing_ok=True)
        self.manifest["status"] = "failed" if failure else "success"
        if failure:
            self.manifest["failure"] = (f"{type(failure).__name__}: {failure}"
                                        .replace(self.password, "<redacted>")
                                        .replace(self.client_secret, "<redacted>"))
        self.manifest["elapsed_seconds"] = round(time.monotonic() - self.started, 3)
        self.manifest["after_normal_profile"] = normal_fingerprints()
        preserved = self.manifest["before_normal_profile"] == self.manifest["after_normal_profile"]
        self.manifest["normal_profile_unchanged"] = preserved
        if not preserved:
            self.manifest["status"] = "failed"
            self.manifest["failure"] = "normal profile fingerprint changed during experiment"
        self.manifest["secret_files_removed"] = all(not p.exists() for p in self.secret_files)
        self.manifest["transport_events"] = [event for admin in self.admins for event in admin.events]
        self.manifest["log_errors"] = self.errors
        self.write()
        manifest_text = (self.artifacts / "manifest.json").read_text()
        require(all(secret not in manifest_text for secret in (self.password, self.client_secret)),
                "secret leaked into manifest")
        print(f"{self.probe_kind.replace('-', ' ')} {self.manifest['status']}: {self.artifacts}")
        if failure:
            print(self.manifest["failure"], file=sys.stderr)
        return 0 if self.manifest["status"] == "success" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=str(base.DEFAULT_BINARY))
    parser.add_argument("--deadline", type=float, default=120)
    parser.add_argument("--seed", type=int, default=base.DEFAULT_SEED)
    args = parser.parse_args()
    if not math.isfinite(args.deadline) or args.deadline <= 0 or not 0 <= args.seed < 0xFFFFFFFE:
        parser.error("positive finite deadline and seed between 0 and 4294967293 required")
    experiment = Experiment(Path(args.binary).resolve(), args.deadline, args.seed)
    error = None
    try:
        experiment.run()
    except Exception as exc:
        error = exc
    return experiment.finish(error)


if __name__ == "__main__":
    raise SystemExit(main())
