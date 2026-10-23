# Current status

Updated: 2026-10-23, America/Vancouver.

## Repository

- GitHub: [CaptainCucumber/openttd-copilot](https://github.com/CaptainCucumber/openttd-copilot), private.
- Planning and implementation checkpoints through the M2d tile seam are on `origin/main`. This session adds industry and rail-catalog read-only checkpoints; the clean engine branch `copilot/m2d-industry-snapshot` is published at `9428e3ecdd98d066feb3f984bdeb266fe4a4c711`. Copilot repository publication is recorded in the work log. Code, source-hashed evidence, decisions, and project records are committed together; commit metadata and remote publication are verified during each handoff.
- Git author and committer must use the repository-local GitHub no-reply identity in `AGENTS.md`. The user's work email is prohibited for this project.

## Outcome so far

**M2a is complete: the selected native bridge now has a measured read-only seam.** A custom OpenTTD 15.3 branch based directly on revision `14ec60f…` adds one authenticated, versioned, loopback-only identity request/response independent of the GameScript slot. The custom build identified the world and sole human company from an isolated copy of the representative autosave, rejected an unsupported bridge version, and remained responsive while a saved foreign GameScript advanced from tick 10 to 13 with zero mutations. See the [M2a report](M2A_REPORT.md), [probe instructions](NATIVE_BRIDGE_PROBE.md), and [evidence](evidence/2026-10-23-native-bridge-probe.json).

**M2b is complete as a bounded one-piece checkpoint, not a railway builder.** Protocol v2 posts one capped single-rail command through normal OpenTTD command validation, returns actual cost and tile/company readback, and saves world/operation sequence and outcome. The committed custom binary passed cap rejection, one 90-unit build, duplicate replay, save/reload replay, and older-save classification in an isolated copied world. See the [M2b report](M2B_REPORT.md), [probe instructions](NATIVE_MUTATION_PROBE.md), and [evidence](evidence/2026-10-23-native-mutation-probe.json). Fault-injected pending-save recovery and the mutation/save crash gap remain open.

**M2c is complete as a vehicle-observation checkpoint.** Protocol v3 reports train departure load/capacity and exact industry-accepted cargo with the paying vehicle ID through a bounded, paged, runtime-only event ring. The committed custom binary observed the isolated fixture's assigned train leave its mine twice at 30/30 coal and deliver to the intended power-station industry on both trips. The GameScript still built and operated that fixture; native full-route construction remains open. See the [M2c report](M2C_REPORT.md), [probe instructions](NATIVE_VEHICLE_PROBE.md), and [evidence](evidence/2026-10-23-native-vehicle-probe.json).

**M2d has started with a read-only tile snapshot checkpoint.** An additive protocol-v3 request returns up to 32 contiguous tile records per page, including validity, tile type, owner, slope, height, and plain/crossing rail geometry. The clean custom build matched known rail/station/void tiles in a copied save, rejected a wrong world ID, and returned identical tiles after reload without company mutation. This is the first world-data seam for planning, not a complete route builder. See the [tile report](M2D_TILE_REPORT.md), [probe instructions](NATIVE_TILE_PROBE.md), and [evidence](evidence/2026-10-23-native-tile-probe.json).

**M2d now has industry and company rail-catalog read-only checkpoints.** Protocol-v3 industry pages report ID/type, anchor tile, and produced/accepted cargo IDs; the copied control save returned 13 industries. Rail catalog pages returned 116 train definitions, 14 currently buildable for human company 0, with compatibility and price fields. A wider tile sweep exposed and corrected an earlier assertion on house/industry owner lookup. The clean committed fork passed copied-save query and reload gates with no gameplay mutation. See the [industry report](M2D_INDUSTRY_REPORT.md), [catalog report](M2D_RAIL_CATALOG_REPORT.md), and their [industry](evidence/2026-10-23-native-industry-probe.json) and [catalog](evidence/2026-10-23-native-rail-catalog-probe.json) evidence.

The first model-free local chat seam remains a disposable fixture demonstration. It opens a generated map, reads a bounded industry summary, waits for the supported coal request, runs the one-train vehicle probe after `build`, and shows the live/completed world. It is not the M2 route planner or a production adapter.

The first implementation checkpoint passes in real OpenTTD 15.3: an isolated server/client harness discovers a human company, reads the world, builds one rail piece and a two-tile station, verifies exact costs and ownership, and rejects duplicate track without mutation. Reloading a copied save preserves the result and performs no construction. **This is a control probe, not a working railway service or conversational Copilot.** See [test instructions](CONTROL_PROBE.md) and the [evidence report](evidence/2026-10-21-control-probe.json).

| Milestone | State | Evidence |
|---|---|---|
| M0: requirements, source research, durable plan | Complete as an initial baseline | [Plan](PROJECT_PLAN.md), [research](RESEARCH.md), [decisions](DECISIONS.md), [acceptance criteria](ACCEPTANCE.md) |
| M1: prove game control and choose adapter | **Complete** | Stock capability, lifecycle, vehicle, throughput, copied-save, and one-GameScript-slot evidence recorded. Production choice: narrow native OpenTTD bridge; see [M1 report](M1_REPORT.md). |
| M2: railway builder from structured intent | **In progress — M2a/M2b/M2c complete; M2d observation slices proven** | Identity, one typed mutation, vehicle-tagged service observation, tiles, industries, and rail catalog proven; planner and native complete-route construction remain open. |
| M3: terrain, budget, and recovery reliability | Planned | No implementation |
| M4: conversational Copilot | Planned | No implementation |
| M5: usable local alpha | Planned | No implementation |

## Next work, in order

1. **M2d — Deterministic complete rail job:** add industry footprints/names, station/depot/vehicle asset readback and relevant settings; then station/depot search, directed route planning, whole-job pricing, sequential typed execution, and two verified full-load deliveries. Tile, industry cargo, and company rail catalog pages are available. Revalidate non-atomic observations before construction.
2. **M3 recovery tests:** fault-inject the pending-save and mutation/save/journal windows; do not retry an uncertain operation without reconciliation.

M1 and M2a–M2c are complete. The bridge only mutates one clear flat rail tile per world; M2's planning and native end-to-end railway gate remain open.

## Implemented and tested checkpoint

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
- `tools/run_native_industry_probe.py`: read-only M2d industry and tile-window gate. Final run `artifacts/native-industry-probe/20261023T181812Z-53cf83e7/` passed against clean fork commit `9428e3ecdd`, observing 13 industries and a four-page, 35-by-2 tile sweep. An earlier failed sweep exposed `GetTileOwner` asserting on a house tile; fix commit `4af552687f` reports houses/industries unowned. The failed crash artifact is retained.
- `tools/run_native_rail_catalog_probe.py`: read-only M2d human-company rail catalog gate. Final run `artifacts/native-rail-catalog-probe/20261023T181812Z-3feed216/` passed against the same clean fork and observed 116 train definitions, 14 currently buildable. Wrong-world/missing-company rejection and fresh-process reload passed. No mutation request was sent.
- Normal profile configuration and three original saves retain identical content hashes and modification times. Failed setup attempts are retained and described in the work log.

## Confirmed decisions and provisional defaults

- Local play on macOS, one human company, external chat first.
- OpenTTD 15.3, temperate climate, standard vehicles and industries, no additional gameplay NewGRFs for the initial test profile.
- **User confirmed:** “Full train” means depart the mine fully loaded, then deliver to the power station. Production-based sizing is a separate later capability.
- “Current budget” means existing cash, with a disclosed operating reserve and no automatic loan increase.
- **User confirmed:** a custom OpenTTD build is acceptable; prioritize reliable control. M1 evidence now selects a narrow native bridge; stock GameScript/Admin fixtures remain regression/reference tools rather than the production adapter.
- **Recommendation under discussion:** use local MCP for the first conversational interface so compatible AI clients can supply their own model access; retain one deterministic game-control core and allow in-game chat later. This is not yet a user-confirmed change to M4 or a working integration. See [D010](DECISIONS.md#d010--recommend-mcp-as-the-first-conversational-interface).

The user answered both initial questions during this session. Remaining environment/profile choices are defaults to validate against the eventual test world.

## Local environment observed

- Workspace was empty and was not a Git repository when planning began. The user subsequently requested GitHub publication; see the repository section above.
- Installed executable reports OpenTTD **15.3** at `/Applications/OpenTTD.app`; runtime and binary hash verified in the probe.
- OpenGFX2 Classic 0.8.1 loads successfully from an isolated copy; content and bundled resource hashes are in the evidence report.
- Apple Silicon; Python 3.14.6, Node 24.3.0, CMake 4.4.2, Apple clang 21.0.0 observed. Ninja and `openttd` were not found on PATH.
- Original saves were not loaded or modified. No credentials were read or configured.

## Known uncertainties

General native mutation compatibility beyond one clear flat tile; complete-job cost accounting; pending-operation save/load fault injection; mutation/journal/save crash windows; rejected/uncertain-operation resolution beyond the tested cases; event-ring overflow and save/reload continuity in a real game; route-planner coverage; backwards/forwards handling of saves written by the custom build. Tile, industry, and rail-catalog pages are read-only and can span frames. Tile rail bits exclude station/depot geometry; industry anchors omit footprints/names; train catalog values need purchase/refit readback. Station/depot and vehicle assets still require live queries. M2c proves vehicle-tagged observation in an isolated GameScript-built service, not native complete-route construction.
