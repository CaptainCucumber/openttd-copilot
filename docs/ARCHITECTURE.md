# Architecture and implementation direction

Status: 2026-10-24. The native simple-profile railway now connects existing
businesses with a whole-job budget and verified service. Read-only construction
quotes/catchment, bounded directed planning, fsynced execution and visible MCP
use the native bridge independently of GameScript. Broader terrain and crash
recovery remain open. The bounded town-bus/ordinary-map expansion also has
clean-engine service, guards, replay and actual conversational-build evidence;
see [bus report](M2E_TOWN_BUS_REPORT.md). See [D029](DECISIONS.md#d029---connect-a-bounded-existing-business-native-railway-before-expanding-scope)
and [the native railway report](M2D_NATIVE_RAILWAY_REPORT.md).

## Responsibilities

The native mutation boundary now includes capped station/depot construction
and default-cargo rail vehicle purchase with retained actual created IDs.
COPL schema 5 migrates earlier outcomes. Independent asset/parts observations,
immutable replay, and fresh-process reload are measured in the
[purchase report](M2D_TRAIN_PURCHASE_REPORT.md). Bounded native wagon attachment,
two append-only station orders, and explicit start/stop are now verified in the
[configuration report](M2D_TRAIN_CONFIGURATION_REPORT.md). The
[native railway layer](NATIVE_PLAYABLE_ALPHA.md) now composes these primitives
into the bounded standard-coal job.

| Component | Owns | Must not do |
|---|---|---|
| Conversation layer | Intent, clarification, explanations, progress | Invent tile coordinates, prices, or successful outcomes |
| World reader | Company, industries, cargo, tiles, infrastructure, vehicles, settings, freshness | Treat stale observations as current |
| Deterministic planner | Station/depot placement, rail geometry, train composition, costs, alternatives | Rely on prose as a construction program |
| Job executor | Preconditions, spending limits, operation order, retries, cancellation, journaling | Blindly replay uncertain mutations |
| Game adapter | Validated observations and normal game commands | Bypass game rules or execute arbitrary model code |
| Verifier | Actual assets, reachability, orders, loading, delivery, health | Equate successful construction with a working service |

The implementation uses a Python service for protocol handling, deterministic
planning, fsynced JSON jobs/per-operation journals and terminal/MCP interfaces,
backed by the narrow C++ bridge selected in M1. SQLite job storage was a proposed
design, not the current execution store. Squirrel remains only in
reference/regression fixtures. MCP exposes high-level jobs; it is not the
planning algorithm or reliability layer.

## Integration options

| Option | Strength | Cost / limitation | Position |
|---|---|---|---|
| Standard GameScript + Admin interface | Supported company-context commands and normal game validation | Cannot attach Copilot to an ordinary save; saved scripts retain the sole slot; no general vehicle ID on delivery telemetry | Retain as reference and regression fixture, not production adapter |
| Small custom OpenTTD bridge | Independent of GameScript slot; existing-save attachment, one native rail mutation, and vehicle-tagged service events proven | Engine builds, update maintenance, distribution, strict game-thread integration | **Selected in M1; M2a–M2c checkpoints proven** |
| NoAI controller | Established autonomous company API | An autonomous AI company differs from assisting the player's company | Reference/test tool, not initial product adapter |
| Screenshot/mouse automation | Can use ordinary UI | Fragile execution and limited authoritative state | Visual QA only |

The stock experiment hosts a local game and connects the normal client to the human company. Do not assume the Admin interface alone is a general construction API: the GameScript performs gameplay operations. The adapter contract should permit replacement without rewriting the planner.

**Planned topology change (D032, M2f, not implemented):** local single-player
games only. Replace the dedicated server + joining client + Admin connection
with one visible OpenTTD process hosting a loopback, per-launch-token Copilot
endpoint polled on the game thread. Request payloads, COPL, journals, planners
and MCP tools are unchanged; protocol v4 adds hello, local company, game
mode/pause, tick frames, typed refusals and save/quit. Multiplayer use is
refused. The paragraph below describes the currently implemented Admin path.
See the [M2f plan](M2F_LOCAL_BRIDGE_PLAN.md).

The selected bridge is deliberately narrow. M2a added protocol v1 identity packets 11 and 130 to the authenticated Admin connection and rejected non-loopback peers. M2b protocol v2 adds a typed single-rail request and operation-status query. A wrapper posts through OpenTTD's normal command pipeline, quotes and checks the cap before execution, and returns authoritative cost plus tile/company readback after the callback. A versioned COPL save chunk persists world/operation sequence and terminal outcome; an external fsynced journal records intent before send. M2c protocol v3 adds paged vehicle-tagged station departures and exact accepted-industry deliveries. Its bounded observation ring is runtime-only and reports gaps; it does not extend the persisted COPL chunk. M2d adds protocol-v3 tile pages (32 contiguous tiles), industry pages (16 IDs/types/anchors/cargo lists), human-company rail catalog pages (16 train definitions), station/depot pages (16 assets), and bounded train-part pages (16 records from at most 256 scanned vehicle IDs). Pages report frames; a multi-page sweep is not atomic and needs dependency revalidation before construction. House and industry tiles are marked unowned without invoking OpenTTD's restricted owner helper. The rail primitive still admits only a flat clear tile; station/depot primitives require a level clear footprint. Their shared retained-operation boundary is described below. The Python service retains intent parsing, future planning, budgets, journaling, and verification. Only copied saves have been tested; stock-build compatibility is not established.

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

M2b established a world ID, monotonic successful-operation sequence, head operation ID, and one saved operation record. The M2d sequential checkpoint extends COPL to schema 2: one active operation and chronological terminal history, bounded to 64 total records without eviction. A rejected operation consumes a record but preserves the last successful sequence/head. Pending and uncertain operations block further admission; a full history rejects new IDs while retaining old-ID status/replay. Schema-1 single-record saves migrate on load. See [D025](DECISIONS.md#d025--retain-a-bounded-native-operation-history-before-adding-railway-commands).

The client rejects mismatched worlds/protocols and compares each external journal position to distinguish the current world, an older save, changed world, an ahead save, or diverged history. External intent is retained in separate fsynced single-operation journal files rather than overwriting the previous operation. A loaded pending operation is marked uncertain and must not be replayed automatically. Historical status returns the original cost/error/completion frame alongside the current global sequence/head and live tile/company readback, not a historical world snapshot. This is not a complete save lineage or atomic transaction; a command executed after the most recent save can still be absent from a reloaded older save.

## Planning the railway

`native_route_plan.py` consumes observed tiles and proposes two-tile station
sites and directed track with a source-inline depot. Search state includes the
previous track to respect default no-90-degree train transitions. Request 17
tests costs and prospective catchment against the selected industry's occupied
tiles. `native_railway.py` checks the entire infrastructure/consist cost, reserve
and available 64-record history, then revalidates dependencies per operation.
Each intent is fsynced before send; rejected/uncertain outcomes stop the job
with existing work retained. Three loaded source departures and two accepted
delivery cycles prove the service returned twice; empty departures are not
emitted by the current event seam. See [alpha limits](NATIVE_PLAYABLE_ALPHA.md).

The purchase boundary adds protocol-v3 request 13 and extended status 14.
It buys one default-cargo rail engine or wagon in an owned depot, rechecking
the cap through normal `CMD_BUILD_VEHICLE` validation. Its typed tuple callback
retains the actual returned VehicleID; a missing/mismatched result becomes
uncertain rather than triggering another purchase. COPL schema 4 persists
engine identity and migrates older histories. Independent train-part pages
establish current engine/owner/depot/chain/cargo state. Engine purchases do
not adopt free wagons; wagon purchases refuse the stock implicit-joining case.
Refit remains unsupported. See [D027](DECISIONS.md#d027--purchase-rail-vehicles-with-the-commands-returned-identity).

Configuration requests 15/16 add explicit free-wagon-chain attachment to an
owned stopped primary's tail in the same depot, append-index-guarded station
orders on unshared stopped-depot trains (maximum two), and desired-state
start/stop. Source policy is full-load-all/no-unload; delivery policy is
no-load/unload-if-possible. Normal native commands own legality. Starting
requires two orders and a stopped depot train; stopping uses the observed live
tile. An already-desired state completes without toggling. Historical start
replay after a stop returns the original result, not another start.
Schema 5 retains action/source/target/index/policy and migrates old sentinel
fields. Earlier status endpoints refuse configuration identities. Independent
parts/orders verify the result; successful start is not a service proof.
Starting also permits normal movement and running expenses, which are separate
from the zero configuration-command charges. See
[D028](DECISIONS.md#d028--configure-a-train-through-explicit-retained-actions-not-toggle-replay).

M2d infrastructure requests 11/12 extend the same journal with capped new default
single-platform stations (length 1–7, either axis) and single-tile depots.
Normal engine validation owns placement/cost; a clear flat footprint is an
additional restriction, not a substitute. COPL schema 3 retains the original
created station/depot ID and migrates schema-1/2 rail records. Extended status
can read either kind; old rail-only status explicitly refuses infrastructure.
Historical created IDs must be checked against current independent asset
pages, because removal/reuse can invalidate the original association. The
64-record limit remains shared across rail, infrastructure, and admitted
rejections. This is not whole-route reservation, station joining, train
purchase, or automatic recovery. See [D026](DECISIONS.md#d026--build-bounded-new-rail-stations-and-depots-through-normal-commands).

1. **Resolve the job.** Check source produces coal, destination accepts it, company exists, and suitable engines are available in the current year.
2. **Generate station candidates.** Consider cargo catchment/acceptance, station footprint, slopes, approach direction, spread limits, authority rating, and track/depot space. Rank candidate pairs rather than selecting the nearest station at each end independently.
3. **Select train and station length together.** Use live engine availability, refittability, capacity, length, weight, power/tractive effort, rail compatibility, purchase/refit price, and running cost. For the first supported profile, verify the actual built consist after purchase. Do not assume all wagons have equal length or cost.
4. **Search legal directed rail states.** Use A* or equivalent deterministic search over entry/exit track geometry and terrain. Include turn and gradient costs. Expand bridge/tunnel spans as explicit actions in M3. A route over tile centers alone is insufficient.
5. **Maintain a planned-world overlay.** Planned track, stations, depots, and terrain changes affect later actions. Prevent conflicting geometry and account for construction dependencies. The overlay proposes feasibility; OpenTTD remains authoritative.
6. **Price and compare complete alternatives.** Include stations, clearing/terrain, track, bridges/tunnels, depot, train, refit, and retained operating cash. Prefer feasible affordable designs; report search/time limits distinctly from proven constraints.
7. **Validate the sequence.** Check individual commands and dependencies. Where the adapter cannot validate a dependent sequence without mutation, rehearse in a disposable copied world with the same engine/content/settings. Record differences in tick/state and revalidate before live application.

The first line has one train, two terminal stations, and connected depot access, so it can avoid shared-track signals. The route must permit travel and reversal in both directions under the actual settings. Signals and junction capacity enter when supporting multiple trains, not as decorative construction.

## Town passenger buses and normal worlds

The user-requested M2e expansion adds protocol-v3 request 18: bounded JSON
queries for towns, road tiles, road engines, assets and orders, normal-command
quotes and retained actions. Tile pages contain at most eight records.
Actions 7-12 add road bits, a new drive-through stop, a new road depot,
a default-cargo passenger bus, an append-only ordinary station order and an
explicit running state. They share COPL schema 5's existing fields and
64-record history; no layout change, eviction or transaction is introduced.
Road-vehicle departures and town-accepted passenger deliveries use the
existing bounded runtime event ring.

`native_bus.py` owns a bounded 192x192 corridor and multi-source road search,
at most 160 path tiles and 100,000 expansions. It prefers existing standard
two-way roads; new road/depot footprints are flat clear/tree land. It rejects
houses, water, rail, bridges/tunnels, one-way roads and unsupported content.
Prospective stops require actual passenger production and at least eight
eighths of acceptance from the explicitly selected town's house callbacks,
not mere proximity to its anchor. Stops are secured before tree clearing can
affect local-authority permission. The cheapest currently buildable supported
passenger bus is selected; this is not an optimality or profitability claim.

Rail and bus execution share `JournaledExecutor`'s identity, cap/reserve,
loan, fsynced-intent, polling and reconciliation boundary. Independent bus
asset/order observations precede startup; `operating` additionally requires
vehicle/company/cargo-attributed passenger acceptance at both selected stops.
Different explicit requests may start new durable jobs only after verified
operation, while cash/history permit. An identical request is a lookup;
partial/uncertain jobs still block changed requests.

The conversational launcher defaults to a randomly seeded normal 256x256
temperate world with towns, trees, hills and water/rivers. The selected flat
seed-6 profile remains an explicit railway fixture. Copied saves keep their
settings. Profiles, saves and MCP configuration are isolated from normal play.
Inspection exposes only currently buildable standard passenger engines to
bound host-visible output. Coding tools are explicitly excluded; output
truncation is not permission for shell/SQL fallback.

**Integration status:** the bounded clean-engine bus path passed actual
passengers at both stops, command-cap/shape guards, rejected-record and all
service-outcome reload/replay, older-save refusal, coal regressions and actual
conversational build/inspection/saved close. See [bus report](M2E_TOWN_BUS_REPORT.md).
This does not close broader supported-world or fault-injected recovery gates.

Next architectural work follows the existing layers rather than new transport
types: version supported-world fixtures and failure boundaries; add explicit
cancellation and durable job/world reconciliation; extend read-only telemetry
for production, waiting cargo and finance with freshness/units; then expose
authorized restart/resume through conversation. Observation does not grant
optimization-mutation permission. Bridges/terrain/shared networks require
separate explicit acceptance before expanding planner or command scope.
See [milestone sequencing](PROJECT_PLAN.md#next-milestone-sequencing).

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

Keep network control local with authentication, bounded messages, version negotiation, and redacted credentials. After M2f the control channel is a loopback-only local endpoint inside the single-player process, authenticated by a per-launch token in the isolated profile; it exposes no console, RCON or arbitrary command execution, and refuses work while networked, paused (mutations), outside a normal game or for a non-local company. Game text and model output are data, never executable Squirrel, shell, or arbitrary console instructions. Keep narrow lifecycle controls for the test harness separate from gameplay operations.

The eventual chat UI shows the route, estimated/actual cost, retained cash, current phase, and observed outcome. API keys stay in the external process. In-game chat and visual route previews can be added after the core loop passes acceptance tests.

The current external interface is interactive Copilot CLI (`game_chat.py`),
with a repository game-only agent and inline session-local native MCP settings.
No new provider/key or global configuration edit is required. Its six native
tools separate open/close, live inspection, read-only planning, explicit
construction and cached job status. Only the three read-only/status tools are
automatically allowed; host permission checks remain on lifecycle/construction.

Inspection collects bounded current company/business/catalog/asset/consist/order
pages, at most 16 primary trains and four event pages per train. It checks
world/operation position before/after, reports non-atomic frame bounds,
epoch/gaps/truncation and unavailable metrics. The Admin socket is not shared
with an active construction worker. Read-only planning uses the same actual
geometry/quote/budget code with manifest recording disabled: it does not change
the active payload or start a worker. A later build replans live.

A pre-executor planning failure is `rejected`, with
`construction_started: false`, retained rejection history and permission for a
changed explicit request on the same map. Set `construction_started` before
entering execution, conservatively even if its first action later fails.
Execution/verifier failures retain conflict/no-retry restrictions. A validated
station-footprint Manhattan lower bound filters pairs exceeding 50 rail tiles;
it proves only a bound for those selected candidates, not global infeasibility.
