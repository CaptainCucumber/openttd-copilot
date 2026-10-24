from pathlib import Path
from copy import deepcopy
import json
import tempfile
import unittest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_native_train_configuration_probe as probe


class NativeTrainConfigurationProbeTests(unittest.TestCase):
    def test_operation_parts_and_payload_hash_are_stable(self):
        value = (1 << 127) + 7
        self.assertEqual(probe.operation_parts(value), (1 << 63, 7))
        request = {"action": 5, "vehicle_id": 4, "target_id": 8, "policy": 1}
        self.assertEqual(probe.payload_hash(request), probe.payload_hash(dict(request)))

    def test_make_request_binds_all_configuration_fields(self):
        identity = {
            "world_id": "world", "sequence": 2, "head": {"hi": 3, "lo": 4},
            "head_hi": 3, "head_lo": 4,
        }
        request, wire = probe.make_request(
            identity, tile=100, action=5, vehicle_id=7, target_id=9,
            order_index=1, policy=1, operation=17,
        )
        self.assertEqual(
            (request["action"], request["vehicle_id"], request["target_id"],
             request["order_index"], request["policy"]),
            (5, 7, 9, 1, 1),
        )
        self.assertEqual((wire["operation_hi"], wire["operation_lo"]), (0, 17))
        self.assertEqual((wire["payload_hash_hi"], wire["payload_hash_lo"]),
                         probe.payload_hash(request))

    def test_make_request_rejects_invalid_action_policy_combinations(self):
        identity = {"world_id": "world", "sequence": 0, "head": None,
                    "head_hi": 0, "head_lo": 0}
        cases = [
            dict(action=3, vehicle_id=1, target_id=2, order_index=0, policy=0),
            dict(action=4, vehicle_id=1, target_id=probe.INVALID_ID, order_index=0, policy=0),
            dict(action=4, vehicle_id=1, target_id=2, order_index=1, policy=0),
            dict(action=5, vehicle_id=1, target_id=2, order_index=0, policy=2),
            dict(action=5, vehicle_id=1, target_id=0xFFFF, order_index=0, policy=0),
            dict(action=5, vehicle_id=1, target_id=2, order_index=2, policy=0),
            dict(action=6, vehicle_id=1, target_id=2, order_index=0, policy=1),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                probe.make_request(identity, tile=100, operation=1, **case)

    def test_source_default_points_at_retained_purchase_fixture(self):
        self.assertTrue(str(probe.DEFAULT_SAVE).endswith(
            "native-train-purchase-probe/20261024T221240Z-89c4c574/train-purchase-final.sav"
        ))

    def test_legacy_outcome_normalizes_configuration_sentinels(self):
        record = {key: 0 for key in (
            "operation", "payload_hash", "company_id", "tile", "rail_type", "track",
            "max_cost", "actual_cost", "error", "frame", "state", "length",
            "created_asset_id", "engine_id")}
        record["infrastructure_kind"] = 3
        current = {**record, "kind": 3, "vehicle_id": probe.INVALID_ID,
                   "target_id": probe.INVALID_ID, "order_index": 0, "policy": 0}
        self.assertEqual(probe.immutable_config(record), probe.immutable_config(current))
        for key in ("vehicle_id", "target_id", "order_index", "policy", "frame", "actual_cost"):
            with self.subTest(key=key):
                changed = {**current, key: current[key] + 1}
                self.assertNotEqual(probe.immutable_config(record), probe.immutable_config(changed))

    def test_source_reference_requires_success_and_matching_save_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            save = Path(directory) / "fixture.sav"
            save.write_bytes(b"copied fixture")
            manifest = {"status": "success", "checks": {"reload_retains_purchase": {
                "outcomes": [{}] * 12, "save": {"sha256": probe.base.sha256_file(save)}}}}
            path = save.parent / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(len(probe.source_reference(save)[0]), 12)
            for status, digest in (("failed", probe.base.sha256_file(save)), ("success", "wrong")):
                manifest["status"] = status
                manifest["checks"]["reload_retains_purchase"]["save"]["sha256"] = digest
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(probe.base.ProbeError):
                    probe.source_reference(save)

    def test_order_verifier_rejects_wrong_destination_or_policy(self):
        orders = [{"order_type": 1, "destination_id": 11, "load_type": 2,
                   "unload_type": 4, "nonstop_flags": 0},
                  {"order_type": 1, "destination_id": 12, "load_type": 4,
                   "unload_type": 0, "nonstop_flags": 0}]
        probe.require_orders(orders, [11, 12])
        for index, key, value in ((0, "load_type", 3), (0, "unload_type", 0),
                                  (1, "unload_type", 1), (1, "destination_id", 13),
                                  (0, "nonstop_flags", 1)):
            with self.subTest(index=index, key=key):
                bad = deepcopy(orders)
                bad[index][key] = value
                with self.assertRaises(probe.base.ProbeError):
                    probe.require_orders(bad, [11, 12])

    def test_consist_verifier_rejects_broken_links_or_changed_spare(self):
        common = {"owner": 0, "engine_id": 0, "tile": 99, "in_depot": True,
                  "cargo_type": 0, "cargo_capacity": 0, "cargo_amount": 0,
                  "previous_vehicle_id": probe.INVALID_ID, "next_vehicle_id": probe.INVALID_ID,
                  "is_primary": True, "stopped": True}
        original = [{**common, "vehicle_id": 4, "first_vehicle_id": 4},
                    {**common, "vehicle_id": 5, "first_vehicle_id": 5, "is_primary": False,
                     "engine_id": 29, "cargo_type": 1, "cargo_capacity": 30},
                    {**common, "vehicle_id": 6, "first_vehicle_id": 6}]
        attached = deepcopy(original)
        attached[0]["next_vehicle_id"] = 5
        attached[1].update(first_vehicle_id=4, previous_vehicle_id=4)
        probe.require_consist(attached, original, 4, 5)
        for index, key, value in ((0, "next_vehicle_id", 6), (1, "previous_vehicle_id", 6),
                                  (1, "cargo_capacity", 29), (2, "stopped", False)):
            with self.subTest(index=index, key=key):
                bad = deepcopy(attached)
                bad[index][key] = value
                with self.assertRaises(probe.base.ProbeError):
                    probe.require_consist(bad, original, 4, 5)


if __name__ == "__main__":
    unittest.main()
