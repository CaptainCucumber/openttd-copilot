from pathlib import Path
import tempfile
import unittest
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_native_sequence_probe as probe


class NativeSequenceProbeTests(unittest.TestCase):
    def test_operation_parts_and_payload_hash_are_deterministic(self):
        operation = (1 << 127) + 9
        self.assertEqual(probe.operation_parts(operation), ((1 << 63), 9))
        request = {"tile": 8255, "max_cost": 1000, "operation": {"hi": 1, "lo": 9}}
        self.assertEqual(probe.payload_hash(request), probe.payload_hash(dict(request)))

    def test_clear_flat_tiles_requires_live_observation_and_prefers_adjacent(self):
        class Admin:
            def copilot_tile_snapshot(self, world_id, start, count, timeout):
                tiles = []
                for tile in range(start, start + count):
                    tiles.append({
                        "tile": tile, "valid": True, "tile_type": 0, "owner": probe.OWNER_NONE,
                        "slope": 0, "track_bits": 0, "rail_type": 0,
                    })
                return {"tiles": tiles}

        tiles = probe.clear_flat_tiles(Admin(), "world", 8255, lambda: 1)
        self.assertEqual(tiles[0]["tile"], 8255)
        self.assertIn(8254, [tile["tile"] for tile in tiles])
        self.assertEqual(len(tiles), 128)

    def test_engine_provenance_hashes_required_engine_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            for name in probe.ENGINE_FILES:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name, encoding="utf-8")
            responses = [
                mock.Mock(stdout="abc123\n"),
                mock.Mock(stdout=""),
                mock.Mock(returncode=0, stdout="OpenTTD 20261023-gabc123\n", stderr=""),
            ]
            with mock.patch.object(probe, "ENGINE_SOURCE", source), \
                    mock.patch.object(probe.subprocess, "run", side_effect=responses):
                result = probe.engine_provenance(Path("/custom/openttd"), False)
            self.assertEqual(result["head"], "abc123")
            self.assertEqual(set(result["source_hashes"]), set(probe.ENGINE_FILES))

    def test_make_request_binds_identity_and_wire_hash(self):
        identity = {
            "world_id": "world", "sequence": 2, "head": {"hi": 3, "lo": 4},
            "head_hi": 3, "head_lo": 4,
        }
        request, wire = probe.make_request(identity, 8254, 0, 17)
        self.assertEqual(request["expect_sequence"], 2)
        self.assertEqual(request["expect_head"], {"hi": 3, "lo": 4})
        self.assertEqual((wire["operation_hi"], wire["operation_lo"]), (0, 17))
        self.assertEqual(
            (wire["payload_hash_hi"], wire["payload_hash_lo"]),
            probe.payload_hash(request),
        )

    def test_reads_legacy_operation_identity_from_m2b_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            save = directory / "completed-native-mutation.sav"
            save.write_bytes(b"save")
            (directory / "manifest.json").write_text(
                '{"checks":{"native_mutation_completed":{"accepted":'
                '{"operation_hi":99,"operation_lo":100},'
                '"final":{"state_name":"completed","operation_hi":3,"operation_lo":4,'
                '"payload_hash_hi":5,"payload_hash_lo":6,"company_id":0,"tile":8255,'
                '"rail_type":0,"track":1,"max_cost":1000,"actual_cost":90,"frame":77}}}}',
                encoding="utf-8",
            )
            self.assertEqual(
                probe.legacy_operation_from_manifest(save),
                {
                    "operation_hi": 3, "operation_lo": 4,
                    "payload_hash_hi": 5, "payload_hash_lo": 6,
                    "company_id": 0, "tile": 8255, "rail_type": 0, "track": 1,
                    "max_cost": 1000, "actual_cost": 90, "frame": 77,
                },
            )

    def test_requires_legacy_save_instead_of_skipping_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(probe.base.ProbeError, "required schema-1 save"):
                probe.run_legacy_gate(mock.Mock(), Path(temporary) / "missing.sav", mock.Mock())

    def test_reload_accepts_historical_position_as_ahead(self):
        class Journal:
            def __init__(self, name, sequence, head, classification):
                self.path = Path(name)
                self.position = ("world", sequence, head)
                self._classification = classification

            def classify_position(self, identity):
                return self._classification

        journals = [
            Journal("first.json", 1, (1, 2), "ahead"),
            Journal("latest.json", 2, (3, 4), "current"),
        ]
        classifications = probe.verify_reload_journal_positions(
            journals, {"sequence": 2, "head": {"hi": 3, "lo": 4}},
        )
        self.assertEqual(classifications, {"first.json": "ahead", "latest.json": "current"})

        for journal in (
            Journal("diverged.json", 2, (9, 9), "diverged"),
            Journal("newer.json", 3, (5, 6), "older_save"),
        ):
            with self.subTest(path=journal.path), self.assertRaises(probe.base.ProbeError):
                probe.verify_reload_journal_positions(
                    [journals[1], journal], {"sequence": 2, "head": {"hi": 3, "lo": 4}},
                )


if __name__ == "__main__":
    unittest.main()
