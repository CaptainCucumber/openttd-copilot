#!/usr/bin/env python3
"""Local MCP tools for the disposable OpenTTD coal-railway demo."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import uuid
from typing import Any

import copilot_chat
import run_control_probe as base


ROOT = base.REPO_ROOT
PROBE = ROOT / "tools" / "run_vehicle_probe.py"
ARTIFACTS = ROOT / "artifacts" / "vehicle-probe"
RUNTIME = ROOT / ".runtime" / "mcp-demo"
PROTOCOL_VERSION = "2024-11-05"


class ToolError(ValueError):
    """A requested MCP action is outside the supported demo boundary."""


def validate_build_request(arguments: Any) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ToolError("Tool arguments must be an object.")
    expected = {"cargo", "origin", "destination", "wait_for_full_load"}
    if set(arguments) != expected:
        raise ToolError(f"Supply exactly these fields: {', '.join(sorted(expected))}.")
    cargo = arguments["cargo"]
    origin = arguments["origin"]
    destination = arguments["destination"]
    full_load = arguments["wait_for_full_load"]
    if cargo != "coal":
        raise ToolError("The playable demo currently supports coal only.")
    if not isinstance(origin, str) or "coal mine" not in origin.casefold():
        raise ToolError("The demo origin must identify a coal mine.")
    if not isinstance(destination, str) or not any(
        name in destination.casefold() for name in ("power station", "power plant")
    ):
        raise ToolError("The demo destination must identify a power station.")
    if full_load is not True:
        raise ToolError("The demo requires a full-load departure at the coal mine.")
    return {
        "cargo": "coal",
        "origin": origin,
        "destination": destination,
        "wait_for_full_load": True,
        "scope": "controlled_demo_fixture",
    }


class DemoJob:
    def __init__(self, binary: str, deadline: float, seed: int, show: bool) -> None:
        self.binary = binary
        self.deadline = deadline
        self.seed = seed
        self.show = show
        self.process: subprocess.Popen[bytes] | None = None
        self.job_id: str | None = None
        self.job_dir: Path | None = None
        self.ready_file: Path | None = None
        self.artifact_dir: Path | None = None
        self.log_stream = None
        self.state = "idle"
        self.failure: str | None = None
        self.result: dict[str, Any] | None = None
        self.displayed = False
        self.artifact_dirs_before: set[Path] = set()

    def open_map(self) -> dict[str, Any]:
        if self.process is not None:
            self.refresh()
            if self.state in {"waiting_for_build", "building"}:
                raise ToolError("A demo job is already active; inspect its status first.")

        self.job_id = uuid.uuid4().hex
        self.job_dir = RUNTIME / self.job_id
        self.job_dir.mkdir(parents=True, exist_ok=False)
        self.ready_file = self.job_dir / "map-ready"
        log_path = self.job_dir / "probe.log"
        self.artifact_dirs_before = {
            path.resolve() for path in ARTIFACTS.iterdir() if path.is_dir()
        } if ARTIFACTS.is_dir() else set()
        command = [
            sys.executable, "-B", str(PROBE), "--binary", self.binary,
            "--deadline", str(self.deadline), "--seed", str(self.seed),
            "--wait-file", str(self.ready_file),
        ]
        if self.show:
            command.append("--visible")
        self.log_stream = log_path.open("wb")
        self.process = subprocess.Popen(
            command, cwd=ROOT, stdin=subprocess.DEVNULL,
            stdout=self.log_stream, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.state = "opening_map"
        end = time.monotonic() + min(self.deadline, 90)
        while not self.ready_file.exists():
            if self.process.poll() is not None:
                self._close_log()
                self.refresh()
                raise ToolError(f"OpenTTD demo failed to open; inspect {log_path}.")
            if time.monotonic() >= end:
                self.process.terminate()
                self.process.wait(timeout=10)
                self._close_log()
                self.state = "failed"
                self.failure = "Timed out while opening the disposable map."
                raise ToolError(self.failure)
            time.sleep(0.1)

        artifacts = [
            path.resolve() for path in ARTIFACTS.iterdir()
            if path.is_dir() and path.resolve() not in self.artifact_dirs_before
        ] if ARTIFACTS.is_dir() else []
        if len(artifacts) != 1:
            self.process.terminate()
            self.process.wait(timeout=10)
            self._close_log()
            self.state = "failed"
            self.failure = "Could not uniquely identify this demo run's evidence directory."
            raise ToolError(self.failure)
        self.artifact_dir = artifacts[0]
        self.state = "waiting_for_build"
        if self.show:
            copilot_chat.activate_game()
        manifest = self._read_manifest()
        discovery = manifest.get("map_discovery", {})
        return {
            "job_id": self.job_id,
            "status": self.state,
            "map": "new disposable temperate map",
            "observed_industry_count": discovery.get("industry_count"),
            "coal_producer_count": len(discovery.get("coal_producers", [])),
            "coal_acceptor_count": len(discovery.get("coal_acceptors", [])),
            "observed_coal_producers": discovery.get("coal_producers", []),
            "observed_coal_acceptors": discovery.get("coal_acceptors", []),
            "limitations": [
                "This is a controlled demo fixture, not a planner for arbitrary "
                "existing industries.",
                "The observed existing businesses are not yet used by the fixture builder.",
                "The demo creates a separate test coal mine and power station after "
                "the build request.",
            ],
        }

    def build(self, arguments: Any) -> dict[str, Any]:
        intent = validate_build_request(arguments)
        if self.process is None or self.process.poll() is not None:
            raise ToolError("Open a new demo map before requesting construction.")
        if self.state != "waiting_for_build" or self.ready_file is None:
            raise ToolError("The demo map is not waiting for a build request.")
        self.ready_file.unlink()
        self.state = "building"
        return {
            "job_id": self.job_id,
            "status": self.state,
            "intent": intent,
            "message": (
                "The deterministic demo is building and verifying its controlled railway. "
                "The supplied business names are not bound to the observed existing industries."
            ),
            "evidence_log": str(self.job_dir / "probe.log"),
        }

    def refresh(self) -> dict[str, Any]:
        if self.process is None:
            raise ToolError("No demo job has been started.")
        if self.process.poll() is None:
            return {"job_id": self.job_id, "status": self.state}
        self._close_log()
        manifest = self._read_manifest()
        if manifest.get("status") == "success":
            discovery = manifest.get("map_discovery")
            checks = manifest.get("checks")
            service_check = (
                checks.get("two_full_load_deliveries")
                if isinstance(checks, dict) else None
            )
            service_summary = (
                service_check.get("summary") if isinstance(service_check, dict) else None
            )
            saves = manifest.get("saves")
            final_save = saves.get("service-final") if isinstance(saves, dict) else None
            save_path = final_save.get("path") if isinstance(final_save, dict) else None
            world_id = discovery.get("world") if isinstance(discovery, dict) else None
            if (
                not isinstance(world_id, str)
                or not world_id
                or not isinstance(service_summary, dict)
            ):
                self.state = "failed"
                self.failure = (
                    "Probe reported success but its manifest omitted world or delivery evidence."
                )
            elif any(
                type(service_summary.get(key)) is not int or service_summary[key] < 2
                for key in ("departures", "deliveries")
            ):
                self.state = "failed"
                self.failure = (
                    "Probe reported success without two verified departures and deliveries."
                )
            elif not isinstance(save_path, str) or not save_path:
                self.state = "failed"
                self.failure = (
                    "Probe reported success but its manifest omitted the completed save path."
                )
            else:
                self.state = "completed"
                self.result = {
                    "checks": sorted(checks.keys()),
                    "artifact_dir": str(self.artifact_dir),
                    "world_id": world_id,
                    "service_summary": service_summary,
                    "completed_save": save_path,
                }
                if self.show and not self.displayed:
                    copilot_chat.show_saved_game(self.binary, self.artifact_dir)
                    self.displayed = True
        else:
            self.state = "failed"
            self.failure = manifest.get("failure") or (
                f"Probe exited with {self.process.returncode}."
            )
        response: dict[str, Any] = {"job_id": self.job_id, "status": self.state}
        if self.result is not None:
            response["result"] = self.result
        if self.failure is not None:
            response["failure"] = self.failure
            response["artifact_dir"] = str(self.artifact_dir)
        return response

    def _read_manifest(self) -> dict[str, Any]:
        if self.artifact_dir is None:
            return {}
        manifest_path = self.artifact_dir / "manifest.json"
        try:
            value = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _close_log(self) -> None:
        if self.log_stream is not None:
            self.log_stream.close()
            self.log_stream = None


class McpServer:
    def __init__(self, job: DemoJob) -> None:
        self.job = job

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self._error(message.get("id") if isinstance(message, dict) else None,
                               -32600, "Invalid JSON-RPC request.")
        method = message.get("method")
        request_id = message.get("id")
        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return self._result(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "openttd-copilot-demo", "version": "0.1.0"},
            })
        if method == "ping":
            return self._result(request_id, {})
        if method == "tools/list":
            return self._result(request_id, {"tools": self._tools()})
        if method == "tools/call":
            params = message.get("params")
            if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                return self._error(request_id, -32602, "tools/call requires a tool name.")
            try:
                value = self._call_tool(params["name"], params.get("arguments", {}))
            except ToolError as exc:
                return self._result(request_id, {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                })
            except OSError as exc:
                return self._result(request_id, {
                    "content": [{"type": "text", "text": f"Local demo I/O failed: {exc}"}],
                    "isError": True,
                })
            return self._result(request_id, {
                "content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}],
                "isError": False,
            })
        if method == "logging/setLevel":
            return self._result(request_id, {})
        return self._error(request_id, -32601, f"Method not found: {method}")

    def _call_tool(self, name: str, arguments: Any) -> dict[str, Any]:
        if name == "open_demo_map":
            if arguments not in ({}, None):
                raise ToolError("open_demo_map takes no arguments.")
            return self.job.open_map()
        if name == "build_coal_railway":
            return self.job.build(arguments)
        if name == "get_build_status":
            if not isinstance(arguments, dict) or set(arguments) != {"job_id"}:
                raise ToolError("Supply exactly the job_id returned when opening the map.")
            if arguments["job_id"] != self.job.job_id:
                raise ToolError("Unknown demo job ID.")
            return self.job.refresh()
        raise ToolError(f"Unknown tool: {name}")

    @staticmethod
    def _tools() -> list[dict[str, Any]]:
        return [
            {
                "name": "open_demo_map",
                "description": (
                    "Open a new disposable OpenTTD 15.3 map for the supported coal-railway demo. "
                    "This does not modify normal saves. It reports existing coal businesses, but "
                    "the demo builder currently creates and uses separate controlled "
                    "test industries."
                ),
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "build_coal_railway",
                "description": (
                    "Build the supported demo railway after open_demo_map. Accepts only "
                    "a coal mine "
                    "to power station/plant coal route with a full-load departure. The game-side "
                    "deterministic fixture performs construction, train setup, and "
                    "delivery checks. "
                    "Business names are not yet resolved to existing map industries."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cargo": {"type": "string", "const": "coal"},
                        "origin": {"type": "string", "description": "Must identify a coal mine."},
                        "destination": {
                            "type": "string",
                            "description": "Must identify a power station or power plant.",
                        },
                        "wait_for_full_load": {"type": "boolean", "const": True},
                    },
                    "required": ["cargo", "origin", "destination", "wait_for_full_load"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "get_build_status",
                "description": "Get progress or verified completion for an opened demo job.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"job_id": {"type": "string"}},
                    "required": ["job_id"],
                    "additionalProperties": False,
                },
            },
        ]

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": code, "message": message}}


def serve(server: McpServer) -> int:
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = McpServer._error(None, -32700, "Parse error.")
        else:
            response = server.handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=str(base.DEFAULT_BINARY),
                        help="OpenTTD 15.3 binary used by the disposable fixture")
    parser.add_argument("--deadline", type=float, default=600)
    parser.add_argument("--seed", type=int, default=base.DEFAULT_SEED)
    parser.add_argument("--no-show", action="store_true",
                        help="run the demo without opening a visible game window")
    args = parser.parse_args()
    if not math.isfinite(args.deadline) or args.deadline <= 0 or not 0 <= args.seed < 0xFFFFFFFE:
        parser.error("deadline must be positive and seed between 0 and 4294967293")
    job = DemoJob(args.binary, args.deadline, args.seed, not args.no_show)
    return serve(McpServer(job))


if __name__ == "__main__":
    raise SystemExit(main())
