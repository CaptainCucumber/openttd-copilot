"""Collect and validate the native bridge's paged industry observations."""

from __future__ import annotations

from typing import Any

try:
    from tools.native_world_snapshot import SnapshotChanged
except ModuleNotFoundError:  # Direct execution of a probe from tools/.
    from native_world_snapshot import SnapshotChanged


def read_industries(client: Any, *, max_industries: int = 4096) -> dict[str, Any]:
    """Read all current industries; record the non-atomic frame span.

    A changed world or Copilot operation sequence aborts the scan. Industry
    closure/creation and cargo changes can still occur between page frames;
    selected IDs and cargo must be rechecked immediately before planning and
    execution.
    """
    if isinstance(max_industries, bool) or not isinstance(max_industries, int) or max_industries < 1:
        raise ValueError("max_industries must be positive")
    before = client.copilot_identity()
    world_id = before["world_id"]
    start = 0
    records: list[dict[str, Any]] = []
    pages: list[dict[str, int]] = []
    seen: set[int] = set()
    while True:
        page = client.copilot_industry_snapshot(world_id, start, 16)
        count = page["count"]
        if page["world_id"] != world_id or page["start_index"] != start or count != len(page["industries"]):
            raise SnapshotChanged("industry page did not match the requested world and range")
        if count > 16 or start + count > max_industries:
            raise SnapshotChanged("industry scan exceeded its record limit")
        for industry in page["industries"]:
            if industry["industry_id"] in seen:
                raise SnapshotChanged("industry ID repeated during paged scan")
            seen.add(industry["industry_id"])
            records.append(industry)
        pages.append({"start_index": start, "count": count, "frame": page["frame"]})
        if count < 16:
            break
        start += count
    after = client.copilot_identity()
    if after["world_id"] != world_id or after["sequence"] != before["sequence"]:
        raise SnapshotChanged("world or Copilot operation sequence changed during industry scan")
    frames = [before["frame"], after["frame"]] + [page["frame"] for page in pages]
    return {"world_id": world_id, "sequence": before["sequence"],
            "frame_min": min(frames), "frame_max": max(frames),
            "pages": pages, "industries": records, "atomic": False}


def require_cargo_pair(catalog: dict[str, Any], *, source_id: int,
                       destination_id: int, cargo_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve explicit IDs and validate advertised production/acceptance."""
    if source_id == destination_id:
        raise ValueError("source and destination must differ")
    by_id = {item["industry_id"]: item for item in catalog["industries"]}
    if source_id not in by_id or destination_id not in by_id:
        raise ValueError("source or destination industry is absent from the observation")
    source, destination = by_id[source_id], by_id[destination_id]
    if cargo_id not in source["produced_cargo"]:
        raise ValueError("source does not advertise the requested cargo")
    if cargo_id not in destination["accepted_cargo"]:
        raise ValueError("destination does not advertise acceptance of the requested cargo")
    return source, destination
