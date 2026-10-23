# M2d checkpoint — existing rail stations and depots

Status: **read-only checkpoint passed; M2 remains in progress**, 2026-10-23.

Protocol-v3 request kind 7 returns pages of up to 16 rail stations or depots
for an explicit human company and world. Station records contain ID, base
tile, train-platform tile/width/height, and current cargo acceptance mask.
Depot records contain ID, tile, entrance direction, and rail type. The query
uses the authenticated loopback Admin path and sends no gameplay command.

## Real-engine result

The clean OpenTTD 15.3 fork commit
`5f8b9d56af8f03e7794ef941e0172cbdff85c0de` produced a matching runtime
revision. The final copied-save run
`artifacts/native-rail-assets-probe/20261023T183111Z-bd545e5d/manifest.json`
passed control-world, reload, and service-world checks. The
[source-hashed evidence](evidence/2026-10-23-native-rail-assets-probe.json)
contains exact records and save hashes.

- In the control save, station 0 occupies a 2×1 platform starting at tile
  8257. The company owns no rail depot. A fresh-process reload returned the
  same records. Wrong-world and missing-company queries returned typed errors.
- In a separate copied service save, the endpoint observed stations 0 and 1
  and depot 0 at tile 3092, entrance direction 2, rail type 0. Station 1's
  acceptance mask included coal cargo ID 1. The original service save stayed
  byte-for-byte unchanged.
- Company cash, loan, and Copilot operation sequence were unchanged in the
  control gate. The original control save and normal profile were unchanged;
  temporary Admin secrets were removed. The service save's running company
  may earn or spend money with simulation time, so its read-only check binds
  world and operation sequence rather than assuming a static balance.

The fixture has no AI company, so the nonhuman-company rejection branch is
implemented and protocol-tested but lacks real-engine evidence. A current
acceptance mask describes an existing station. It cannot establish that a
proposed station site will accept or collect cargo. Industry footprints,
candidate catchment, station rail geometry, vehicle/consist and order
readback, construction, and recovery remain open.
