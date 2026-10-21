# Current status

Updated: 2026-10-21, America/Vancouver.

## Repository

- GitHub: [CaptainCucumber/openttd-copilot](https://github.com/CaptainCucumber/openttd-copilot), private.
- Planning baseline published on `main`; local branch tracks `origin/main`. GitHub commit metadata and all ten initial project files were verified remotely.
- Git author and committer must use the repository-local GitHub no-reply identity in `AGENTS.md`. The user's work email is prohibited for this project.

## Outcome so far

The first implementation checkpoint passes in real OpenTTD 15.3: an isolated server/client harness discovers a human company, reads the world, builds one rail piece and a two-tile station, verifies exact costs and ownership, and rejects duplicate track without mutation. Reloading a copied save preserves the result and performs no construction. **This is a control probe, not a working railway service or conversational Copilot.** See [test instructions](CONTROL_PROBE.md) and the [evidence report](evidence/2026-10-21-control-probe.json).

| Milestone | State | Evidence |
|---|---|---|
| M0: requirements, source research, durable plan | Complete as an initial baseline | [Plan](PROJECT_PLAN.md), [research](RESEARCH.md), [decisions](DECISIONS.md), [acceptance criteria](ACCEPTANCE.md) |
| M1: prove game control and choose adapter | In progress: S1/S2 checkpoint passes | Two real-engine construction runs; final-source run and reload readback in the evidence report. Full M1 exit criteria still open. |
| M2: railway builder from structured intent | Planned | No implementation |
| M3: terrain, budget, and recovery reliability | Planned | No implementation |
| M4: conversational Copilot | Planned | No implementation |
| M5: usable local alpha | Planned | No implementation |

## Next work, in order

1. **User testing point:** inspect the saved probe using `python3 tools/run_control_probe.py --inspect latest --open`. Expected: company 0 owns rail at (64,64) and station tiles at (65,64)–(66,64); no trains yet. The command opens a fresh inspection copy.
2. **S3a — Transport and lifecycle spike:** round-trip versioned Admin/GameScript requests with paging, status lookup, reconnect, save/reload, and pause/unpause. Detect older-save loads and changed worlds. The current reload guard covers only this one-shot fixture.
3. **S3b — Complete M1 measurements:** prove vehicle purchase/order/readback and attributable delivery telemetry; measure 10,000 tile queries and 100 construction pieces across five runs. Check attaching to copied existing saves and coexistence with another GameScript.
4. **S4 — Adapter decision:** compare findings to every M1 exit criterion. Keep stock GameScript if sufficient; otherwise implement the smallest engine bridge that closes demonstrated gaps. Record the decision before the production adapter.
5. **S5 / M2 — First complete rail job:** use a fixed structured request and a known feasible flat map; build, buy, order, run, and verify two full-load coal deliveries.

S1/S2 are complete for the declared fixture. See [M1 in the plan](PROJECT_PLAN.md#m1--prove-control-and-select-the-integration) for remaining pass/fail criteria. No final adapter selection has been made.

## Implemented and tested checkpoint

- `tools/run_control_probe.py`: standard-library harness; isolated server/client profiles; copied app resources/OpenGFX; loopback-only game listener; no Admin authentication configured; version/config/content/source hashes; initial/final saves and failure logs.
- `game/copilot_probe/`: GameScript API 15; human-client company association; 13 observed industries and 14 currently available rail engines/wagons in the final fixture; bounded station/rail site search; engine test/execute accounting and readback.
- Final run `artifacts/control-probe/20261021T180450Z-f8fc9132/`: 90 rail + 750 station = **840 engine money units**; cash 100,000 → 99,160; existing loan unchanged at 100,000. Duplicate rail returns `ERR_ALREADY_BUILT`, costs zero, and changes no observed assets.
- `tools/check_probe_reload.py`: copied-save readback matches tile ownership/geometry, cash, loan, and recorded cost; no construction events; original final save hash unchanged. This is not general recovery or exactly-once execution evidence.
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

Adapter performance; complete telemetry for per-train deliveries; existing-save/GameScript coexistence; pause behavior; full command cost accounting; restart reconciliation; actual coverage of the route planner. These require real-engine experiments, not more architectural claims.
