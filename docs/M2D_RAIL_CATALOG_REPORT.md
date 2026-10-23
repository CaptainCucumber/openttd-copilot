# M2d checkpoint — company rail catalog

Status: **read-only checkpoint passed; M2 remains in progress**, 2026-10-23.

Protocol-v3 request kind 6 returns up to 16 train engine definitions per
page for an explicit human company and world. Each record includes current
buildability, rail vehicle class and compatible rail types, default cargo and
capacity, refit mask, purchase and running cost, speed, power, weight, and
nominal shortening factor. The page also reports the company's buildable rail
types and its observation frame. It uses the authenticated loopback Admin
boundary and sends no gameplay command.

## Real-engine result

The clean OpenTTD 15.3 fork at
`5f8b9d56af8f03e7794ef941e0172cbdff85c0de` produced a binary with the
matching revision. The final copied-save run
`artifacts/native-rail-catalog-probe/20261023T183111Z-70babcc2/manifest.json`
passed catalog and reload checks with an additional guarded multi-page
collector. The
[concise evidence](evidence/2026-10-23-native-rail-catalog-probe.json) records
source/binary hashes and all currently buildable entries.

- Company 0 exposed 116 train engine definitions, 14 currently buildable.
  Company rail type mask was 1. The buildable entries include a coal wagon
  with cargo ID 1, capacity 30, and engine ID 29. These IDs and prices are
  observations from this fixture, not constants for other worlds.
- Wrong-world and missing-company requests returned typed errors. Paging
  preserved ordered unique engine IDs. Fresh-process reload returned the same
  catalog. Cash, loan, operation sequence, source save, and normal profile
  were unchanged; temporary Admin secrets were removed.

Buildability and default capacity are candidate inputs. Refit callbacks,
articulated parts, actual consist length, final price, and command legality
still require normal OpenTTD build/refit validation and purchased-vehicle
readback. The catalog is not a vehicle purchase API or full route planner.

Industry footprints, station/depot assets, vehicle orders, and sequential
native construction remain to be implemented. M2's complete-service and M3's
recovery gates remain open.
