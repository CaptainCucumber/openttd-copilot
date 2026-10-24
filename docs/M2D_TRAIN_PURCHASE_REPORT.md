# M2d native rail vehicle purchase

Date: 2026-10-24. **Complete as a bounded purchase checkpoint; M2 remains open.**

The native bridge now buys a rail engine or wagon through normal OpenTTD
commands, rechecks a per-command cost cap, and retains the actual returned
VehicleID. Independent train-part pages verify what was created. This does
not assemble a train or start a service. See [D027](DECISIONS.md#d027--purchase-rail-vehicles-with-the-commands-returned-identity),
[operator instructions](NATIVE_TRAIN_PURCHASE_PROBE.md), and
[source-hashed evidence](evidence/2026-10-24-native-train-purchase-probe.json).

## Exact build and measured result

Engine branch `CaptainCucumber/OpenTTD:copilot/m2d-native-train-purchase`,
clean commit `7252756e936740771bac43fa74b66b050b8c68ce`, runtime
`20261024-m2d-native-train-purchase-g7252756e93`. Patch 0015 passes reverse
applicability. The dedicated asserted OpenTTD 15.3 build still emits the
installed macOS libpng/lzo deployment-target linker warnings.

Final run `artifacts/native-train-purchase-probe/20261024T221240Z-89c4c574/`
passed all three gates in **4.589 seconds**. It loaded an isolated copy of the
schema-3 infrastructure fixture: 128x128 temperate, seed 20261021, human
company 0, standard vehicles/industries, OpenGFX2 Classic 0.8.1, no gameplay
NewGRFs. Raw evidence records configuration/content/resource/binary/source
hashes, exact requests/replies, journal files, logs, and final save.

Live company/depot/catalog observations selected owned depot tile 8251,
currently buildable engine 0 and default coal wagon 29. The fixture uses
standard temperate coal cargo 1; it is not a generic cargo-label resolver.
The selector explicitly distinguishes single-head/multihead/wagon classes
0/1/2 and requires compatibility with the observed depot rail type.

| Purchase | Returned VehicleID | Actual cost | Independent result |
|---|---|---|---|
| Locomotive, engine 0 | 4 | 8,203 | Owned, stopped, in requested depot, separate primary chain |
| Coal wagon, engine 29 | 5 | 1,031 | Owned, empty, 30 coal capacity, separate free wagon |
| Second locomotive, engine 0 | 6 | 8,203 | Distinct stopped primary; did not adopt the free wagon |

Cash **97,870 -> 80,433**, loan unchanged at **100,000**.
Successful sequence **2 -> 5** and head matched the third purchase. The
second locomotive succeeded with an exact 8,203 cap; an 8,202 cap rejected
without charge. Zero cap, purchase on an owned station rather than depot,
unavailable catalog engine 1, and stock same-type free-wagon joining also
rejected without changing parts/assets, finances, or successful position.

Same operation ID with another engine and unchanged hash conflicted.
Wrong world, stale position, old rail/infrastructure status endpoints, and
old build endpoints refused mismatched requests. Exact purchase replay
preserved original ID/cost/frame with no new charge, asset, or head change.
Separate fsynced journals classified current, ahead, and older-save positions.

All four earlier schema-3 infrastructure outcomes migrated unchanged.
After saving schema 4 and fresh-process reload, all **12 retained outcomes**
(four earlier infrastructure, three purchases, five admitted purchase
rejections), parts, stations/depots, finances, and successful head matched.
Replay after reload again caused no mutation. The source save and normal
profile fingerprints were unchanged; private runtime credentials were removed.

The final client also passed clean-engine sequential regression at
`artifacts/native-sequence-probe/20261024T221147Z-8abe1be1/`
(including schema-1 migration/full history/older-save detection) and
infrastructure regression at
`artifacts/native-infrastructure-probe/20261024T221159Z-c6ec40aa/`
(including all 64 schema-2 outcomes before and after reload).
All **151 Python tests** pass. Final source/binary hashes match the raw
purchase manifest and concise evidence.

## Supported boundary and remaining gates

Request 13 is a typed default-cargo rail purchase, not a general vehicle
command. Request 14 adds engine ID to historical status and reads earlier
operation kinds too; old response layouts remain unchanged. COPL schema 4
migrates earlier histories and retains immutable engine/created identity.
No model-selected IDs, invented prices, or vehicle-pool inference determine
purchase success.

Normal ownership, engine availability, depot/rail compatibility, cash, and
vehicle limits remain authoritative. Locomotive adoption of free wagons is
disabled. Wagon purchase refuses a same-type free chain rather than silently
joining it. Multihead/articulated/default-cargo variations are admitted by
the normal primitive but were not runtime-tested in this checkpoint; neither
NewGRF nor multiplayer compatibility is established.

Created IDs describe the original outcome, not unreused perpetual identity.
The non-evicting history still has 64 records including rejections; jobs
that exceed it need a separately designed durable strategy, not eviction.
Pending/uncertain operations block further admission. No command/save/journal
atomicity, rollback, automatic uncertain purchase retry, or fault-injected
crash recovery is claimed.

Next: typed consist assembly and order/start configuration using these
retained identities, then deterministic catchment/site selection, directed
routing, whole-job budget/reserve, and two full-load deliveries on a completely
native-built railway. The playable MCP demo remains a separate GameScript
fixture, not arbitrary-existing-business construction.
