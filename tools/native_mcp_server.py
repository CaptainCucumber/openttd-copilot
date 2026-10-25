"""Native OpenTTD transport MCP server (alpha).

The deterministic railway and town bus workflows are separate from the older
controlled demo server.
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
    from . import native_bus
else:
    from mcp_server import McpServer, ToolError, serve
    from native_play_session import CLIENT_BINARY, SERVER_BINARY, NativeSession
    import native_railway
    import native_bus


STATES = {"opening_map", "waiting_for_build", "planning", "building",
          "verifying", "operating", "rejected", "failed"}


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


def validate_bus(arguments: Any, job_id: str) -> dict[str, Any]:
    fields = {"job_id", "source_town_id", "destination_town_id", "construction_cap", "operating_reserve"}
    if (not isinstance(arguments, dict) or not fields <= set(arguments) or
            set(arguments) - fields - {"via_town_ids"}):
        raise ToolError("Supply the five documented bus fields and optional ordered via_town_ids.")
    if arguments["job_id"] != job_id:
        raise ToolError("Unknown native job ID.")
    for key in fields - {"job_id"}:
        _integer(arguments[key], key, positive=key == "construction_cap")
    if arguments["source_town_id"] == arguments["destination_town_id"]:
        raise ToolError("Bus endpoints must be different observed towns.")
    via = arguments.get("via_town_ids", [])
    _town_ids(via, "via_town_ids", minimum=0, maximum=6)
    towns = [arguments["source_town_id"], *via, arguments["destination_town_id"]]
    if len(set(towns)) != len(towns):
        raise ToolError("Bus line towns must be distinct and ordered.")
    return dict(arguments)


def _town_ids(value: Any, name: str, *, minimum: int, maximum: int) -> list[int]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ToolError(f"{name} must be an ordered array of {minimum} through {maximum} town IDs.")
    for town_id in value:
        _integer(town_id, name)
    if len(set(value)) != len(value):
        raise ToolError(f"{name} must contain distinct observed town IDs.")
    return value


def validate_bus_stops(arguments: Any, job_id: str) -> dict[str, Any]:
    fields = {"job_id", "vehicle_id", "town_ids", "insert_index",
              "construction_cap", "operating_reserve"}
    if not isinstance(arguments, dict) or set(arguments) != fields:
        raise ToolError("Supply exactly the six documented add-stops fields.")
    if arguments["job_id"] != job_id:
        raise ToolError("Unknown native job ID.")
    for key in fields - {"job_id", "town_ids"}:
        _integer(arguments[key], key, positive=key == "construction_cap")
    _town_ids(arguments["town_ids"], "town_ids", minimum=1, maximum=6)
    if arguments["insert_index"] > 8:
        raise ToolError("insert_index exceeds the eight-stop line bound.")
    return dict(arguments)


def _plan_bus_payload(session, payload, *, record=True):
    if "vehicle_id" in payload:
        return native_bus.plan_bus_stops(
            session, payload["vehicle_id"], payload["town_ids"], payload["insert_index"],
            payload["construction_cap"], payload["operating_reserve"], record=record)
    kwargs = {"record": record}
    if "via_town_ids" in payload:
        kwargs["via_town_ids"] = payload["via_town_ids"]
    return native_bus.plan_bus(
        session, payload["source_town_id"], payload["destination_town_id"],
        payload["construction_cap"], payload["operating_reserve"], **kwargs)


class NativeJob:
    def __init__(self, binary: str | Path, client_binary: str | Path,
                 deadline: float, seed: int, visible: bool, map_style="railway-fixture") -> None:
        self.binary, self.client_binary = binary, client_binary
        self.deadline, self.seed, self.visible = deadline, seed, visible
        self.map_style = map_style
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
        self.construction_started = False
        self._finished = False
        self.execution_id: str | None = None

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
                                         visible=self.visible, map_style=self.map_style)
            try:
                self.session.start_world("play", save=save)
                self.artifact_dir = str(self.session.artifacts)
                self.discovery = native_railway.discover(self.session.admin)
                if self.map_style == "normal":
                    self.discovery["towns"] = native_bus.discover(self.session)
                self.status = "waiting_for_build"
                self.session.write()
            except Exception as exc:
                self._fail_locked(exc)
                self._finish_session()
                raise ToolError(self.failure or "Could not open native map.")
            return self._open_response_locked()

    def build(self, arguments: Any, *, bus=False, bus_stops=False) -> dict[str, Any]:
        with self.lock:
            if self.job_id is None or self.discovery is None:
                raise ToolError("Open a native map before requesting construction.")
            payload = (validate_bus_stops(arguments, self.job_id) if bus_stops else
                       validate_bus(arguments, self.job_id) if bus else
                       validate_build(arguments, self.discovery, self.job_id))
            if self.payload is not None:
                if payload == self.payload:
                    return self._snapshot_locked()
                if self.status not in ("rejected", "operating"):
                    raise ToolError("A different build payload conflicts with this native job.")
            if self.status not in ("waiting_for_build", "rejected", "operating"):
                raise ToolError("The native map is not waiting for a build request.")
            if self.worker is not None and self.worker.is_alive():
                raise ToolError("The previous planner is still finishing; wait for it before submitting another request.")
            self.payload = payload
            if self.status == "operating":
                self.session.manifest.setdefault("completed_jobs", []).append(self.result)
                self.execution_id = uuid.uuid4().hex
            elif self.execution_id is None:
                self.execution_id = self.job_id
            self.result = self.failure = None
            self.construction_started = False
            self.session.deadline = time.monotonic() + self.deadline
            self.status = "planning"
            self.session.manifest.pop("failure", None)
            self.session.manifest.pop("plan", None)
            self.session.manifest.update(status="running", job_state="planning", build_request=payload)
            self.session.write()
            self.worker = threading.Thread(target=self._run, name="native-railway", daemon=True)
            self.worker.start()
            return self._snapshot_locked()

    def refresh(self, arguments: Any) -> dict[str, Any]:
        if (not isinstance(arguments, dict) or "job_id" not in arguments or
                set(arguments) - {"job_id", "wait_seconds"}):
            raise ToolError("Supply job_id and optionally wait_seconds (0 through 10).")
        wait = _integer(arguments.get("wait_seconds", 0), "wait_seconds")
        if wait > 10:
            raise ToolError("wait_seconds must be at most 10.")
        end, initial_status = time.monotonic() + wait, self.status
        while True:
            with self.lock:
                if arguments["job_id"] != self.job_id:
                    raise ToolError("Unknown native job ID.")
                if (self.status != initial_status or self.worker is None or
                        not self.worker.is_alive() or time.monotonic() >= end):
                    return self._snapshot_locked()
            time.sleep(min(0.1, max(0, end - time.monotonic())))

    def _idle_session(self):
        if self.session is None or self._finished:
            raise ToolError("Open a native map first.")
        if self.worker is not None and self.worker.is_alive():
            raise ToolError("A native job is active. Use get_native_status for cached progress; "
                            "live inspection/planning is available after it finishes.")
        self.session.deadline = time.monotonic() + 120
        return self.session

    def inspect(self, arguments: Any) -> dict[str, Any]:
        if arguments not in ({}, None):
            raise ToolError("inspect_native_game takes no arguments.")
        with self.lock:
            session = self._idle_session()
            try:
                observations = native_railway.inspect_game(session)
                if self.map_style == "normal":
                    roads = native_bus.inspect(session)
                    if (roads["world_id"] != observations["world_id"] or
                            roads["position"] != observations["position"]):
                        raise RuntimeError("world/operation position changed between rail and bus observations")
                    frames = observations["observation_frame_span"] + roads["observation_frame_span"]
                    observations.update(roads)
                    observations["observation_frame_span"] = [min(frames), max(frames)]
            except Exception as exc:
                raise ToolError(f"Live game inspection failed: {self._redact(str(exc))}") from exc
            return {"job_id": self.job_id, "job_status": self.status, "read_only": True,
                    "observations": observations}

    def preview(self, arguments: Any) -> dict[str, Any]:
        with self.lock:
            session = self._idle_session()
            payload = validate_build(arguments, self.discovery, self.job_id)
            try:
                plan = native_railway.plan_railway(
                    session, payload["source_id"], payload["destination_id"],
                    payload["construction_cap"], payload["operating_reserve"], record=False)
            except Exception as exc:
                raise ToolError(f"No construction attempted. Planning did not return an affordable "
                                f"supported route: {self._redact(str(exc))}") from exc
            return {
                "job_id": self.job_id, "read_only": True, "construction_started": False,
                "world_id": plan["world_id"], "position": plan["position"],
                "source": plan["source"], "destination": plan["destination"],
                "quoted_total": plan["quoted_total"], "construction_cap": plan["construction_cap"],
                "operating_reserve": plan["operating_reserve"],
                "rail_tiles": len(plan["geometry"]["rails"]),
                "operations_required": plan["operation_count"],
                "available_records": plan["available_records"],
                "locomotive": plan["locomotive"], "wagon": plan["wagon"],
                "observation_frame_span": plan["observation_frame_span"],
                "scope": plan["scope"],
                "limits": "A current bounded construction quote, not a profit forecast or globally optimal route. "
                          "Building requires a separate explicit request and live replanning.",
            }

    def preview_bus(self, arguments: Any, *, bus_stops=False) -> dict[str, Any]:
        with self.lock:
            session = self._idle_session()
            payload = (validate_bus_stops(arguments, self.job_id) if bus_stops else
                       validate_bus(arguments, self.job_id))
            try:
                plan = _plan_bus_payload(session, payload, record=False)
            except Exception as exc:
                raise ToolError(f"No construction attempted. Bus planning failed: {self._redact(str(exc))}") from exc
            return {key: plan[key] for key in (
                "world_id", "source", "destination", "quoted_total", "construction_cap",
                "operating_reserve", "operation_count", "available_records", "engine",
                "observation_frame_span", "road_tiles_to_build", "scope")} | {
                    "job_id": self.job_id, "read_only": True, "construction_started": False,
                    "route_tiles": len(plan["geometry"]["path"]),
                    "clearing": "New road/depot tiles may clear trees within the quoted footprint; no houses, existing assets or terrain are removed.",
                    "town_ids": [payload["source_town_id"], *payload.get("via_town_ids", []),
                                 payload["destination_town_id"]] if not bus_stops else payload["town_ids"],
                    "existing_vehicle_id": payload.get("vehicle_id"),
                    "insert_index": payload.get("insert_index"),
                    "orders": "ordinary passenger pickup and unloading at every stop, not full load",
                    "limits": "Current bounded construction quote, not a profit forecast. Building replans live."
                } | {key: plan[key] for key in ("towns", "old_orders") if key in plan}

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
            self.construction_started = False
            self.execution_id = None
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
            try:
                bus = "source_town_id" in payload or "vehicle_id" in payload
                plan = (_plan_bus_payload(session, payload) if bus else
                    native_railway.plan_railway(
                        session, payload["source_id"], payload["destination_id"],
                        payload["construction_cap"], payload["operating_reserve"]))
            except Exception as exc:
                with self.lock:
                    self.status = "rejected"
                    self.failure = self._redact(str(exc))
                    session.manifest.setdefault("planning_rejections", []).append({
                        "request": payload, "failure": self.failure,
                        "kind": getattr(exc, "kind", type(exc).__name__),
                        "construction_started": False})
                    session.manifest.update(job_state="rejected", failure=self.failure)
                    session.write()
                return
            with self.lock:
                self.construction_started = True
                self.status = "building"
            result = (native_bus.execute_bus if bus else native_railway.execute_railway)(
                session, plan, self.execution_id)
            with self.lock:
                self.status = "verifying"
            verified = (native_bus.verify_bus if bus else native_railway.verify_service)(session, result)
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
                    "artifact_dir": self.artifact_dir,
                    "construction_started": self.construction_started}
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
            "towns": self.discovery.get("towns", []),
            "map_style": self.map_style,
            "business_pairs_note": "Observed coal-compatible pairs, not verified buildable routes. "
                                   "Only routes of at most 50 rail tiles are supported.",
            "supported_conditions": [
                "coal rail: flat clear unowned land only, at most 50 rail tiles",
                "passenger bus: existing two-way roads plus bounded new roads/tree clearing",
                "no automatic demolition, borrowing, bridges or terraform",
                "one human company", "maximum 64 shared retained operations",
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
        if name == "build_native_bus":
            return self.job.build(arguments, bus=True)
        if name == "plan_native_bus":
            return self.job.preview_bus(arguments)
        if name == "add_native_bus_stops":
            return self.job.build(arguments, bus_stops=True)
        if name == "plan_native_bus_stops":
            return self.job.preview_bus(arguments, bus_stops=True)
        if name == "get_native_status":
            return self.job.refresh(arguments)
        if name == "inspect_native_game":
            return self.job.inspect(arguments)
        if name == "plan_native_railway":
            return self.job.preview(arguments)
        if name == "close_native_map":
            return self.job.close(arguments)
        raise ToolError(f"Unknown tool: {name}")

    @staticmethod
    def _tools() -> list[dict[str, Any]]:
        tools = [
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
            {"name": "get_native_status", "description": "Read cached native job state without using the game socket. "
             "During a build, use wait_seconds=10 to wait for a phase change or at most 10 seconds, avoiding rapid polling.",
             "inputSchema": {"type": "object", "properties": {
                 "job_id": {"type": "string"}, "wait_seconds": {"type": "integer", "minimum": 0, "maximum": 10}},
                             "required": ["job_id"], "additionalProperties": False}},
            {"name": "inspect_native_game",
             "description": "Read live towns, bus catalog/vehicles/stops/depots/orders on normal maps, "
                            "company cash/loan, discovered businesses, owned rail stations/depots, "
                            "train consists/cargo/stopped state/orders, recent vehicle-tagged events and "
                            "buildable engine purchase/running-cost catalog. No construction. Profit, "
                            "production rates, actual speed and station queues are unavailable; do not "
                            "invent them. Cannot read concurrently with an active build; use cached status.",
             "annotations": {"readOnlyHint": True, "destructiveHint": False},
             "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
            {"name": "plan_native_railway",
             "description": "Read-only live station/route/cost/affordability plan for an explicit observed "
                            "coal business pair. Use for advice and comparing options without building. "
                            "Supply existing job/industry IDs, explicit cap/reserve and full load. "
                            "Cannot run while a build is active. Not a profit or optimality prediction.",
             "annotations": {"readOnlyHint": True, "destructiveHint": False},
             "inputSchema": {"type": "object", "properties": {
                 "job_id": {"type": "string"}, "source_id": {"type": "integer"},
                 "destination_id": {"type": "integer"},
                 "construction_cap": {"type": "integer", "minimum": 1},
                 "operating_reserve": {"type": "integer", "minimum": 0},
                 "wait_for_full_load": {"type": "boolean", "const": True},
                 "cargo": {"type": "string", "const": "coal"}},
                 "required": ["job_id", "source_id", "destination_id", "construction_cap",
                              "operating_reserve", "wait_for_full_load", "cargo"],
                 "additionalProperties": False}},
            {"name": "close_native_map", "description": "Save and close an idle native map.",
             "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}},
                             "additionalProperties": False}},
        ]
        bus_schema = {"type": "object", "properties": {
            "job_id": {"type": "string"}, "source_town_id": {"type": "integer", "minimum": 0},
            "destination_town_id": {"type": "integer", "minimum": 0},
            "via_town_ids": {"type": "array", "items": {"type": "integer", "minimum": 0},
                             "maxItems": 6, "uniqueItems": True,
                             "description": "Ordered intermediate observed towns; one bus line, not separate services."},
            "construction_cap": {"type": "integer", "minimum": 1},
            "operating_reserve": {"type": "integer", "minimum": 0}},
            "required": ["job_id", "source_town_id", "destination_town_id",
                         "construction_cap", "operating_reserve"], "additionalProperties": False}
        tools += [
            {"name": "plan_native_bus", "description": "Read-only costed passenger bus service between observed towns. "
             "One line through source, optional ordered via_town_ids, and destination (2-8 distinct towns). "
             "New drive-through stops, connected depot, one available bus and ordinary orders. "
             "Reuses two-way roads; may add bounded roads and clear trees at quoted cost. "
             "No house demolition, bridges or terraforming. Cap/reserve required. Not a profit forecast.",
             "inputSchema": bus_schema, "annotations": {"readOnlyHint": True, "destructiveHint": False}},
            {"name": "build_native_bus", "description": "Explicitly authorized passenger bus construction and "
             "verification of passenger delivery at every stop. Uses the same supported scope as plan_native_bus; "
             "may clear trees on disclosed new road/depot tiles. No automatic retry of partial/uncertain work.",
             "inputSchema": bus_schema},
        ]
        stops_schema = {"type": "object", "properties": {
            "job_id": {"type": "string"}, "vehicle_id": {"type": "integer", "minimum": 0},
            "town_ids": {"type": "array", "items": {"type": "integer", "minimum": 0},
                         "minItems": 1, "maxItems": 6, "uniqueItems": True},
            "insert_index": {"type": "integer", "minimum": 0, "maximum": 8,
                             "description": "Zero-based insertion index in the observed orders; count appends."},
            "construction_cap": {"type": "integer", "minimum": 1},
            "operating_reserve": {"type": "integer", "minimum": 0}},
            "required": ["job_id", "vehicle_id", "town_ids", "insert_index",
                         "construction_cap", "operating_reserve"], "additionalProperties": False}
        tools += [
            {"name": "plan_native_bus_stops",
             "description": "Read-only quote to insert ordered new town stops into an observed running owned "
             "passenger bus line, before insert_index (count appends). Preserves the bus, depot and all old "
             "orders; connects both neighboring stops. Unshared ordinary orders only; total at most eight. "
             "Includes new stops, bounded road links/tree clearing and explicit cap/reserve.",
             "inputSchema": stops_schema, "annotations": {"readOnlyHint": True, "destructiveHint": False}},
            {"name": "add_native_bus_stops",
             "description": "Explicitly authorized insertion of new town stops into an existing bus line. "
             "Same scope as plan_native_bus_stops. Stops the selected bus only to edit its orders, then resumes "
             "and verifies accepted passengers at every stop. No new bus/depot, replacement of old orders, "
             "shared-order edits or automatic retry/rollback; a partial failure may leave the bus stopped.",
             "inputSchema": stops_schema},
        ]
        return tools


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Alpha native OpenTTD MCP server: town buses and bounded coal railways.")
    parser.add_argument("--binary", default=str(SERVER_BINARY))
    parser.add_argument("--client-binary", default=str(CLIENT_BINARY))
    parser.add_argument("--deadline", type=float, default=900)
    parser.add_argument("--seed", type=int, default=6)
    parser.add_argument("--map-style", choices=("normal", "railway-fixture"), default="normal")
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
    job = NativeJob(args.binary, args.client_binary, args.deadline, args.seed, not args.no_show, args.map_style)
    server = NativeMcpServer(job)
    try:
        if args.save:
            job.open({"save": args.save})
        return serve(server)
    finally:
        job.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
