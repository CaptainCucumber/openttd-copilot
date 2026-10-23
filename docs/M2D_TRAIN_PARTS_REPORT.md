# M2d checkpoint — company train consist parts

Status: **read-only checkpoint passed; M2 remains in progress**, 2026-10-23.

Protocol-v3 request kind 8 scans at most 256 vehicle pool IDs and returns at
most 16 owned train parts per page. It uses an exclusive vehicle-ID cursor and
reports whether the pool end was reached. Each part has its vehicle/engine ID,
company, primary train/root ID, previous and next links, unit number, tile,
state bits, cargo ID, amount, and capacity. This lets the client reconstruct
an observed consist without treating wagons as separate trains. Pages carry
their own frame and are not an atomic snapshot.

## Real-engine result

The clean OpenTTD 15.3 fork commit
`5f8b9d56af8f03e7794ef941e0172cbdff85c0de` produced a matching runtime
revision. The final copied-save run
`artifacts/native-train-parts-probe/20261023T183058Z-927cf8e9/manifest.json`
passed in 1.703 seconds. Its
[source-hashed evidence](evidence/2026-10-23-native-train-parts-probe.json)
records the exact parts, links, cargo, pages, and source save hashes.

- The control save returned no owned train parts. The service save returned
  primary train 2 (engine ID 0) linked to wagon part 3 (engine ID 29). Links
  were reciprocal and both parts identified root 2. The wagon reported coal
  cargo ID 1, amount 25, capacity 30 at its observed frame.
- Wrong-world and missing-company requests returned typed errors. The probe
  made no gameplay mutation, and both original saves, the normal profile,
  and temporary-secret checks passed.
- The industry, rail catalog, and station/depot probes also passed against
  this same clean engine revision. The Python suite passed 104 tests.

The cargo amount is a momentary observation, not a full-load departure. The
existing vehicle-tagged event ring remains the service observer. This query
does not report orders, prove who purchased the train, validate a proposed
consist, or resolve mutation/reload uncertainty. Train IDs can be reused and
multi-page scans can span frames; revalidate before acting. Native purchase,
orders, route construction, and two-delivery acceptance remain open.
