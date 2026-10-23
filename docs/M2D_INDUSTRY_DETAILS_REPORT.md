# M2d checkpoint — industry names and location bounds

Status: **read-only checkpoint passed; M2 remains in progress**, 2026-10-23.

Protocol-v3 request kind 10 adds an industry-details page without changing
existing kind 5. Each page contains at most eight records: industry ID/type,
anchor tile, OpenTTD `TileArea` width and height, cached UTF-8 display name,
explicit truncation marker, and valid produced/accepted cargo IDs. Names are
bounded to 96 encoded bytes and truncation is intended to stop on a code-point
boundary. The rectangle bounds the industry's location; it is **not** an exact
occupied-tile footprint. Names are display values, not stable identifiers.
Industry ID plus world identity remains the key.

## Real-engine result

The clean OpenTTD 15.3 fork commit
`211e780180c021b208a87d2612f4c24be9f743a6` built with runtime revision
`20261023-m2d-industry-snapshot-g211e780180`. The isolated copied-save run
`artifacts/native-industry-probe/20261023T201424Z-a96fafa0/manifest.json`
passed the industry-page, four-page tile-window, and fresh-process reload
checks in 2.277 seconds. See the
[concise source-hashed evidence](evidence/2026-10-23-native-industry-details-probe.json).

- The 128×128 temperate control save (seed 20261021, company 0, OpenGFX2
  Classic 0.8.1, no gameplay NewGRFs) returned 13 details records over two
  pages. Every name was nonempty and untruncated; every positive rectangle
  fit within map coordinates.
- IDs, types, anchors, and cargo lists matched the existing kind-5 pages.
  The coal source resolved to **Madhattan Coal Mine** (ID 0, tile 12404,
  3×4 bound); the accepting destination resolved to **Great Beninghall Power
  Station** (ID 12, tile 3371, 4×2 bound).
- A wrong-world kind-10 request returned typed status 5. Company cash
  (99,160), loan (100,000), and operation sequence (0) were unchanged around
  the read. Reload in a fresh process returned identical kind-5 and kind-10
  pages. The original save and normal profile were unchanged, and temporary
  Admin secrets were removed.
- The same run repeated the existing 35×2 tile-window sweep across four
  pages, including the known owned rail and station tiles.
- The regression train-order probe passed both its service-order readback and
  copied-save reload checks against the new engine build. All 109 Python tests
  passed.

The Python decoder tests exercise multibyte UTF-8 and explicit truncation
markers, but this fixture had no name long enough to trigger native
truncation. The C++ UTF-8 boundary handling is build- and code-reviewed, not
runtime-exercised with a truncated industry name.

This read adds names and location bounds only. It does not report the exact
occupied industry tiles, station catchment, station/depot construction
geometry, route feasibility, or a complete railway. Multi-page observations
can span frames and must be revalidated before future mutations.
