# M2d checkpoint — industry pages and wider tile reads

Status: **read-only checkpoint passed; M2 remains in progress**, 2026-10-23.

The OpenTTD 15.3 fork adds protocol-v3 request kind 5 for paged industry IDs,
types, anchor tiles, and valid produced/accepted cargo IDs. A page contains at
most 16 records and its own frame. The Python tile-window reader combines
existing 32-tile pages by row, records every page frame, and checks world and
Copilot operation sequence before and after the scan. It marks the result
non-atomic. Neither endpoint sends a gameplay command.

## Real-engine result

The clean fork commit `9428e3ecdd98d066feb3f984bdeb266fe4a4c711` produced
a matching runtime revision. The final isolated run
`artifacts/native-industry-probe/20261023T181812Z-53cf83e7/manifest.json`
passed three checks in 2.139 seconds. Its [concise evidence](evidence/2026-10-23-native-industry-probe.json)
includes source and binary hashes, industry records, and tile-page frames.
The copied 128×128 temperate control save used seed 20261021, standard graphics,
company 0, and no gameplay NewGRFs.

- The bridge returned 13 industries with unique IDs, including coal producers
  and accepting power stations in this fixture. A wrong-world query returned
  status 5. Fresh-process reload returned the same industry records.
- A 35-by-2 window across four tile pages included the known owned rail and
  station tiles. Pages spanned distinct frames; the world ID and operation
  sequence remained fixed. Company cash stayed 99,160 and loan 100,000.
- The original save and normal OpenTTD profile were unchanged; temporary
  Admin secrets were removed. The source-hashed run sent no mutation request.

## Failure found and corrected

The first wider sweep, retained at
`artifacts/native-industry-probe/20261023T181250Z-fce131d6/`, crashed the
earlier tile endpoint. Its crash log identifies an assertion in `GetTileOwner`
for a house tile. OpenTTD has no company owner for house and industry tiles.
The native tile endpoint now reports `OWNER_NONE` for those types. The corrected
build passed the same sweep. The earlier four-tile test had not covered them.

Industry anchor tiles do not provide footprints or station catchment. Cargo
IDs here are capabilities, not proof that a proposed station will accept or
load cargo. Read-only pages can become stale between frames. The next M2d
slices need rail/vehicle availability, asset readback, station/depot search,
directed track planning, whole-job budget accounting, and typed sequential
construction. This checkpoint does not establish native end-to-end service or
the M3 recovery gate.
