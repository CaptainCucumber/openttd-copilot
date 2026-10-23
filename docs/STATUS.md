# Current status

Updated: 2026-10-23, America/Vancouver.

## Repository

- GitHub: [CaptainCucumber/openttd-copilot](https://github.com/CaptainCucumber/openttd-copilot), private.
- Planning and implementation checkpoints through M2a are kept on `main`; local branch tracks `origin/main`. Code, source-hashed evidence, decisions, and project records are committed together; commit metadata and remote publication are verified during each handoff.
- Git author and committer must use the repository-local GitHub no-reply identity in `AGENTS.md`. The user's work email is prohibited for this project.

## Outcome so far

**M2a is complete: the selected native bridge now has a measured read-only seam.** A custom OpenTTD 15.3 branch based directly on revision `14ec60f…` adds one authenticated, versioned, loopback-only identity request/response independent of the GameScript slot. The custom build identified the world and sole human company from an isolated copy of the representative autosave, rejected an unsupported bridge version, and remained responsive while a saved foreign GameScript advanced from tick 10 to 13 with zero mutations. See the [M2a report](M2A_REPORT.md), [probe instructions](NATIVE_BRIDGE_PROBE.md), and [evidence](evidence/2026-10-23-native-bridge-probe.json).

The first model-free local chat seam remains a disposable fixture demonstration. It opens a generated map, reads a bounded industry summary, waits for the supported coal request, runs the one-train vehicle probe after `build`, and shows the live/completed world. It is not the M2 route planner or a production adapter.

The first implementation checkpoint passes in real OpenTTD 15.3: an isolated server/client harness discovers a human company, reads the world, builds one rail piece and a two-tile station, verifies exact costs and ownership, and rejects duplicate track without mutation. Reloading a copied save preserves the result and performs no construction. **This is a control probe, not a working railway service or conversational Copilot.** See [test instructions](CONTROL_PROBE.md) and the [evidence report](evidence/2026-10-21-control-probe.json).

| Milestone | State | Evidence |
|---|---|---|
| M0: requirements, source research, durable plan | Complete as an initial baseline | [Plan](PROJECT_PLAN.md), [research](RESEARCH.md), [decisions](DECISIONS.md), [acceptance criteria](ACCEPTANCE.md) |
| M1: prove game control and choose adapter | **Complete** | Stock capability, lifecycle, vehicle, throughput, copied-save, and one-GameScript-slot evidence recorded. Production choice: narrow native OpenTTD bridge; see [M1 report](M1_REPORT.md). |
| M2: railway builder from structured intent | **In progress — M2a complete** | Native read-only bridge proven; typed mutation, telemetry, planner, and complete service remain open. |
| M3: terrain, budget, and recovery reliability | Planned | No implementation |
| M4: conversational Copilot | Planned | No implementation |
| M5: usable local alpha | Planned | No implementation |

## Next work, in order

1. **M2b — Typed mutation and recovery contract:** execute one bounded rail command through the normal game-thread command pipeline, return authoritative cost/readback, persist world/operation identity, and stop uncertain around the still-open mutation/save crash gap.
2. **M2c — Vehicle-tagged observation:** expose loaded-departure and delivered-cargo observations with vehicle identity, then reproduce the existing isolated service gate through the native bridge.
3. **M2d — Deterministic complete rail job:** replace fixture placement with typed intent, world snapshot, station/depot search, directed route planning, consist selection, whole-job pricing, execution, and two verified full-load deliveries.

M1 and M2a are complete. The bridge is read-only and does not yet satisfy M2's mutation, telemetry, planning, or end-to-end railway gate.

## Implemented and tested checkpoint

- `tools/run_control_probe.py`: standard-library harness; isolated server/client profiles; copied app resources/OpenGFX; loopback-only game listener; no Admin authentication configured; version/config/content/source hashes; initial/final saves and failure logs.
- `game/copilot_probe/`: GameScript API 15; human-client company association; 13 observed industries and 14 currently available rail engines/wagons in the final fixture; bounded station/rail site search; engine test/execute accounting and readback.
- Final run `artifacts/control-probe/20261021T180450Z-f8fc9132/`: 90 rail + 750 station = **840 engine money units**; cash 100,000 → 99,160; existing loan unchanged at 100,000. Duplicate rail returns `ERR_ALREADY_BUILT`, costs zero, and changes no observed assets.
- `tools/check_probe_reload.py`: copied-save readback matches tile ownership/geometry, cash, loan, and recorded cost; no construction events; original final save hash unchanged. This is not general recovery or exactly-once execution evidence.
- `tools/run_throughput_probe.py`: five disposable worlds, 50,000 valid tile observations total, 500 tested/executed/read-back rail pieces total, per-run pause refusal and responsiveness samples, median/p95 aggregation, and source-hashed evidence. This is a simple-operation benchmark, not route-planning or full-row transport evidence.
- `tools/run_environment_probe.py`: non-mutating copied-save and saved-GameScript-slot probe. The representative autosave stayed byte-for-byte and timestamp identical; Admin remained responsive; Copilot did not attach; the saved foreign script resumed with persisted state and zero gameplay mutations.
- `engine/`: reproducible patch and build instructions for fork commit `2850af59a`; the tested branch is `CaptainCucumber/OpenTTD:copilot/m2a-native-identity`.
- `tools/run_native_bridge_probe.py`: M2a copied-save and coexistence gate. Final run `artifacts/native-bridge-probe/20261023T160625Z-65d8877d/` passed both checks in 2.369 seconds with zero gameplay mutation requests. Its runtime revision string names engine commit `2850af59a`; the manifest also requires that exact clean checkout and hashes all four modified engine files.
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

Native mutation correctness and compatibility; durable world/operation identity; complete job cost accounting; mutation/journal/save crash windows; rejected/uncertain-operation resolution; vehicle-tagged telemetry; route-planner coverage; backwards/forwards handling of saves written by the custom build. M2a proves only the read-only seam.
