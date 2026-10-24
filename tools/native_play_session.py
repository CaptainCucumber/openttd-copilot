"""Isolated native OpenTTD world lifecycle, independent of any GameScript."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import time

import run_control_probe as base
from run_environment_probe import file_fingerprint, require
from run_lifecycle_probe import Experiment
from run_native_train_purchase_probe import engine_provenance

ROOT = base.REPO_ROOT
SERVER_BINARY = ROOT / "build/openttd-m2a/openttd"
CLIENT_BINARY = ROOT / "build/openttd-native-client/openttd"


class NativeSession(Experiment):
    probe_kind = "native-railway"

    def __init__(self, binary=SERVER_BINARY, client_binary=CLIENT_BINARY, *,
                 timeout=900, seed=6, visible=False):
        super().__init__(Path(binary).resolve(), timeout, seed)
        self.client_binary = Path(client_binary).resolve()
        self.visible_client = visible
        self.source_fingerprints = {}
        self.manifest["scope"] = "native existing-business railway; isolated development profile"
        self.manifest["limits"] = {"operations": 64, "cargo": "standard temperate coal",
                                   "terrain": "flat clear unowned land only"}
        self.manifest["binary_sha256"] = base.sha256_file(self.binary)
        self.manifest["client_binary_sha256"] = base.sha256_file(self.client_binary)
        self.manifest["engine"] = engine_provenance(self.binary, allow_dirty=True)
        self.manifest["client_engine"] = engine_provenance(self.client_binary, allow_dirty=True)
        names = ("native_play_session.py", "native_railway.py", "native_route_plan.py",
                 "native_mcp_server.py", "admin_transport.py", "native_mutation_journal.py",
                 "native_world_snapshot.py", "run_native_railway_probe.py", "play_native.py",
                 "run_vehicle_probe.py", "run_native_train_purchase_probe.py",
                 "run_native_train_configuration_probe.py", "run_native_train_orders_probe.py",
                 "run_lifecycle_probe.py", "run_environment_probe.py", "run_control_probe.py")
        self.manifest["source_hashes"] = {
            f"tools/{name}": base.sha256_file(ROOT / "tools" / name) for name in names}
        self.write()

    def stage(self, profile, port, admin_port=None):
        profile.mkdir()
        (profile / "save").mkdir()
        resources = base.stage_builtin_resources(profile, base.bundle_resources(base.DEFAULT_BINARY))
        archive = base.stage_opengfx(base.find_opengfx_archive(), profile)
        config, private = base.write_config(profile, port, include_game_script=False,
                                            server=admin_port is not None)
        text = config.read_text(encoding="utf-8")
        if admin_port is not None:
            text = text.replace("server_admin_port = 0",
                                f"server_admin_port = {admin_port}\nallow_insecure_admin_login = true")
            text = text.replace("[game_creation]\n", "[game_creation]\ntree_placer = 0\n")
            text = text.replace("[difficulty]\n", "[difficulty]\nindustry_density = 4\n")
            private.write_text(private.read_text(encoding="utf-8") +
                               "\n[server_bind_addresses]\n127.0.0.1 =\n", encoding="utf-8")
        config.write_text(text, encoding="utf-8")
        secret = profile / "secrets.cfg"
        fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.secret_files.append(secret)
        with os.fdopen(fd, "w") as stream:
            setting = f"admin_password = {self.password}" if admin_port is not None else (
                f"client_secret_key = {self.client_secret}")
            stream.write(f"[network]\n{setting}\n")
        return config, {"config_sha256": base.sha256_file(config),
                        "private_config_sha256": base.sha256_file(private),
                        "content_sha256": base.sha256_file(archive), "resources": resources,
                        "game_script": None}

    def start_world(self, label, save=None, seed=None):
        self.stop_world()
        self.port, self.admin_port = base.find_free_port(), base.find_free_port()
        require(self.port != self.admin_port, "ephemeral port collision")
        server_profile, client_profile = self.profile / f"{label}-server", self.profile / f"{label}-client"
        config, metadata = self.stage(server_profile, self.port, self.admin_port)
        client_config, client_metadata = self.stage(client_profile, self.port)
        argv = base.build_server_argv(self.binary, config, self.port, self.seed if seed is None else seed)
        if save is not None:
            save = Path(save).resolve()
            self.source_fingerprints.setdefault(str(save), file_fingerprint(save))
            copied = server_profile / "save/loaded-copy.sav"
            shutil.copy2(save, copied)
            require(file_fingerprint(copied) == file_fingerprint(save), "copied save differs")
            argv += ["-g", str(copied)]
        argv += ["-d", "net=3,misc=1"]
        self.server, self.server_pump = self.launch_process(argv, server_profile, label + "-server", True)
        base.wait_for_port(self.admin_port, time.monotonic() + self.remaining(25))
        listeners = subprocess.run(
            ["/usr/sbin/lsof", "-nP", "-a", "-p", str(self.server.pid), "-iTCP", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5, check=True).stdout
        require(listeners.splitlines()[1:] and
                all("127.0.0.1:" in line for line in listeners.splitlines()[1:]),
                "native world listener is not exclusively loopback")
        self.client_config = client_config
        client_argv = base.build_client_argv(self.client_binary, client_config, self.port, self.visible_client)
        if save is not None:
            client_argv[-1] += "#1"
        self.client, _ = self.launch_process(client_argv, client_profile, label + "-client")
        self.connect()
        end = time.monotonic() + self.remaining(25)
        while True:
            identity = self.admin.copilot_identity(timeout=self.remaining())
            if identity["companies"]:
                break
            require(self.client.poll() is None, f"native client exited {self.client.returncode}")
            require(time.monotonic() < end, "human client did not create/join company")
            time.sleep(0.1)
        require(len(identity["companies"]) == 1 and not identity["companies"][0]["is_ai"],
                "initial playable scope requires one human company 0")
        self.manifest["phases"].append({
            "label": label, "server": metadata, "client": client_metadata,
            "argv": base.redact_argv(argv), "client_argv": base.redact_argv(client_argv),
            "listeners": listeners, "identity": identity,
            "source_save": str(save) if save is not None else None,
        })
        self.write()
        return identity

    def finish(self, failure=None):
        self.manifest["source_saves_unchanged"] = all(
            file_fingerprint(Path(path)) == value for path, value in self.source_fingerprints.items())
        if not self.manifest["source_saves_unchanged"] and failure is None:
            failure = base.ProbeError("source save changed")
        return super().finish(failure)
