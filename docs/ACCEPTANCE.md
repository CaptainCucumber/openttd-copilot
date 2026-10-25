# Acceptance and reliability plan

Status: 2026-10-24. **The narrow native M2 end-to-end transport path is now
verified** on naturally generated seed 6: selected existing businesses,
whole-job affordability, 44 native actions, three full departures, two accepted
deliveries and both returns. Visible MCP, saved close and retained
reload/replay also passed. See [native railway evidence](M2D_NATIVE_RAILWAY_REPORT.md).
**Fault-injected crash recovery and the release scenario suite below remain
open.** One selected seed is not a success-rate or general reliability claim.

## What “reliable” means

The 2026-10-24 [purchase checkpoint](M2D_TRAIN_PURCHASE_REPORT.md) additionally
proves capped native station/depot construction and rail vehicle purchase in
copied fixtures, retained created IDs, independent readback, and replay/reload.
These are primitive-level results, not the complete-route/service or release
gates below. The [configuration checkpoint](M2D_TRAIN_CONFIGURATION_REPORT.md)
now proves explicit wagon attachment, exact station-order policies, desired-state
start/stop, historical replay after stopping, and all 24 outcomes after reload.
Its seven successful commands cost zero, but normal running expense reduced
cash by two units while the train briefly ran. That historical configuration
checkpoint did not prove service; the later native railway checkpoint above
does, within its explicitly narrower alpha profile.

Within a declared supported game profile, Copilot completes feasible requests repeatedly, respects the spending/ownership constraints, and detects failures without falsely reporting success. It does not promise to find a railway on every possible map or guarantee future profitability.

Track separately: intent accuracy, planning success on known feasible tasks, construction completion, verified deliveries, cost error, constraint violations, recovery correctness, and elapsed time. A successfully rejected request is a policy result, not a successful build.

## First end-to-end test

Prepare a reproducible, known feasible temperate map with a coal producer, accepting power station, a human company, sufficient starting cash, and standard available rail vehicles. Freeze the scenario and content/settings manifest. Use the user's names if assigned by the fixture; otherwise bind the real names from that fixture.

Issue a structured request first, then the natural-language equivalent at M4. Assert:

1. The intended company and industry IDs are selected, with valid coal production/acceptance.
2. No loan increase, grants, cheats, or silent budget expansion occurs.
3. Stations actually cover the relevant industries; track is traversable in both directions and the depot is reachable.
4. The purchased consist can carry coal, fits the platforms, and runs on all track segments.
5. The train has full-load-at-source and delivery-at-destination orders and is started.
6. An independent observer sees two full-load departures, two coal deliveries, and continued return service.
7. Recorded construction charges stay within the cap and retain the declared reserve, accounting for unrelated balance changes separately.
8. Repeating/status-checking the request causes no duplicate assets.

Full load is checked against actual coal capacity immediately before leaving the source station. Destination evidence must associate the assigned train with delivery to an accepting destination. A decrease in load by itself or revenue from another train is insufficient.

## M2e bus expansion gate

The requested normal-map passenger-bus alpha has a separate narrow exit:
observe ordinary map features and real towns; plan without changing assets,
finances or retained position; reject insufficient whole-job budget; construct
two distinct accepting/producing stops, connected roads/depot and one available
passenger bus; independently inspect capacity and ordinary two-stop orders;
observe passenger acceptance attributed to that bus at **both stops**.
No borrowing or house/asset demolition is allowed. Tree clearing is limited
to the disclosed quoted new-road/depot footprint.

Duplicate lookup must not construct; fresh-process reload and exact replay
must preserve every retained action, including orientation, road bits,
historical operation sequence, cost and returned identities. An older initial
save must not inherit completed external job state. Preserve original saves
and normal profiles. Exercise the actual signed-in conversational host with
bounded game output and no shell/SQL/coding fallback. A selected normal seed
is not a random-world feasibility, profitability or reliability cohort.

**Current result:** bounded M2e exit passed on the clean engine. Normal seed
20261024 delivered passengers at both stops, preserved all 27 outcomes across
reload/replay, refused older-save completion, malformed shapes and below-cap
execution, and retained/reloaded the rejection. Actual conversational build,
independent bus/order inspection and saved close passed; coal/legacy-save
regressions passed. See [bus evidence](evidence/2026-10-24-native-town-buses.json).
The broader scenario/recovery/release gates below remain open.

## Multi-town bus line and existing-line edit gate

**Bounded gate passed (D033), including actual-host edit/inspection/saved
close.** Quote one ordered three-town line without mutation and reject
insufficient cap/reserve/history before infrastructure. Build exactly one bus
and depot, verify its exact ordinary orders and accepted passengers at every
stop. Separately extend an existing two-town running unshared bus at an explicit
index to make one three-town line; connect both neighbors, preserve the old orders and assets, and observe
passenger acceptance at all resulting stops. Cover insertion at beginning,
middle and end in unit tests, stale/shared/unsupported order rejection,
eight-stop bound, duplicate lookup, all retained outcomes after fresh-process
reload/replay and older-save refusal. Recheck the prior two-town bus and coal
gates. Expose ordered planning/build/edit through native-only conversation
without autoallowing mutations. No general random-world or recovery claim.

Final engine `faf823d8ab` passed direct normal-density three-town service,
54-outcome replay and older-save refusal (`20261025T175057Z-88a7a87a`).
The explicit high-town-density seed-20261024 case
`20261025T175339Z-be1d4f76` inserted Plontford between Pafingfield and Prarnway
on the same bus 5: orders `[0,1] -> [0,2,1]`, 23 added actions costing 3,182,
all three stops accepted passengers, no new bus/depot, all 50 combined
outcomes reloaded/replayed, older-save refusal passed. Original two-town/cap
guards and final-engine coal legacy resave/replay passed. The normal-density
copied-line insertion search remained infeasible within the 64-record bound;
no fourth-town or random-world reliability gate is claimed.
Actual Copilot gate `20261025T175806Z-63f0d5e9` planned and edited a separate
copy once, observed passengers at every stop, inspected the same running bus
with `[0,2,1]` orders and saved/closed. It used only native tools. See
[source-hashed evidence](evidence/2026-10-25-native-bus-lines.json).

## M2f single-process gate

Planned (D032). All checks run on the local endpoint in **one** OpenTTD
process with no dedicated server, joining client, Admin password or client key.
Record binary/source hashes, video driver and pacing (headless `null` runs are
unpaced; at least one visible run is required).

1. **Refactor neutrality (before behavior changes):** existing Admin-path coal
   and bus gates pass on the dispatcher-refactored binary.
2. **Services:** native coal railway (three full departures, two deliveries)
   and normal-map bus service (accepted passengers at both stops) pass on the
   local path with duplicate lookup, all-outcome fresh-process reload/replay
   and older-save refusal.
3. **Legacy saves:** the accepted 44-outcome coal save and 27-outcome bus save
   load, replay and resave unchanged in content.
4. **Endpoint guards:** no endpoint without a configured token; wrong token,
   non-loopback peer, oversize frame and second concurrent connection are
   refused without game effect.
5. **Single-player guards, each with zero mutation and zero history use:**
   main menu / no active game; paused game (reads still succeed); wrong or
   non-local company; networked game; Shift held during a mutation does not
   produce an estimate-only or pending record (`NoEst`).
6. **Frames:** completion/observation/event frames advance in single-player
   and remain monotonic across save/reload.
7. **Lifecycle:** typed save writes only a validated name in the isolated
   save directory; path-like names are refused; quit ends only the
   launcher-owned process. Normal profile and original saves unchanged.
8. **Portability checks:** no Unix-domain sockets or platform-tool
   subprocesses on the product path; platform default video driver; journal
   unit tests cover the Windows durability branch. (Runtime evidence on
   Windows/Linux is an M5 gate, not M2f.)
9. **Actual host:** `game_chat.py` opens one visible process; Copilot inspects,
   plans, builds a bus service to verified operation, saves and closes using
   only native tools.

## Scenario matrix

| Family | Cases | Required outcome |
|---|---|---|
| Basic geometry | Adjacent, diagonal offset, long distance, four station orientations | Complete service on known feasible cases |
| Station placement | Tight catchment, blocked approach, wrong-side nearest site, limited spread | Find an alternate valid pair or explain constraint |
| Terrain | Slopes, hills, river bridge, tunnel, narrow corridor, unsupported terrain | Supported cases succeed; unsupported cases stop explicitly |
| Existing assets | Roads, own rail, rival rail/station, human buildings in corridor | Respect ownership/reuse policy and original assets |
| Money | Ample, just enough, infrastructure-only funds, funds spent by player mid-job | Whole-job affordability; no overspend or silent loan |
| Vehicles | Engine unavailable in year, wrong rail type, insufficient platform length, incompatible cargo/refit | Select compatible affordable consist or reject before building |
| Orders/cargo | Mine loads slowly, zero production, destination not accepting, industry closes | Correct orders, progress diagnosis, honest degraded/blocked state |
| Identity | Duplicate names, renamed industry, reused IDs, new world, older save | Clarify or invalidate; never act on stale identity |
| Lifecycle | Pause, save/reload, reconnect, cancellation, executor restart | No hidden continuation or duplicate effects; accurate status |
| Failure injection | Command rejection; reply lost after build/purchase; crash around journal writes | Reconcile or stop uncertain, retain evidence |
| Model input | Paraphrases, contradictory constraints, unknown entities, malformed output, unavailable provider | No unintended mutation; clear clarification/error |

M2 covers the simple isolated railway. M3 adds terrain and fault coverage. Shared networks and NewGRFs remain outside the initial profile; tests should explicitly reject unsupported profiles rather than imply compatibility.

## Proposed release gates

- **Curated suite:** at least 25 versioned scenarios spanning the supported matrix, including at least 10 known feasible routes with reference constructions. All mandatory assertions pass, including expected rejections and recovery behavior.
- **Generated cohort:** at least 100 reproducible requests across at least 20 fixed map seeds. Include independent held-out seeds. Classify known feasible, known infeasible, and unknown separately; do not exclude a case because our planner failed it.
- **Build target:** at least 95% completion on the independently established feasible, supported cohort, with counts and confidence intervals reported. Every supported feature family must also pass its curated cases. This is an initial target to validate, not a current capability claim or universal guarantee.
- **Constraint target:** zero unauthorized borrowing, unauthorized asset destruction, construction-cap violations, duplicate purchases after retries, or false completion reports in the suite.
- **Recovery target:** every designated disconnect/crash/cancellation test resolves to verified continuation, a correct partial-work report, or an explicit uncertain state. Never count an unresolved outcome as success.
- **Operation target:** two loaded deliveries for each successful build; selected soak scenarios run for ten round trips or until a declared simulated-time bound. Diagnose stalls rather than wait indefinitely.
- **Latency:** report planning and execution p50/p95, script/adapter throughput, and status/cancel responsiveness. M1 establishes hardware-specific budgets; retain both wall time and simulation ticks.

These finite gates cannot prove a zero failure rate. Publish scenario scope and failures with results. A reliability claim must name the version and test cohort it describes.

## Test layers

1. Pure planner checks for directed connectivity, consist/platform fit, budget arithmetic, and alternative candidate ranking. Use adversarial layouts and meaningful properties, not tests that simply mirror code.
2. Adapter contract tests for serialization, paging, identity, malformed requests, backpressure, timeouts, and idempotency conflicts.
3. Real-engine fixtures for command legality, exact costs, sequential dependencies, construction, train movement, and cargo handling.
4. Fault-injection runs at send/ack/journal/save boundaries, including the mutation-before-journal gap.
5. End-to-end chat tests using both fixed model outputs and recorded live model runs. Deterministic construction tests must not require paid model calls.

The verifier should not trust the builder's own “completed” flag or planned geometry. Read the resulting game state through an independent observation path and retain enough evidence to diagnose disagreements. Verify the observer itself with deliberately broken track, wrong orders, and unrelated company income.

## Evidence bundle for each run

Record build revision (or source hash if uncommitted), engine version and binary hash, adapter/protocol version, OS, graphics/content/settings manifest, scenario hash/seed, initial save hash, company and intent, plan, operations and actual costs, observation timeline, assertion results, final save, wall/simulation durations, and failure reason. Keep credentials and private prompts out of shareable artifacts.

Store large saves/logs in ignored `artifacts/`; publish concise JSON/Markdown summaries under `docs/evidence/` when created. A failed case becomes a regression fixture after reproduction. Do not replace failing seeds with more convenient ones.

## Comparing the reference projects

Source review identifies capabilities and likely gaps, not a measured success rate. If a comparison is useful, use the same engine/content, initial saves, tasks, budget rules, observation window, and independent observer. Include installation failures and unsupported cases separately. Do not claim Copilot outperforms either project until such a comparison exists.
