"""Narrow native OpenTTD railway MCP server (alpha).

This interface deliberately exposes only the existing-business coal railway
workflow.  It is separate from the controlled demo server.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
from pathlib import Path
import sys
import threading
import time
import uuid
from typing import Any

# ``mcp_server`` predates package-style imports and imports its sibling
# ``copilot_chat`` by name.  Keep both module and script execution working.
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

if __package__:
    from .mcp_server import McpServer, ToolError, serve
    from .native_play_session import CLIENT_BINARY, SERVER_BINARY, NativeSession
    from . import native_railway
else:
    from mcp_server import McpServer, ToolError, serve
    from native_play_session import CLIENT_BINARY, SERVER_BINARY, NativeSession
    import native_railway


STATES = {"opening_map", "waiting_for_build", "planning", "building",
          "verifying", "operating", "failed"}


def _integer(value: Any, name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"{name} must be an integer.")
    if positive and value <= 0:
        raise ToolError(f"{name} must be positive.")
    if value < 0:
        raise ToolError(f"{name} must be nonnegative.")
    return value


def _industry_map(discovery: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result = {}
    for record in discovery.get("industries", []):
        if isinstance(record, dict) and type(record.get("industry_id")) is int:
            result[record["industry_id"]] = record
    return result


def _validate_save(value: Any) -> str:
    if not isinstance(value, str) or Path(value).suffix != ".sav" or not Path(value).is_file():
        raise ToolError("The optional save path must identify an existing .sav file.")
    return value


def validate_build(arguments: Any, discovery: dict[str, Any], job_id: str) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ToolError("Build arguments must be an object.")
    expected = {"job_id", "source_id", "destination_id", "construction_cap",
                "operating_reserve", "wait_for_full_load", "cargo"}
    if set(arguments) != expected:
        raise ToolError("Supply exactly the seven documented build fields.")
    if arguments["job_id"] != job_id:
        raise ToolError("Unknown native job ID.")
    source_id = _integer(arguments["source_id"], "source_id")
    destination_id = _integer(arguments["destination_id"], "destination_id")
    cap = _integer(arguments["construction_cap"], "construction_cap", positive=True)
    reserve = _integer(arguments["operating_reserve"], "operating_reserve")
    if arguments["cargo"] != "coal":
        raise ToolError("The native alpha supports coal only.")
    if arguments["wait_for_full_load"] is not True:
        raise ToolError("wait_for_full_load must be true.")
    industries = _industry_map(discovery)
    source, destination = industries.get(source_id), industries.get(destination_id)
    if source is None or destination is None:
        raise ToolError("source_id and destination_id must be discovered industry IDs.")
    if 1 not in source.get("produced_cargo", []):
        raise ToolError("source_id is not an advertised coal producer.")
    if 1 not in destination.get("accepted_cargo", []):
        raise ToolError("destination_id is not an advertised coal acceptor.")
    if source_id == destination_id:
        raise ToolError("source_id and destination_id must differ.")
    pairs = discovery.get("business_pairs", [])
    if pairs and not any(
        isinstance(pair, dict)
        and pair.get("source_id") == source_id
        and pair.get("destination_id") == destination_id
        for pair in pairs
    ):
        raise ToolError("The discovered industries are not a supported coal business pair.")
    return {
        "job_id": job_id, "source_id": source_id, "destination_id": destination_id,
        "construction_cap": cap, "operating_reserve": reserve,
        "wait_for_full_load": True, "cargo": "coal",
    }


class NativeJob:
    def __init__(self, binary: str | Path, client_binary: str | Path,
                 deadline: float, seed: int, visible: bool) -> None:
        self.binary, self.client_binary = binary, client_binary
        self.deadline, self.seed, self.visible = deadline, seed, visible
        self.lock = threading.RLock()
        self.session: NativeSession | None = None
        self.job_id: str | None = None
        self.discovery: dict[str, Any] | None = None
        self.payload: dict[str, Any] | None = None
        self.status: str | None = None
        self.artifact_dir: str | None = None
        self.result: dict[str, Any] | None = None
        self.failure: str | None = None
        self.worker: threading.Thread | None = None
        self._finished = False

    def open(self, arguments: Any) -> dict[str, Any]:
        if arguments not in ({}, None) and not (
            isinstance(arguments, dict) and set(arguments) == {"save"}
        ):
            raise ToolError("open_native_map accepts only an optional save path.")
        save = arguments.get("save") if isinstance(arguments, dict) else None
        if save is not None:
            save = _validate_save(save)
        with self.lock:
            if self.session is not None:
                raise ToolError("A native map is already open.")
            self.job_id = uuid.uuid4().hex
            self.status = "opening_map"
            self.failure = self.result = None
            self._finished = False
            self.session = NativeSession(binary=self.binary, client_binary=self.client_binary,
                                         timeout=self.deadline, seed=self.seed,
                                         visible=self.visible)
            try:
                self.session.start_world("play", save=save)
                self.artifact_dir = str(self.session.artifacts)
                self.discovery = native_railway.discover(self.session.admin)
                self.status = "waiting_for_build"
                self.session.write()
            except Exception as exc:
                self._fail_locked(exc)
                self._finish_session()
                raise ToolError(self.failure or "Could not open native map.")
            return self._open_response_locked()

    def build(self, arguments: Any) -> dict[str, Any]:
        with self.lock:
            if self.job_id is None or self.discovery is None:
                raise ToolError("Open a native map before requesting construction.")
            payload = validate_build(arguments, self.discovery, self.job_id)
            if self.payload is not None:
                if payload != self.payload:
                    raise ToolError("A different build payload conflicts with this native job.")
                return self._snapshot_locked()
            if self.status != "waiting_for_build":
                raise ToolError("The native map is not waiting for a build request.")
            self.payload = payload
            self.session.deadline = time.monotonic() + self.deadline
            self.status = "planning"
            self.worker = threading.Thread(target=self._run, name="native-railway", daemon=True)
            self.worker.start()
            return self._snapshot_locked()

    def refresh(self, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, dict) or set(arguments) != {"job_id"}:
            raise ToolError("Supply exactly the job_id returned when opening the map.")
        with self.lock:
            if arguments["job_id"] != self.job_id:
                raise ToolError("Unknown native job ID.")
            return self._snapshot_locked()

    def close(self, arguments: Any) -> dict[str, Any]:
        if arguments not in ({}, None) and not (
            isinstance(arguments, dict) and set(arguments) == {"job_id"}
        ):
            raise ToolError("close_native_map accepts only job_id.")
        with self.lock:
            if self.job_id is None:
                raise ToolError("No native map is open.")
            if isinstance(arguments, dict) and arguments and arguments["job_id"] != self.job_id:
                raise ToolError("Unknown native job ID.")
            if self.worker is not None and self.worker.is_alive():
                raise ToolError("Cannot close while native construction is running.")
            save_path = None
            save_error = None
            if self.session is not None:
                try:
                    self.session.deadline = time.monotonic() + 20
                    save_path = self.session.save("player-save")
                except Exception as exc:
                    save_error = str(exc)
                self._finish_session(failure=save_error)
            response = self._snapshot_locked()
            response["closed"] = True
            if save_path is not None:
                response["save"] = str(save_path)
            if save_error is not None:
                response["save_failure"] = save_error
            self.session = None
            self.job_id = self.discovery = self.payload = None
            self.worker = None
            self.status = None
            self.artifact_dir = None
            self.result = self.failure = None
            return response

    def cleanup(self) -> None:
        worker = self.worker
        if worker is not None and worker.is_alive():
            worker.join()
        with self.lock:
            if self.session is not None:
                if not self._finished:
                    closed = self.close({})
                    if "save_failure" in closed:
                        print(f"Final save failed: {closed['save_failure']}", file=sys.stderr)

    def _finish_session(self, failure: str | None = None) -> None:
        if self.session is not None and not self._finished:
            with contextlib.redirect_stdout(sys.stderr):
                self.session.finish(failure=failure if failure is not None else self.failure)
            self._finished = True

    def _run(self) -> None:
        try:
            with self.lock:
                session, payload = self.session, self.payload
                self.status = "planning"
            plan = native_railway.plan_railway(
                session, payload["source_id"], payload["destination_id"],
                payload["construction_cap"], payload["operating_reserve"])
            with self.lock:
                self.status = "building"
            result = native_railway.execute_railway(session, plan, self.job_id)
            with self.lock:
                self.status = "verifying"
            verified = native_railway.verify_service(session, result)
            with self.lock:
                self.result = verified
                self.status = "operating"
                session.manifest["result"] = self.result
                session.write()
        except Exception as exc:
            with self.lock:
                self._fail_locked(exc)

    def _fail_locked(self, exc: Exception) -> None:
        self.status = "failed"
        self.failure = self._redact(str(exc))
        if self.session is not None:
            self.session.manifest["failure"] = self.failure
            self.session.manifest["status"] = "failed"
            self.session.write()

    def _redact(self, value: str) -> str:
        if self.session is None:
            return value
        for secret_name in ("password", "client_secret"):
            secret = getattr(self.session, secret_name, None)
            if isinstance(secret, str) and secret:
                value = value.replace(secret, "[REDACTED]")
        return value

    def _snapshot_locked(self) -> dict[str, Any]:
        response = {"job_id": self.job_id, "status": self.status,
                    "artifact_dir": self.artifact_dir}
        if self.result is not None:
            response["result"] = self.result
        if self.failure is not None:
            response["failure"] = self.failure
        return response

    def _open_response_locked(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id, "status": self.status,
            "world_id": self.discovery.get("world_id"),
            "industries": self.discovery.get("industries", []),
            "business_pairs": self.discovery.get("business_pairs", []),
            "supported_conditions": [
                "flat clear unowned land only", "standard temperate coal",
                "one human company", "maximum 64 records",
            ],
            "artifact_dir": self.artifact_dir,
        }


class NativeMcpServer(McpServer):
    def __init__(self, job: NativeJob) -> None:
        super().__init__(job)
        self.job = job

    def handle(self, message: Any) -> dict[str, Any] | None:
        response = super().handle(message)
        if isinstance(response, dict) and response.get("result", {}).get("serverInfo"):
            response["result"]["serverInfo"]["name"] = "openttd-copilot-native"
        return response

    def _call_tool(self, name: str, arguments: Any) -> dict[str, Any]:
        if name == "open_native_map":
            return self.job.open(arguments)
        if name == "build_native_railway":
            return self.job.build(arguments)
        if name == "get_native_status":
            return self.job.refresh(arguments)
        if name == "close_native_map":
            return self.job.close(arguments)
        raise ToolError(f"Unknown tool: {name}")

    @staticmethod
    def _tools() -> list[dict[str, Any]]:
        return [
            {"name": "open_native_map", "description": "Open an isolated native map.",
             "inputSchema": {"type": "object", "properties": {
                 "save": {"type": "string"}}, "additionalProperties": False}},
            {"name": "build_native_railway", "description": "Build and verify one coal railway.",
             "inputSchema": {"type": "object", "properties": {
                 "job_id": {"type": "string"}, "source_id": {"type": "integer"},
                 "destination_id": {"type": "integer"}, "construction_cap": {"type": "integer", "minimum": 1},
                 "operating_reserve": {"type": "integer", "minimum": 0},
                 "wait_for_full_load": {"type": "boolean", "const": True},
                 "cargo": {"type": "string", "const": "coal"}},
                 "required": ["job_id", "source_id", "destination_id", "construction_cap",
                              "operating_reserve", "wait_for_full_load", "cargo"],
                 "additionalProperties": False}},
            {"name": "get_native_status", "description": "Read cached native job state.",
             "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}},
                             "required": ["job_id"], "additionalProperties": False}},
            {"name": "close_native_map", "description": "Save and close an idle native map.",
             "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}},
                             "additionalProperties": False}},
        ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Alpha native OpenTTD MCP server: isolated coal railway only.")
    parser.add_argument("--binary", default=str(SERVER_BINARY))
    parser.add_argument("--client-binary", default=str(CLIENT_BINARY))
    parser.add_argument("--deadline", type=float, default=900)
    parser.add_argument("--seed", type=int, default=6)
    parser.add_argument("--save")
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    if args.save is not None and (Path(args.save).suffix != ".sav" or
                                  not Path(args.save).is_file()):
        parser.error("--save must identify an existing .sav file")
    if not math.isfinite(args.deadline) or args.deadline <= 0 or args.deadline > 900:
        parser.error("--deadline must be finite, positive, and no greater than 900")
    if not 0 <= args.seed <= 0xFFFFFFFF:
        parser.error("--seed must be between 0 and 4294967295")
    job = NativeJob(args.binary, args.client_binary, args.deadline, args.seed, not args.no_show)
    server = NativeMcpServer(job)
    try:
        if args.save:
            job.open({"save": args.save})
        return serve(server)
    finally:
        job.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
