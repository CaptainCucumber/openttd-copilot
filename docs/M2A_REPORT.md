# M2a native bridge report

Date: 2026-10-23. Result: **complete**.

## Exit result

| Gate | Result | Evidence |
|---|---|---|
| Exact pinned OpenTTD fork and reproducible patch | Pass | Engine commit `2850af59a`; tracked patch SHA-256 `255ddcc7569ccb245edf8f72a7d824c89f75fe3ef457dcf609138267bb00c718` |
| Versioned authenticated message family | Pass | Protocol v1 request/response; unsupported v2 rejected; request correlation checked |
| Loopback-only boundary | Pass | Both game and Admin listeners bound to `127.0.0.1`; handler also rejects non-loopback peers |
| Existing-save read-only attachment | Pass | Copied representative autosave returned world fields and human company 0 |
| Independence from GameScript slot | Pass | Saved foreign script stayed loaded, advanced tick 10 to 13, and reported zero mutations while native queries succeeded |
| Preserve user data | Pass | Original autosave hash, size, mtime, normal configuration, and three normal autosaves remained unchanged |

The final real-engine run is
`artifacts/native-bridge-probe/20261023T160625Z-65d8877d/`. The published summary
is [here](evidence/2026-10-23-native-bridge-probe.json).

## Implemented boundary

The fork adds packet 11 from Admin to server and packet 130 from server to
Admin. The v1 request contains only protocol version, typed request kind,
correlation ID, and an explicit company selector. The response contains bounded
map/date/seed/frame fields and company ID, human/AI flag, signed cash, loan, and
name. Existing Admin authentication must already have completed. The handler
checks IPv4 or IPv6 loopback before returning state.

The handler runs in the existing Admin receive path on the game thread and does
not call `Game::instance`, replace the saved GameScript, invoke RCON, or expose
arbitrary commands. The external Python client validates framing, version,
request identity, status, booleans, UTF-8 names, record counts, and trailing
bytes.

## Honest boundary

The seed, map dimensions, landscape, and date are observed identity inputs, not
a durable save lineage. No new save chunk exists yet. The saved foreign fixture
world contains no company, so the gate separately proves company selection on
the representative autosave and GameScript coexistence on the saved foreign
world. This is sufficient for the M2a adapter seam; M2b must persist explicit
world and operation identity before claiming recovery safety.

M2a is read-only. It does not satisfy the M2 railway exit gate.

## M2b entry point

Add one allowlisted rail mutation using an explicit company, tile, rail type,
track piece, operation ID, payload hash, and cost cap. Test and execute it only
through OpenTTD's normal command pipeline, then return authoritative cost and
independent readback. Persist versioned world/operation identity and treat the
mutation/save/journal crash window as uncertain until reconciled.
