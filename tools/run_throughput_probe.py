#!/usr/bin/env python3
"""Run five disposable M1 tile-observation and rail-construction cohorts.

This harness is intentionally not an adapter decision. Each cohort creates a
fresh isolated OpenTTD world, observes exactly 10,000 relevant tile rows in the
GameScript, and builds exactly 100 simple rail pieces through normal commands.
It retains per-run wall/tick/message evidence and reports median plus
nearest-rank p95 only after every requested cohort passes.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import statistics
import time
import uuid

from admin_transport import AdminClient
import run_control_probe as base
from run_lifecycle_probe import Experiment, ROOT, require


OBSERVATION_COUNT = 10_000
CONSTRUCTION_COUNT = 100
CONSTRUCTION_CAP = 20_000
DEFAULT_RUNS = 5


def nearest_rank_p95(values):
    """Return the nearest-rank 95th percentile (the maximum for five runs)."""
    require(bool(values), "cannot summarize an empty cohort")
    ordered = sorted(values)
    rank = math.ceil(0.95 * len(ordered))
    return ordered[rank - 1]


def summarize_runs(runs):
    """Validate complete, comparable cohorts before producing aggregates."""
    require(bool(runs), "at least one throughput run is required")
    metrics = {
        "observation_wall_seconds": [], "observation_ticks": [],
        "construction_wall_seconds": [], "construction_ticks": [],
        "post_operation_hello_seconds": [], "admin_ping_seconds": [],
        "worst_concurrent_admin_ping_seconds": [],
        "worst_queued_hello_seconds": [],
        "max_gamescript_packet_bytes": [],
    }
    for index, run in enumerate(runs, 1):
        require(run.get("status") == "passed", f"throughput run {index} did not pass")
        require(run.get("observation", {}).get("count") == OBSERVATION_COUNT,
                f"throughput run {index} observed the wrong tile count")
        construction = run.get("construction", {})
        require(construction.get("built") == CONSTRUCTION_COUNT
                and construction.get("readback_present") == CONSTRUCTION_COUNT
                and construction.get("wrong_owner") == 0,
                f"throughput run {index} lacks complete owned-rail readback")
        require(construction.get("cost", -1) >= 0
                and construction.get("cost", CONSTRUCTION_CAP + 1) <= CONSTRUCTION_CAP,
                f"throughput run {index} exceeded the construction cap")
        for name in metrics:
            value = run.get("metrics", {}).get(name)
            require(type(value) in (int, float) and not isinstance(value, bool)
                    and math.isfinite(value) and value >= 0,
                    f"throughput run {index} has invalid {name}")
            metrics[name].append(value)
    return {
        "method": "median and nearest-rank p95 across independent disposable worlds",
        "run_count": len(runs),
        "metrics": {
            name: {"median": statistics.median(values), "p95": nearest_rank_p95(values)}
            for name, values in metrics.items()
        },
    }


class ThroughputExperiment(Experiment):
    probe_kind = "throughput-probe"
    script_source = ROOT / "game/copilot_throughput"
    script_name = "Copilot Throughput Probe"

    def __init__(self, binary, timeout, seed, runs=DEFAULT_RUNS):
        super().__init__(binary, timeout, seed)
        self.runs = runs
        self.manifest["scope"] = (
            "M1 throughput fixture only; five disposable worlds by default; "
            "no adapter decision or final real-engine acceptance"
        )
        self.manifest["limits"].update(
            observation_tiles=OBSERVATION_COUNT,
            construction_pieces=CONSTRUCTION_COUNT,
            construction_cap=CONSTRUCTION_CAP,
            cohort_runs=runs,
        )
        self.manifest["script_runtime"] = {
            "opcode_budget": "stock OpenTTD 15.3 setting; not overridden by fixture",
            "evidence": "start/end simulation ticks disclose any script suspension",
            "game_script_json_bytes": 1449,
        }
        self.manifest["throughput_runs"] = []
        self.write()

    def stage(self, profile, port, admin_port=None):
        config, metadata = super().stage(profile, port, admin_port)
        if admin_port is not None:
            shutil.copy2(ROOT / "game/copilot_lifecycle/main.nut",
                         profile / "game/copilot_probe/lifecycle.nut")
        return config, metadata

    def timed_request(self, command, **fields):
        self.counter += 1
        rid = f"benchmark-{self.counter}-{uuid.uuid4().hex[:8]}"
        request = {"v": 1, "rid": rid, "cmd": command, **fields}
        observer = AdminClient(self.admin_port, self.password, timeout=self.remaining(10))
        self.admins.append(observer)
        observer.connect()
        try:
            started = time.monotonic()
            response_rid = self.admin.send_request(request)
            ping_started = time.monotonic()
            require(observer.ping(0xBEEF) == 0xBEEF, "concurrent Admin ping mismatch")
            concurrent_ping = time.monotonic() - ping_started
            queued_rid = f"queued-{rid}"
            queued_started = time.monotonic()
            observer.send_request({"v": 1, "rid": queued_rid, "cmd": "hello"})
            reply = self.admin.receive_response(response_rid, self.remaining(60))
            wall = time.monotonic() - started
            queued_hello = observer.receive_response(queued_rid, self.remaining(10))
            queued_wall = time.monotonic() - queued_started
        finally:
            observer.close()
        require(queued_hello.get("ok") is True
                and queued_hello.get("world") == fields.get("world"),
                f"queued hello failed after {command}: {queued_hello}")
        packets = [event for event in self.admin.events
                   if event.get("packet_type") == "gamescript"
                   and event.get("payload", {}).get("rid") == rid]
        require(reply.get("ok") is True, f"unexpected {command} reply: {reply}")
        require(len(packets) == 2, f"missing request/response packet evidence for {command}")
        return reply, {
            "wall_seconds": wall,
            "concurrent_admin_ping_seconds": concurrent_ping,
            "queued_hello_seconds": queued_wall,
            "request_bytes": next(event["packet_length"] for event in packets
                                  if event["direction"] == "sent"),
            "response_bytes": next(event["packet_length"] for event in packets
                                   if event["direction"] == "received"),
        }

    def latency_sample(self, world):
        started = time.monotonic()
        require(self.admin.ping(0xC0DE) == 0xC0DE, "Admin ping mismatch")
        ping = time.monotonic() - started
        started = time.monotonic()
        hello = self.call("hello")
        hello_wall = time.monotonic() - started
        require(hello.get("world") == world, "post-operation hello changed world")
        return ping, hello_wall

    def run_one(self, index):
        hello = self.start_world(f"run-{index}", seed=self.seed + index - 1)
        world, session = uuid.uuid4().hex, uuid.uuid4().hex
        initialized = self.call("init", world=world)
        self.call("bind", world=world, session=session)
        require(hello.get("company") == 0 and initialized.get("world") == world,
                "throughput world did not bind the human company")

        observation, observation_wire = self.timed_request(
            "observe_benchmark", world=world, start=0, count=OBSERVATION_COUNT)
        require(observation.get("count") == OBSERVATION_COUNT,
                "tile observation count mismatch")

        benchmark = uuid.uuid4().hex
        prepared = self.call("prepare_construction", world=world, session=session,
                             benchmark=benchmark, count=CONSTRUCTION_COUNT)
        require(prepared.get("count") == CONSTRUCTION_COUNT
                and 0 < prepared.get("quote", 0) <= CONSTRUCTION_CAP,
                f"invalid construction preparation: {prepared}")

        # Paused mutation must be rejected and must not be queued for later.
        base.send_console(self.server, "pause")
        stop = time.monotonic() + self.remaining(10)
        while not self.call("hello")["paused"]:
            require(time.monotonic() < stop, "pause not observed")
        refused = self.admin.request({
            "v": 1, "rid": f"paused-{index}", "cmd": "construct_benchmark",
            "world": world, "session": session, "benchmark": benchmark,
            "company": 0, "cap": CONSTRUCTION_CAP,
        }, timeout=self.remaining(10))
        require(refused.get("ok") is False and refused.get("error") == "paused",
                f"paused construction was not refused: {refused}")
        base.send_console(self.server, "unpause")
        while self.call("hello")["paused"]:
            require(time.monotonic() < stop, "unpause not observed")

        construction, construction_wire = self.timed_request(
            "construct_benchmark", world=world, session=session,
            benchmark=benchmark, company=0, cap=CONSTRUCTION_CAP)
        result = construction.get("result", {})
        require(result.get("state") == "completed"
                and result.get("built") == CONSTRUCTION_COUNT,
                f"construction sequence incomplete: {construction}")
        require(result.get("cost") == prepared["quote"] <= CONSTRUCTION_CAP,
                "construction cost differed from the complete tested quote")
        require(result.get("loan") == hello.get("loan"), "construction changed loan")
        readback = self.call("construction_readback", world=world,
                             benchmark=benchmark)
        require(readback.get("present") == CONSTRUCTION_COUNT
                and readback.get("wrong_owner") == 0,
                f"construction readback mismatch: {readback}")
        ping, hello_wall = self.latency_sample(world)
        maximum_packet = max(
            observation_wire["request_bytes"], observation_wire["response_bytes"],
            construction_wire["request_bytes"], construction_wire["response_bytes"],
        )
        require(maximum_packet <= 1460, "benchmark packet exceeded Admin compatibility MTU")
        return {
            "index": index, "seed": self.seed + index - 1, "status": "passed",
            "world": world, "company": 0, "pause_refusal": refused,
            "observation": {
                "count": observation["count"], "start": observation["start"],
                "examined": observation["examined"],
                "checksum": observation["checksum"], "owned": observation["owned"],
                "rail": observation["rail"], "water": observation["water"],
                "buildable": observation["buildable"],
                "start_tick": observation["start_tick"],
                "end_tick": observation["end_tick"], "wire": observation_wire,
            },
            "construction": {
                "requested": CONSTRUCTION_COUNT, "built": result["built"],
                "quote": prepared["quote"], "cost": result["cost"],
                "cash": result["cash"], "loan": result["loan"],
                "start_tick": result["start_tick"], "end_tick": result["end_tick"],
                "readback_present": readback["present"],
                "wrong_owner": readback["wrong_owner"], "wire": construction_wire,
            },
            "metrics": {
                "observation_wall_seconds": observation_wire["wall_seconds"],
                "observation_ticks": observation["end_tick"] - observation["start_tick"],
                "construction_wall_seconds": construction_wire["wall_seconds"],
                "construction_ticks": result["end_tick"] - result["start_tick"],
                "post_operation_hello_seconds": hello_wall,
                "admin_ping_seconds": ping,
                "worst_concurrent_admin_ping_seconds": max(
                    observation_wire["concurrent_admin_ping_seconds"],
                    construction_wire["concurrent_admin_ping_seconds"],
                ),
                "worst_queued_hello_seconds": max(
                    observation_wire["queued_hello_seconds"],
                    construction_wire["queued_hello_seconds"],
                ),
                "max_gamescript_packet_bytes": maximum_packet,
            },
        }

    def run(self):
        self.manifest["binary_sha256"] = base.sha256_file(self.binary)
        sources = [Path(__file__), ROOT / "tools/admin_transport.py",
                   ROOT / "tools/run_lifecycle_probe.py",
                   ROOT / "tools/run_control_probe.py",
                   self.script_source / "main.nut", self.script_source / "info.nut",
                   ROOT / "game/copilot_lifecycle/main.nut"]
        self.manifest["source_hashes"] = {
            str(path.relative_to(ROOT)): base.sha256_file(path) for path in sources
        }
        version_profile = self.profile / "version"
        version_profile.mkdir()
        self.manifest["engine_version"] = base.run_version(
            self.binary, base.write_config(version_profile, base.find_free_port(), False)[0],
            self.artifacts / "version.log")
        for index in range(1, self.runs + 1):
            result = self.run_one(index)
            self.manifest["throughput_runs"].append(result)
            self.write()
            print(f"PASS throughput_run_{index}", flush=True)
        self.manifest["summary"] = summarize_runs(self.manifest["throughput_runs"])
        self.check("cohort_complete", {"runs": self.runs, "summary": self.manifest["summary"]})
        require(not self.errors, f"structured log errors: {self.errors}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=str(base.DEFAULT_BINARY))
    parser.add_argument("--deadline", type=float, default=300)
    parser.add_argument("--seed", type=int, default=base.DEFAULT_SEED)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    args = parser.parse_args()
    if (not math.isfinite(args.deadline) or args.deadline <= 0
            or not 0 <= args.seed < 0xFFFFFFFE - args.runs
            or not 1 <= args.runs <= 20):
        parser.error("positive finite deadline, 1..20 runs, and safe seed range required")
    experiment = ThroughputExperiment(Path(args.binary).resolve(), args.deadline,
                                      args.seed, args.runs)
    error = None
    try:
        experiment.run()
    except Exception as exc:
        error = exc
    return experiment.finish(error)


if __name__ == "__main__":
    raise SystemExit(main())
