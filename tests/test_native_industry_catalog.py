from __future__ import annotations

import unittest

from tools.native_industry_catalog import read_industries, require_cargo_pair
from tools.native_world_snapshot import SnapshotChanged


class FakeClient:
    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.identities = [self.identity(1), self.identity(5)]
        self.repeat_first = False

    @staticmethod
    def identity(frame: int) -> dict:
        return {"world_id": "world-1", "sequence": 0, "frame": frame}

    def copilot_identity(self) -> dict:
        return self.identities.pop(0)

    def copilot_industry_snapshot(self, world_id: str, start: int, count: int) -> dict:
        records = self.records[start:start + count]
        if self.repeat_first and start:
            records = [self.records[0]]
        return {"world_id": world_id, "start_index": start, "count": len(records),
                "frame": start // 16 + 2, "industries": records}


class IndustryCatalogTests(unittest.TestCase):
    def test_exact_page_boundary_and_explicit_cargo_pair(self) -> None:
        records = [{"industry_id": n, "produced_cargo": [1] if n == 0 else [],
                    "accepted_cargo": [1] if n == 15 else []} for n in range(16)]
        result = read_industries(FakeClient(records))
        self.assertEqual([p["count"] for p in result["pages"]], [16, 0])
        self.assertEqual(len(result["industries"]), 16)
        self.assertEqual(require_cargo_pair(result, source_id=0, destination_id=15,
                                            cargo_id=1), (records[0], records[15]))
        self.assertFalse(result["atomic"])

    def test_changed_sequence_duplicate_ids_and_missing_cargo_fail(self) -> None:
        records = [{"industry_id": n, "produced_cargo": [],
                    "accepted_cargo": []} for n in range(17)]
        client = FakeClient(records)
        client.identities[-1]["sequence"] = 1
        with self.assertRaisesRegex(SnapshotChanged, "sequence changed"):
            read_industries(client)
        client = FakeClient(records)
        client.repeat_first = True
        with self.assertRaisesRegex(SnapshotChanged, "repeated"):
            read_industries(client)
        with self.assertRaisesRegex(ValueError, "source does not advertise"):
            require_cargo_pair({"industries": records}, source_id=0,
                               destination_id=1, cargo_id=1)

    def test_record_cap_stops_a_long_scan(self) -> None:
        records = [{"industry_id": n} for n in range(17)]
        with self.assertRaisesRegex(SnapshotChanged, "record limit"):
            read_industries(FakeClient(records), max_industries=16)


if __name__ == "__main__":
    unittest.main()
