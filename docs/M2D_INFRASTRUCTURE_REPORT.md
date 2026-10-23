# M2d native station/depot checkpoint

Date: 2026-10-23. **Complete as a bounded construction checkpoint; M2 remains open.**

The dedicated OpenTTD 15.3 fork now builds capped new default rail stations and
depots for the human company through normal engine commands. Created asset
identity is retained alongside the immutable outcome. Protocol-v3 requests
11/12 extend the existing rail journal rather than introducing an untracked
construction path. See [D026](DECISIONS.md#d026--build-bounded-new-rail-stations-and-depots-through-normal-commands),
[operator instructions](NATIVE_INFRASTRUCTURE_PROBE.md), and
[source-hashed evidence](evidence/2026-10-23-native-infrastructure-probe.json).

## Exact build and environment

- Fork branch `CaptainCucumber/OpenTTD:copilot/m2d-native-infrastructure`,
  clean commit `2c4dfef1bdee73f9994323c8139afd25768db150`, reverse-checked
  patch 0014. Asserted dedicated build; existing installed libpng/lzo macOS
  deployment-target linker warnings remain.
- Runtime `20261023-m2d-native-infrastructure-g2c4dfef1bd`.
  All four acceptance manifests hash the same binary and seven relevant engine
  files, plus client/journal/probe sources. Exact revision and source hashes
  were checked against the final checkout.
- Isolated copies of the retained control world: 128x128 temperate,
  seed 20261021, company 0 human, standard industries/vehicles, OpenGFX2 Classic
  0.8.1, no gameplay NewGRFs. Raw manifests retain configuration/content/resource
  hashes, commands, responses, saved worlds, and logs.

## Real-engine results

All runs are under `artifacts/native-infrastructure-probe/`.

| Run | Station axis | Depot direction | Result |
|---|---|---|---|
| `20261023T215235Z-f535454c` | 0 | 0 | Three gates passed, 8.664 s |
| `20261023T215251Z-e59be4e7` | 1 | 1 | Three gates passed, 9.147 s |
| `20261023T215251Z-7afa0a5b` | 0 | 2 | Three gates passed, 9.216 s |
| `20261023T215251Z-be38e788` | 1 | 3 | Three gates passed, 9.171 s |

Each run first loads the published schema-2 save with 64 retained rail
outcomes, compares every immutable outcome, reads rail identity through
extended status, rejects a new infrastructure operation because history is
full, then saves/reloads schema 3 and checks all 64 outcomes again.

Each fresh construction world rejects a zero-cap station attempt, builds a
two-tile station at observed tile 8254 for **750**, rejects a zero-cap depot
attempt, and builds the observed depot site 8251 for **540**. The created IDs
are station 1 and depot 0. Successful sequence advances to 2; cash goes
**99,160 -> 97,870**, loan stays **100,000**. Both station axes and all four
depot directions were exercised; station lengths other than 2 were not.

Independent company-filtered asset pages establish the exact station platform
rectangle and depot tile/direction/rail type. Tile pages establish ownership
and tile type; original station/depot records remain unchanged. Zero-cap
rejections preserve finances, successful head/sequence, and asset sets.
Changed payload/old-rail-ID reuse, wrong world, stale position, and old
rail-only status are rejected. Exact replay preserves original cost/frame/ID
without a new charge or asset; after fresh-process reload all four admitted
outcomes (including both rejections) and built assets are unchanged. The
schema-2 source save, control source, and normal profile remain unchanged.

The clean sequential-rail regression also passed all nine gates at
`artifacts/native-sequence-probe/20261023T214829Z-6b0d5a99/`, including schema-1
migration, historical replay, full history, and older-save detection.
All **135 Python tests** pass.

## Honest limits and next gate

The API permits new default single-platform station length 1–7 and one-tile
depots on level clear land. It does not join/reuse stations, terraform, or
override normal authority, money, ownership, rail-type, or command rules.
Created IDs describe the original result, not perpetual live asset identity.
The plain-rail bit excludes station/depot geometry; use asset/tile pages.
Station pages do not report station-tile rail type; this checkpoint does not
claim an independent readback of that station-specific property.

The 64-record journal cap still includes admitted rejections. It is not yet
sufficient for an arbitrary-length railway; a durable history-growth strategy
is a prerequisite if the planned job cannot fit. Uncertain commands stop new
admission. No mutation/save/journal atomicity, automatic rollback, or
fault-injected crash recovery is claimed. Corrupt-save negative fixtures,
multiplayer, and stock-build compatibility remain unproven.

Next: typed train purchase/configuration with authoritative vehicle identity,
then deterministic station/catchment selection, directed routing, whole-job
cost/reserve, and a complete native-built railway with two verified full-load
deliveries. The MCP demo remains a separate GameScript fixture.
