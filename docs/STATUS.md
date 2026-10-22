# Current status

Updated: 2026-10-22, America/Vancouver.

## Repository

- GitHub: [CaptainCucumber/openttd-copilot](https://github.com/CaptainCucumber/openttd-copilot), private.
- Planning and implementation checkpoints through M1 are on `main`; local branch tracks `origin/main`. Code, source-hashed evidence, decisions, and project records are committed together; commit metadata and remote publication are verified during each handoff.
- Git author and committer must use the repository-local GitHub no-reply identity in `AGENTS.md`. The user's work email is prohibited for this project.

## Outcome so far

**M1 is complete: select a narrow native OpenTTD bridge for the production adapter.** S1–S3 prove stock GameScript/Admin control, lifecycle handling, isolated vehicle service, and adequate simple-operation throughput in OpenTTD 15.3. The final environment probe loaded an untouched copy of a representative user autosave: Admin remained responsive, but the configured Copilot GameScript did not attach. A saved foreign GameScript also retained the single script slot when Copilot was configured and both scripts were installed. Together with stock CargoMonitor's lack of vehicle identity, these are measured gaps—not speculative objections—and justify the smallest custom bridge described in [D013](DECISIONS.md#d013--select-a-narrow-native-openttd-bridge). See the [M1 report](M1_REPORT.md) and [environment evidence](evidence/2026-10-22-environment-probe.json).

The first model-free local chat seam remains a disposable fixture demonstration. It opens a generated map, reads a bounded industry summary, waits for the supported coal request, runs the one-train vehicle probe after `build`, and shows the live/completed world. It is not the M2 route planner or a production adapter.

The first implementation checkpoint passes in real OpenTTD 15.3: an isolated server/client harness discovers a human company, reads the world, builds one rail piece and a two-tile station, verifies exact costs and ownership, and rejects duplicate track without mutation. Reloading a copied save preserves the result and performs no construction. **This is a control probe, not a working railway service or conversational Copilot.** See [test instructions](CONTROL_PROBE.md) and the [evidence report](evidence/2026-10-21-control-probe.json).

| Milestone | State | Evidence |
|---|---|---|
| M0: requirements, source research, durable plan | Complete as an initial baseline | [Plan](PROJECT_PLAN.md), [research](RESEARCH.md), [decisions](DECISIONS.md), [acceptance criteria](ACCEPTANCE.md) |
| M1: prove game control and choose adapter | **Complete** | Stock capability, lifecycle, vehicle, throughput, copied-save, and one-GameScript-slot evidence recorded. Production choice: narrow native OpenTTD bridge; see [M1 report](M1_REPORT.md). |
| M2: railway builder from structured intent | Planned | No implementation |
| M3: terrain, budget, and recovery reliability | Planned | No implementation |
| M4: conversational Copilot | Planned | No implementation |
| M5: usable local alpha | Planned | No implementation |

## Next work, in order

1. **M2a — Native bridge skeleton:** fork the pinned OpenTTD 15.3 revision and add a versioned, loopback-only Copilot Admin message family independent of the GameScript slot. Prove read-only world/company identity on a copied existing save while a foreign GameScript continues running.
2. **M2b — Typed mutation and recovery contract:** execute one bounded rail command through the normal game-thread command pipeline, return authoritative cost/readback, persist world/operation identity, and stop uncertain around the still-open mutation/save crash gap.
3. **M2c — Vehicle-tagged observation:** expose loaded-departure and delivered-cargo observations with vehicle identity, then reproduce the existing isolated service gate through the native bridge.
4. **M2d — Deterministic complete rail job:** replace fixture placement with typed intent, world snapshot, station/depot search, directed route planning, consist selection, whole-job pricing, execution, and two verified full-load deliveries.

M1's bounded experiments and adapter decision are complete. This does not implement the chosen bridge or satisfy M2's end-to-end railway gate.

## Implemented and tested checkpoint

- `tools/run_control_probe.py`: standard-library harness; isolated server/client profiles; copied app resources/OpenGFX; loopback-only game listener; no Admin authentication configured; version/config/content/source hashes; initial/final saves and failure logs.
- `game/copilot_probe/`: GameScript API 15; human-client company association; 13 observed industries and 14 currently available rail engines/wagons in the final fixture; bounded station/rail site search; engine test/execute accounting and readback.
- Final run `artifacts/control-probe/20261021T180450Z-f8fc9132/`: 90 rail + 750 station = **840 engine money units**; cash 100,000 → 99,160; existing loan unchanged at 100,000. Duplicate rail returns `ERR_ALREADY_BUILT`, costs zero, and changes no observed assets.
- `tools/check_probe_reload.py`: copied-save readback matches tile ownership/geometry, cash, loan, and recorded cost; no construction events; original final save hash unchanged. This is not general recovery or exactly-once execution evidence.
- `tools/run_throughput_probe.py`: five disposable worlds, 50,000 valid tile observations total, 500 tested/executed/read-back rail pieces total, per-run pause refusal and responsiveness samples, median/p95 aggregation, and source-hashed evidence. This is a simple-operation benchmark, not route-planning or full-row transport evidence.
- `tools/run_environment_probe.py`: non-mutating copied-save and saved-GameScript-slot probe. The representative autosave stayed byte-for-byte and timestamp identical; Admin remained responsive; Copilot did not attach; the saved foreign script resumed with persisted state and zero gameplay mutations.
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

Native bridge implementation and compatibility; complete job cost accounting; mutation/journal/save crash windows; rejected/uncertain-operation resolution; route-planner coverage; backwards/forwards handling of saves written by the custom build. M1 selected the bridge but did not prove these M2/M3 capabilities.
