# Current status

Updated: 2026-10-25, America/Vancouver.

## Repository

- GitHub: [CaptainCucumber/openttd-copilot](https://github.com/CaptainCucumber/openttd-copilot), private.
- Engine branch `copilot/m2e-town-buses` is published at `03ac6d9aee0163b3dbd71e1a3991b9f826702684`, exact fork SHA verified; matching clean server/client rebuilt and dispatcher patch 0022 exported/reverse-checked. Project F1 integration/evidence is published on `origin/main` at `08caaa6cd70dd03758e8b3397837bb97624e59f5`, exact GitHub ref verified; this records-only handoff follows. Historical bus acceptance remains on engine `faf823d8ab`; the earlier two-town baseline was `2fb530eda6`. Both repositories use the required no-reply Git identity.
- Git author and committer must use the repository-local GitHub no-reply identity in `AGENTS.md`. The user's work email is prohibited for this project.

## Outcome so far

**M2f F1 is verified: the bridge dispatcher is transport-neutral.** Engine
`03ac6d9aee` moves kinds 0-18 into a game-thread byte-in/byte-out dispatcher;
Admin retains authentication, loopback enforcement and framing. Clean-engine
coal construction/service passed (44 actions, 14,979, three full departures
and two deliveries), as did same-bus two-to-three-stop expansion (23 added
actions, 3,182, all 50 outcomes/reload/replay/older-save guards). Exact error
bytes passed 26 cases; four malformed payloads were refused with successful
reconnect and zero history use. Legacy coal reload/resave also passed. All
283 Python tests pass. See [evidence](evidence/2026-10-25-m2f-dispatcher.json).
**This is not the single-process launcher:** F2-F7, including the local
endpoint and single-player command semantics, remain open.

**Multi-town bus lines and adding stops are ready for bounded user testing
(R13/D033).** One line can
serve 2-8 ordered towns. Final-engine direct three-town gate
`20261025T175057Z-88a7a87a` passed actual passengers at all three stops and all
54 outcomes/reload/replay/older-save guards. Existing-line gate
`20261025T175339Z-be1d4f76` inserted Plontford between Pafingfield and Prarnway
on the same bus 5: 3,182/23 new actions, orders `[0,1] -> [0,2,1]`, passengers
at all three stops and all 50 combined outcomes reloaded/replayed. No second
bus/depot or old-order replacement. This selected insertion case uses an
explicit high-town-density generated world; the prior normal-density copied
line's attempted additions exceeded remaining history and were safely
refused. Eight stops and 64 shared records remain bounds, not a promise of
every route. Actual Copilot edited a copy exactly once, reached verified
operation, independently inspected orders and saved/closed using only native
tools. All 277 tests pass. See [evidence](evidence/2026-10-25-native-bus-lines.json)
and the [operator guide](NATIVE_PLAYABLE_ALPHA.md). M2f single-process work
remains planned.

**Town buses on normal maps are ready for bounded user testing.** The launcher
defaults to a randomly seeded ordinary 256x256 temperate world. Final clean
gate `20261025T003710Z-042103ac` built two stops, depot, 20 road tiles and bus 6
for 8,725, accepted 31 passengers at station 1 and five at station 0, and passed
all 27 outcomes/duplicate/reload/replay/older-save, malformed-field and
below-cap rejected-record guards. Actual Copilot build `20261025T003929Z-33e9b3d4`
reached verified operation, inspected real bus/orders and saved/closed using
only native tools. Coal and all 44 legacy resaved outcomes passed regressions.
All 263 tests pass. This is one selected pair, not random-map reliability or
measured profit. Earlier partial jobs are retained and never automatically retried.
See [report](M2E_TOWN_BUS_REPORT.md) and [evidence](evidence/2026-10-24-native-town-buses.json).

**Actual AI game conversation is available for user testing.** Run
`python3 -B tools/game_chat.py` using the installed, signed-in Copilot CLI.
Ask normally about the live game, compare coal routes with an explicit cap and
reserve, then authorize construction. Only inspection, read-only quotes and
cached status are autoallowed; construction retains host permission checks.
This uses the user's Copilot allowance without a new key/global MCP change.
The older `play_native.py` is model-free and does not meet the conversational
requirement. See [guide](NATIVE_PLAYABLE_ALPHA.md) for copied saves and for moving
from an existing standalone session; this does not attach to that running game.

**Measured bounds:** a real Copilot session resolved named Canley/Hunninghead
businesses, inspected live cash/assets, compared actual plans without building,
and saved/closed. Canley 10 -> 1 quoted 14,979/35 rails; Hunninghead 12 -> 1 was
rejected at a minimum 70 rails against the 50-rail limit. Fresh inspections
confirmed zero infrastructure/vehicles, sequence 0 and unchanged cash/loan.
Separate copied-service inspection read train 2, two parts, 30 coal capacity
and exact two orders without construction/history changes. The current bridge
does not expose profit, actual speed, production or station queues, so financial
optimization is not established. [Evidence](evidence/2026-10-24-native-game-chat.json).

**Planning-only failures now remain nonmutating and revisable.** The user's
12 -> 1 attempt was a preconstruction rejection, not partial work. A real same-map
regression rejected it without mutation, then built and verified 10 -> 1 for
14,979 with three full departures/two deliveries. Execution/uncertain failures
still block revised payloads. No normal configuration or original save is
overwritten. All 226 Python tests pass.

**M2's simple-profile exit now has native evidence.** Final gate
`20261024T230856Z-d0747072` passed in 228.091 seconds: 35 rail tiles, two
stations, depot, locomotive/wagon, 44 retained actions costing 14,979, three
30/30 departures and two accepted delivery cycles, proving both returns.
Whole-job low-budget refusal, no borrowing, independent orders/consist,
duplicate lookup and all-outcome fresh-process reload/replay passed.
Visible stdio MCP build/duplicate/saved-close and a selected-industry
quote/older-save regression also passed. See
[report](M2D_NATIVE_RAILWAY_REPORT.md) and
[evidence](evidence/2026-10-24-native-railway.json). This is one selected flat
standard-coal scenario, **not** the M3 reliability suite, general terrain,
conversational acceptance or a packaged release.

**M2d now assembles and configures native trains.** The clean engine attached the purchased coal wagon to its locomotive, appended exact full-load/no-unload and no-load/unload-if-possible orders, and explicitly started/stopped the primary. Independent parts/orders, no-op states, original start replay after stopping, all 24 outcomes after reload, and spare-vehicle preservation passed. Seven successful commands cost zero; normal running expense reduced cash 80,433 -> 80,431, loan unchanged 100,000. The primary began leaving the depot before stopping on its tile. This proves configuration, not a connected service. See [report](M2D_TRAIN_CONFIGURATION_REPORT.md), [probe](NATIVE_TRAIN_CONFIGURATION_PROBE.md), and [evidence](evidence/2026-10-24-native-train-configuration-probe.json).

**M2d purchases native rail vehicles with actual returned IDs.** The clean engine bought two locomotives at 8,203 each and a 30-capacity coal wagon at 1,031 in an observed owned depot. Cash 97,870 -> 80,433, loan unchanged 100,000. Independent parts confirmed three separate chains, no automatic adoption, exact-cap success, rejection below cap/at invalid depot/for unavailable engine, and no duplicate on replay. All 12 old/new retained outcomes and assets matched after fresh-process reload, including schema-3 migration. See [report](M2D_TRAIN_PURCHASE_REPORT.md), [probe](NATIVE_TRAIN_PURCHASE_PROBE.md), and [evidence](evidence/2026-10-24-native-train-purchase-probe.json).

**M2d now builds bounded native rail stations and depots.** Four clean-engine copied-world runs covered both station axes and all four depot directions. Each new two-tile station cost 750 and depot 540; cash 99,160 -> 97,870, loan unchanged at 100,000. Created IDs, independent geometry/ownership, retained rejection/success outcomes, replay without duplicates, and reload passed. All 64 populated schema-2 rail outcomes survived migration/reload; the sequential regression also passed schema-1 migration. This is not train purchase or a complete railway. See [report](M2D_INFRASTRUCTURE_REPORT.md), [probe](NATIVE_INFRASTRUCTURE_PROBE.md), and [evidence](evidence/2026-10-23-native-infrastructure-probe.json).

**M2a is complete: the selected native bridge now has a measured read-only seam.** A custom OpenTTD 15.3 branch based directly on revision `14ec60f…` adds one authenticated, versioned, loopback-only identity request/response independent of the GameScript slot. The custom build identified the world and sole human company from an isolated copy of the representative autosave, rejected an unsupported bridge version, and remained responsive while a saved foreign GameScript advanced from tick 10 to 13 with zero mutations. See the [M2a report](M2A_REPORT.md), [probe instructions](NATIVE_BRIDGE_PROBE.md), and [evidence](evidence/2026-10-23-native-bridge-probe.json).

**M2b is complete as a bounded one-piece checkpoint, not a railway builder.** Protocol v2 posts one capped single-rail command through normal OpenTTD command validation, returns actual cost and tile/company readback, and saves world/operation sequence and outcome. The committed custom binary passed cap rejection, one 90-unit build, duplicate replay, save/reload replay, and older-save classification in an isolated copied world. See the [M2b report](M2B_REPORT.md), [probe instructions](NATIVE_MUTATION_PROBE.md), and [evidence](evidence/2026-10-23-native-mutation-probe.json). Fault-injected pending-save recovery and the mutation/save crash gap remain open.

**M2d now supports bounded sequential native rail operations.** The clean custom build constructed two capped rail pieces for 90 units each, retained both outcomes across later commands and reload, and rejected changed-ID payloads and stale requests. COPL schema 2 retains 64 admitted records without eviction; all 64 were queried individually after reload, with exact old-ID replay causing no new charge. A completed schema-1 M2b save migrated and accepted a second command; older-save detection and source/profile preservation passed. This remains a rail-primitive checkpoint, not a route builder or whole-job budget. See [the sequence report](M2D_SEQUENCE_REPORT.md), [probe](NATIVE_SEQUENCE_PROBE.md), and [source-hashed evidence](evidence/2026-10-23-native-sequence-probe.json).

**M2c is complete as a vehicle-observation checkpoint.** Protocol v3 reports train departure load/capacity and exact industry-accepted cargo with the paying vehicle ID through a bounded, paged, runtime-only event ring. The committed custom binary observed the isolated fixture's assigned train leave its mine twice at 30/30 coal and deliver to the intended power-station industry on both trips. The GameScript still built and operated that fixture; native full-route construction remains open. See the [M2c report](M2C_REPORT.md), [probe instructions](NATIVE_VEHICLE_PROBE.md), and [evidence](evidence/2026-10-23-native-vehicle-probe.json).

**M2d has started with a read-only tile snapshot checkpoint.** An additive protocol-v3 request returns up to 32 contiguous tile records per page, including validity, tile type, owner, slope, height, and plain/crossing rail geometry. The clean custom build matched known rail/station/void tiles in a copied save, rejected a wrong world ID, and returned identical tiles after reload without company mutation. This is the first world-data seam for planning, not a complete route builder. See the [tile report](M2D_TILE_REPORT.md), [probe instructions](NATIVE_TILE_PROBE.md), and [evidence](evidence/2026-10-23-native-tile-probe.json).

**M2d now has industry names and location-bound observations alongside the cargo catalog.** The additive protocol-v3 request returned 13 named industries with positive rectangular bounds, cargo records matching the existing snapshot, correct coal source/destination names, and unchanged values after fresh-process reload. The probe also rechecked the wider tile sweep and rejected a wrong-world details request. These are `TileArea` bounds, not exact occupied-tile footprints. The clean committed fork passed without gameplay mutation. See the [industry details report](M2D_INDUSTRY_DETAILS_REPORT.md), [probe instructions](NATIVE_INDUSTRY_PROBE.md), and [source-hashed evidence](evidence/2026-10-23-native-industry-details-probe.json); the earlier [industry snapshot report](M2D_INDUSTRY_REPORT.md) remains the record of cargo paging and the house-tile fix.

**M2d also has read-only existing-asset checkpoints.** Company rail station/depot pages read a copied control station and a depot plus coal-accepting destination station in a copied service save. Bounded train-part pages returned a two-part locomotive/wagon consist with actual cargo and capacity. These probes passed against the clean `5f8b9d56af` engine build. See the [rail assets](M2D_RAIL_ASSETS_REPORT.md) and [train parts](M2D_TRAIN_PARTS_REPORT.md) reports. These observations do not prove native purchase, station placement, or route construction.

**M2d now includes train-order readback.** Protocol-v3 kind 9 pages up to 16 orders for an explicit owned primary train and reports engine-decoded type, destination, load/unload policy, and non-stop flags. Non-applicable fields are explicitly marked unavailable for other order types. OpenTTD 15.3 on a copied service save returned the full-load order to station 0 and no-load/unload order to station 1, unchanged after reload. Wrong-world, missing-company, and missing-train requests were rejected. See the [train-order report](M2D_TRAIN_ORDERS_REPORT.md) and [source-hashed evidence](evidence/2026-10-23-native-train-orders-probe.json). This observes configuration; it does not construct or validate a route.

**A playable AI-client demo is now available through local MCP tools.** `tools/mcp_server.py` opens a new disposable map, reports naturally generated coal businesses, accepts only the bounded coal-mine-to-power-station full-load request, runs the real-engine fixture, and returns the world ID plus verified delivery summary. The reported businesses are informational: the fixture creates separate controlled test industries and its multi-command job is still GameScript-based. It does not select arbitrary existing businesses or attach to normal saves. See [the demo guide](MCP_PLAYABLE_DEMO.md).

The first implementation checkpoint passes in real OpenTTD 15.3: an isolated server/client harness discovers a human company, reads the world, builds one rail piece and a two-tile station, verifies exact costs and ownership, and rejects duplicate track without mutation. Reloading a copied save preserves the result and performs no construction. **This is a control probe, not a working railway service or conversational Copilot.** See [test instructions](CONTROL_PROBE.md) and the [evidence report](evidence/2026-10-21-control-probe.json).

| Milestone | State | Evidence |
|---|---|---|
| M0: requirements, source research, durable plan | Complete as an initial baseline | [Plan](PROJECT_PLAN.md), [research](RESEARCH.md), [decisions](DECISIONS.md), [acceptance criteria](ACCEPTANCE.md) |
| M1: prove game control and choose adapter | **Complete** | Stock capability, lifecycle, vehicle, throughput, copied-save, and one-GameScript-slot evidence recorded. Production choice: narrow native OpenTTD bridge; see [M1 report](M1_REPORT.md). |
| M2: railway builder from structured intent | **Simple-profile exit complete** | Existing seed-6 businesses, whole-job affordability, native build/service, two returns, duplicate/reload/replay; see native railway report. |
| M2e: town buses and ordinary maps | **Bounded exit complete** | Clean-engine passenger service, 27 outcomes/reload/replay, cap/shape/rejected-record guards, coal/legacy regressions and actual native-only conversational build passed. |
| M2e follow-up: multi-town lines / adding stops | **Bounded exit complete** | Direct three-town service, same-bus middle insertion, all-stop passengers, all-outcome replay/older-save guards, actual-host edit/inspection/saved close; 277 tests pass. |
| M3: terrain, budget, and recovery reliability | Planned | No implementation |
| M4: conversational Copilot | **Bounded actual Copilot host integrated** | Live inspection, read-only comparison, explicit build boundary; broader paraphrase/ambiguity/cancellation/resumption acceptance remains open. |
| M5: usable local alpha | Planned release gate; development launcher available | Visible isolated native game can be tried now; packaging and representative-save acceptance remain open. |

## Next work, in order

1. **User testing point:** run `python3 -B tools/game_chat.py`, compare an ordered multi-town line with an explicit cap/reserve, then authorize it. Use `--seed 20261024` for Dudinghall -> Hudinghattan Ridge -> Drahill. To test adding a stop to the measured existing two-stop line, copy-load the commissioned world in the [guide](M2E_TOWN_BUS_REPORT.md#2026-10-25-follow-up-one-line-through-multiple-towns-and-added-stops) and ask to insert Plontford between Pafingfield and Prarnway. Save/close through the AI; partial/uncertain jobs are not retried. Broader normal-map feasibility remains unproven.
2. **M2f single-process local bridge (F1 verified; D032):** user confirmed local single-player only. Next is F2: `NoEst`, tick frames, pre-admission pause/game-mode/network/local-company guards and synchronous-callback audit. Then F3-F7 add the loopback token endpoint, portable Python path, lifecycle and actual-host acceptance before retiring server/client. See the [M2f plan](M2F_LOCAL_BRIDGE_PLAN.md) and [acceptance](ACCEPTANCE.md#m2f-single-process-gate). Cross-platform is required (R12): loopback TCP, not Unix sockets; F4 removes macOS-only Python code. No single-player mutation is supported yet.
3. **M3a/M3b:** establish varied independently feasible supported road/map cases, then inject reply/process/journal/save failures and cancellation. Prove reconciliation or explicit uncertainty; do not add terrain scope or automatic retries as shortcuts.
4. **M4a/M4b:** expose production/waiting-cargo/financial observations and observation-window evidence for useful advice, then held-out phrasing/ambiguity/unintended-action checks and authorized durable resumption.
5. **M5:** reproducible setup/compatibility, representative copied-save and restart/resume acceptance, packaging and a scoped release report. Keep the shared 64-record bound and no-autonomous-management direction explicit.

See [next milestone sequencing](PROJECT_PLAN.md#next-milestone-sequencing)
for the concrete exit evidence and dependencies.

M1 and the simple M2 path are complete within their recorded scopes. The native
backend selects explicit observed coal businesses, plans and prices a bounded
route, constructs it and verifies service. Ordinary-map passenger buses are the
active measured expansion; general terrain, shared networks, other transport
modes and M3 recovery gates remain open. Historical primitive
checkpoints below retain their original narrower conclusions.

## Implemented and tested checkpoint

- `tools/run_native_train_configuration_probe.py`: clean run `20261024T223606Z-54d739b4` passed schema-4 migration, native configuration, and fresh-process reload in 11.305 seconds. All 24 prior/new outcomes matched, historical start replay did not restart the stopped primary, and the spare locomotive/infrastructure were preserved. Already-running state was independently rechecked after its no-op, and stop used the live observed tile. All 166 Python tests pass. Final-client purchase/schema-3, rail/schema-1, and full-history infrastructure/schema-2 regressions passed on the same clean binary. Inspectable final world: `artifacts/native-train-configuration-probe/20261024T223606Z-54d739b4/train-configuration-final.sav`. This is a disconnected developer fixture, not the business-to-business playable job.

- `tools/run_native_train_purchase_probe.py`: clean run `20261024T221240Z-89c4c574` passed purchase, populated schema-3 migration, and fresh-process reload in 4.589 seconds. Eight new records (three purchases/five rejections) and four earlier infrastructure records survived individual comparison; exact replay and old/wrong-world/stale/conflict guards caused no mutations. All 151 Python tests pass. Rail/schema-1 and infrastructure/schema-2 regressions also passed against the final client and same clean binary. Runtime purchase coverage is a standard single-head engine and coal wagon, not multihead/articulated/NewGRF vehicles.

- `tools/run_native_infrastructure_probe.py`: four clean-revision runs recorded in the [report](M2D_INFRASTRUCTURE_REPORT.md) passed populated schema-2 migration, capped construction, independent created-asset readback, immutable replay, and fresh-process reload. Both station axes and all depot directions were tested at station length 2; other permitted lengths remain untested in real engine. All 135 Python tests pass. Patch 0014 and engine build instructions pin the exact revision.

- `tools/run_control_probe.py`: standard-library harness; isolated server/client profiles; copied app resources/OpenGFX; loopback-only game listener; no Admin authentication configured; version/config/content/source hashes; initial/final saves and failure logs.
- `game/copilot_probe/`: GameScript API 15; human-client company association; 13 observed industries and 14 currently available rail engines/wagons in the final fixture; bounded station/rail site search; engine test/execute accounting and readback.
- Final run `artifacts/control-probe/20261021T180450Z-f8fc9132/`: 90 rail + 750 station = **840 engine money units**; cash 100,000 → 99,160; existing loan unchanged at 100,000. Duplicate rail returns `ERR_ALREADY_BUILT`, costs zero, and changes no observed assets.
- `tools/check_probe_reload.py`: copied-save readback matches tile ownership/geometry, cash, loan, and recorded cost; no construction events; original final save hash unchanged. This is not general recovery or exactly-once execution evidence.
- `tools/run_throughput_probe.py`: five disposable worlds, 50,000 valid tile observations total, 500 tested/executed/read-back rail pieces total, per-run pause refusal and responsiveness samples, median/p95 aggregation, and source-hashed evidence. This is a simple-operation benchmark, not route-planning or full-row transport evidence.
- `tools/run_environment_probe.py`: non-mutating copied-save and saved-GameScript-slot probe. The representative autosave stayed byte-for-byte and timestamp identical; Admin remained responsive; Copilot did not attach; the saved foreign script resumed with persisted state and zero gameplay mutations.
- `engine/`: reproducible patch and build instructions for fork commit `2850af59a`; the tested branch is `CaptainCucumber/OpenTTD:copilot/m2a-native-identity`.
- `tools/run_native_bridge_probe.py`: M2a copied-save and coexistence gate. Final run `artifacts/native-bridge-probe/20261023T160625Z-65d8877d/` passed both checks in 2.369 seconds with zero gameplay mutation requests. Its runtime revision string names engine commit `2850af59a`; the manifest also requires that exact clean checkout and hashes all four modified engine files.
- `tools/run_native_mutation_probe.py`: M2b copied-save gate. Final run `artifacts/native-mutation-probe/20261023T163704Z-fb8cb770/` passed four checks in 3.252 seconds. The runtime revision string names clean engine commit `8b8f3d7bad`; the manifest hashes the binary and relevant source files. The 90-unit command reduced cash from 99,160 to 99,070, left loan at 100,000, and survived duplicate request and reload.
- `tools/run_native_vehicle_probe.py`: M2c generated-world service gate. Final run `artifacts/native-vehicle-probe/20261023T172550Z-485cd1fd/` passed native vehicle-tagged observation alongside the stock fixture's two-cycle gate in 160.388 seconds. The runtime revision names clean engine commit `37f88cc03d`; the manifest hashes the binary and source. Train 2 departed twice at 30/30 coal and delivered accepted cargo to industry 11 on both visits. The event ring is runtime-only and resets on world load.
- `tools/run_native_tile_probe.py`: M2d read-only tile gate. Final run `artifacts/native-tile-probe/20261023T174736Z-1b7db921/` passed in 1.654 seconds against clean engine commit `bf789a968c`; the manifest hashes binary and source. It matched the known rail piece, two station tiles, and void border, rejected a wrong-world query, and repeated the same tiles after fresh-process reload. No mutation request was sent.
- `tools/run_native_industry_probe.py`: read-only M2d industry and tile-window gate. Final regression run `artifacts/native-industry-probe/20261023T183111Z-92c08e46/` passed against clean fork commit `5f8b9d56af`, observing 13 industries and a four-page, 35-by-2 tile sweep. An earlier failed sweep exposed `GetTileOwner` asserting on a house tile; fix commit `4af552687f` reports houses/industries unowned. The failed crash artifact is retained.
- `tools/run_native_rail_catalog_probe.py`: read-only M2d human-company rail catalog gate. Final regression run `artifacts/native-rail-catalog-probe/20261023T183111Z-70babcc2/` passed against the same clean fork and observed 116 train definitions, 14 currently buildable. Wrong-world/missing-company rejection and fresh-process reload passed. No mutation request was sent.
- `tools/run_native_rail_assets_probe.py`: clean-build gate `artifacts/native-rail-assets-probe/20261023T183111Z-bd545e5d/` read the control station and service-world depot/two stations, including coal acceptance at the destination; wrong-world/missing-company and copied-save reload passed.
- `tools/run_native_train_parts_probe.py`: clean-build gate `artifacts/native-train-parts-probe/20261023T183058Z-927cf8e9/` returned no control-world train and one service-world two-part consist (primary train 2, wagon 3) with reciprocal links and coal cargo/capacity. No gameplay mutation request was sent.
- `tools/run_native_train_orders_probe.py`: clean-build gate `artifacts/native-train-orders-probe/20261023T200105Z-b32c26c8/` observed train 2's two orders: full load at station 0, then no-load/unload at station 1. Typed wrong-world, missing-company, and missing-train rejections and copied-save reload persistence passed. Normal config/saves and the source service save were unchanged.
- `tools/run_native_sequence_probe.py`: clean-engine gate `artifacts/native-sequence-probe/20261023T213034Z-f2d4546a/` passed nine checks in 11.716 seconds. Two 90-unit native builds reduced cash 99,160 -> 98,980, with loan unchanged at 100,000. All 64 admitted outcomes survived individual reload checks; journal-full, stale/conflict, schema-1 migration, old-ID replay, older-save detection, and source/profile preservation passed. All 122 Python tests pass.
- Normal profile configuration and three original saves retain identical content hashes and modification times. Failed setup attempts are retained and described in the work log.

## Confirmed decisions and provisional defaults

- Local play on macOS, one human company, external chat first.
- **User confirmed 2026-10-24:** local single-player only; multiplayer not needed. Planned single-process bridge (D032); the current implementation still uses server + client + Admin until M2f passes.
- OpenTTD 15.3, temperate climate, standard vehicles and industries, no additional gameplay NewGRFs for the initial test profile.
- **User confirmed:** “Full train” means depart the mine fully loaded, then deliver to the power station. Production-based sizing is a separate later capability.
- “Current budget” means existing cash, with a disclosed operating reserve and no automatic loan increase.
- **User confirmed:** a custom OpenTTD build is acceptable; prioritize reliable control. M1 evidence now selects a narrow native bridge; stock GameScript/Admin fixtures remain regression/reference tools rather than the production adapter.
- **Implemented provisional host:** installed signed-in Copilot CLI with session-local MCP, no new key/global server changes. Actual live advice and nonmutating planning are measured; the user's provider preference and broad M4 acceptance are not inferred. This supersedes the earlier D010 host recommendation; see D030/D031.

The user answered both initial questions during this session. Remaining environment/profile choices are defaults to validate against the eventual test world.

## Local environment observed

- Workspace was empty and was not a Git repository when planning began. The user subsequently requested GitHub publication; see the repository section above.
- Installed executable reports OpenTTD **15.3** at `/Applications/OpenTTD.app`; runtime and binary hash verified in the probe.
- OpenGFX2 Classic 0.8.1 loads successfully from an isolated copy; content and bundled resource hashes are in the evidence report.
- Apple Silicon; Python 3.14.6, Node 24.3.0, CMake 4.4.2, Apple clang 21.0.0 observed. Ninja and `openttd` were not found on PATH.
- Original saves are only used through isolated copies and remain unchanged.
  Disposable loopback Admin/client secrets are generated per run and removed
  during cleanup; no personal credentials are recorded in project evidence.

## Known uncertainties

General native compatibility beyond the measured coal and ordinary passenger
bus profiles; held-out normal-map feasibility; pending-save and mutation/journal/
save crash windows; uncertain-operation resolution and cancellation; event-ring
overflow and observation continuity; custom-save backward/forward compatibility;
durable host/job restart and representative-save release coverage. Complete-job
cost/reserve and actual transport are measured for the selected rail/bus runs,
not every terrain/content combination. Read-only pages span frames; industry
bounds are not occupied footprints; catalogs and configuration are not service
proof without live command/readback/delivery evidence. Profit, production rates
and station queues remain unavailable. The old GameScript demo is fixture-bound
and non-resumable; it is not the current native production path.
