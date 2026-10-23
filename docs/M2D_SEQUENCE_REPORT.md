# M2d native sequence checkpoint

Status: **complete as a bounded rail-operation checkpoint**, 2026-10-23.
M2's complete railway and transport-service acceptance remains open.

## Change

The native bridge can now execute distinct capped rail operations sequentially,
retaining up to 64 admitted outcomes without eviction. Previously it refused a
second operation for the lifetime of the world.

Successful commands advance the global sequence and head. Rejected commands
consume a history record but leave that successful position unchanged.
Pending/uncertain operations block new admission. Exact old-ID replay returns
the retained result; changed fields/hash reject as an identity conflict.
Journal-full rejection never discards old records.

COPL schema 2 persists the active record and terminal history. Loading validates
indices, count, states, unique IDs, and sequence progression. Existing schema-1
single-record saves migrate in memory. Pending loads still become uncertain.
The wire format remains protocol v3, with an additive journal-full status 12.

Outcome cost/error/completion frame are historical; response sequence/head and
tile/company readback are current. External intent remains a separate fsynced
single-operation journal file for every admitted request.

## Real-engine evidence

Final run:
`artifacts/native-sequence-probe/20261023T213034Z-f2d4546a/`.
Elapsed: 11.716 seconds. Custom OpenTTD 15.3 engine commit:
`bded382135c91932c86f354f071b4f101af3b85e`; runtime revision:
`20261023-m2d-sequential-rail-gbded382135`.
The clean checkout, executable, relevant sources, copied resources/settings,
and source saves are fingerprinted in the manifest.

The copied control fixture is a 128x128 temperate map, seed 20261021,
standard industries/vehicles, company 0. Both rail commands used type 0,
track 1, and a 1,000-unit per-command cap.

| Gate | Observed result |
|---|---|
| Sequential construction | Tiles 8255 and 8254 built and read back owned track; 90 units each; sequence 0 -> 1 -> 2 |
| Cash and loan | Cash 99,160 -> 99,070 -> 98,980; loan unchanged at 100,000 |
| Historical replay | First outcome retained after second command, with original cost/frame and current position/readback; no second charge |
| Conflict/stale protection | Changed old-ID payload rejected with status 8; stale new request rejected with status 11 |
| Rejection position | Consecutive zero-cap rejections cost zero and preserve the second successful head |
| Capacity | 64 admitted records (two completed, 62 rejected); next new ID rejected with status 12 |
| Persistence | All 64 saved records queried individually after reload and matched their journaled immutable outcomes; old-ID build replay caused no mutation |
| Legacy migration | Completed schema-1 M2b operation migrated, another command advanced to sequence 2, and both old-ID replay and new outcome survived reload |
| Older save | Original source save classified older than retained operation journals |
| Preservation | Both original source saves and the normal configuration/saves unchanged; temporary secrets removed |

All 122 Python tests passed. The copied-save train-order regression also
passed readback/reload on the same native sources before the final clean
revision rebuild. Patch 0013 reverse-applies to the committed engine.

Three earlier diagnostic runs exposed verifier errors: clear-tile ownership
uses engine value 16, an earlier journal legitimately classifies a later
position as ahead, and the legacy manifest's pending acceptance response is
not its completed outcome. They are retained and described in the work log;
none is counted as a completed gate. Final integration additionally queries
every retained record, rejects diverged/newer local positions, and requires
the legacy source instead of silently skipping migration.

## Still open

This is not a connected-route or train-service result. The only gameplay
primitive remains one rail piece on a flat clear tile. Native station/depot
construction, vehicle purchase/orders, existing-industry site selection,
directed routing, whole-job pricing/reserve, and the two-delivery native
railway gate remain open.

The 64-record cap is deliberately finite and includes rejections. No eviction,
automatic cleanup, whole-job transaction, or exactly-once guarantee is added.
Pending-save fault injection, the mutation/save crash gap, corrupt-save
negative fixtures, multiplayer synchronization, and stock-build save
compatibility remain unproven. Earlier custom binaries are not expected to
load schema-2 saves.

Run instructions: [native sequence probe](NATIVE_SEQUENCE_PROBE.md).
Concise evidence: [source-hashed result](evidence/2026-10-23-native-sequence-probe.json).
