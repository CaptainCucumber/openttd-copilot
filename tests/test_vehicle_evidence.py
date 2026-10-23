import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_vehicle_probe import validate_service_events, validate_native_service_events
from run_control_probe import ProbeError


class VehicleEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.telemetry = {"gap": None, "scope": "isolated_one_train"}
        self.fixture = {"source_station": 3, "destination_station": 4, "destination_industry": 2}
        departure = {"kind": "departure", "vehicle": 7, "tick": 20, "fleet_count": 1,
                     "load": 30, "capacity": 30, "source_station": 3, "source_load": 30,
                     "source_capacity": 30, "source_tick": 19, "profit": -100}
        delivery = {"kind": "delivery", "vehicle": 7, "tick": 40, "fleet_count": 1,
                    "load": 0, "capacity": 30, "destination_station": 4,
                    "destination_industry": 2, "amount": 30, "profit": 500}
        self.events = [departure, delivery,
                       {**departure, "tick": 60, "source_tick": 59, "profit": 450},
                       {**delivery, "tick": 80, "profit": 1100}]

    def test_two_observed_full_deliveries_pass_only_with_isolated_scope(self):
        result = validate_service_events(self.events, self.fixture, 7, self.telemetry)
        self.assertEqual(result["deliveries"], 2)
        self.assertEqual(result["scope"], "isolated_one_train")

    def test_other_vehicle_and_additional_fleet_cannot_claim_attribution(self):
        for field, value in [("vehicle", 8), ("fleet_count", 2)]:
            with self.subTest(field=field):
                events = copy.deepcopy(self.events)
                events[1][field] = value
                with self.assertRaises(ProbeError):
                    validate_service_events(events, self.fixture, 7, self.telemetry)

    def test_wrong_industry_and_load_decrease_without_delivery_are_rejected(self):
        for field, value in [("destination_industry", 99), ("destination_station", 99),
                             ("amount", 0), ("amount", 31), ("load", 30)]:
            with self.subTest(field=field, value=value):
                events = copy.deepcopy(self.events)
                events[1][field] = value
                with self.assertRaises(ProbeError):
                    validate_service_events(events, self.fixture, 7, self.telemetry)

    def test_partial_loading_and_missing_source_observation_are_rejected(self):
        for field, value in [("load", 29), ("source_load", 29), ("source_capacity", 29),
                             ("source_station", 99), ("source_tick", 21), ("capacity", 0)]:
            with self.subTest(field=field):
                events = copy.deepcopy(self.events)
                events[0][field] = value
                with self.assertRaises(ProbeError):
                    validate_service_events(events, self.fixture, 7, self.telemetry)

    def test_observation_gap_fails_even_when_recorded_deliveries_look_valid(self):
        for gap in ["fleet_not_isolated", "observe_exception", "event_overflow"]:
            with self.subTest(gap=gap):
                with self.assertRaises(ProbeError):
                    validate_service_events(self.events, self.fixture, 7,
                                            {"gap": gap, "scope": "isolated_one_train"})

    def test_loss_making_delivery_is_still_a_delivery(self):
        events = copy.deepcopy(self.events)
        events[1]["profit"] = -110
        validate_service_events(events, self.fixture, 7, self.telemetry)

    def test_missing_cycles_replayed_events_and_reordered_events_are_rejected(self):
        for events in [self.events[:2], self.events[1:], self.events[:2] * 2,
                       [self.events[0], self.events[2], self.events[1], self.events[3]]]:
            with self.subTest(events=events):
                with self.assertRaises(ProbeError):
                    validate_service_events(events, self.fixture, 7, self.telemetry)


class NativeVehicleEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = {"company": 0, "cargo": 1, "source_station": 3,
                        "destination_station": 4, "destination_industry": 2}
        self.events = [
            {"seq": 0, "kind": "departure", "frame": 20, "vehicle": 7, "company": 0,
             "station": 3, "cargo": 1, "amount": 30, "capacity": 30, "industry": 65535},
            {"seq": 1, "kind": "delivery", "frame": 40, "vehicle": 7, "company": 0,
             "station": 4, "cargo": 1, "amount": 5, "capacity": 30, "industry": 2},
            {"seq": 2, "kind": "departure", "frame": 60, "vehicle": 7, "company": 0,
             "station": 3, "cargo": 1, "amount": 30, "capacity": 30, "industry": 65535},
            {"seq": 3, "kind": "delivery", "frame": 80, "vehicle": 7, "company": 0,
             "station": 4, "cargo": 1, "amount": 5, "capacity": 30, "industry": 2},
        ]

    def test_two_vehicle_tagged_cycles(self):
        result = validate_native_service_events(self.events, self.fixture, 7)
        self.assertEqual((result["departures"], result["deliveries"]), (2, 2))

    def test_wrong_vehicle_destination_or_partial_departure(self):
        for index, field, value in [(1, "vehicle", 8), (1, "industry", 9),
                                    (0, "amount", 29), (2, "station", 9)]:
            with self.subTest(index=index, field=field):
                events = copy.deepcopy(self.events)
                events[index][field] = value
                with self.assertRaises(ProbeError):
                    validate_native_service_events(events, self.fixture, 7)

    def test_missing_or_replayed_event(self):
        for events in [self.events[:2], self.events[1:], self.events[:2] * 2]:
            with self.subTest(events=events):
                with self.assertRaises(ProbeError):
                    validate_native_service_events(events, self.fixture, 7)


if __name__ == "__main__":
    unittest.main()
