# Current status

Updated: 2026-10-21, America/Vancouver.

## Repository

- GitHub: [CaptainCucumber/openttd-copilot](https://github.com/CaptainCucumber/openttd-copilot), private.
- Planning baseline published on `main`; local branch tracks `origin/main`. GitHub commit metadata and all ten initial project files were verified remotely.
- Git author and committer must use the repository-local GitHub no-reply identity in `AGENTS.md`. The user's work email is prohibited for this project.

## Outcome so far

Planning foundation created. Source research identifies a plausible stock OpenTTD integration and concrete gaps that our construction and test design must cover. Documentation links, anchors, code fences, and whitespace checks pass. **There is no working Copilot yet, and no game integration has been tested.**

| Milestone | State | Evidence |
|---|---|---|
| M0: requirements, source research, durable plan | Complete as an initial baseline | [Plan](PROJECT_PLAN.md), [research](RESEARCH.md), [decisions](DECISIONS.md), [acceptance criteria](ACCEPTANCE.md) |
| M1: prove game control and choose adapter | Next | Source support exists; runtime proof pending |
| M2: railway builder from structured intent | Planned | No implementation |
| M3: terrain, budget, and recovery reliability | Planned | No implementation |
| M4: conversational Copilot | Planned | No implementation |
| M5: usable local alpha | Planned | No implementation |

## Next work, in order

1. **S1 — Isolated harness:** create a disposable OpenTTD 15.3 profile and fixture, pin settings/content, and capture startup/version evidence. Keep the normal installation and saves intact.
2. **S2 — Company control spike:** query a human company, industries, rail vehicles, and tiles; test/build/read back one rail piece and a station; measure the real cash charge. Run in the user's company context, not merely an AI-owned test company.
3. **S3 — Transport and lifecycle spike:** round-trip versioned requests with paging, status lookup, reconnect, save/reload, and pause/unpause. Measure map query and command throughput. Check attaching to a copied existing save and handling an already-installed GameScript.
4. **S4 — Adapter decision:** compare findings to M1 exit criteria. Keep stock GameScript if sufficient; otherwise specify and implement the smallest engine bridge that closes demonstrated gaps. Record evidence in an ADR before building the production adapter.
5. **S5 — First complete rail job:** use a fixed structured request and a known feasible flat map; build, buy, order, run, and verify two full-load coal deliveries.

See [M1 in the plan](PROJECT_PLAN.md#m1--prove-control-and-select-the-integration) for pass/fail criteria. S1–S4 are the next bounded engineering effort; the current session did not attempt them.

## Confirmed decisions and provisional defaults

- Local play on macOS, one human company, external chat first.
- OpenTTD 15.3, temperate climate, standard vehicles and industries, no additional gameplay NewGRFs for the initial test profile.
- **User confirmed:** “Full train” means depart the mine fully loaded, then deliver to the power station. Production-based sizing is a separate later capability.
- “Current budget” means existing cash, with a disclosed operating reserve and no automatic loan increase.
- **User confirmed:** a custom OpenTTD build is acceptable; prioritize reliable control. Select the adapter based on evidence, with no requirement to preserve stock-app compatibility at the expense of reliability.

The user answered both initial questions during this session. Remaining environment/profile choices are defaults to validate against the eventual test world.

## Local environment observed

- Workspace was empty and was not a Git repository when planning began. The user subsequently requested GitHub publication; see the repository section above.
- Installed app metadata reports OpenTTD **15.3** at `/Applications/OpenTTD.app`.
- An OpenGFX2 Classic 0.8.1 archive exists in the user's OpenTTD content directory; loadability and checksums have not been checked.
- Apple Silicon; Python 3.14.6, Node 24.3.0, CMake 4.4.2, Apple clang 21.0.0 observed. Ninja and `openttd` were not found on PATH.
- Original saves were located but not loaded or modified. No credentials were read or configured.

## Known uncertainties

Adapter performance; complete telemetry for per-train deliveries; existing-save/GameScript coexistence; pause behavior; full command cost accounting; restart reconciliation; actual coverage of the route planner. These require real-engine experiments, not more architectural claims.
