# Proposed architecture

Status: M2a identity, M2b bounded mutation, and M2c vehicle-tagged observation complete, 2026-10-23. The M2d tile seam is implemented and tested, but complete route construction remains open. The custom OpenTTD 15.3 build exposes bounded world/company identity, one typed rail mutation, paged train departure/industry delivery events, and read-only tile pages through authenticated loopback-only Admin packets independent of GameScript. See the [tile report](M2D_TILE_REPORT.md) and [D017](DECISIONS.md#d017--add-bounded-native-tile-observation-without-changing-the-mutation-boundary).

## Responsibilities

| Component | Owns | Must not do |
|---|---|---|
| Conversation layer | Intent, clarification, explanations, progress | Invent tile coordinates, prices, or successful outcomes |
| World reader | Company, industries, cargo, tiles, infrastructure, vehicles, settings, freshness | Treat stale observations as current |
| Deterministic planner | Station/depot placement, rail geometry, train composition, costs, alternatives | Rely on prose as a construction program |
| Job executor | Preconditions, spending limits, operation order, retries, cancellation, journaling | Blindly replay uncertain mutations |
| Game adapter | Validated observations and normal game commands | Bypass game rules or execute arbitrary model code |
| Verifier | Actual assets, reachability, orders, loading, delivery, health | Equate successful construction with a working service |

The implementation uses a Python service for protocol handling and the future planner, SQLite job storage, and terminal/CLI interface, backed by the narrow C++ bridge selected in M1. Squirrel remains only in reference/regression fixtures. MCP can expose the same high-level jobs later, but it is not the planning algorithm or the reliability layer.

## Integration options

| Option | Strength | Cost / limitation | Position |
|---|---|---|---|
| Standard GameScript + Admin interface | Supported company-context commands and normal game validation | Cannot attach Copilot to an ordinary save; saved scripts retain the sole slot; no general vehicle ID on delivery telemetry | Retain as reference and regression fixture, not production adapter |
| Small custom OpenTTD bridge | Independent of GameScript slot; existing-save attachment, one native rail mutation, and vehicle-tagged service events proven | Engine builds, update maintenance, distribution, strict game-thread integration | **Selected in M1; M2a–M2c checkpoints proven** |
| NoAI controller | Established autonomous company API | An autonomous AI company differs from assisting the player's company | Reference/test tool, not initial product adapter |
| Screenshot/mouse automation | Can use ordinary UI | Fragile execution and limited authoritative state | Visual QA only |

The stock experiment hosts a local game and connects the normal client to the human company. Do not assume the Admin interface alone is a general construction API: the GameScript performs gameplay operations. The adapter contract should permit replacement without rewriting the planner.

The selected bridge is deliberately narrow. M2a added protocol v1 identity packets 11 and 130 to the authenticated Admin connection and rejected non-loopback peers. M2b protocol v2 adds a typed single-rail request and operation-status query. A wrapper posts through OpenTTD's normal command pipeline, quotes and checks the cap before execution, and returns authoritative cost plus tile/company readback after the callback. A versioned COPL save chunk persists world/operation sequence and terminal outcome; an external fsynced journal records intent before send. M2c protocol v3 adds paged vehicle-tagged station departures and exact accepted-industry deliveries. Its bounded observation ring is runtime-only and reports gaps; it does not extend the persisted COPL chunk. M2d adds an additive protocol-v3 tile-page request, capped at 32 contiguous tiles, reporting validity, type, owner, slope, height, and plain/crossing rail geometry. Pages report their frame; a multi-page sweep is not atomic and needs dependency revalidation before construction. The current command admits only a flat clear tile, one operation per world. The Python service retains intent parsing, future planning, budgets, journaling, and verification. Only copied saves have been tested; stock-build compatibility is not established.

## Intent and identity

A `TransportIntent` contains:

- Current world identity and selected company.
- Source and destination entity references, cargo label/ID, and transport mode.
- Loading/delivery policy, capacity preference, and permitted infrastructure reuse.
- Construction spending cap, operating reserve, loan policy, and terrain/demolition limits.
- Whether the request asks for a plan or authorizes construction.

Names are resolved from observations; ambiguous matches remain unresolved until clarified. Stable references include world identity and entity type as well as numeric ID. Revalidate before execution because industries can close and IDs can be reused. Money is represented as integral engine money units with explicit display-currency conversion; the wire format must preserve integer precision.

The first request uses `rail`, `COAL`, full load at source, delivery at destination, existing cash only, and one train. The source/destination names from the user are examples, not hard-coded world entities.

## Observation and freshness

Read the map incrementally by relevant region. Gather terrain height/slope, water, ownership, rail pieces and directions, crossings, station/depot geometry, town constraints, available rail types, engine/refit properties, industry production and cargo acceptance, company cash, and relevant settings.

Responses carry protocol version, world/session identity, observation tick, and query scope. A multi-page scan must either use a consistent captured snapshot or disclose its tick range and recheck dependencies; a single timestamp on changing data is not a snapshot.

M2b persists a world ID, monotonic successful-operation sequence, head operation ID, and one operation record in the COPL chunk. The client rejects mismatched worlds/protocols and compares the external journal position to distinguish the current world, an older save, changed world, an ahead save, or diverged history. A loaded pending operation is marked uncertain and must not be replayed automatically. This is not a complete save lineage or atomic transaction; a command executed after the most recent save can still be absent from a reloaded older save.

## Planning the railway

1. **Resolve the job.** Check source produces coal, destination accepts it, company exists, and suitable engines are available in the current year.
2. **Generate station candidates.** Consider cargo catchment/acceptance, station footprint, slopes, approach direction, spread limits, authority rating, and track/depot space. Rank candidate pairs rather than selecting the nearest station at each end independently.
3. **Select train and station length together.** Use live engine availability, refittability, capacity, length, weight, power/tractive effort, rail compatibility, purchase/refit price, and running cost. For the first supported profile, verify the actual built consist after purchase. Do not assume all wagons have equal length or cost.
4. **Search legal directed rail states.** Use A* or equivalent deterministic search over entry/exit track geometry and terrain. Include turn and gradient costs. Expand bridge/tunnel spans as explicit actions in M3. A route over tile centers alone is insufficient.
5. **Maintain a planned-world overlay.** Planned track, stations, depots, and terrain changes affect later actions. Prevent conflicting geometry and account for construction dependencies. The overlay proposes feasibility; OpenTTD remains authoritative.
6. **Price and compare complete alternatives.** Include stations, clearing/terrain, track, bridges/tunnels, depot, train, refit, and retained operating cash. Prefer feasible affordable designs; report search/time limits distinctly from proven constraints.
7. **Validate the sequence.** Check individual commands and dependencies. Where the adapter cannot validate a dependent sequence without mutation, rehearse in a disposable copied world with the same engine/content/settings. Record differences in tick/state and revalidate before live application.

The first line has one train, two terminal stations, and connected depot access, so it can avoid shared-track signals. The route must permit travel and reversal in both directions under the actual settings. Signals and junction capacity enter when supporting multiple trains, not as decorative construction.

## Dry-run limits

OpenTTD test mode checks commands without retaining their mutations. Testing “build track” and then “place a signal on that track” against the untouched map is not a sequential simulation. Likewise a train purchase cannot be proven against a depot that only exists in the plan. Test mode is useful but does not supply transaction semantics. [Test-mode source](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_testmode.hpp).

A rehearsal can expose sequence failures and improve cost estimates, but the live game can change afterward. Revalidate affected tiles, company money, train availability, and industry state before each phase. Do not advertise an exact fixed quote when dependencies remain uncertain.

## Budget contract

Let `cap` be the agreed maximum construction spend, `spent` the recorded charges attributable to this job, and `reserve` the retained operating cash. Before a mutation with current cost `cost` and conservative remaining completion estimate `remaining`:

```text
spent + cost + remaining <= cap
current_cash - cost >= reserve + remaining
```

The default cap is derived from cash when accepting the job, less the disclosed reserve. Rising company revenue does not silently enlarge it. Falling cash from player actions or operating costs triggers revalidation. Additional borrowing is disabled unless explicitly requested. A required command whose authoritative cost cannot be bounded must stop for replanning.

Track costs through engine command accounting, not only before/after bank balance: income and running costs can change the balance independently. OpenTTD exposes script accounting for tested and executed commands. [Accounting source](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_accounting.hpp).

Reserve money for the train throughout construction. Record proceeds/refunds separately; do not treat speculative resale as budget. Handle a final execution rejection without retry loops that spend beyond the cap.

## Job lifecycle and execution protocol

```text
received → resolving → planning → ready → building → commissioning → verifying → operating
                ↘ needs_input       ↘ stale/replan      ↘ blocked/partial        ↘ degraded
                                  cancellation → cancelled (with retained-work report)
```

This describes job states, not game pause state. Every mutation has a job ID, operation ID, payload hash, world/company binding, preconditions, expected postconditions, and cost bound. The adapter accepts only supported typed operations.

Record pending work before sending it. Persist the adapter-side outcome with the game where feasible. Return acknowledged operation IDs, actual results/costs, created IDs, and state fingerprints. After a timeout, query operation status and read back the world before deciding what to do next. The same operation ID with different content is rejected.

The crash between a mutation and its durable journal record is a specific M1/M3 fault case. Do not promise exactly-once effects unless that gap is closed. If reconciliation cannot prove whether a vehicle was purchased, enter `uncertain` and stop; do not buy another.

Saving and loading can roll back the game-side journal while the external database still contains later work. Detect this through save/world lineage and reconcile from the loaded world. Never automatically replay actions from a later save onto an earlier one.

Cancellation takes effect between operations. It reports spent money and retained assets. Cleanup is compensating work, not a database rollback: removing infrastructure can cost money, lose value, or interfere with new player work. Automatic cleanup is restricted to demonstrably job-created, unchanged assets under the job's policy. Restoring a full save is a separate explicit action.

## Verification and reporting

Verification has distinct levels:

1. **Built:** expected owned track, station coverage/acceptance, depot connection, and vehicle exist.
2. **Configured:** consist, capacity, rail type, platform fit, orders, and running state match the intent.
3. **Operating:** the assigned train reaches the mine, loads, departs full, reaches the accepting station, unloads/delivers, and completes repeated service.
4. **Economic:** attributable cargo receipts and running costs over a declared observation window; profitability is separate from delivery success.

Positive company cash flow does not prove this route delivered cargo. The stock adapter's ability to attribute deliveries and revenue is an M1 question. Define an independent observer using vehicle/station/cargo evidence; add engine events if necessary. Do not infer delivery merely from motion or a successful order command.

Monitor no-path states, depot trapping, lack of production, loading without progress, industry closure, insufficient operating cash, breakdowns, and player changes. Use simulation time for loading/travel windows and wall-clock limits for transport/service responsiveness. Paused games suspend simulation deadlines and report that state.

## Local interface and runtime boundaries

Keep network control local with authentication, bounded messages, version negotiation, and redacted credentials. Game text and model output are data, never executable Squirrel, shell, or arbitrary console instructions. Keep narrow lifecycle controls for the test harness separate from gameplay operations.

The eventual chat UI shows the route, estimated/actual cost, retained cash, current phase, and observed outcome. API keys stay in the external process. In-game chat and visual route previews can be added after the core loop passes acceptance tests.
