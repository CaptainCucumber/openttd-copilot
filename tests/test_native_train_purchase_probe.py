import unittest
from pathlib import Path
import sys
import tempfile
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_native_train_purchase_probe as probe


class NativeTrainPurchaseProbeTests(unittest.TestCase):
    def test_engine_provenance_covers_dispatcher_and_build_registration(self):
        self.assertTrue({"src/copilot_bridge.cpp", "src/copilot_bridge.h",
                         "src/CMakeLists.txt"} <= set(probe.ENGINE_FILES))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            for name in probe.ENGINE_FILES:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name, encoding="utf-8")
            responses = [mock.Mock(stdout="abc123\n"), mock.Mock(stdout=""),
                         mock.Mock(stdout="OpenTTD test-gabc123\n", stderr="")]
            with mock.patch.object(probe, "ENGINE_SOURCE", source), \
                    mock.patch.object(probe.subprocess, "run", side_effect=responses):
                result = probe.engine_provenance(Path("/custom/openttd"), False)
            self.assertTrue(result["clean"])
            self.assertEqual(set(result["source_hashes"]), set(probe.ENGINE_FILES))
            self.assertEqual(result["source_hashes"]["src/copilot_bridge.cpp"],
                             probe.base.sha256_file(source / "src/copilot_bridge.cpp"))

    def test_payload_hash_and_operation_parts_are_deterministic(self):
        operation = (1 << 127) + 9
        self.assertEqual(probe.operation_parts(operation), (1 << 63, 9))
        request = {"depot_tile": 8255, "engine_id": 4, "max_cost": 100000}
        self.assertEqual(probe.payload_hash(request), probe.payload_hash(dict(request)))

    def test_catalog_choice_uses_live_fields_not_ids(self):
        catalog = [
            {"engine_id": 55, "buildable": True, "railveh_type": 2, "default_cargo": 1,
             "default_capacity": 30, "railtypes": 1, "purchase_cost": 100},
            {"engine_id": 9, "buildable": True, "railveh_type": 0, "default_cargo": 255,
             "default_capacity": 0, "railtypes": 1, "purchase_cost": 500},
            {"engine_id": 22, "buildable": True, "railveh_type": 0, "default_cargo": 255,
             "default_capacity": 0, "railtypes": 1, "purchase_cost": 300},
        ]
        locomotive, wagon = probe.choose_engines(catalog, 1)
        self.assertEqual(locomotive["engine_id"], 22)
        self.assertEqual(wagon["engine_id"], 55)

    def test_catalog_choice_rejects_missing_live_capability(self):
        with self.assertRaisesRegex(probe.base.ProbeError, "locomotive"):
            probe.choose_engines([], 1)
        with self.assertRaisesRegex(probe.base.ProbeError, "wagon"):
            probe.choose_engines([
                {"engine_id": 2, "buildable": True, "railveh_type": 0,
                 "default_cargo": 255, "default_capacity": 0,
                 "railtypes": 1, "purchase_cost": 1},
            ], 1)

    def test_catalog_choice_does_not_confuse_passengers_or_multihead_with_coal_wagon(self):
        locomotive = {"engine_id": 7, "buildable": True, "railveh_type": 0,
                      "railtypes": 1, "purchase_cost": 10}
        for wrong_wagon in (
            {"railveh_type": 2, "default_cargo": 0, "railtypes": 1},
            {"railveh_type": 1, "default_cargo": 1, "railtypes": 1},
            {"railveh_type": 2, "default_cargo": 1, "railtypes": 2},
        ):
            entry = {"engine_id": 8, "buildable": True, "purchase_cost": 1,
                     "default_capacity": 30, **wrong_wagon}
            with self.subTest(entry=entry):
                with self.assertRaisesRegex(probe.base.ProbeError, "wagon"):
                    probe.choose_engines([locomotive, entry], 1)

    def test_source_migration_requires_reference_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(probe.base.ProbeError, "schema-3 source manifest"):
                probe.source_outcomes(Path(directory) / "source.sav")

    def test_parts_scan_rejects_nonadvancing_cursor(self):
        class Admin:
            def copilot_train_parts(self, world, company, cursor, count, scan, timeout):
                return {"parts": [], "complete": False, "next_after_id": cursor}

        with self.assertRaisesRegex(probe.base.ProbeError, "did not advance"):
            probe.read_parts(Admin(), "world", 0, lambda: 1)

    def test_success_requires_new_head_and_exact_charge(self):
        previous = {"sequence": 2, "companies": [{"money": 100, "loan": 50}]}
        operation = {"hi": 3, "lo": 4}
        current = {"sequence": 3, "head": operation, "companies": [{"money": 90, "loan": 50}]}
        outcome = {"state_name": "completed", "actual_cost": 10, "operation": operation,
                   "sequence": 3, "head": operation}
        probe.require_success(previous, current, outcome, 10)
        for changed in ({**current, "head": None},
                        {**current, "companies": [{"money": 89, "loan": 50}]}):
            with self.assertRaisesRegex(probe.base.ProbeError, "cost, finances"):
                probe.require_success(previous, changed, outcome, 10)

    def test_catalog_reader_terminates_on_short_page(self):
        class Admin:
            def __init__(self):
                self.starts = []

            def copilot_rail_catalog(self, world, company, start, count, timeout):
                self.starts.append(start)
                return {
                    "start_index": start, "count": 16 if start == 0 else 1,
                    "engines": [{"engine_id": start + i} for i in range(16)]
                    if start == 0 else [{"engine_id": start}],
                    "company_railtypes": 1,
                }

        admin = Admin()
        records, pages = probe.read_catalog(admin, "world", 0, lambda: 1)
        self.assertEqual(len(records), 17)
        self.assertEqual(admin.starts, [0, 16])
        self.assertEqual(len(pages), 2)

    def test_catalog_reader_has_bounded_page_limit(self):
        class Admin:
            def copilot_rail_catalog(self, world, company, start, count, timeout):
                return {
                    "start_index": start, "count": 16,
                    "engines": [{"engine_id": start + i} for i in range(16)],
                    "company_railtypes": 1,
                }

        with self.assertRaisesRegex(probe.base.ProbeError, "bounded"):
            probe.read_catalog(Admin(), "world", 0, lambda: 1)

    def test_purchase_request_has_exact_method_arguments(self):
        identity = {
            "world_id": "world", "sequence": 2, "head": {"hi": 3, "lo": 4},
            "head_hi": 3, "head_lo": 4,
        }
        request, wire = probe.make_request(identity, 8255, 42, 100000, 7)
        self.assertEqual(request["engine_id"], 42)
        self.assertEqual(
            set(wire),
            {"world_id", "company_id", "depot_tile", "engine_id", "max_cost",
             "expected_sequence", "expected_head_hi", "expected_head_lo",
             "operation_hi", "operation_lo", "payload_hash_hi", "payload_hash_lo"},
        )


if __name__ == "__main__":
    unittest.main()
