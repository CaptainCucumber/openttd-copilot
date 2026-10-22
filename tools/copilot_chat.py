#!/usr/bin/env python3
"""Small local chat adapter for the first supported OpenTTD job.

This is intentionally model-free. It accepts the fixed coal request used by
the S3b fixture, produces a structured intent, and delegates execution to the
deterministic vehicle probe. It is a test seam for the eventual chat adapter,
not yet a general route planner.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "run_vehicle_probe.py"


class ChatInputError(ValueError):
    """The request is outside the currently supported intent scope."""


def parse_request(text: str) -> dict:
    """Parse the deliberately narrow first chat intent without guessing.

    Names are optional because the disposable fixture binds the actual source
    and destination names from the generated world. Unsupported cargo,
    transport, or operating constraints are rejected before any game action.
    """
    normalized = " ".join(text.lower().strip().split())
    if not normalized:
        raise ChatInputError("Please describe a transport job.")
    if "coal" not in normalized:
        raise ChatInputError("The first supported job carries coal.")
    if not any(word in normalized for word in ("rail", "railway", "train")):
        raise ChatInputError("The first supported job uses a railway train.")
    if "full load" not in normalized and "fully loaded" not in normalized:
        raise ChatInputError("Please specify that the train must wait for a full load.")
    if not any(word in normalized for word in ("power station", "power plant")):
        raise ChatInputError("The first supported destination is a power station.")
    return {
        "cargo": "coal",
        "mode": "rail",
        "source": "coal mine",
        "destination": "power station",
        "loading": "full_load",
        "verification": ["two_full_load_departures", "two_deliveries"],
        "scope": "disposable_fixture",
    }


def format_plan(intent: dict) -> str:
    return (
        "I understand: build a coal railway from a coal mine to a power station, "
        "wait for a full load, and verify two loaded departures and two deliveries.\n"
        "This uses the disposable OpenTTD fixture; it will not touch your normal saves.\n"
        f"Intent: {json.dumps(intent, sort_keys=True)}"
    )


def show_saved_game(binary: str, artifact: Path) -> None:
    manifest_path = artifact / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    save = Path(manifest["saves"]["service-final"]["path"])
    if not save.is_file():
        raise RuntimeError(f"successful job did not leave a final save: {save}")
    # Use the installed profile only for read-only game display. -x prevents
    # configuration writes; the generated save remains under artifacts/.
    process = subprocess.Popen([
        binary, "-x", "-v", "cocoa", "-s", "null", "-m", "null", "-g", str(save)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    start_new_session=True)
    print(f"OpenTTD is open with the completed route (pid {process.pid}).")


def run_job(binary: str, deadline: float, seed: int, show: bool) -> int:
    command = [sys.executable, "-B", str(PROBE), "--binary", binary,
               "--deadline", str(deadline), "--seed", str(seed)]
    if show:
        command.append("--visible")
    print("Starting the disposable OpenTTD job...", flush=True)
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode == 0:
        artifact = max((ROOT / "artifacts" / "vehicle-probe").iterdir(),
                       key=lambda path: path.stat().st_mtime)
        print("Job complete. Inspect artifacts/vehicle-probe/ for the evidence.")
        if show:
            show_saved_game(binary, artifact)
    else:
        print("Job failed; diagnostics were retained under artifacts/vehicle-probe/.",
              file=sys.stderr)
    return completed.returncode


def launch_live_job(binary: str, deadline: float, seed: int, show: bool):
    """Open the map and stop before purchase until chat authorizes the job."""
    wait_file = ROOT / ".runtime" / "chat-session" / f"{uuid.uuid4().hex}.ready"
    wait_file.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-B", str(PROBE), "--binary", binary,
               "--deadline", str(deadline), "--seed", str(seed),
               "--wait-file", str(wait_file)]
    if show:
        command.append("--visible")
    print("Starting a disposable OpenTTD map...", flush=True)
    process = subprocess.Popen(command, cwd=ROOT)
    end = time.monotonic() + min(deadline, 90)
    while not wait_file.exists():
        if process.poll() is not None:
            raise RuntimeError(f"OpenTTD job stopped before the map opened (exit {process.returncode})")
        if time.monotonic() >= end:
            process.terminate()
            raise RuntimeError("Timed out waiting for the OpenTTD map to open")
        time.sleep(0.1)
    print("The OpenTTD map is open. The fixture found its coal source and power station.")
    return process, wait_file


def finish_live_job(binary: str, process, wait_file: Path, show: bool) -> int:
    wait_file.unlink(missing_ok=True)
    result = process.wait()
    if result == 0 and show:
        artifact = max((ROOT / "artifacts" / "vehicle-probe").iterdir(),
                       key=lambda path: path.stat().st_mtime)
        show_saved_game(binary, artifact)
    return result


def cancel_live_job(process, wait_file: Path) -> None:
    wait_file.unlink(missing_ok=True)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def interactive(binary: str, deadline: float, seed: int, show: bool) -> int:
    print("OpenTTD Copilot chat (first supported job: coal railway)")
    print("Opening a disposable map before accepting the build request...")
    try:
        process, wait_file = launch_live_job(binary, deadline, seed, show)
    except RuntimeError as exc:
        print(f"Could not open the game: {exc}", file=sys.stderr)
        return 2
    print("Type a request, 'plan', 'build', 'help', or 'quit'.")
    pending: dict | None = None
    while True:
        try:
            line = input("you> ").strip()
        except EOFError:
            print()
            cancel_live_job(process, wait_file)
            return 0
        if line.lower() in {"quit", "exit"}:
            cancel_live_job(process, wait_file)
            return 0
        if line.lower() == "help":
            print("Example: Build a railway carrying coal from a coal mine to a power station. Wait for a full load.")
            continue
        if line.lower() == "plan":
            if pending is None:
                print("Give me the transport request first.")
            else:
                print(format_plan(pending))
            continue
        if line.lower() == "build":
            if pending is None:
                print("Give me the transport request first.")
            else:
                return finish_live_job(binary, process, wait_file, show)
            continue
        try:
            pending = parse_request(line)
        except ChatInputError as exc:
            print(f"I cannot run that yet: {exc}")
        else:
            print(format_plan(pending))
            print("Type 'build' to run it, or 'quit' to leave without changing the game.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="/Applications/OpenTTD.app/Contents/MacOS/openttd")
    parser.add_argument("--deadline", type=float, default=600)
    parser.add_argument("--seed", type=int, default=20261021)
    parser.add_argument("--no-show", action="store_true",
                        help="leave the successful save on disk without opening the GUI")
    parser.add_argument("request", nargs="*", help="optional one-shot request")
    args = parser.parse_args()
    if args.request:
        try:
            intent = parse_request(" ".join(args.request))
        except ChatInputError as exc:
            parser.error(str(exc))
        print(format_plan(intent))
        return 0
    return interactive(args.binary, args.deadline, args.seed, not args.no_show)


if __name__ == "__main__":
    raise SystemExit(main())
