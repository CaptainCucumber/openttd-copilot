#!/usr/bin/env python3
"""S3b vehicle purchase, order, and isolated delivery experiment in OpenTTD 15.3."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import time
import uuid

from lifecycle_journal import Journal
import run_control_probe as base
from run_lifecycle_probe import Experiment, ROOT, require


def validate_service_events(events, fixture, vehicle, telemetry):
    """Check observations, never the builder's success flag or company income alone.

    CargoMonitor has no vehicle identity. Attribution here depends on a fresh
    one-train world and the engine's exact destination-industry delivery counter.
    This deliberately does not claim per-vehicle telemetry on arbitrary saves.
    """
    require(telemetry.get("gap") is None and "gap" in telemetry, "telemetry has an observation gap")
    require(telemetry.get("scope") == "isolated_one_train", "unsupported attribution scope")
    departures, deliveries = [], []
    last_tick = -1
    for event in events:
        require(event.get("vehicle") == vehicle, "telemetry refers to another vehicle")
        require(event.get("fleet_count") == 1, "delivery attribution requires exactly one train")
        tick = event.get("tick")
        require(type(tick) is int and tick > last_tick, "telemetry ticks must increase")
        last_tick = tick
        capacity, load = event.get("capacity"), event.get("load")
        require(type(capacity) is int and capacity > 0 and type(load) is int
                and 0 <= load <= capacity, "invalid cargo observation")
        if event.get("kind") == "departure":
            require(len(departures) == len(deliveries), "departure has no intervening delivery")
            require(load == capacity, "train departed without a full coal load")
            require(event.get("source_station") == fixture["source_station"], "wrong loading station")
            require(event.get("source_load") == capacity
                    and event.get("source_capacity") == capacity, "missing full source observation")
            require(type(event.get("source_tick")) is int
                    and last_tick > event["source_tick"], "missing pre-departure observation")
            departures.append(event)
        elif event.get("kind") == "delivery":
            require(len(departures) == len(deliveries) + 1, "delivery has no full-load departure")
            require(event.get("destination_industry") == fixture["destination_industry"]
                    and event.get("destination_station") == fixture["destination_station"],
                    "delivery destination mismatch")
            amount = event.get("amount")
            require(type(amount) is int and amount > 0, "load decrease alone does not prove delivery")
            require(amount <= departures[-1]["load"], "delivery exceeds assigned train load")
            require(load < departures[-1]["load"], "assigned train did not unload")
            require(type(event.get("profit")) is int, "vehicle profit observation missing")
            deliveries.append(event)
        else:
            raise base.ProbeError("unknown telemetry event")
    require(len(departures) >= 2 and len(deliveries) >= 2,
            "two full departures and two deliveries are required")
    return {"departures": len(departures), "deliveries": len(deliveries),
            "vehicle": vehicle, "scope": "isolated_one_train"}


class VehicleExperiment(Experiment):
    probe_kind = "vehicle-probe"
    script_source = ROOT / "game/copilot_vehicle"
    script_name = "Copilot Vehicle Probe"

    def __init__(self, binary, timeout, seed, visible=False, wait_file=None):
        super().__init__(binary, timeout, seed)
        self.visible_client = visible
        self.wait_file = Path(wait_file).resolve() if wait_file else None
        self.manifest["scope"] = "S3b disposable one-train fixture; no general per-vehicle delivery event or crash-gap proof"
        self.manifest["limits"].update(fixture_cap=20000, purchase_cap=50000,
                                       max_telemetry_events=32)
        self.write()

    def stage(self, profile, port, admin_port=None):
        config, metadata = super().stage(profile, port, admin_port)
        if admin_port is not None:
            shutil.copy2(ROOT / "game/copilot_lifecycle/main.nut",
                         profile / "game/copilot_probe/lifecycle.nut")
            # These are scenario-generation settings, not gameplay money or
            # command-validation bypasses. Only this disposable S3b world uses them.
            settings = config.read_text().replace("[difficulty]\n", "[difficulty]\nindustry_density = 0\n")
            settings = settings.replace("[economy]\n", "[economy]\nmultiple_industry_per_town = true\n")
            config.write_text(settings)
            metadata["config_sha256"] = base.sha256_file(config)
        return config, metadata

    def mutate(self, ledger, command, session, **fields):
        request = {"v": 1, "rid": uuid.uuid4().hex, "cmd": command,
                   "world": ledger.data["position"]["world"], "session": session,
                   "company": 0, "op": uuid.uuid4().hex,
                   "expect_seq": ledger.data["position"]["seq"], "cap": 50000, **fields}
        ledger.pending(request)
        response = self.admin.request(request, timeout=self.remaining(30))
        require(response.get("ok") is True, f"{command} failed: {response}")
        ledger.complete(request["op"], response, response["outcome"])
        return request, response

    def vehicle(self, world):
        return self.call("vehicle", world=world)["vehicle"]

    def run(self):
        self.manifest["binary_sha256"] = base.sha256_file(self.binary)
        paths = [ROOT / "tools" / name for name in
                 ("run_vehicle_probe.py", "run_lifecycle_probe.py", "run_control_probe.py",
                  "admin_transport.py", "lifecycle_journal.py")]
        paths += [ROOT / "game/copilot_lifecycle/main.nut", *sorted(self.script_source.glob("*.nut"))]
        self.manifest["source_hashes"] = {str(p.relative_to(ROOT)): base.sha256_file(p) for p in paths}
        hello = self.start_world("initial")
        self.manifest["engine_version"] = base.run_version(
            self.binary, self.profile / "initial-server/openttd.cfg", self.artifacts / "version.log")
        require("15.3" in self.manifest["engine_version"], "OpenTTD 15.3 required")
        self.check("human_company", hello)
        world, session = uuid.uuid4().hex, uuid.uuid4().hex
        initialized = self.call("init", world=world)
        self.call("bind", world=world, session=session)
        ledger = Journal(self.artifacts / "external-journal.json", initialized)
        # Fixture setup is deliberately one-shot. A timeout or partial build
        # leaves diagnostic state; the harness never retries setup.
        self.counter += 1
        response = self.admin.request({"v": 1, "rid": f"r{self.counter}", "cmd": "fixture",
                                       "world": world, "session": session, "company": 0, "cap": 20000},
                                      timeout=self.remaining(90))
        require(response.get("ok") is True, f"fixture setup failed: {response}")
        fixture = response["fixture"]
        require(0 < fixture["cost"] <= 20000, "fixture construction cap violated")
        require(self.call("hello")["loan"] == hello["loan"], "fixture borrowed money")
        self.check("fixture_built", fixture)
        if self.wait_file is not None:
            self.wait_file.parent.mkdir(parents=True, exist_ok=True)
            self.wait_file.write_text("ready\n", encoding="utf-8")
            print("READY game_open", flush=True)
            while self.wait_file.exists():
                self.remaining()
                time.sleep(0.1)
        baseline = self.save("before-purchase")
        request = {"v": 1, "rid": "lost-purchase", "cmd": "purchase", "world": world,
                   "session": session, "company": 0, "op": uuid.uuid4().hex,
                   "expect_seq": ledger.data["position"]["seq"], "cap": 50000}
        before_guards = self.call("hello")
        rejections = []
        for changed, error in [({"v": 99}, "unsupported_version"),
                               ({"session": "stale"}, "session_mismatch"),
                               ({"company": 1}, "company_mismatch"),
                               ({"expect_seq": 1}, "seq_mismatch")]:
            rejected = self.admin.request({**request, "rid": uuid.uuid4().hex, **changed})
            require(rejected.get("ok") is False and rejected.get("error") == error,
                    f"purchase guard failed: {rejected}")
            rejections.append(rejected)
        base.send_console(self.server, "pause")
        end = time.monotonic() + self.remaining()
        while not self.call("hello")["paused"]:
            require(time.monotonic() < end, "pause not observed")
        paused_purchase = self.admin.request({**request, "rid": "paused-purchase"})
        require(paused_purchase.get("error") == "paused" and paused_purchase.get("ok") is False,
                "paused purchase was accepted")
        base.send_console(self.server, "unpause")
        while self.call("hello")["paused"]:
            require(time.monotonic() < end, "unpause not observed")
        after_guards = self.call("hello")
        require(all(before_guards[key] == after_guards[key] for key in ("cash", "loan", "seq"))
                and self.vehicle(world) is None, "rejected purchase changed world")
        self.check("purchase_identity_and_pause_guards", {"rejections": rejections, "paused": paused_purchase})
        low_cap = self.admin.request({**request, "rid": "low-cap", "op": uuid.uuid4().hex, "cap": 0})
        require(low_cap.get("ok") is False or low_cap.get("outcome", {}).get("state") == "rejected",
                "purchase cap was ignored")
        after_cap = self.call("hello")
        require(all(after_cap[key] == after_guards[key] for key in ("cash", "loan", "seq"))
                and self.vehicle(world) is None, "rejected purchase changed world")
        self.check("purchase_cap_rejected", low_cap)
        ledger.pending(request)
        self.admin.send_request(request)
        self.admin.close()
        self.connect()
        end = time.monotonic() + self.remaining(30)
        while True:
            recovered = self.call("status", world=world, op=request["op"])
            outcome = recovered.get("outcome", {})
            if outcome.get("state") == "completed":
                break
            require(time.monotonic() < end and outcome.get("state") not in {"uncertain", "rejected"},
                    f"lost purchase not proven complete: {recovered}")
            time.sleep(0.05)
        ledger = Journal(self.artifacts / "external-journal.json")
        ledger.complete(request["op"], recovered, outcome)
        vehicle = self.vehicle(world)
        vehicle_id = vehicle["id"]
        require(vehicle["fleet_count"] == 1 and vehicle["in_depot"] is True,
                "purchase did not produce one stopped depot vehicle")
        require(vehicle["engine"] == fixture["engine"], "purchased wrong engine")
        require(outcome["cost"] == fixture["engine_quote"] > 0, "purchase quote/accounting mismatch")
        require(outcome["loan"] == hello["loan"], "purchase borrowed money")
        self.check("lost_purchase_reconciled", {"status": recovered, "readback": vehicle})
        duplicate = self.admin.request({**request, "rid": "repeat"})
        conflict = self.admin.request({**request, "rid": "conflict", "cap": 49999})
        require(duplicate.get("duplicate") is True and duplicate.get("outcome") == outcome,
                "purchase replay changed outcome")
        require(conflict.get("ok") is False and conflict.get("error") == "id_conflict",
                "changed purchase accepted under same ID")
        require(self.vehicle(world) == vehicle, "purchase replay created or changed a vehicle")
        self.check("purchase_replay_no_duplicate", {"duplicate": duplicate, "conflict": conflict})
        latest = self.save("purchased-seq1")
        reloaded = self.start_world("purchase-reload", latest)
        require(ledger.classify(reloaded) == "current" and reloaded["session"] is None,
                "purchase save did not retain position/reset binding")
        session = uuid.uuid4().hex
        self.call("bind", world=world, session=session)
        before = self.vehicle(world)
        replay = self.admin.request({**request, "rid": "reload-replay", "session": session})
        require(replay.get("duplicate") is True and replay.get("outcome") == outcome,
                "saved purchase was not deduplicated")
        require(self.vehicle(world) == before and before["id"] == vehicle_id and before["fleet_count"] == 1,
                "reload replay bought or changed vehicle")
        self.check("purchase_save_reload_replay", {"hello": reloaded, "replay": replay, "vehicle": before})
        _, configured = self.mutate(ledger, "configure", session)
        consist = self.vehicle(world)
        require(consist["id"] == vehicle_id and consist["num_wagons"] == 2
                and consist["fleet_count"] == 1 and consist["capacity"] > 0 and consist["in_depot"] is True,
                "consist readback mismatch")
        require(consist["length"] <= 32, "train does not fit two-tile platforms")
        orders = consist["orders"]
        require(len(orders) == 2 and orders[0]["destination"] == fixture["source_tile"]
                and orders[1]["destination"] == fixture["destination_tile"], "order destinations mismatch")
        # Values pinned to OpenTTD 15.3 script_order.hpp, verified against readback.
        require(orders[0]["flags"] == 64 and orders[1]["flags"] == 132, "full-load/unload/no-load orders absent")
        self.check("consist_and_orders_readback", {"operation": configured, "vehicle": consist})
        _, started = self.mutate(ledger, "start", session)
        self.check("train_started", started)
        observations = []
        while True:
            telemetry = self.call("telemetry", world=world)
            self.manifest["last_telemetry"] = telemetry
            self.write()
            require(not telemetry.get("error") and not telemetry.get("failure")
                    and telemetry.get("gap") is None,
                    f"telemetry failed: {telemetry}")
            if telemetry.get("departures", 0) >= 2 and telemetry.get("deliveries", 0) >= 2:
                for index in range(telemetry["event_count"]):
                    observations.append(self.call("telemetry", world=world, index=index)["event"])
                break
            self.remaining()
            time.sleep(0.25)
        summary = validate_service_events(observations, fixture, vehicle_id, telemetry)
        self.check("two_full_load_deliveries", {"summary": summary, "events": observations})
        final = self.vehicle(world)
        require(final["loan"] == hello["loan"], "service changed loan")
        self.check("loan_preserved", final)
        self.save("service-final")
        older = self.start_world("before-purchase-reload", baseline)
        require(ledger.classify(older) == "older_save", "older pre-purchase save not recognized")
        unknown = self.call("status", world=world, op=request["op"])
        require(unknown.get("state") == "unknown", "older save contains later purchase")
        self.check("older_purchase_save_stopped", {"hello": older, "status": unknown})
        require(not self.errors, f"structured log errors: {self.errors}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=str(base.DEFAULT_BINARY))
    parser.add_argument("--deadline", type=float, default=600)
    parser.add_argument("--seed", type=int, default=base.DEFAULT_SEED)
    parser.add_argument("--visible", action="store_true",
                        help="show the disposable client while the job runs")
    parser.add_argument("--wait-file", help="pause after opening the map until this file is removed")
    args = parser.parse_args()
    if not math.isfinite(args.deadline) or args.deadline <= 0 or not 0 <= args.seed < 0xFFFFFFFE:
        parser.error("positive finite deadline and seed between 0 and 4294967293 required")
    experiment = VehicleExperiment(Path(args.binary).resolve(), args.deadline, args.seed,
                                   args.visible, args.wait_file)
    failure = None
    try:
        experiment.run()
    except Exception as exc:
        failure = exc
    return experiment.finish(failure)


if __name__ == "__main__":
    raise SystemExit(main())
