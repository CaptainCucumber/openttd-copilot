"""Collect a human company's native rail catalog without assuming atomic pages."""

from __future__ import annotations

from typing import Any

try:
    from tools.native_world_snapshot import SnapshotChanged
except ModuleNotFoundError:  # Direct execution of a probe from tools/.
    from native_world_snapshot import SnapshotChanged


def read_rail_catalog(client: Any, *, company_id: int,
                      max_engines: int = 4096) -> dict[str, Any]:
    """Read every train definition, retaining frame and company-railtype data.

    The bridge reports buildability at each page frame. Recheck selected
    engine IDs before purchase; this collection alone does not authorize one.
    """
    if isinstance(company_id, bool) or not isinstance(company_id, int) or not 0 <= company_id < 255:
        raise ValueError("company_id must identify a human company")
    if isinstance(max_engines, bool) or not isinstance(max_engines, int) or max_engines < 1:
        raise ValueError("max_engines must be positive")
    before = client.copilot_identity(company_id=company_id)
    if len(before["companies"]) != 1 or before["companies"][0]["id"] != company_id or before["companies"][0]["is_ai"]:
        raise SnapshotChanged("selected human company is absent from identity")
    world_id = before["world_id"]
    start = 0
    records: list[dict[str, Any]] = []
    pages: list[dict[str, int]] = []
    seen: set[int] = set()
    railtypes: int | None = None
    while True:
        page = client.copilot_rail_catalog(world_id, company_id, start, 16)
        count = page["count"]
        if (page["world_id"] != world_id or page["company_id"] != company_id
                or page["start_index"] != start or count != len(page["engines"])):
            raise SnapshotChanged("rail catalog page did not match the requested scope")
        if count > 16 or start + count > max_engines:
            raise SnapshotChanged("rail catalog exceeded its record limit")
        if railtypes is None:
            railtypes = page["company_railtypes"]
        elif railtypes != page["company_railtypes"]:
            raise SnapshotChanged("company rail types changed during catalog scan")
        for engine in page["engines"]:
            if engine["engine_id"] in seen:
                raise SnapshotChanged("engine ID repeated during catalog scan")
            seen.add(engine["engine_id"])
            records.append(engine)
        pages.append({"start_index": start, "count": count, "frame": page["frame"]})
        if count < 16:
            break
        start += count
    after = client.copilot_identity(company_id=company_id)
    if (after["world_id"] != world_id or after["sequence"] != before["sequence"]
            or len(after["companies"]) != 1 or after["companies"][0]["id"] != company_id
            or after["companies"][0]["is_ai"]):
        raise SnapshotChanged("world, operation sequence, or company changed during catalog scan")
    frames = [before["frame"], after["frame"]] + [page["frame"] for page in pages]
    return {"world_id": world_id, "company_id": company_id,
            "sequence": before["sequence"], "company_railtypes": railtypes,
            "frame_min": min(frames), "frame_max": max(frames),
            "pages": pages, "engines": records, "atomic": False}
