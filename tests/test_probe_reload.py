from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))
import check_probe_reload as checker  # noqa: E402


class ProbeReloadVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        rail_tiles = [{"tile": 8256, "owner": 0, "tracks": 1, "rail_type": 0, "station": 65535, "x": 64, "y": 64}]
        station_tiles = [
            {"tile": 8257, "owner": 0, "tracks": 1, "rail_type": 0, "station": 0, "x": 65, "y": 64},
            {"tile": 8258, "owner": 0, "tracks": 1, "rail_type": 0, "station": 0, "x": 66, "y": 64},
        ]
        self.original = {
            "events": [
                {"protocol": 1, "kind": "rail_built", "tiles": rail_tiles},
                {"protocol": 1, "kind": "station_built", "tiles": station_tiles},
                {
                    "protocol": 1,
                    "kind": "probe_complete",
                    "company": 0,
                    "cash_after": 99160,
                    "total_cost": 840,
                    "loan_before": 100000,
                    "loan_after": 100000,
                },
            ]
        }
        self.loaded = {
            "protocol": 1,
            "kind": "loaded_readback",
            "saved_state": "complete",
            "current_company": 0,
            "current_rail_tiles": rail_tiles,
            "current_station_tiles": station_tiles,
            "saved": {"total_cost": 840, "loan_before": 100000, "loan_after": 100000},
            "current_cash": 99160,
            "current_loan": 100000,
        }

    def assert_rejected(self, loaded: dict) -> None:
        with self.assertRaises(checker.ReloadError):
            checker.verify_reload(self.original, [loaded], [])

    def test_valid_readback_passes(self) -> None:
        result = checker.verify_reload(self.original, [self.loaded], [])
        self.assertTrue(result["money"]["cash_matches"])
        self.assertTrue(result["money"]["loan_stable"])

    def test_wrong_owner_is_rejected(self) -> None:
        loaded = deepcopy(self.loaded)
        loaded["current_rail_tiles"][0]["owner"] = 1
        self.assert_rejected(loaded)

    def test_missing_tile_is_rejected(self) -> None:
        loaded = deepcopy(self.loaded)
        loaded["current_station_tiles"].pop()
        self.assert_rejected(loaded)

    def test_replayed_construction_event_is_rejected(self) -> None:
        with self.assertRaises(checker.ReloadError):
            checker.verify_reload(self.original, [self.loaded, {"protocol": 1, "kind": "rail_built"}], [])

    def test_cash_or_loan_change_is_rejected(self) -> None:
        for field, value in (("current_cash", 99159), ("current_loan", 99999)):
            with self.subTest(field=field):
                loaded = deepcopy(self.loaded)
                loaded[field] = value
                self.assert_rejected(loaded)

    def test_lost_saved_state_is_rejected(self) -> None:
        loaded = deepcopy(self.loaded)
        loaded["saved_state"] = "loaded_readback"
        self.assert_rejected(loaded)


if __name__ == "__main__":
    unittest.main()
