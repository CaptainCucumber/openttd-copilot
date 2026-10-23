import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from mcp_server import DemoJob, McpServer, ToolError, validate_build_request


class McpServerTests(unittest.TestCase):
    def setUp(self):
        self.server = McpServer(DemoJob("/not/launched", 30, 1, False))

    def test_initialization_and_tool_discovery(self):
        initialized = self.server.handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
        })
        self.assertEqual(initialized["result"]["protocolVersion"], "2024-11-05")
        self.assertIn("tools", initialized["result"]["capabilities"])
        listed = self.server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(
            [tool["name"] for tool in listed["result"]["tools"]],
            ["open_demo_map", "build_coal_railway", "get_build_status"],
        )

    def test_build_requires_supported_coal_job(self):
        request = {
            "cargo": "coal",
            "origin": "coal mine",
            "destination": "power station",
            "wait_for_full_load": True,
        }
        intent = validate_build_request(request)
        self.assertEqual(intent["cargo"], "coal")
        self.assertEqual(intent["scope"], "controlled_demo_fixture")
        invalid_requests = [
            {**request, "cargo": "iron ore"},
            {**request, "origin": "forest"},
            {**request, "destination": "factory"},
            {**request, "wait_for_full_load": False},
            {**request, "unexpected": True},
        ]
        for invalid in invalid_requests:
            with self.subTest(invalid=invalid), self.assertRaises(ToolError):
                validate_build_request(invalid)

    def test_completed_status_maps_world_and_service_summary(self):
        service_summary = {
            "deliveries": 2,
            "departures": 2,
            "scope": "isolated_one_train",
            "vehicle": 2,
        }
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            manifest = {
                "status": "success",
                "map_discovery": {"world": "world-123"},
                "checks": {
                    "two_full_load_deliveries": {"summary": service_summary},
                    "consist_and_orders_readback": {},
                },
                "saves": {"service-final": {"path": "/tmp/completed.sav"}},
            }
            (artifact_dir / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            job = DemoJob("/not/launched", 30, 1, False)
            job.process = Mock()
            job.process.poll.return_value = 0
            job.process.returncode = 0
            job.artifact_dir = artifact_dir
            job.job_id = "job-123"

            status = job.refresh()

        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["result"]["world_id"], "world-123")
        self.assertEqual(status["result"]["service_summary"], service_summary)
        self.assertEqual(status["result"]["completed_save"], "/tmp/completed.sav")

    def test_success_manifest_without_delivery_gate_is_not_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            (artifact_dir / "manifest.json").write_text(
                json.dumps({
                    "status": "success",
                    "map_discovery": {"world": "world-123"},
                    "checks": {"two_full_load_deliveries": {"summary": {
                        "departures": 2, "deliveries": 1,
                    }}},
                    "saves": {"service-final": {"path": "/tmp/completed.sav"}},
                }),
                encoding="utf-8",
            )
            job = DemoJob("/not/launched", 30, 1, False)
            job.process = Mock()
            job.process.poll.return_value = 0
            job.process.returncode = 0
            job.artifact_dir = artifact_dir
            job.job_id = "job-123"

            status = job.refresh()

        self.assertEqual(status["status"], "failed")
        self.assertIn("two verified departures and deliveries", status["failure"])

    def test_build_cannot_run_before_demo_map_is_open(self):
        response = self.server.handle({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {
                "name": "build_coal_railway",
                "arguments": {
                    "cargo": "coal", "origin": "coal mine",
                    "destination": "power station", "wait_for_full_load": True,
                },
            },
        })
        self.assertTrue(response["result"]["isError"])
        self.assertIn("Open a new demo map", response["result"]["content"][0]["text"])

    def test_unknown_job_tool_returns_tool_error(self):
        response = self.server.handle({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "unbounded_build", "arguments": {}},
        })
        self.assertTrue(response["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
