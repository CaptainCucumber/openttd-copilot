#!/usr/bin/env python3
"""Reload one saved control-probe world and verify its persisted evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import run_control_probe as harness  # noqa: E402


class ReloadError(RuntimeError):
    """A reload proof failed or could not be established."""


def _event(events: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    matches = [event for event in events if event.get("kind") == kind]
    if len(matches) != 1:
        raise ReloadError(f"expected exactly one {kind} event, found {len(matches)}")
    return matches[0]


def _same_rows(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ReloadError(f"{label} readback differs from the original saved rows")


def _reload_argv(argv: list[str]) -> list[str]:
    updated = list(argv)
    video_index = updated.index("-v") + 1
    updated[video_index] = "null:ticks=300"
    updated.extend(["-d", "script=4"])
    return updated


def _parse_output(stdout: str, stderr: str) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    for stream_name, output in (("stdout", stdout), ("stderr", stderr)):
        for line in output.splitlines():
            try:
                event = harness.parse_event_line(line)
            except harness.ProbeError as exc:
                errors.append(f"{stream_name}: {exc}")
                continue
            if event is not None:
                event = dict(event)
                event["source"] = stream_name
                events.append(event)
    return events, errors


def verify_reload(original: dict[str, Any], events: list[dict[str, Any]], parse_errors: list[str]) -> dict[str, Any]:
    if parse_errors:
        raise ReloadError("reload output contained parse errors")
    loaded = _event(events, "loaded_readback")
    for forbidden in ("probe_started", "rail_built", "station_built", "probe_complete", "probe_failed"):
        if any(event.get("kind") == forbidden for event in events):
            raise ReloadError(f"reload emitted forbidden event {forbidden}")
    if loaded.get("protocol") != 1:
        raise ReloadError("loaded_readback protocol is not 1")
    if loaded.get("saved_state") != "complete":
        raise ReloadError(f"loaded saved_state is {loaded.get('saved_state')!r}, expected 'complete'")

    complete = _event(original["events"], "probe_complete")
    rail = _event(original["events"], "rail_built")
    station = _event(original["events"], "station_built")
    if loaded.get("current_company") != complete.get("company"):
        raise ReloadError("loaded current company differs from the original complete event")
    _same_rows(loaded.get("current_rail_tiles"), rail.get("tiles"), "rail tile")
    _same_rows(loaded.get("current_station_tiles"), station.get("tiles"), "station tile")

    saved = loaded.get("saved")
    if not isinstance(saved, dict):
        raise ReloadError("loaded_readback lacks the saved result object")
    for field in ("total_cost", "loan_before", "loan_after"):
        if saved.get(field) != complete.get(field):
            raise ReloadError(f"saved {field} differs from the original complete event")

    expected_cash = complete.get("cash_after")
    observed_cash = loaded.get("current_cash")
    expected_loan = complete.get("loan_after")
    observed_loan = loaded.get("current_loan")
    if observed_loan != expected_loan:
        raise ReloadError("loaded loan differs from the saved loan")
    cash_matches = observed_cash == expected_cash
    # Script ticks restart on load and cannot establish world-time equality.
    # This fixture has no operating vehicles; its immediate readback must match.
    if not cash_matches:
        raise ReloadError("immediate fixture cash differs from the saved cash")

    return {
        "loaded_event": loaded,
        "original_complete": complete,
        "money": {
            "expected_cash": expected_cash,
            "observed_cash": observed_cash,
            "cash_matches": cash_matches,
            "cash_status": "matched",
            "expected_loan": expected_loan,
            "observed_loan": observed_loan,
            "loan_stable": True,
        },
    }


def run_check(run_arg: str) -> int:
    run = harness.resolve_inspect_run(Path(run_arg))
    artifact = run.resolve()
    result_path = artifact / "reload.json"
    log_path = artifact / "reload.log"
    result: dict[str, Any] = {
        "schema": 1,
        "run": artifact.name,
        "status": "running",
        "artifact": str(artifact),
        "reload_log": str(log_path),
        "result": None,
    }
    process: subprocess.CompletedProcess[str] | None = None
    inspection_profile: Path | None = None
    final_save: Path | None = None
    before_hash: str | None = None
    try:
        manifest_path = artifact / "manifest.json"
        if not manifest_path.is_file():
            raise ReloadError(f"run manifest does not exist: {manifest_path}")
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        if original.get("status") != "success":
            raise ReloadError("reload requires a successful control-probe run")
        final_save = Path(original["final_save"])
        before_hash = harness.sha256_file(final_save)
        argv, inspection_profile = harness.prepare_inspection(artifact)
        argv = _reload_argv(argv)
        result.update({"argv": argv, "cwd": str(inspection_profile), "final_save_sha256_before": before_hash})
        try:
            process = subprocess.run(
                argv,
                cwd=inspection_profile,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(errors="replace")
            stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode(errors="replace")
            log_path.write_text(
                "argv = " + json.dumps(argv) + "\n\n--- stdout ---\n" + stdout + "\n--- stderr ---\n" + stderr + "\n",
                encoding="utf-8",
            )
            raise ReloadError("reload process exceeded 20 second timeout") from exc
        log_path.write_text(
            "argv = " + json.dumps(argv) + "\n\n--- stdout ---\n" + process.stdout + "\n--- stderr ---\n" + process.stderr + "\n",
            encoding="utf-8",
        )
        if process.returncode != 0:
            raise ReloadError(f"reload process exited with code {process.returncode}")
        events, parse_errors = _parse_output(process.stdout, process.stderr)
        verification = verify_reload(original, events, parse_errors)
        after_hash = harness.sha256_file(final_save)
        result["final_save_sha256_after"] = after_hash
        if after_hash != before_hash:
            raise ReloadError("original final save hash changed during reload")
        result.update({"events": events, "parse_errors": parse_errors, "result": verification, "status": "success", "returncode": process.returncode})
    except Exception as exc:
        result.update({"status": "failed", "failure": str(exc)})
        if process is not None:
            result["returncode"] = process.returncode
    finally:
        if final_save is not None and before_hash is not None and final_save.is_file():
            after_hash = harness.sha256_file(final_save)
            result.setdefault("final_save_sha256_after", after_hash)
            result["final_save_hash_unchanged"] = after_hash == before_hash
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if result["status"] == "success":
        print(f"probe reload check passed: {result_path}")
        return 0
    print(f"probe reload check failed: {result.get('failure')}; evidence: {artifact}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default="latest", help="control-probe artifact run name or path")
    args = parser.parse_args(argv)
    try:
        return run_check(args.run)
    except (OSError, harness.ProbeError, ReloadError, ValueError, json.JSONDecodeError) as exc:
        print(f"probe reload check failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
