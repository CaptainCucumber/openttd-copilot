from pathlib import Path
import json
import tempfile
import unittest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_native_infrastructure_probe as probe


class NativeInfrastructureProbeTests(unittest.TestCase):
    def test_operation_parts_and_hash_are_stable(self):
        value = (1 << 127) + 7
        self.assertEqual(probe.operation_parts(value), (1 << 63, 7))
        request = {"tile": 8255, "infrastructure_kind": 1, "length": 2}
        self.assertEqual(probe.payload_hash(request), probe.payload_hash(dict(request)))

    def test_site_selection_requires_adjacent_station_tiles_and_separate_depot(self):
        tiles = [
            {"tile": 8254, "height": 3}, {"tile": 8255, "height": 3},
            {"tile": 8260, "height": 3},
        ]
        station, depot = probe.select_infrastructure_sites(tiles, 8254, 64, 256, 0)
        self.assertEqual(station["tile"], 8254)
        self.assertEqual(depot["tile"], 8260)
        with self.assertRaisesRegex(probe.base.ProbeError, "station footprint"):
            probe.select_infrastructure_sites(
                [{"tile": 1, "height": 0}, {"tile": 9, "height": 0}], 1, 8, 8, 0,
            )

    def test_site_selection_rejects_row_wrap_and_height_mismatch(self):
        tiles = [
            {"tile": 7, "height": 1}, {"tile": 8, "height": 1},
            {"tile": 16, "height": 2}, {"tile": 24, "height": 2},
        ]
        with self.assertRaisesRegex(probe.base.ProbeError, "station footprint"):
            probe.select_infrastructure_sites(tiles, 7, 8, 8, 0)
        station, _ = probe.select_infrastructure_sites(
            [{"tile": 7, "height": 1}, {"tile": 15, "height": 1}, {"tile": 30, "height": 2}],
            7, 8, 8, 1,
        )
        self.assertEqual(station["tile"], 7)

    def test_make_request_binds_infrastructure_fields_and_hash(self):
        identity = {
            "world_id": "world", "sequence": 2, "head": {"hi": 3, "lo": 4},
            "head_hi": 3, "head_lo": 4,
        }
        request, wire = probe.make_request(identity, 8255, 1, 0, 2, 1000, 9)
        self.assertEqual(request["infrastructure_kind"], 1)
        self.assertEqual(request["length"], 2)
        self.assertEqual(wire["operation_lo"], 9)
        self.assertEqual(
            (wire["payload_hash_hi"], wire["payload_hash_lo"]),
            probe.payload_hash(request),
        )

    def test_site_selection_rejects_adjacent_unequal_height(self):
        with self.assertRaisesRegex(probe.base.ProbeError, "station footprint"):
            probe.select_infrastructure_sites(
                [{"tile": 2, "height": 1}, {"tile": 3, "height": 2},
                 {"tile": 7, "height": 2}], 2, 8, 8,
            )

    def test_asset_reader_pages_to_completion(self):
        class Admin:
            def __init__(self):
                self.starts = []

            def copilot_rail_assets(self, world, company, kind, start, count, timeout):
                self.starts.append(start)
                self.assert_timeout = timeout
                records = [{"station_id": i} for i in range(start, min(start + count, 17))]
                return {"count": len(records), "stations": records}

        admin = Admin()
        self.assertEqual(len(probe.read_assets(admin, "world", 1, 1)), 17)
        self.assertEqual(admin.starts, [0, 16])
        self.assertGreater(admin.assert_timeout, 0)

    def test_schema2_manifest_is_required_and_exactly_64_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            save = Path(temporary) / "sequence-final.sav"
            save.write_bytes(b"save")
            with self.assertRaisesRegex(probe.base.ProbeError, "manifest"):
                probe.legacy_sequence_records(save)
            (Path(temporary) / "manifest.json").write_text(
                json.dumps({"checks": {"reload_retains_records": {"retained_outcomes": []}}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(probe.base.ProbeError, "exactly 64"):
                probe.legacy_sequence_records(save)

    def test_engine_provenance_file_set_includes_command_type_and_admin_header(self):
        self.assertIn("src/command_type.h", probe.ENGINE_FILES)
        self.assertIn("src/network/network_admin.h", probe.ENGINE_FILES)


if __name__ == "__main__":
    unittest.main()
