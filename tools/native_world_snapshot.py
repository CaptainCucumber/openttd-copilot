"""Bounded tile-window reader for the native Copilot bridge.

Pages are observations from separate game frames, never an atomic map snapshot.
Callers must revalidate affected tiles and costs before any construction.
"""

from __future__ import annotations

from typing import Any


class SnapshotChanged(RuntimeError):
    """The world or Copilot operation sequence changed during observation."""


def read_tile_window(
    client: Any,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    max_tiles: int = 4096,
    max_frame_span: int | None = None,
) -> dict[str, Any]:
    """Read a rectangular window, preserving each page's frame and scope.

    Tile IDs use OpenTTD's row-major ``y * map_width + x`` layout. The
    identity query on either side detects a loaded world or a Copilot command
    during the scan. Ordinary game changes between pages remain possible.
    """
    before = client.copilot_identity()
    map_width = before["map_width"]
    map_height = before["map_height"]
    for name, value in (("x", x), ("y", y), ("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    if x < 0 or y < 0 or width < 1 or height < 1:
        raise ValueError("tile window must have a nonnegative origin and positive size")
    if x + width > map_width or y + height > map_height:
        raise ValueError("tile window exceeds the observed map")
    if isinstance(max_tiles, bool) or not isinstance(max_tiles, int) or max_tiles < 1:
        raise ValueError("max_tiles must be positive")
    if width * height > max_tiles:
        raise ValueError("tile window exceeds max_tiles")
    if max_frame_span is not None and (
        isinstance(max_frame_span, bool) or not isinstance(max_frame_span, int)
        or max_frame_span < 0
    ):
        raise ValueError("max_frame_span must be nonnegative")

    world_id = before["world_id"]
    rows: list[list[dict[str, Any]]] = []
    pages: list[dict[str, int]] = []
    for row_y in range(y, y + height):
        row: list[dict[str, Any]] = []
        for offset in range(0, width, 32):
            start = row_y * map_width + x + offset
            count = min(32, width - offset)
            page = client.copilot_tile_snapshot(world_id, start, count)
            if (page["world_id"] != world_id or page["start_tile"] != start
                    or page["count"] != count
                    or [tile["tile"] for tile in page["tiles"]]
                    != list(range(start, start + count))):
                raise SnapshotChanged("tile page did not match the requested world and range")
            row.extend(page["tiles"])
            pages.append({"start_tile": start, "count": count, "frame": page["frame"]})
        rows.append(row)

    after = client.copilot_identity()
    if (after["world_id"] != world_id or after["sequence"] != before["sequence"]
            or after["map_width"] != map_width or after["map_height"] != map_height):
        raise SnapshotChanged("world or Copilot operation sequence changed during tile scan")
    frames = [before["frame"], after["frame"]] + [page["frame"] for page in pages]
    frame_min, frame_max = min(frames), max(frames)
    if max_frame_span is not None and frame_max - frame_min > max_frame_span:
        raise SnapshotChanged("tile scan exceeded the allowed frame span")
    return {
        "world_id": world_id,
        "sequence": before["sequence"],
        "origin": {"x": x, "y": y},
        "size": {"width": width, "height": height},
        "map_width": map_width,
        "frame_min": frame_min,
        "frame_max": frame_max,
        "pages": pages,
        "rows": rows,
        "atomic": False,
    }
