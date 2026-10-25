from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import native_mcp_server as server


class FakeSession:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.artifacts = Path(tempfile.mkdtemp(prefix="native-mcp-test-"))
        self.admin = object()
        self.manifest = {}
        self.started_save = None
        self.finish_calls = 0
        self.finish_failure = None
        self.saved = False
        self.write_count = 0
        self.__class__.instances.append(self)

    def start_world(self, label, save=None):
        self.started_label, self.started_save = label, save

    def write(self):
        self.write_count += 1

    def save(self, name):
        self.saved = True
        return self.artifacts / (name + ".sav")

    def finish(self, failure=None):
        self.finish_calls += 1
        self.finish_failure = failure


DISCOVERY = {
    "world_id": "world-1",
    "industries": [
        {"industry_id": 11, "name": "North Mine", "produced_cargo": [1],
         "accepted_cargo": []},
        {"industry_id": 22, "name": "South Power Station", "produced_cargo": [],
         "accepted_cargo": [1]},
    ],
    "business_pairs": [{"source_id": 11, "destination_id": 22}],
}


class NativeMcpServerTests(unittest.TestCase):
    def setUp(self):
        FakeSession.instances.clear()
        self.discover = patch.object(server.native_railway, "discover",
                                     return_value=DISCOVERY)
        self.plan = patch.object(server.native_railway, "plan_railway",
                                 return_value={"route": "p"})
        self.execute = patch.object(server.native_railway, "execute_railway",
                                    return_value={"vehicle_id": 7, "cost": 99})
        self.verify = patch.object(server.native_railway, "verify_service",
                                   return_value={"departures": 2, "deliveries": 2})
        self.discover_mock = self.discover.start()
        self.plan_mock = self.plan.start()
        self.execute_mock = self.execute.start()
        self.verify_mock = self.verify.start()
        self.session = patch.object(server, "NativeSession", FakeSession)
        self.session.start()
        self.job = server.NativeJob("server", "client", 900, 123, False)
        self.mcp = server.NativeMcpServer(self.job)

    def tearDown(self):
        self.session.stop()
        for patcher in (self.discover, self.plan, self.execute, self.verify):
            patcher.stop()
        self.job.cleanup()

    def call(self, request_id, name, arguments):
        response = self.mcp.handle({
            "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], request_id)
        return json.loads(response["result"]["content"][0]["text"]), response

    def test_initialize_tools_and_server_name(self):
        response = self.mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(response["result"]["serverInfo"]["name"], "openttd-copilot-native")
        listing = self.mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in listing["result"]["tools"]}
        self.assertEqual(names, {"open_native_map", "build_native_railway",
                                 "get_native_status", "close_native_map",
                                 "inspect_native_game", "plan_native_railway",
                                 "plan_native_bus", "build_native_bus"})

    def test_open_validates_existing_save_and_copies_it_to_session(self):
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "original.sav"
            save.write_bytes(b"save")
            result, _ = self.call(1, "open_native_map", {"save": str(save)})
        self.assertEqual(result["world_id"], "world-1")
        self.assertEqual(result["status"], "waiting_for_build")
        self.assertEqual(FakeSession.instances[0].started_save, str(save))
        self.assertEqual(self.discover_mock.call_args.args[0], FakeSession.instances[0].admin)

    def test_open_rejects_missing_save_before_session(self):
        with self.assertRaises(server.ToolError):
            self.job.open({"save": "does-not-exist.sav"})
        self.assertEqual(FakeSession.instances, [])

    def test_request_schema_rejects_bool_integer_and_unknown_fields(self):
        self.job.open({})
        args = {"job_id": self.job.job_id, "source_id": True, "destination_id": 22,
                "construction_cap": 100, "operating_reserve": 10,
                "wait_for_full_load": True, "cargo": "coal"}
        with self.assertRaises(server.ToolError):
            self.job.build(args)
        args["source_id"] = 11
        args["extra"] = 1
        with self.assertRaises(server.ToolError):
            self.job.build(args)

    def test_real_ids_are_bound_and_duplicate_build_runs_once(self):
        self.job.open({})
        args = {"job_id": self.job.job_id, "source_id": 11, "destination_id": 22,
                "construction_cap": 100, "operating_reserve": 10,
                "wait_for_full_load": True, "cargo": "coal"}
        first = self.job.build(args)
        self.job.worker.join(timeout=2)
        second = self.job.build(args)
        self.assertEqual(first["job_id"], second["job_id"])
        self.assertEqual(self.plan_mock.call_count, 1)
        self.assertEqual(self.execute_mock.call_count, 1)
        self.assertEqual(self.verify_mock.call_count, 1)
        self.assertEqual(self.job.status, "operating")
        self.assertEqual(self.job.result["deliveries"], 2)
        self.assertNotIn("verification", self.job.result)

    def test_new_explicit_request_after_verified_service_uses_new_job(self):
        self.job.open({})
        args = {"job_id": self.job.job_id, "source_id": 11, "destination_id": 22,
                "construction_cap": 100, "operating_reserve": 10,
                "wait_for_full_load": True, "cargo": "coal"}
        self.job.build(args)
        self.job.worker.join(timeout=2)
        first_execution = self.job.execution_id
        args["construction_cap"] = 101
        self.job.build(args)
        self.job.worker.join(timeout=2)
        self.assertEqual(self.plan_mock.call_count, 2)
        self.assertNotEqual(first_execution, self.job.execution_id)
        self.assertEqual(len(self.job.session.manifest["completed_jobs"]), 1)

    def test_worker_error_is_failed_with_partial_artifact_not_operating(self):
        self.execute_mock.side_effect = RuntimeError("construction stopped after station")
        self.job.open({})
        args = {"job_id": self.job.job_id, "source_id": 11, "destination_id": 22,
                "construction_cap": 100, "operating_reserve": 10,
                "wait_for_full_load": True, "cargo": "coal"}
        self.job.build(args)
        self.job.worker.join(timeout=2)
        status = self.job.refresh({"job_id": self.job.job_id})
        self.assertEqual(status["status"], "failed")
        self.assertNotIn("result", status)
        self.assertIn("artifact_dir", status)
        self.assertNotEqual(status["status"], "operating")
        self.assertIn("failure", FakeSession.instances[0].manifest)
        self.assertTrue(status["construction_started"])
        self.job.build(args)
        self.assertEqual(self.execute_mock.call_count, 1)
        with self.assertRaisesRegex(server.ToolError, "conflicts"):
            self.job.build({**args, "construction_cap": 200})

    def test_planning_rejection_is_nonmutating_and_another_request_can_build(self):
        self.plan_mock.side_effect = [RuntimeError("route pair search bound exceeded"), {"route": "p"}]
        self.job.open({})
        args = {"job_id": self.job.job_id, "source_id": 11, "destination_id": 22,
                "construction_cap": 100, "operating_reserve": 10,
                "wait_for_full_load": True, "cargo": "coal"}
        self.job.build(args)
        self.job.worker.join(timeout=2)
        status = self.job.refresh({"job_id": self.job.job_id})
        self.assertEqual(status["status"], "rejected")
        self.assertFalse(status["construction_started"])
        self.assertEqual(status["failure"], "route pair search bound exceeded")
        self.execute_mock.assert_not_called()
        self.verify_mock.assert_not_called()
        self.assertEqual(self.job.build(args)["status"], "rejected")
        self.assertEqual(self.plan_mock.call_count, 1)
        revised = {**args, "construction_cap": 200}
        self.job.build(revised)
        self.job.worker.join(timeout=2)
        status = self.job.refresh({"job_id": self.job.job_id})
        self.assertEqual(status["status"], "operating")
        self.assertTrue(status["construction_started"])
        self.assertNotIn("failure", status)
        self.execute_mock.assert_called_once()
        history = FakeSession.instances[0].manifest["planning_rejections"]
        self.assertEqual(history[0]["request"], args)
        self.assertFalse(history[0]["construction_started"])
        self.assertNotIn("failure", FakeSession.instances[0].manifest)

    def test_planning_budget_rejection_keeps_map_open_for_changed_budget(self):
        self.plan_mock.side_effect = RuntimeError("whole railway costs 200, above construction cap 100")
        self.job.open({})
        args = {"job_id": self.job.job_id, "source_id": 11, "destination_id": 22,
                "construction_cap": 100, "operating_reserve": 10,
                "wait_for_full_load": True, "cargo": "coal"}
        self.job.build(args)
        self.job.worker.join(timeout=2)
        self.assertEqual(self.job.status, "rejected")
        self.assertEqual(FakeSession.instances[0].finish_calls, 0)
        self.execute_mock.assert_not_called()
        self.plan_mock.side_effect = None
        self.job.build({**args, "construction_cap": 300})
        self.job.worker.join(timeout=2)
        self.assertEqual(self.job.status, "operating")

    def test_verification_failure_cannot_authorize_a_different_build(self):
        self.verify_mock.side_effect = RuntimeError("telemetry gap")
        self.job.open({})
        args = {"job_id": self.job.job_id, "source_id": 11, "destination_id": 22,
                "construction_cap": 100, "operating_reserve": 10,
                "wait_for_full_load": True, "cargo": "coal"}
        self.job.build(args)
        self.job.worker.join(timeout=2)
        self.assertEqual(self.job.status, "failed")
        self.assertTrue(self.job.refresh({"job_id": self.job.job_id})["construction_started"])
        with self.assertRaisesRegex(server.ToolError, "conflicts"):
            self.job.build({**args, "construction_cap": 300})
        self.execute_mock.assert_called_once()

    def test_refresh_does_not_call_discover_and_close_saves_then_finishes(self):
        self.job.open({})
        self.discover_mock.reset_mock()
        status = self.job.refresh({"job_id": self.job.job_id})
        self.assertEqual(status["status"], "waiting_for_build")
        self.discover_mock.assert_not_called()
        closed = self.job.close({"job_id": self.job.job_id})
        self.assertTrue(closed["closed"])
        self.assertTrue(FakeSession.instances[0].saved)
        self.assertEqual(FakeSession.instances[0].finish_calls, 1)

    def test_validation_uses_cargo_lists_without_pairs_and_rejects_same_id(self):
        discovery = dict(DISCOVERY, business_pairs=[])
        self.job.open({})
        self.discover_mock.return_value = discovery
        # The already-open discovery remains authoritative; exercise the validator directly.
        args = {"job_id": self.job.job_id, "source_id": 11, "destination_id": 22,
                "construction_cap": 100, "operating_reserve": 10,
                "wait_for_full_load": True, "cargo": "coal"}
        self.assertEqual(server.validate_build(args, discovery, self.job.job_id)["source_id"], 11)
        args["destination_id"] = 11
        with self.assertRaises(server.ToolError):
            server.validate_build(args, discovery, self.job.job_id)

    def test_worker_does_not_redirect_process_stdout(self):
        self.job.open({})
        args = {"job_id": self.job.job_id, "source_id": 11, "destination_id": 22,
                "construction_cap": 100, "operating_reserve": 10,
                "wait_for_full_load": True, "cargo": "coal"}
        original = server.sys.stdout
        self.job.build(args)
        self.job.worker.join(timeout=2)
        self.assertIs(server.sys.stdout, original)

    def test_close_resets_job_and_allows_clean_reopen(self):
        self.job.open({})
        old_id = self.job.job_id
        self.job.close({"job_id": old_id})
        self.assertIsNone(self.job.session)
        reopened = self.job.open({})
        self.assertNotEqual(reopened["job_id"], old_id)
        self.assertIsNone(self.job.payload)
        self.assertEqual(FakeSession.instances[0].finish_calls, 1)


if __name__ == "__main__":
    unittest.main()
