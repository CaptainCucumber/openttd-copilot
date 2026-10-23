# Decision log

Use a new entry when changing a substantial decision. Preserve superseded entries and link the replacement. “Accepted design” describes the current plan; it does not mean implementation is proven.

## D001 — Keep durable project records

- Date: 2026-10-20. Status: **user requirement, implemented for planning**.
- Keep plan, architecture, acceptance criteria, research, decisions, current status, and dated work log in this workspace. `AGENTS.md` tells future sessions how to maintain them.
- Reason: the user expects a long project and explicitly asked to record plans and actions.
- Revisit: simplify files if they become repetitive; retain a single current status/task list.

## D002 — Separate language understanding from construction

- Date: 2026-10-20. Status: **accepted design**.
- The model creates constrained transport intent; deterministic software handles station selection, track geometry, costs, train choice, execution, and checking the result.
- Reason: rail legality and affordability require repeatable state-grounded algorithms. Model fluency is not evidence that a route works.
- Consequence: prove a structured-request builder before adding chat. No arbitrary model-authored game scripts.

## D003 — Reliable control takes priority; custom build permitted

- Date: 2026-10-20. Status: **user confirmed; adapter choice resolved by D013**.
- User answer: “Yes—prioritize reliable control” when asked about running a custom OpenTTD build.
- Conduct a bounded stock GameScript/Admin capability experiment because source supports company-context construction. Choose a narrow native bridge if it better meets required control, performance, telemetry, or lifecycle behavior.
- Stock compatibility is not a reason to retain a fragile workaround. Do not spend multiple milestones trying to avoid an engine patch.
- Evidence needed: M1 timing, human-company commands, costs, delivery observations, pause/save/reconnect behavior, and existing-save support. Current source review is in `RESEARCH.md`.

## D004 — Full means leaving the mine full

- Date: 2026-10-20. Status: **user confirmed**.
- User answer: “Yes—leave the mine fully loaded.”
- Require full-load orders and verify coal load equals coal capacity at departure. Delivery is to the power station.
- Capacity matching to production is a separate extension, not implied by this answer. A slow or closed mine must yield progress/diagnostic information rather than a false completion report.

## D005 — Start with one complete coal railway

- Date: 2026-10-20. Status: **accepted staged scope**.
- Local play, one human company, standard temperate content, one train, two terminal stations, isolated rail, external chat first. OpenTTD 15.3 is the initial pinned engine target.
- Add varied terrain and recovery before presenting the result as a useful reliable alpha. Other modes, shared rail, NewGRFs, and multiplayer follow later.
- Reason: a complete useful vertical slice allows objective testing; broad shallow command coverage would not meet the user's priority.

## D006 — Cash-only, whole-job budget by default

- Date: 2026-10-20. Status: **provisional policy derived from the user request**.
- Use existing cash; disclose retained operating reserve; include train and refit in affordability before starting. Do not automatically borrow or use new company revenue to increase the agreed cap.
- Enforce the cap in the executor and use authoritative command cost accounting.
- Revisit if the user explicitly permits borrowing, sets a different cap, or chooses a different reserve policy. Reserve sizing remains to be measured.

## D007 — Observe real transport before claiming completion

- Date: 2026-10-20. Status: **accepted design and acceptance gate**.
- Separate built, configured, operating, and economic outcomes. First end-to-end acceptance requires two full-load departures and deliveries by the assigned train.
- A tool returning success, moving train, unload event alone, or company-level profit is insufficient proof.
- Reason: the product promise is a functioning transport service. Verifier capability is an M1 requirement.

## D008 — Recover explicitly; no fictional transactions

- Date: 2026-10-20. Status: **accepted design**.
- Persist job/operation identity, track partial work, reconcile uncertain outcomes before retrying, and detect older-save loads. Use operation preconditions and postconditions.
- Test mode is not sequential simulation; cleanup is not a guaranteed refund or rollback. Stop uncertain when evidence cannot resolve the mutation/journal gap.
- Reason: reconnects, evolving worlds, and partial construction are normal conditions in a long-running game.

## D009 — Keep implementation choices provisional until the spike

- Date: 2026-10-20. Status: **superseded by D013 after M1 evidence**.
- Initial service candidate: Python, SQLite, CLI; minimal Squirrel adapter or a narrow C++ engine bridge. External chat/model provider selected after the deterministic builder works. MCP is optional interface work.
- Reason: keep the first engineering effort on state/control and route construction, with few moving parts. No runtime dependencies installed yet.
- Revisit at M1 based on protocol integration and performance measurements.

## D010 — Recommend MCP as the first conversational interface

- Date: 2026-10-21. Status: **recommendation for discussion; not a user-confirmed scope change or implemented capability**.
- User asked whether in-game AI would require an API key and whether exposing game functionality through MCP would let players use their existing AI app and plan more reliably.
- Recommendation: after proving the deterministic builder, expose its high-level jobs through a local MCP server. A compatible AI client owns conversation and model access; the local Copilot service owns world observations, planning, spending constraints, execution, journals, and verification. In-game chat can later use the same core.
- MCP is an interface protocol, not a model, subscription entitlement, game adapter, route planner, or recovery guarantee. It does not replace M1's GameScript/Admin versus custom-engine decision. Client/model differences still affect interpretation and tool use; qualify supported clients against shared acceptance cases.
- Source findings checked on 2026-10-21: [MCP architecture](https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture) describes local and remote servers and separates the protocol from model management. [Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) documents STDIO and Streamable HTTP connections. [Codex authentication](https://learn.chatgpt.com/docs/auth) documents ChatGPT subscription sign-in and separate API-key access. These support a compatible-client approach, not a promise that every AI app or plan can connect to the local game.
- Credential options: a standalone in-game assistant can use player-supplied API credentials, a developer-funded hosted service, an eligible provider-supported account integration, or a local model. UI location does not determine billing. With a tool-only MCP server, model credentials stay with the AI client; local game-control authorization remains separate. Any applicable plan limits still apply, and cloud-hosted clients need a supported path to the local service.
- Proposed public tools should observe the world, create a costed railway plan, execute an authorized plan, and inspect/cancel a job. Do not make model-driven per-tile commands the primary public interface. Validate the same typed intent and constraints for every frontend. Construction jobs should return IDs and have explicit persisted lifecycle/reconciliation behavior independent of a single chat/tool request; client disconnect policy must be disclosed and tested.
- Runtime evidence: none. M1–M3 remain prerequisites; no MCP server, provider connection, engine adapter, or client compatibility test was implemented in this discussion. M4 remains unchanged pending the interface choice.

## D011 — Deliver an isolated control probe before the production adapter

- Date: 2026-10-21. Status: **implemented and runtime-verified for S1/S2; production adapter decision pending**.
- User authorized implementing the plan piece by piece and stopping when there is a useful result to test. This session targets S1/S2, not all M1 exit criteria.
- Use Python standard-library process/evidence tooling and a small Squirrel GameScript. Run the installed, pinned 15.3 binary with `-X -x -c <isolated-config>`, copied base graphics, no gameplay NewGRFs, and separate server/client profiles. Normal player connection creates a human company; gameplay commands execute in its `GSCompanyMode`.
- The first probe uses fixed typed test actions and JSON log evidence. It does not expose an external arbitrary-command interface. Admin transport, authentication, paging, request identity, throughput, and reconciliation are separate S3 work, so this probe cannot justify the final adapter decision.
- Fixture spending is bounded independently of eventual user budget policy. Test and execute charges come from `GSAccounting`; cash and ownership readback corroborate them. A failed or interrupted probe preserves evidence and partial assets, with no automatic cleanup or retry of uncertain construction.
- Saved probe worlds are for inspection. The GameScript stores its state and refuses to start construction on reload. This limited reload guard is not a production operation journal, save-lineage solution, or exactly-once guarantee.
- Source findings: pinned [directory handling](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/fileio.cpp), [null video driver](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/video/null_v.cpp), and [network client observations](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_client.hpp). Runtime verification will determine whether these assumptions hold in the installed build.
- Runtime findings: `-X` also excludes the macOS app bundle, so the harness copies its language/base resources and GameScript compatibility files. OpenTTD 15.3 config needs `ini_version = 7` to read split private settings and a quoted GameScript name containing spaces. These were reproduced startup failures, then fixed and verified.
- Runtime result: the final fixture associates company 0 with the normal human client, observes 13 industries and 14 available rail engines/wagons, builds one rail piece and a two-tile station for 840 engine units, and verifies rejection of duplicate track at zero cost. Copied-save reload matches ownership/geometry, cash, loan, and recorded cost with no construction events. [Evidence](evidence/2026-10-21-control-probe.json).
- Decision boundary retained: these results support continuing the stock-path spike. They do not settle Admin transport, delivery telemetry, pause behavior, save lineage, throughput, or the final adapter choice.

## D012 — Scope the lifecycle checkpoint to a durable rail fixture

- Date: 2026-10-22. Status: **implemented and measured experiment; production adapter remains undecided**.
- Versioned Admin requests use bounded JSON, request correlation, stable captured pages, and a persisted game-side operation journal. External intent is flushed before sending; losing a response triggers status reconciliation, never a blind mutation retry.
- The external journal compares saved world identity, sequence, and head before a new mutation session is bound. A runtime-only session is cleared on load. Older saves, changed worlds, and mismatched heads stop continuation. This is a single-controller fixture, not an atomic server-enforced lease or general branching-save solution.
- Reuse one randomly generated, temporary client key across fixture reloads: OpenTTD 15.3 checks the saved company allow-list against the reconnecting client's public key. Generating a fresh identity caused the previous reload failure. The key and Admin password live only in mode-0600 disposable secret files, are excluded from evidence, and are deleted at shutdown. The user's profile and keys are not used.
- Partial sends close the connection without adding another frame. Response-buffer overflow is explicit. A journal write failure disables further writes until reopen/reconciliation, and completion requires consistent operation/sequence proof.
- The final source-hashed engine run passes all 12 checks, including duplicate replay after reload with unchanged cash/loan/sequence. See [evidence](evidence/2026-10-22-lifecycle-probe.json).
- Limits: two rail mutations, no vehicle or revenue telemetry, no command/save/journal crash-gap proof, no exactly-once claim, no automatic resolution of rejected or unknown/pending operations, no general existing-save/GameScript coexistence result. Continue S3b before S4 adapter selection.

## D013 — Select a narrow native OpenTTD bridge

- Date: 2026-10-22. Status: **accepted production adapter decision; read-only skeleton implemented in M2a**. This resolves D003's and D009's adapter question.
- Keep the external deterministic Python service for typed intent, planning, budgets, execution journaling, and verification. Replace the stock GameScript gameplay adapter with the smallest native OpenTTD bridge that closes the measured gaps.
- Runtime basis: stock GameScript/Admin passes human-company construction, cost/readback, reconnect/save identity, lost-purchase replay, isolated service observation, and the five-run performance targets. It therefore remains valuable as a regression/reference fixture.
- Runtime blockers: on an isolated copy of a representative OpenTTD 15.3 user autosave, the configured Copilot GameScript did not answer while Admin ping remained healthy. In the coexistence fixture, a saved foreign GameScript resumed with persisted state even though Copilot was configured and both scripts were installed. Stock delivery monitoring also lacks vehicle identity outside the isolated one-train scope. See the [M1 report](M1_REPORT.md) and [environment evidence](evidence/2026-10-22-environment-probe.json).
- Source explanation: save loading clears the configured game script and restores the script identity stored in the save ([`game_sl.cpp`](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/saveload/game_sl.cpp)); OpenTTD owns one global `Game::instance` ([`game_core.cpp`](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/game/game_core.cpp)). The runtime probe establishes the product consequence; source alone was not treated as proof.
- Bridge boundary: add a versioned, authenticated, loopback-only Copilot Admin message family and native controller independent of the GameScript slot. Allow only bounded typed queries and mutations. Execute every gameplay mutation on the game thread through normal OpenTTD command test/execute validation; do not edit memory, bypass ownership/money/authority rules, or expose arbitrary console/code execution.
- Bridge evidence required before building the full route: attach read-only to a copied existing save while its GameScript keeps running; identify the intended company/world; execute and read back one capped rail mutation; report vehicle-tagged load/departure/delivery events; persist versioned world/operation identity; and preserve explicit uncertain outcomes around any mutation/save crash gap.
- Save compatibility: all development uses generated worlds or copies. Any bridge-specific save chunk is versioned. Do not overwrite an original save or claim stock-build round-trip compatibility until measured.

## D014 — Freeze the M2a native identity boundary

- Date: 2026-10-23. Status: **implemented and real-engine verified**.
- Fork exact upstream revision `14ec60f248547d4d062a1160f0fc26d742319888`. Publish the engine commit separately and retain the identical mail patch in this repository. The M2a engine commit is `2850af59a5df2fe32aaff718b8e3dbb01808ecdd` on `CaptainCucumber/OpenTTD:copilot/m2a-native-identity`.
- Extend the authenticated Admin transport with request packet 11 and response packet 130. Copilot protocol v1 is independent of OpenTTD Admin protocol v3. The request contains only version, typed request kind, correlation ID, and explicit company selector. Unknown versions, unknown request kinds, missing companies, and non-loopback peers receive bounded typed rejection.
- Return only observed frame, seed, calendar date, map dimensions, landscape, and bounded company records. Company records contain ID, AI/human flag, signed cash, loan, and display name. Do not select a company by name or silently choose among multiple human companies.
- The v1 handler requires an already active Admin connection, checks IPv4/IPv6 loopback, runs in the existing game-thread Admin receive path, and does not call the GameScript instance. It exposes no RCON, arbitrary console, code execution, or gameplay mutation.
- Runtime result: the custom build reads world/company identity from an isolated representative autosave copy and rejects protocol v2. In a separate copied saved-world gate, the foreign GameScript remains loaded, advances tick 10 to 13, and reports zero mutations while two native queries succeed. See the [M2a report](M2A_REPORT.md).
- Identity limit: M2a's observed seed/map/date fields are not a durable world lineage. M2b must add versioned persisted world/operation identity before recovery claims and must keep the first mutation allowlisted, capped, and routed through normal OpenTTD command validation.

## D015 — Bound the first native mutation and persist its identity

- Date: 2026-10-23. Status: **implemented and runtime-verified for M2b's one-piece scope**.
- User requirement: assist the human company through normal game rules, within a construction cap, without fictitious rollback or unsafe replay. The M2b scope is an engineering checkpoint, not authorization to manage the company or build a route.
- Design: protocol v2 accepts a single typed rail-piece command on a flat clear tile, with explicit company/world, expected sequence/head, operation ID, payload hash, and maximum cost. The engine quotes before executing, posts the wrapper through the normal synchronized command pipeline, then records callback outcome and authoritative readback. It admits one operation per world; expanding this requires an explicit bounded-history design.
- Persistence: COPL schema 1 stores world/operation identity and terminal result. The external journal fsyncs intent before send and classifies current/older/changed/ahead/diverged positions. A loaded pending record becomes uncertain, never automatically retried. This does not make save and command execution atomic.
- Source finding: OpenTTD's posted command callback can report the actual result after the game-thread command, while its normal command validation owns terrain, ownership, cost, and company rules. Do not substitute an Admin-thread direct tile edit.
- Runtime result: the clean committed 15.3 custom binary rejected a zero cap without mutation, built one rail piece for 90 under a 1,000 cap, preserved the result across duplicate request and save/reload, and detected the older source save. See [M2b report](M2B_REPORT.md). Pending-save fault injection, client/network synchronization, and stock-build compatibility remain unproven.

## D016 — Observe vehicle-tagged service events in the native bridge

- Date: 2026-10-23. Status: **implemented and runtime-verified for M2c's isolated service scope**.
- User requirement: verify that the assigned train leaves the mine fully loaded and delivers to the intended power station. The stock CargoMonitor's company/industry counts cannot generally identify the delivering vehicle.
- Design: protocol v3 adds a read-only event query behind the existing authenticated loopback Admin boundary. Capture per-cargo train load/capacity in `Vehicle::LeaveStation`. Thread the paying front vehicle ID through `CargoPayment::PayFinalDelivery` to `DeliverGoodsToIndustry`, where the exact industry-accepted amount is known. Return events from a 256-record runtime ring in pages of at most 16, filtered by company and vehicle, with sequence cursor, gap marker, world ID, and randomized per-process epoch incremented on world initialization.
- Lifecycle boundary: events survive Admin reconnect in the same running world. They do not survive save/load or process restart; a changed epoch or gap makes continuity unverified. The ring does not modify COPL save state. Delivery chunks must be grouped by visit rather than counted as separate trips.
- Runtime result: the clean 15.3 custom build observed train 2 depart source station 0 twice at 30/30 coal and deliver to station 1/industry 11 on both trips in the isolated fixture. See the [M2c report](M2C_REPORT.md). The GameScript still built and operated this fixture; native complete-route construction remains M2d.
