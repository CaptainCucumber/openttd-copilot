from __future__ import annotations

import unittest

from tools.native_rail_catalog import read_rail_catalog
from tools.native_world_snapshot import SnapshotChanged


class FakeClient:
    def __init__(self, count: int = 17) -> None:
        self.records = [{"engine_id": n, "buildable": n < 3} for n in range(count)]
        self.identities = [self.identity(1), self.identity(5)]
        self.change_railtypes = False
        self.repeat_id = False

    @staticmethod
    def identity(frame: int) -> dict:
        return {"world_id": "world-1", "sequence": 0, "frame": frame,
                "companies": [{"id": 0, "is_ai": False}]}

    def copilot_identity(self, company_id: int) -> dict:
        assert company_id == 0
        return self.identities.pop(0)

    def copilot_rail_catalog(self, world_id: str, company_id: int,
                             start: int, count: int) -> dict:
        records = [record.copy() for record in self.records[start:start + count]]
        if self.repeat_id and start:
            records[0]["engine_id"] = 0
        return {"world_id": world_id, "company_id": company_id,
                "start_index": start, "count": len(records),
                "company_railtypes": 2 if self.change_railtypes and start else 1,
                "frame": 2 + start // 16, "engines": records}


class RailCatalogTests(unittest.TestCase):
    def test_collects_ordered_pages_and_records_frame_span(self) -> None:
        result = read_rail_catalog(FakeClient(), company_id=0)
        self.assertEqual([page["count"] for page in result["pages"]], [16, 1])
        self.assertEqual(len(result["engines"]), 17)
        self.assertEqual(result["company_railtypes"], 1)
        self.assertEqual((result["frame_min"], result["frame_max"]), (1, 5))
        self.assertFalse(result["atomic"])

    def test_rejects_changed_catalog_and_world_sequence(self) -> None:
        client = FakeClient()
        client.change_railtypes = True
        with self.assertRaisesRegex(SnapshotChanged, "rail types changed"):
            read_rail_catalog(client, company_id=0)
        client = FakeClient()
        client.repeat_id = True
        with self.assertRaisesRegex(SnapshotChanged, "repeated"):
            read_rail_catalog(client, company_id=0)
        client = FakeClient()
        client.identities[-1]["sequence"] = 1
        with self.assertRaisesRegex(SnapshotChanged, "operation sequence"):
            read_rail_catalog(client, company_id=0)

    def test_rejects_invalid_company_and_record_cap(self) -> None:
        with self.assertRaises(ValueError):
            read_rail_catalog(FakeClient(), company_id=255)
        with self.assertRaisesRegex(SnapshotChanged, "record limit"):
            read_rail_catalog(FakeClient(), company_id=0, max_engines=16)


if __name__ == "__main__":
    unittest.main()
