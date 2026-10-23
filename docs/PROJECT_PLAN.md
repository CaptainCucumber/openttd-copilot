# Project plan

Baseline: 2026-10-20. Owner: Niko. Implementation partner: Codex.

## Product objective

The player describes a transport job in ordinary language. Copilot understands the job, resolves the named places in the current world, finds an affordable design, constructs it for the player's company, and checks that it transports the requested cargo. When it cannot complete the job, it explains the specific constraint and the state of any work already done.

The user's coal example is our first end-to-end acceptance case. It is a representative request, not evidence that those named industries exist in a local save.

## Requirements and working assumptions

| ID | Requirement | Origin / interpretation |
|---|---|---|
| R1 | Accept natural-language construction instructions | Explicit user request |
| R2 | Operate in the player's company and use its available money | Implied by “builds for me” and “budget that I currently have” |
| R3 | Build a complete coal railway between named industries | Explicit example; includes stations, connected track, depot, train, and orders |
| R4 | Enforce a full-load instruction | User confirmed: leave the mine fully loaded |
| R5 | Be reliable, with observable completion and useful failure handling | Explicit priority; measurable tests below |
| R6 | Support chat outside the game | Explicitly acceptable; in-game chat can follow |
| R7 | Maintain a durable plan and action history | Explicit requirement; project records implement this |
| R8 | Preserve the requested transport mode, endpoints, and budget | Do not silently replace a railway with trucks or borrow money |
| R9 | Prioritize reliable control; a custom OpenTTD build is acceptable | Explicit user confirmation during planning |

Initial target: local macOS play, one human company, OpenTTD 15.3, temperate climate, standard vehicles/industries. This is a testable starting scope, not a permanent restriction on the project. The user accepts a custom build; do not spend extended effort working around stock API limits if a narrow engine integration provides more dependable control.

“Use my current budget” sets an upper bound; it does not mean spend every available unit of currency. The plan shows infrastructure, train/refit cost, contingency, and retained operating cash. The reserve is configurable and visible. Do not invent a fixed percentage before fixture measurements.

“Full load” is an order and an observed departure condition. It cannot guarantee that a mine keeps producing forever or that a train arrives at the mine already full. If the user also wants capacity matched to production, model that separately using supply and round-trip time.

## First useful version

- Resolve an origin, destination, cargo, and company from live state; ask a focused question when names match multiple entities.
- Choose a buildable pair of station sites with cargo coverage and acceptance, a connected route, and a reachable depot.
- Select an available locomotive and coal-compatible wagons that fit the stations and can operate on the route.
- Estimate the **whole job**, including the train, before committing to construction.
- Build an isolated single-track line with one train. Avoid shared-track signaling complexity until later milestones.
- Install full-load-at-source and delivery-at-destination orders and start the train.
- Show progress, cost, partial failures, and observed operation. Support status and cancellation.
- Recover safely from lost connections and service restarts without blindly duplicating purchases or construction.
- Run against a repeatable real-engine scenario suite, not just a single demonstration map.

The flat-map build in M2 is an engineering checkpoint. The first usable alpha additionally needs M3's terrain and failure coverage and M4's chat experience.

## Deferred scope

Shared rail networks, multi-train signaling and junctions, automatic network expansion, passenger service, roads/ships/aircraft, advanced NewGRF support, multiplayer administration, polished in-game chat, cross-platform packaging, and unrestricted terraforming. Add them through separate milestones after the coal railway is measured and dependable.

Existing infrastructure is protected by default. Initial routes can avoid it; reuse, rebuilding, and demolition require explicit supported policies. Ordinary terrain preparation within a disclosed construction footprint can be added in M3. Full autonomy as company president is a separate product decision.

## Milestones and exit criteria

### M0 — Establish the project

Deliver requirements, source findings, architecture proposal, acceptance criteria, decision log, status page, and work log. Mark all untested claims clearly. **Initial baseline completed in this session.**

### M1 — Prove control and select the integration

Status: **Complete, 2026-10-22.** Production adapter selection is recorded in D013.

**Purpose:** resolve the most expensive architectural uncertainties before writing the route planner.

Deliver an isolated game harness, minimal observation/control adapter, protocol sketch backed by working calls, and an evidence-based adapter decision. Start with standard OpenTTD's GameScript/Admin path; use a custom engine bridge if it fails essential requirements.

Exit checks:

1. Connect locally; identify the correct human company, cash, world, industries, relevant tile data, and available engines.
2. Test, execute, and read back rail/station construction in that company, with costs from the engine. Rejected operations leave no mutation.
3. Demonstrate representative vehicle purchase/order/readback and determine whether actual loaded departures and deliveries can be attributed to that vehicle.
4. Measure 10,000 relevant tile observations and a 100-piece construction sequence; record median/p95 times over five runs, pauses, script limits, message sizes, and responsiveness. Initial UX targets: region query within 5 seconds, 100 simple pieces within 30 seconds at normal speed; these are proposed targets, not measured facts.
5. Show save/reload and lost-response reconciliation without a duplicate purchase. Detect loading an older save and changing worlds.
6. Establish paused-game behavior, human-company setup in the fixture, attaching to copied existing saves, and coexistence limitations with another GameScript.
7. Decide adapter based on coverage and measured performance. If the stock path cannot meet a requirement, identify the specific missing query/event/command behavior before extending OpenTTD.

M1 evidence (2026-10-22): the [rail-only lifecycle probe](LIFECYCLE_PROBE.md) covers request paging, pause, reconnect, saved outcomes, duplicate replay after reload, and older/changed-world detection. S3b adds vehicle-purchase replay and isolated one-train service evidence. S3c's [five-world throughput probe](THROUGHPUT_PROBE.md) covers exit check 4's bounded workload: 10,000 valid tile observations at 2.670s median / 2.678s p95 and 100 simple rail commands at 2.752s median / 2.755s p95. The final [environment probe](ENVIRONMENT_PROBE.md) establishes the stock limitation: Copilot does not attach to an ordinary copied save, and a saved foreign GameScript retains the sole script slot. Exit check 3 also determined that stock delivery monitoring cannot generally attribute delivery to a vehicle. These findings select the narrow native bridge in [D013](DECISIONS.md#d013--select-a-narrow-native-openttd-bridge). The mutation/save crash gap remains an explicit M2/M3 recovery case, not a completed guarantee.

A custom bridge must use the engine's normal command pipeline on the game thread. Source access does not make arbitrary memory edits or unsupported command shortcuts acceptable implementations.

### M2 — Complete one railway without an LLM

Status: **In progress. M2a identity, M2b one-piece mutation, and M2c vehicle-tagged observation completed 2026-10-23; M2d complete rail job is next.**

**Depends on:** M1 adapter and observation contract.

Deliver typed transport intent; world snapshot; station/depot candidate search; directed rail routing; available train selection; costed operation plan; execution journal; readback; route monitoring. Use a structured fixture input so failures can be reproduced without model variability.

Exit: on a known feasible flat-map fixture, construct the complete coal route and observe **two loaded departures and two deliveries by the assigned train**, then return toward the mine again. Charges remain within the authorized construction cap; original assets and loan are unchanged. Repeating a request does not create a second route accidentally. A route that lacks money for its train must fail before infrastructure construction.

### M3 — Make construction and recovery dependable

**Depends on:** the M2 end-to-end path.

Add varied station orientations, longer/detouring routes, slopes, bounded bridges/tunnels, limited terrain preparation where explicitly supported, budget pressure, cancellation, concurrent player changes, save/reload, and injected transport/process failures. Add fallback designs within the original request: alternative station sites, routes, and affordable train sizes.

Exit: [the reliability suite](ACCEPTANCE.md) meets its curated and generated-scenario gates. Unsupported cases return a precise reason. Exceeding search limits is reported as an incomplete search, not proof that a route is impossible. Preserve failure artifacts and compare results to earlier revisions.

### M4 — Add conversation

**Depends on:** stable typed intents and measured deterministic execution.

Deliver an external local chat interface with one model adapter, entity disambiguation, grounded plan summaries, progress events, cancellation, and resumption. Keep the core model-independent; choose a provider at this milestone based on availability and measured intent accuracy. Do not build a broad provider framework upfront.

“Build it” authorizes ordinary construction within the understood constraints. Do not require confirmation for every tile or automatically add a confirmation screen to all jobs. “Show me a plan” performs no construction. Ask only when a material ambiguity or change of scope requires the player's decision.

Exit: the user's coal request and paraphrases produce the same validated intent as the structured fixture. Invalid model output, invented entities, ambiguity, and unavailable models cause no unintended game actions. End-to-end chat success still requires the M2 operating evidence.

### M5 — Package a usable local alpha

**Depends on:** M3 and M4.

Deliver a reproducible launcher, isolated profile setup, start/stop/status commands, compatibility checks, clear error messages, documentation, and versioned evidence. Demonstrate on a newly created world and on a copy of a representative existing save within the supported profile. Document how unsupported GameScripts/content are handled.

Exit: the player can start the game and Copilot, issue the request, observe completion, restart, and resume without manual script editing. Record limitations prominently. Produce an acceptance report before describing the alpha as reliable.

## Dependencies and effort management

Critical path: **game control → observable world → costed railway builder → operating verification → recovery/terrain coverage → usable chat/packaging**. UI prototyping must not replace progress on this path.

Do not give a calendar completion date until M1 measures the adapter and identifies engine work. At each milestone, split the next one into bounded tasks, record what changed and what was learned, and revise the forecast. This is a multi-milestone engineering project, not a chat integration weekend task.

## Principal risks

| Risk | Mitigation / decision trigger |
|---|---|
| Standard adapter lacks throughput or telemetry | M1 measurements; narrow engine bridge if needed |
| Station placement makes otherwise possible routes fail | Search station pairs and approach directions together; retain alternate candidates |
| Tile path looks connected but train cannot traverse it | Directed track representation, engine probes, depot/station reachability, actual train runs |
| Individual dry-run commands miss dependencies | Planned-world overlay plus sequential execution in an isolated rehearsal when required; revalidate live state |
| Railway consumes cash needed for the train | Whole-job affordability, completion reserve, actual cost ledger, bounded spending |
| Connection loss repeats a purchase | Durable request identity, game-side journal, readback reconciliation, explicit uncertain state |
| Human edits or loading an older save invalidates the plan | World identity, save lineage, dependency fingerprints, replan or stop |
| Full-load train never departs | Monitor production, waiting cargo, loading progress, station catchment, and vehicle compatibility |
| Tests overstate reliability | Fixed feasible fixtures, independent checks, disclosed generated cohorts, retained failures |
| Custom build becomes expensive to maintain | Keep a small patch and pinned engine version; isolate adapter from planner and chat |

## Working cadence

Maintain one current task list in `STATUS.md`. Append meaningful actions and verification results to `WORK_LOG.md`; use `DECISIONS.md` for durable tradeoffs. Keep raw game evidence under ignored `artifacts/` and small shareable result summaries under `docs/evidence/` when available. Every milestone review must distinguish implemented, tested, and merely proposed behavior.
