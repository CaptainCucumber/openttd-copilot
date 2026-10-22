# Current status

Updated: 2026-10-22, America/Vancouver.

## Repository

- GitHub: [CaptainCucumber/openttd-copilot](https://github.com/CaptainCucumber/openttd-copilot), private.
- Planning and implementation checkpoints through the measured S3c throughput cohort are on `main`; local branch tracks `origin/main`. The S3c implementation and evidence are committed together under `Add measured OpenTTD throughput probe`; commit metadata and remote publication are verified during handoff.
- Git author and committer must use the repository-local GitHub no-reply identity in `AGENTS.md`. The user's work email is prohibited for this project.

## Outcome so far

**S3a transport/lifecycle, S3b vehicle, and S3c throughput checkpoints pass in OpenTTD 15.3.** S3a covers versioned requests, stable paging, lost-response reconciliation, pause refusal, saved outcomes, replay after reload, older-save detection, and changed-world detection. S3b covers vehicle purchase/order/readback, lost-purchase reconciliation, duplicate/conflict handling, save replay, and two full-load departures plus two destination-industry delivery deltas in an isolated one-train fixture. S3c measures five fresh worlds: 10,000 valid tile observations take 2.670s median / 2.678s p95, and 100 tested rail commands take 2.752s median / 2.755s p95. All 500 pieces were independently read back with the correct owner, no run borrowed money, and the normal profile stayed unchanged. The first model-free local chat seam opens that disposable generated map first, reads a bounded summary of existing industries, waits for the user's supported coal request, runs the vehicle probe in the same world after `build`, shows the live client while the job runs, and opens the completed save in the OpenTTD GUI. Construction still uses bounded fixtures; arbitrary route planning and normal-save attachment remain unsupported. See [lifecycle evidence](evidence/2026-10-22-lifecycle-probe.json), [vehicle evidence](evidence/2026-10-22-vehicle-probe.json), and [throughput evidence](evidence/2026-10-22-throughput-probe.json). Stock CargoMonitor still has no vehicle ID, so the delivery attribution is explicitly limited to this isolated fixture.

The first implementation checkpoint passes in real OpenTTD 15.3: an isolated server/client harness discovers a human company, reads the world, builds one rail piece and a two-tile station, verifies exact costs and ownership, and rejects duplicate track without mutation. Reloading a copied save preserves the result and performs no construction. **This is a control probe, not a working railway service or conversational Copilot.** See [test instructions](CONTROL_PROBE.md) and the [evidence report](evidence/2026-10-21-control-probe.json).

| Milestone | State | Evidence |
|---|---|---|
| M0: requirements, source research, durable plan | Complete as an initial baseline | [Plan](PROJECT_PLAN.md), [research](RESEARCH.md), [decisions](DECISIONS.md), [acceptance criteria](ACCEPTANCE.md) |
| M1: prove game control and choose adapter | In progress: S1/S2 and S3a–S3c pass | Real-engine rail/station control, Admin/lifecycle evidence, vehicle purchase/order/save-replay checks, isolated delivery observations, and the five-run throughput cohort pass. Arbitrary existing-save attachment, coexistence, crash-gap, and final adapter gates remain open. |
| M2: railway builder from structured intent | Planned | No implementation |
| M3: terrain, budget, and recovery reliability | Planned | No implementation |
| M4: conversational Copilot | Planned | No implementation |
| M5: usable local alpha | Planned | No implementation |

## Next work, in order

1. **User testing point:** run `python3 -B tools/run_lifecycle_probe.py`. Expect 12 `PASS` lines and a success manifest; this creates only disposable worlds. The earlier rail/station inspection remains available with `python3 tools/run_control_probe.py --inspect latest --open`.
2. **S3b — Vehicle and observation spike:** purchase/order/readback, lost-purchase reconciliation, duplicate prevention, save replay, train start, and two full-load deliveries now pass in the disposable fixture. The result is isolated one-train evidence; stock per-vehicle delivery attribution and the command/save crash gap remain open.
3. **Chat seam:** `python3 -B tools/copilot_chat.py` accepts the fixed coal request, shows the grounded intent, runs S3b only after `build`, and opens the completed save in the GUI. General route planning and normal-save attachment remain unsupported.
4. **S3c — Throughput measurement:** the bounded [throughput probe](THROUGHPUT_PROBE.md) passes its five-world OpenTTD 15.3 cohort and the proposed <5s observation / <30s construction targets. It returns an aggregate of the 10,000 rows rather than transporting every row, and the construction workload is 100 independent simple pieces rather than a route.
5. **Remaining M1 environment checks:** test attaching to representative copied existing saves and document the one-GameScript-slot/coexistence behavior. Current reloads use this project's generated worlds. Preserve the command/save crash gap as an explicit recovery limitation unless further evidence closes it.
6. **S4 — Adapter decision:** compare findings to every M1 exit criterion. Keep stock GameScript if sufficient; otherwise implement the smallest engine bridge that closes demonstrated gaps. Record the decision before the production adapter.
7. **S5 / M2 — First complete rail job:** replace the fixture delegation with the deterministic structured route builder; build, buy, order, run, and verify two full-load coal deliveries.

S1/S2 and the declared S3a rail fixture are complete. See [M1 in the plan](PROJECT_PLAN.md#m1--prove-control-and-select-the-integration) for remaining pass/fail criteria. No final adapter selection has been made.

## Implemented and tested checkpoint

- `tools/run_control_probe.py`: standard-library harness; isolated server/client profiles; copied app resources/OpenGFX; loopback-only game listener; no Admin authentication configured; version/config/content/source hashes; initial/final saves and failure logs.
- `game/copilot_probe/`: GameScript API 15; human-client company association; 13 observed industries and 14 currently available rail engines/wagons in the final fixture; bounded station/rail site search; engine test/execute accounting and readback.
- Final run `artifacts/control-probe/20261021T180450Z-f8fc9132/`: 90 rail + 750 station = **840 engine money units**; cash 100,000 → 99,160; existing loan unchanged at 100,000. Duplicate rail returns `ERR_ALREADY_BUILT`, costs zero, and changes no observed assets.
- `tools/check_probe_reload.py`: copied-save readback matches tile ownership/geometry, cash, loan, and recorded cost; no construction events; original final save hash unchanged. This is not general recovery or exactly-once execution evidence.
- `tools/run_throughput_probe.py`: five disposable worlds, 50,000 valid tile observations total, 500 tested/executed/read-back rail pieces total, per-run pause refusal and responsiveness samples, median/p95 aggregation, and source-hashed evidence. This is a simple-operation benchmark, not route-planning or full-row transport evidence.
- Normal profile configuration and three original saves retain identical content hashes and modification times. Failed setup attempts are retained and described in the work log.

## Confirmed decisions and provisional defaults

- Local play on macOS, one human company, external chat first.
- OpenTTD 15.3, temperate climate, standard vehicles and industries, no additional gameplay NewGRFs for the initial test profile.
- **User confirmed:** “Full train” means depart the mine fully loaded, then deliver to the power station. Production-based sizing is a separate later capability.
- “Current budget” means existing cash, with a disclosed operating reserve and no automatic loan increase.
- **User confirmed:** a custom OpenTTD build is acceptable; prioritize reliable control. Select the adapter based on evidence, with no requirement to preserve stock-app compatibility at the expense of reliability.
- **Recommendation under discussion:** use local MCP for the first conversational interface so compatible AI clients can supply their own model access; retain one deterministic game-control core and allow in-game chat later. This is not yet a user-confirmed change to M4 or a working integration. See [D010](DECISIONS.md#d010--recommend-mcp-as-the-first-conversational-interface).

The user answered both initial questions during this session. Remaining environment/profile choices are defaults to validate against the eventual test world.

## Local environment observed

- Workspace was empty and was not a Git repository when planning began. The user subsequently requested GitHub publication; see the repository section above.
- Installed executable reports OpenTTD **15.3** at `/Applications/OpenTTD.app`; runtime and binary hash verified in the probe.
- OpenGFX2 Classic 0.8.1 loads successfully from an isolated copy; content and bundled resource hashes are in the evidence report.
- Apple Silicon; Python 3.14.6, Node 24.3.0, CMake 4.4.2, Apple clang 21.0.0 observed. Ninja and `openttd` were not found on PATH.
- Original saves were not loaded or modified. No credentials were read or configured.

## Known uncertainties

Per-train delivery telemetry outside the isolated fixture; existing-save/GameScript coexistence; complete job cost accounting; mutation/journal/save crash windows; rejected/uncertain-operation resolution; route-planner coverage. S3c measures bounded stock-adapter throughput, but not production-sized row transfer or connected-route planning/execution.
