from __future__ import annotations

import unittest

from tools.native_world_snapshot import SnapshotChanged, read_tile_window


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []
        self.identities = [self.identity(10), self.identity(13)]
        self.bad_page = False

    @staticmethod
    def identity(frame: int) -> dict:
        return {"world_id": "world-1", "sequence": 4, "map_width": 64,
                "map_height": 64, "frame": frame}

    def copilot_identity(self) -> dict:
        return self.identities.pop(0)

    def copilot_tile_snapshot(self, world_id: str, start: int, count: int) -> dict:
        assert world_id == "world-1"
        self.calls.append((start, count))
        tiles = [{"tile": i, "valid": True} for i in range(start, start + count)]
        if self.bad_page:
            tiles[-1]["tile"] += 1
        return {"world_id": world_id, "start_tile": start, "count": count,
                "frame": 10 + len(self.calls), "tiles": tiles}


class TileWindowTests(unittest.TestCase):
    def test_crosses_page_boundary_without_reading_adjacent_rows(self) -> None:
        client = FakeClient()
        result = read_tile_window(client, x=20, y=2, width=35, height=2)
        self.assertEqual(client.calls, [(148, 32), (180, 3), (212, 32), (244, 3)])
        self.assertEqual([[t["tile"] for t in row] for row in result["rows"]],
                         [list(range(148, 183)), list(range(212, 247))])
        self.assertEqual((result["frame_min"], result["frame_max"]), (10, 14))
        self.assertFalse(result["atomic"])

    def test_rejects_changed_world_sequence_and_corrupt_page(self) -> None:
        client = FakeClient()
        client.identities[-1]["sequence"] = 5
        with self.assertRaisesRegex(SnapshotChanged, "sequence changed"):
            read_tile_window(client, x=0, y=0, width=1, height=1)
        client = FakeClient()
        client.bad_page = True
        with self.assertRaisesRegex(SnapshotChanged, "did not match"):
            read_tile_window(client, x=0, y=0, width=1, height=1)

    def test_rejects_oversized_and_stale_windows(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_tiles"):
            read_tile_window(FakeClient(), x=0, y=0, width=32, height=32,
                             max_tiles=100)
        with self.assertRaisesRegex(ValueError, "exceeds the observed map"):
            read_tile_window(FakeClient(), x=63, y=0, width=2, height=1)
        with self.assertRaisesRegex(SnapshotChanged, "frame span"):
            read_tile_window(FakeClient(), x=0, y=0, width=1, height=1,
                             max_frame_span=1)


if __name__ == "__main__":
    unittest.main()
