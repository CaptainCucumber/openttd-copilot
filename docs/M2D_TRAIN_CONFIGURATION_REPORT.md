# M2d native train configuration

Date: 2026-10-24. **Complete as a bounded configuration checkpoint; M2 remains open.**

The native bridge now attaches an explicit free wagon chain to an owned
primary train, appends two bounded station orders, and sets an explicit
running/stopped state through normal OpenTTD commands. Independent parts
and orders verify the result. This is not a connected or operating railway
between businesses. See [D028](DECISIONS.md#d028--configure-a-train-through-explicit-retained-actions-not-toggle-replay),
[operator instructions](NATIVE_TRAIN_CONFIGURATION_PROBE.md), and
[source-hashed evidence](evidence/2026-10-24-native-train-configuration-probe.json).

## Measured result

Clean engine `ff8bd20ef55b26505693e315d71d291967cce0a9`,
branch `CaptainCucumber/OpenTTD:copilot/m2d-native-train-configuration`,
runtime `20261024-m2d-native-train-configuration-gff8bd20ef5`.
Patch 0016 passes reverse applicability. The asserted dedicated build passed;
only previously recorded macOS libpng/lzo deployment-target warnings remain.

Final run
`artifacts/native-train-configuration-probe/20261024T223606Z-54d739b4/`
passed three gates in **11.305 seconds**, loading the published purchase
fixture: 128x128 temperate, seed 20261021, human company 0, standard vehicles
and industries, OpenGFX2 Classic 0.8.1, no gameplay NewGRFs.

| Step | Independent observed result |
|---|---|
| Attach | Locomotive 4 links to wagon 5, reciprocal previous/next links, one primary chain, empty 30-capacity coal cargo. Spare locomotive 6 unchanged. |
| Source order | Station 0, full-load-all 2, no-unload 4, non-stop 0. |
| Delivery order | Station 1, no-load 4, unload-if-possible 0, non-stop 0. No forced-unload policy is claimed. |
| Start/stop | Primary stopped flag becomes false, then true. Already-stopped/already-running requests complete without toggling. |
| Historical replay | Original attach/order/start outcomes stay immutable; replaying the old start after stopping does not restart the train. |
| Reload | All 24 outcomes, consist, exact orders, stopped state, spare vehicle, infrastructure, finances, and successful position match after fresh-process load. Replay of all 12 new IDs causes no mutation. |

Seven completed actions and five admitted rejections had **zero command
cost**, advancing successful sequence **5 -> 12**. Cash **80,433 -> 80,431**
includes two units of normal running expense while the locomotive briefly
ran; loan stayed **100,000**. Command caps do not reserve operating cash.
The primary began leaving the depot before stopping on tile 8251; its final
`in_depot` flag is false, while its wagon remains inside. No route reachability,
coal catchment, full-load departure, or cargo delivery is demonstrated here.

Five retained rejections covered a non-free locomotive attachment source,
missing station, wrong append index, start without two orders, and an
additional order while running/already at the two-order limit. That last
case does not isolate the running-state guard from the count guard.
Same-ID changed source/target/index/policy with unchanged hash conflicted;
wrong world, stale position, and all three old status endpoints refused.
Independent snapshots showed no guard-induced changes.

All 12 schema-4 purchase/infrastructure outcomes migrated unchanged. All
24 old/new outcomes were queried individually after schema-5 reload and
compared on immutable fields plus current head/sequence. Separate fsynced
journals distinguished current, ahead, and older-save positions. Source
save and normal profile fingerprints stayed unchanged; private runtime
credentials were removed.

Final-client regressions on the same clean binary passed:

- Purchase/schema-3: `artifacts/native-train-purchase-probe/20261024T223219Z-697f62e2/`.
- Rail/schema-1 and all 64 records: `artifacts/native-sequence-probe/20261024T223231Z-abec4fef/`.
- Infrastructure/all 64 schema-2 records: `artifacts/native-infrastructure-probe/20261024T223243Z-86e9ef09/`.

All **166 Python tests** pass. Raw manifests retain exact source, binary,
content/settings, save hashes, requests/replies, journal files, and logs.

## Failures and remaining gates

Two initial runs exposed verifier assumptions, not engine command failures.
`20261024T222925Z-bf3326bf` wrongly required unchanged cash while a locomotive
was running. Source inspection confirmed normal per-tick running cost
settles on an economy day, including accumulated ticks after stopping.
`20261024T223033Z-a838fc3d` wrongly required the started primary to remain
fully inside the depot. The gate now separately records running balance
movement, settles the known fixture's economy day, and checks actual
movement/state rather than suppressing it. Both failure artifacts remain.

Runtime coverage is one standard single-head/default coal wagon and two
owned stations, not articulated/multihead/NewGRF configurations, shared
orders, rivals, or multiplayer. Normal engine ownership validation remains
in force; a foreign-owned runtime fixture has not been added.

The shared 64-record non-evicting history remains finite. Pending/uncertain
blocks continuation. There is no automatic retry, rollback, exactly-once,
command/save atomicity, or fault-injected recovery claim.

Next: deterministic station catchment/site selection and directed routing
between existing businesses, complete-job affordability/reserve, a durable
capacity strategy, then two full-load departures and deliveries on a
completely native-built line. The playable MCP demo remains the separate
controlled GameScript fixture.
