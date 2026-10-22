#!/usr/bin/env python3
"""Run the disposable OpenTTD control probe.

This is deliberately a small standard-library harness.  It owns the disposable
profile and evidence bundle; the GameScript owns the actual S2 observations and
commands.  The server prints one-line records prefixed with ``COPILOT_EVENT ``:

    {"protocol": 1, "kind": "human_company", ...}
    {"protocol": 1, "kind": "probe_complete", ...}
    {"protocol": 1, "kind": "probe_failed", "detail": "..."}

The harness never treats ordinary log text as evidence.  A successful run must
receive a ``probe_complete`` record and create the requested final save.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = Path(__file__).resolve()
DEFAULT_BINARY = Path("/Applications/OpenTTD.app/Contents/MacOS/openttd")
DEFAULT_SEED = 20261021
DEFAULT_DEADLINE = 90.0
EVENT_PREFIX = "COPILOT_EVENT "
SCRIPT_DEBUG_PREFIX = re.compile(
    r"^\[[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\] dbg: \[script:[0-9]+\] \[[^\]]+\] \[I\] COPILOT_EVENT (.+)$"
)
RUN_NAME_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")


class ProbeError(RuntimeError):
    """A bounded, user-actionable probe failure."""


def utc_run_name(now: time.struct_time | None = None) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", now or time.gmtime())
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(root: Path) -> str:
    """Hash relative names and bytes without following directory symlinks."""
    digest = hashlib.sha256()
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def sha256_paths(paths: Sequence[Path], base: Path | None = None) -> str:
    """Hash named source files and bytes, making the manifest reproducible."""
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda value: str(value)):
        relative = path.relative_to(base).as_posix() if base else str(path)
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def git_revision(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def parse_event_line(line: str) -> dict[str, Any] | None:
    """Parse one machine-readable GameScript event, ignoring normal logs."""
    if line.startswith(EVENT_PREFIX):
        payload = line[len(EVENT_PREFIX) :].strip()
    else:
        match = SCRIPT_DEBUG_PREFIX.match(line)
        if match is None:
            return None
        payload = match.group(1).strip()
    if not payload:
        return None
    try:
        event = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"malformed {EVENT_PREFIX.strip()} line: {exc}") from exc
    if not isinstance(event, dict) or not isinstance(event.get("kind"), str):
        raise ProbeError("GameScript event must be an object with a string 'kind'")
    if type(event.get("protocol")) is not int or event["protocol"] != 1:
        raise ProbeError("GameScript event protocol must be integer 1")
    return event


REQUIRED_CHECKS = {
    "human_company_associated", "coal_producer_and_acceptor", "dry_run_unchanged",
    "spend_cap", "cash_reserve", "loan_unchanged", "rail_readback", "station_readback",
    "rejection_no_mutation",
}


def validate_success_events(events: Sequence[dict[str, Any]], parse_errors: Sequence[str] = ()) -> dict[str, Any]:
    """Require the protocol and every independently reported S2 invariant."""
    if parse_errors or any(event.get("kind") == "probe_failed" for event in events):
        raise ProbeError("probe output contained parse errors or probe_failed")
    completes = [event for event in events if event.get("kind") == "probe_complete"]
    if not completes:
        raise ProbeError("probe_complete event is missing")
    complete = completes[-1]
    if type(complete.get("protocol")) is not int or complete["protocol"] != 1:
        raise ProbeError("probe_complete protocol is not 1")
    checks = complete.get("checks")
    if not isinstance(checks, dict):
        raise ProbeError("probe_complete lacks checks object")
    if set(checks) != REQUIRED_CHECKS or any(checks.get(key) is not True for key in REQUIRED_CHECKS):
        raise ProbeError("probe_complete checks did not prove every required S2 invariant")
    return complete


def find_opengfx_archive(explicit: Path | None = None) -> Path:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if not candidate.is_file():
            raise ProbeError(f"OpenGFX2 Classic archive does not exist: {candidate}")
        return candidate

    home = Path.home()
    roots = [
        home / "Documents" / "OpenTTD",
        home / "Library" / "Application Support" / "OpenTTD",
        home / "Library" / "Containers" / "org.openttd.openttd" / "Data" / "Documents" / "OpenTTD",
    ]
    matches: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            name = path.name.lower()
            if "opengfx2" in name and "classic" in name and path.suffix.lower() in {".tar", ".gz", ".bz2", ".xz"}:
                matches.append(path)
    if not matches:
        searched = ", ".join(str(root) for root in roots)
        raise ProbeError(f"OpenGFX2 Classic archive not found; searched: {searched}")
    return sorted(matches, key=lambda path: ("content_download" not in path.parts, str(path)))[0].resolve()


def stage_opengfx(archive: Path, profile: Path) -> Path:
    baseset = profile / "baseset"
    baseset.mkdir(parents=True, exist_ok=True)
    destination = baseset / archive.name
    if destination.exists():
        raise ProbeError(f"refusing to replace existing staged content: {destination}")
    shutil.copy2(archive, destination)
    if sha256_file(archive) != sha256_file(destination):
        raise ProbeError("copied OpenGFX2 Classic archive hash differs from source")
    return destination


def bundle_resources(binary: Path) -> Path:
    """Locate the installed app resources needed when ``-X`` excludes the bundle."""
    candidates = [binary.parent.parent / "Resources", binary.parent / "Resources"]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise ProbeError("OpenTTD application Resources directory is missing beside the binary")


def _selected_files(root: Path, predicate: Any) -> list[Path]:
    if not root.is_dir():
        raise ProbeError(f"bundled resource directory is missing: {root}")
    selected: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ProbeError(f"refusing symlink in bundled resources: {path}")
        if path.is_file() and predicate(path):
            selected.append(path)
    return selected


def _hash_selected(root: Path, files: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def stage_builtin_resources(profile: Path, resources: Path) -> dict[str, Any]:
    """Copy bundle data into a profile without retaining bundle symlinks."""
    selections = {
        "lang": (resources / "lang", lambda path: True),
        "baseset": (resources / "baseset", lambda path: True),
        "game_compat": (resources / "game", lambda path: path.name.startswith("compat_") and path.suffix == ".nut"),
    }
    metadata: dict[str, Any] = {"source": str(resources), "source_sha256": {}, "staged_sha256": {}, "file_counts": {}}
    for name, (source_root, predicate) in selections.items():
        source_files = _selected_files(source_root, predicate)
        if not source_files:
            raise ProbeError(f"no bundled {name} files found under {source_root}")
        destination_root = profile / ("game" if name == "game_compat" else name)
        destination_root.mkdir(parents=True, exist_ok=False)
        for source in source_files:
            relative = source.relative_to(source_root)
            destination = destination_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise ProbeError(f"refusing to replace existing staged content: {destination}")
            shutil.copy2(source, destination)
        staged_files = [destination_root / source.relative_to(source_root) for source in source_files]
        metadata["source_sha256"][name] = _hash_selected(source_root, source_files)
        metadata["staged_sha256"][name] = _hash_selected(destination_root, staged_files)
        metadata["file_counts"][name] = len(source_files)
    return metadata


def stage_game_script(profile: Path, source: Path | None = None) -> Path:
    source = (source or REPO_ROOT / "game" / "copilot_probe").resolve()
    if not source.is_dir():
        raise ProbeError(f"GameScript fixture directory is missing: {source}")
    required = (source / "info.nut", source / "main.nut")
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ProbeError("GameScript fixture is missing: " + ", ".join(missing))
    destination = profile / "game" / "copilot_probe"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ProbeError(f"refusing to replace existing staged GameScript: {destination}")
    shutil.copytree(source, destination, symlinks=False)
    return destination


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def config_text(port: int, include_game_script: bool = True) -> str:
    # These are 15.3 setting names.  generation_seed is intentionally passed
    # with -G because the source marks game_creation.generation_seed NotInConfig.
    return ("""# Disposable OpenTTD Copilot control probe; generated, never hand-edited.
[version]
version_string = 15.3
ini_version = 7

[misc]
language = english.lng
sounddriver = null
musicdriver = null
videodriver = null

[network]
server_port = {port}
server_admin_port = 0
server_game_type = local
pause_on_join = false

[game_creation]
landscape = temperate
map_x = 7
map_y = 7
starting_year = 1950
amount_of_rivers = 0

[difficulty]
terrain_type = 0
quantity_sea_lakes = 0
max_no_competitors = 0

[economy]
inflation = false

[gui]
autosave_interval = 0
autosave_on_exit = false
autosave_on_network_disconnect = false

""".format(port=port) + ("\n[game_scripts]\n\"Copilot Control Probe\" =\n" if include_game_script else ""))


def private_config_text(server: bool = False) -> str:
    """Private settings live beside an explicit -c config in the cwd."""
    return """# Disposable OpenTTD Copilot control probe private settings.
[network]
{client}server_name = Copilot Probe Server
""".format(client="" if server else "client_name = Copilot Probe Human\n")


def write_config(profile: Path, port: int, include_game_script: bool = True, server: bool = False) -> tuple[Path, Path]:
    config = profile / "openttd.cfg"
    private = profile / "private.cfg"
    config.write_text(config_text(port, include_game_script), encoding="utf-8")
    private.write_text(private_config_text(server), encoding="utf-8")
    return config, private


def redact_argv(argv: Sequence[str]) -> list[str]:
    """Return argv suitable for a manifest; no passwords are accepted here."""
    output = list(argv)
    for index, value in enumerate(output[:-1]):
        if value in {"-p", "--password"}:
            output[index + 1] = "<redacted>"
    return output


def build_server_argv(binary: Path, config: Path, port: int, seed: int = DEFAULT_SEED) -> list[str]:
    return [str(binary), "-X", "-x", "-c", str(config), "-G", str(seed), "-D", f"127.0.0.1:{port}"]


def build_client_argv(binary: Path, config: Path, port: int, visible: bool = False) -> list[str]:
    video = "cocoa" if visible else "null:ticks=100000000"
    return [
        str(binary),
        "-X",
        "-x",
        "-c",
        str(config),
        "-v",
        video,
        "-s",
        "null",
        "-m",
        "null",
        "-n",
        f"127.0.0.1:{port}",
    ]


def build_inspect_argv(binary: Path, config: Path, final_save: Path) -> list[str]:
    return [
        str(binary),
        "-X",
        "-x",
        "-c",
        str(config),
        "-v",
        "cocoa",
        "-s",
        "null",
        "-m",
        "null",
        "-g",
        str(final_save),
    ]


def shell_command(argv: Sequence[str], cwd: Path | None = None) -> str:
    import shlex

    command = " ".join(shlex.quote(part) for part in argv)
    return f"(cd {shlex.quote(str(cwd))} && {command})" if cwd else command


def wait_for_port(port: int, deadline: float) -> None:
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise ProbeError(f"OpenTTD dedicated server did not listen on 127.0.0.1:{port}")


def wait_for_file_stable(path: Path, deadline: float, stable_seconds: float = 0.5) -> bool:
    stable_since: float | None = None
    while time.monotonic() < deadline:
        if path.is_file() and path.stat().st_size > 0:
            if stable_since is None:
                stable_since = time.monotonic()
            elif time.monotonic() - stable_since >= stable_seconds:
                return True
        else:
            stable_since = None
        time.sleep(0.05)
    return False


def wait_for_save(pump: "OutputPump", save_path: Path, deadline: float) -> bool:
    """Require both OpenTTD's exact success message and a stable save file."""
    marker = f"Map successfully saved to '{save_path}'."
    while time.monotonic() < deadline:
        if any(marker in line for line in pump.lines_seen):
            return wait_for_file_stable(save_path, deadline)
        time.sleep(0.05)
    return False


class OutputPump:
    def __init__(self, name: str, stream: Any, output: Path, events: list[dict[str, Any]], errors: list[str]) -> None:
        self.name = name
        self.stream = stream
        self.output = output
        self.events = events
        self.errors = errors
        self.lines: queue.Queue[str] = queue.Queue()
        self.lines_seen: list[str] = []
        self.thread = threading.Thread(target=self._read, name=f"probe-{name}", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _read(self) -> None:
        try:
            with self.output.open("w", encoding="utf-8") as destination:
                for raw in iter(self.stream.readline, ""):
                    line = raw.rstrip("\n")
                    destination.write(line + "\n")
                    destination.flush()
                    self.lines.put(line)
                    self.lines_seen.append(line)
                    try:
                        event = parse_event_line(line)
                    except ProbeError as exc:
                        self.errors.append(f"{self.name}: {exc}")
                        continue
                    if event is not None:
                        event = dict(event)
                        event["source"] = self.name
                        self.events.append(event)
        finally:
            self.lines.put("")

    def join(self, timeout: float = 2.0) -> None:
        self.thread.join(timeout)


def terminate_process(process: subprocess.Popen[str] | None, timeout: float = 5.0) -> str:
    if process is None or process.poll() is not None:
        return "already_exited"
    try:
        process.terminate()
        process.wait(timeout=timeout)
        return "terminated"
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            return "kill_timeout"
        return "killed_after_timeout"


def send_console(process: subprocess.Popen[str] | None, command: str) -> None:
    if process is None or process.poll() is not None or process.stdin is None:
        return
    try:
        process.stdin.write(command + "\n")
        process.stdin.flush()
    except (BrokenPipeError, OSError):
        pass


def inspect_command(run: Path) -> str:
    run = resolve_inspect_run(run)
    manifest_path = run / "manifest.json"
    if not manifest_path.is_file():
        raise ProbeError(f"run manifest does not exist: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    binary = Path(manifest["binary"])
    config = Path(manifest["server_config"])
    final_save = Path(manifest["final_save"])
    if not config.is_absolute() or not final_save.is_absolute():
        raise ProbeError("manifest paths must be absolute")
    profile = Path(manifest["server_profile"])
    if not profile.is_absolute():
        raise ProbeError("manifest server_profile must be absolute")
    return shell_command(build_inspect_argv(binary, config, final_save), profile)


def prepare_inspection(run: Path) -> tuple[list[str], Path]:
    """Copy the saved proof into a fresh profile before an explicit GUI launch."""
    run = resolve_inspect_run(run)
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    source_profile = Path(manifest["server_profile"]).resolve()
    source_save = Path(manifest["final_save"]).resolve()
    if not source_profile.is_dir() or not source_save.is_file():
        raise ProbeError("cannot prepare inspection: server profile or final save is missing")
    target = source_profile.parent / f"inspection-{uuid.uuid4().hex[:8]}"
    target.mkdir(exist_ok=False)
    shutil.copytree(source_profile, target, dirs_exist_ok=True)
    target_save = target / "save" / "control-probe-inspect.sav"
    shutil.copy2(source_save, target_save)
    config = target / "openttd.cfg"
    argv = build_inspect_argv(Path(manifest["binary"]).resolve(), config, target_save)
    return argv, target


def resolve_inspect_run(run: Path) -> Path:
    """Resolve a run directory, an artifact run name, or the latest run."""
    raw = str(run)
    if raw == "latest":
        root = (REPO_ROOT / "artifacts" / "control-probe").resolve()
        candidates = sorted(
            (path for path in root.iterdir() if path.is_dir() and RUN_NAME_RE.fullmatch(path.name) and (path / "manifest.json").is_file()),
            key=lambda path: path.name,
        ) if root.is_dir() else []
        if not candidates:
            raise ProbeError(f"no completed control-probe runs found under {root}")
        return candidates[-1]
    candidate = run.expanduser()
    if not candidate.is_absolute() and (REPO_ROOT / "artifacts" / "control-probe" / candidate).is_dir():
        candidate = REPO_ROOT / "artifacts" / "control-probe" / candidate
    return candidate.resolve()


def run_version(binary: Path, config: Path, output: Path) -> str:
    completed = subprocess.run(
        [str(binary), "-X", "-x", "-c", str(config), "-h"],
        cwd=config.parent,
        capture_output=True,
        text=True,
        timeout=10,
    )
    output.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise ProbeError(f"OpenTTD help/version probe failed with exit code {completed.returncode}")
    match = re.search(r"OpenTTD\s+([0-9]+(?:\.[0-9]+)+)", completed.stdout + completed.stderr)
    if not match:
        raise ProbeError("OpenTTD help/version output did not contain a version")
    version = match.group(1)
    if version != "15.3":
        raise ProbeError(f"expected OpenTTD 15.3, found {version}")
    return version


def copy_evidence(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def create_run(run_root: Path, artifact_root: Path) -> tuple[str, Path, Path]:
    for root in (run_root, artifact_root):
        root.mkdir(parents=True, exist_ok=True)
    run_name = utc_run_name()
    profile = run_root / run_name
    artifacts = artifact_root / run_name
    profile.mkdir(exist_ok=False)
    artifacts.mkdir(exist_ok=False)
    return run_name, profile, artifacts


def run_probe(args: argparse.Namespace) -> int:
    started = time.monotonic()
    deadline = started + float(args.deadline)
    run_root = (REPO_ROOT / ".runtime" / "control-probe").resolve()
    artifact_root = (REPO_ROOT / "artifacts" / "control-probe").resolve()
    run_name, profile, artifacts = create_run(run_root, artifact_root)
    server_profile = profile / "server"
    client_profile = profile / "client"
    server_profile.mkdir()
    client_profile.mkdir()
    for isolated in (server_profile, client_profile):
        (isolated / "save").mkdir()
        (isolated / "scenario").mkdir()

    binary = Path(args.binary).expanduser().resolve()
    server: subprocess.Popen[str] | None = None
    client: subprocess.Popen[str] | None = None
    server_pump: OutputPump | None = None
    client_pump: OutputPump | None = None
    events: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    initial_save_base = server_profile / "save" / "control-probe-initial"
    initial_save = server_profile / "save" / "control-probe-initial.sav"
    initial_save_evidence = artifacts / "control-probe-initial.sav"
    final_save_base = server_profile / "save" / "control-probe-final"
    final_save = server_profile / "save" / "control-probe-final.sav"
    final_save_evidence = artifacts / "control-probe-final.sav"
    server_log = artifacts / "server.log"
    client_log = artifacts / "client.log"
    combined_log = artifacts / "combined.log"
    termination: dict[str, str] = {}
    manifest_path = artifacts / "manifest.json"
    failure: Exception | None = None

    manifest: dict[str, Any] = {
        "schema": 1,
        "run": run_name,
        "status": "setup",
        "binary": str(binary),
        "source_revision": git_revision(REPO_ROOT),
        "engine_source_revision": "14ec60f248547d4d062a1160f0fc26d742319888",
        "source_hash": None,
        "platform": sys.platform,
        "machine": platform.machine(),
        "seed": int(args.seed),
        "map": {"width": 128, "height": 128, "climate": "temperate", "starting_year": 1950},
        "profile": str(profile),
        "server_profile": str(server_profile),
        "client_profile": str(client_profile),
        "artifacts": str(artifacts),
        "initial_save": str(initial_save),
        "final_save": str(final_save),
        "evidence_paths": {"version": str(artifacts / "version.log"), "server": str(server_log), "client": str(client_log), "combined": str(combined_log), "initial_save": str(initial_save_evidence), "final_save": str(final_save_evidence)},
        "asserts": {"required_event": "probe_complete", "protocol": 1, "final_save": False, "parse_errors": []},
        "initial_save_captured": False,
        "events": [],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    try:
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise ProbeError(f"OpenTTD 15.3 binary is not executable: {binary}")
        port = find_free_port()
        server_config, server_private = write_config(server_profile, port, True, server=True)
        client_config, client_private = write_config(client_profile, port, False, server=False)
        resources = bundle_resources(binary)
        bundled_server = stage_builtin_resources(server_profile, resources)
        bundled_client = stage_builtin_resources(client_profile, resources)
        archive = find_opengfx_archive(Path(args.opengfx_archive) if args.opengfx_archive else None)
        staged_server_archive = stage_opengfx(archive, server_profile)
        staged_client_archive = stage_opengfx(archive, client_profile)
        script_source = (Path(args.game_script) if args.game_script else REPO_ROOT / "game" / "copilot_probe").resolve()
        script = stage_game_script(server_profile, script_source)
        version = run_version(binary, server_config.resolve(), artifacts / "version.log")
        server_argv = build_server_argv(binary, server_config.resolve(), port, int(args.seed)) + ["-d", "script=4,misc=1"]
        client_argv = build_client_argv(binary, client_config.resolve(), port)
        manifest.update({
            "status": "running",
            "engine_version": version,
            "binary_sha256": sha256_file(binary),
            "source_hash": sha256_paths(
                [MODULE_PATH, script_source / "info.nut", script_source / "main.nut", server_config, client_config, server_private, client_private]
            ),
            "content_source": str(archive),
            "server_content": str(staged_server_archive),
            "client_content": str(staged_client_archive),
            "content_sha256": sha256_file(staged_server_archive),
            "bundled_resources": {
                "source": str(resources),
                "source_sha256": bundled_server["source_sha256"],
                "server": {"profile": str(server_profile), "sha256": bundled_server["staged_sha256"], "file_counts": bundled_server["file_counts"]},
                "client": {"profile": str(client_profile), "sha256": bundled_client["staged_sha256"], "file_counts": bundled_client["file_counts"]},
            },
            "script": str(script),
            "script_sha256": sha256_tree(script),
            "server_config": str(server_config.resolve()),
            "client_config": str(client_config.resolve()),
            "server_private_config": str(server_private.resolve()),
            "client_private_config": str(client_private.resolve()),
            "config_sha256": {"server": sha256_file(server_config), "client": sha256_file(client_config)},
            "private_config_sha256": {"server": sha256_file(server_private), "client": sha256_file(client_private)},
            "port": port,
            "argv": {"server": redact_argv(server_argv), "client": redact_argv(client_argv)},
        })
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        server = subprocess.Popen(
            server_argv,
            cwd=server_profile,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert server.stdout is not None
        server_pump = OutputPump("server", server.stdout, server_log, events, parse_errors)
        server_pump.start()
        wait_for_port(port, min(deadline, time.monotonic() + 20))

        # Capture the generated world before a client joins and creates a company.
        probe_started_deadline = min(deadline, time.monotonic() + 20)
        while time.monotonic() < probe_started_deadline and not any(event.get("kind") == "probe_started" for event in events):
            if server.poll() is not None:
                raise ProbeError(f"dedicated server exited before probe_started (code {server.returncode})")
            time.sleep(0.05)
        if not any(event.get("kind") == "probe_started" for event in events):
            raise ProbeError("timeout waiting for probe_started before client launch")
        send_console(server, f'save "{initial_save_base}"')
        if server_pump is None or not wait_for_save(server_pump, initial_save, min(deadline, time.monotonic() + 15)):
            raise ProbeError(f"server did not create initial save: {initial_save}")
        copy_evidence(initial_save, initial_save_evidence)
        manifest["initial_save_captured"] = True

        client = subprocess.Popen(
            client_argv,
            cwd=client_profile,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert client.stdout is not None
        client_pump = OutputPump("client", client.stdout, client_log, events, parse_errors)
        client_pump.start()

        final_kind: str | None = None
        while time.monotonic() < deadline:
            if any(event.get("kind") in {"probe_complete", "probe_failed"} for event in events):
                final_kind = next(event["kind"] for event in reversed(events) if event.get("kind") in {"probe_complete", "probe_failed"})
                break
            if server.poll() is not None:
                raise ProbeError(f"dedicated server exited before completion (code {server.returncode})")
            if client.poll() is not None:
                raise ProbeError(f"headless human client exited before completion (code {client.returncode})")
            time.sleep(0.05)

        if final_kind != "probe_complete":
            reason = "timeout waiting for probe_complete"
            if any(event.get("kind") == "probe_failed" for event in events):
                reason = "GameScript emitted probe_failed"
            raise ProbeError(reason)

        validate_success_events(events, parse_errors)
        send_console(server, f'save "{final_save_base}"')
        save_deadline = min(deadline, time.monotonic() + 15)
        save_done = server_pump is not None and wait_for_save(server_pump, final_save, save_deadline)
        if not save_done:
            raise ProbeError(f"server did not create final save: {final_save}")
        send_console(server, "quit")
        termination["server"] = "console_quit_sent"
        termination["client"] = terminate_process(client)
        try:
            server.wait(timeout=min(5.0, max(0.1, deadline - time.monotonic())))
            termination["server_exit"] = "console_quit"
        except subprocess.TimeoutExpired:
            termination["server_exit"] = terminate_process(server)
        copy_evidence(final_save, final_save_evidence)
        manifest["status"] = "success"
        manifest["asserts"]["final_save"] = True
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["failure"] = str(exc)
        failure = exc
    finally:
        if client is not None and client.poll() is None:
            termination.setdefault("client", terminate_process(client))
        if server is not None and server.poll() is None:
            termination.setdefault("server_exit", terminate_process(server))
        for pump in (server_pump, client_pump):
            if pump is not None:
                pump.join()
        with combined_log.open("w", encoding="utf-8") as destination:
            for label, path in (("server", server_log), ("client", client_log)):
                destination.write(f"--- {label} ---\n")
                if path.is_file():
                    destination.write(path.read_text(encoding="utf-8"))
        manifest["events"] = events
        manifest["asserts"]["parse_errors"] = parse_errors
        manifest["termination"] = termination
        manifest["elapsed_seconds"] = round(time.monotonic() - started, 3)
        manifest["final_save_sha256"] = sha256_file(final_save) if final_save.is_file() else None
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if failure is not None:
        print(f"control probe failed: {failure}; evidence: {artifacts}", file=sys.stderr)
        return 2
    print(f"control probe {manifest['status']}: {artifacts}")
    if manifest["status"] == "success":
        print("inspect:", inspect_command(artifacts))
        return 0
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=str(DEFAULT_BINARY), help="pinned OpenTTD 15.3 executable")
    parser.add_argument("--opengfx-archive", help="explicit installed OpenGFX2 Classic archive")
    parser.add_argument("--game-script", help="GameScript fixture directory (default: game/copilot_probe)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--deadline", type=float, default=DEFAULT_DEADLINE, help="total wall-clock deadline in seconds")
    parser.add_argument("--inspect", metavar="RUN", help="print the isolated GUI inspection command for an artifact run")
    parser.add_argument("--open", action="store_true", help="with --inspect, launch a copied isolated inspection profile")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.inspect:
            if args.open:
                inspect_argv, inspect_profile = prepare_inspection(Path(args.inspect))
                subprocess.Popen(inspect_argv, cwd=inspect_profile)
                print("opened:", shell_command(inspect_argv, inspect_profile))
            else:
                print(inspect_command(Path(args.inspect)))
            return 0
        if args.open:
            raise ProbeError("--open requires --inspect RUN")
        if not math.isfinite(args.deadline) or args.deadline <= 0:
            raise ProbeError("--deadline must be finite and positive")
        if not 0 <= args.seed < 0xFFFFFFFF:
            raise ProbeError("--seed must be between 0 and 4294967294; 4294967295 means random in OpenTTD")
        return run_probe(args)
    except (OSError, ProbeError, ValueError, json.JSONDecodeError) as exc:
        print(f"control probe failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
