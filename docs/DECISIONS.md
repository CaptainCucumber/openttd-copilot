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

## D017 — Add bounded native tile observation without changing the mutation boundary

- Date: 2026-10-23. Status: **implemented and real-engine verified as an M2d read-only checkpoint**.
- User requirement: derive railway placement from the live game world while preserving company assets and normal command validation. The planner needs authoritative terrain and ownership records before selecting a route.
- Design: add request kind 4 to protocol v3 so existing identity, mutation, and vehicle-event clients remain compatible. Require authenticated loopback Admin, exact world identity, a contiguous start tile, and count 1–32. Return frame and typed validity, tile type, owner, slope, height, and plain/crossing rail geometry. Keep reads on the game-thread Admin path and do not expand the mutation allowlist or COPL save state.
- Snapshot limit: a page is coherent at its response frame, but multiple pages can span game frames. `track_bits` excludes station/depot rail geometry. This is not an industry/asset/catalog snapshot and does not prove route feasibility. Revalidate planned dependencies before any mutation.
- Runtime result: a clean committed custom build observed the known clear, rail, station and void tiles in a copied control save; rejected a mismatched world ID; repeated the tile page after reload; and changed no company balance, loan, operation sequence, source save, or normal profile. See the [tile report](M2D_TILE_REPORT.md). M2d's complete railway gate remains open.

## D018 — Extend read-only world observation and correct unowned tile handling

- Date: 2026-10-23. Status: **implemented and real-engine verified for industry pages and a broader tile window**.
- User requirement: resolve coal producers and accepting destinations from the loaded world, then plan from observed terrain without crashing on ordinary map tiles. This remains a read-only planning checkpoint.
- Design: protocol-v3 request kind 5 returns at most 16 industries per page with ID, type, anchor tile, and valid produced/accepted cargo IDs. Ordinal pages carry their own frame and world ID. A short page ends the scan. Anchor tiles do not describe the industry's whole footprint, and cargo IDs do not substitute for a catchment or station-acceptance check.
- Source/runtime correction: OpenTTD's `GetTileOwner` asserts on `MP_HOUSE` and `MP_INDUSTRY`; a 35-by-2 tile sweep reproduced this against a copied save, crashing the earlier tile handler. Return `OWNER_NONE` for those unowned tile types. The failed artifact is retained; the corrected committed build passed the same sweep. Multiple tile/industry pages are not atomic, so the client records frame range and rejects a changed world/operation sequence while collecting them.
- The change adds no gameplay mutation and does not expand the persisted COPL schema. See [industry checkpoint report](M2D_INDUSTRY_REPORT.md). Native full-route construction and recovery gates remain open.

## D019 — Read the human company's rail catalog before train selection

- Date: 2026-10-23. Status: **implemented and real-engine verified as a read-only M2d checkpoint**.
- User requirement: select a currently available locomotive and coal-compatible wagons that can run on the company's rail type and fit the planned platforms, without inventing availability, capacity, or price.
- Design: protocol-v3 request kind 6 returns company rail types and up to 16 train engine definitions per page. For each definition, derive current buildability through `IsEngineBuildable`, and report rail vehicle class/types, default cargo/capacity, refit mask, purchase/running cost, speed, power, weight, and nominal shortening. Require explicit world/company and retain page frames; reject non-human or missing companies.
- Boundary: catalog values only nominate candidates. NewGRF/refit callbacks, articulated capacity and length, actual purchase cost, orders, and final consist state require normal engine command validation and readback. Multiple pages can span frames and must be rechecked before mutation. No COPL save or mutation boundary changed.
- Runtime result: the clean committed build returned 116 train definitions, 14 buildable for human company 0, with typed wrong-world/missing-company rejection and identical copied-save reload. See [catalog report](M2D_RAIL_CATALOG_REPORT.md). Native purchase and full railway construction remain open.

## D020 — Read existing company rail stations and depots

- Date: 2026-10-23. Status: **implemented and real-engine verified for the tested human-company assets**.
- User requirement: preserve existing infrastructure and verify what the company already owns before proposing station/depot placement or interpreting a completed build.
- Design: protocol-v3 request kind 7 returns bounded separate pages of company-owned rail stations and depots. Station records report ID, sign/base tile, train-platform area, and current acceptance mask; depot records report ID, tile, entrance direction, and rail type. All pages bind world/company/class/frame. The query does not mutate the world or COPL save state.
- Scope: current acceptance at an existing station does not predict candidate catchment. Industry footprints, full station tile track geometry, and vehicle/order details require additional reads. The saved fixture lacks an AI company, so the nonhuman rejection branch is not runtime-proven.
- Runtime result: the clean custom build read station 0's 2×1 platform in the control save and an owned depot plus two stations in a copied service save; the destination station's mask included coal. Wrong-world/missing-company rejection and fresh-process control-save reload passed. See [assets report](M2D_RAIL_ASSETS_REPORT.md).

## D021 — Observe bounded train consist parts without inferring orders

- Date: 2026-10-23. Status: **implemented and real-engine verified for an empty control save and one-train service save**.
- User requirement: verify the actual purchased consist and coal capacity rather than relying only on train catalog estimates or assuming a wagon is a separate train.
- Design: protocol-v3 request kind 8 scans at most 256 vehicle pool IDs and returns at most 16 owned train parts per page. An exclusive ID cursor handles sparse pools. Records include primary/root/previous/next IDs, engine, unit, tile, state, cargo ID, amount, and capacity. The query requires an explicit human company and world, remains read-only, and does not extend COPL save state.
- Boundary: parts and cargo are momentary observations; multiple pages are not atomic. Orders, who purchased the train, route traversal, loaded departure, accepted delivery, save-lineage reconciliation, and native purchase remain separate. A displayed cargo amount is not service success.
- Runtime result: the clean build returned no train in the control save and a reciprocal two-part consist (primary train 2, coal wagon 3) in a copied service save. Typed wrong-world/missing-company rejection and unchanged source saves passed. See [train-parts report](M2D_TRAIN_PARTS_REPORT.md).

## D022 — Read bounded train orders without expanding mutation scope

- Date: 2026-10-23. Status: **implemented and real-engine verified as an M2d read-only checkpoint**.
- User requirement: ensure the train's actual orders express full-load-at-origin and delivery-at-destination intent; catalog and consist observations alone do not establish this.
- Design: protocol-v3 request kind 9 reads a page of at most 16 orders from an explicit human-company primary train. Return world/frame/company/train identity, total order count and offset, plus engine-decoded order type, destination ID where applicable, load policy, unload policy, and non-stop flags. Non-applicable policy/stop fields use an explicit unavailable sentinel rather than interpreting overlapping flags from depot/conditional orders. It rejects non-trains, non-primary parts, foreign/missing companies, wrong worlds, and invalid ranges. No gameplay command, save chunk, or mutation allowlist is added.
- Observation limits: pages are frame-stamped but not an atomic snapshot; vehicle and station IDs can change as the world advances. This read proves configured order values, not route reachability, cargo arrival, purchase identity, or service success. Revalidate before acting.
- Runtime result: clean engine commit `5f8e025d70c9eb6faeca1bc797b1377039ed0ca8` returned two orders for train 2 in a copied service save: full load to station 0, then no-load/unload to station 1. Reload returned the same values; wrong-world, missing-company, and missing-train rejection passed. The client also unit-tests explicit unavailable fields on conditional orders. See [train-order report](M2D_TRAIN_ORDERS_REPORT.md).

## D023 — Add industry names and location bounds as a separate read-only page

- Date: 2026-10-23. Status: **implemented and real-engine verified as an M2d read-only checkpoint**.
- User requirement: resolve named origin/destination industries using live world data, while keeping route geometry and construction deterministic.
- Design: protocol-v3 request kind 10 adds a separately typed page of up to eight industry records with ID/type, anchor, cached UTF-8 name (up to 96 bytes with explicit code-point-safe truncation marker), `TileArea` width/height, and valid produced/accepted cargo IDs. Keep kind 5 unchanged, bind every page to the requested world, and do not change the mutation allowlist or save state.
- Boundary: `TileArea` is a rectangular location bound, not proof that every enclosed tile is occupied. The details page is frame-stamped and can be stale across pages; compare identity and revalidate before acting. Names are engine-cached/localized display strings, not stable identity; use industry ID plus world ID as identity.
- Runtime result: clean engine commit `211e780180c021b208a87d2612f4c24be9f743a6` returned 13 names and positive bounds on the copied 128×128 control save. Details matched kind-5 identity/type/anchor/cargo fields; the coal pair resolved to Madhattan Coal Mine and Great Beninghall Power Station. Wrong-world rejection, bounds checks, unchanged company/operation values, tile sweep regression, and fresh-process reload passed. The source save and normal profile remained unchanged. Parser tests cover UTF-8 and truncation markers; no fixture name crossed the real-engine truncation threshold. See [details report](M2D_INDUSTRY_DETAILS_REPORT.md).

## D024 — Provide the first AI-facing playable demo through local MCP

- Date: 2026-10-23. Status: **implemented as a controlled demo; general builder remains open**.
- User requirement: open a new map, tell an AI to build a simple railway between businesses, and play the result.
- Provisional interface choice: use a local stdio MCP server so a compatible AI client supplies conversation/model access and the game-control process remains local. This follows the prior D010 recommendation; it does not claim user confirmation of a particular MCP host or provider.
- Implementation: expose `open_demo_map`, `build_coal_railway`, and `get_build_status`. The server validates the one supported coal/full-load request and delegates to the previously real-engine-verified disposable one-train fixture. The build tool call authorizes the fixture; the game opens before construction, and successful completion opens the saved service.
- Boundary: this is not a general route planner or production adapter. The fixture creates its own test mine and power station, uses GameScript for multi-command construction, and does not select arbitrary existing businesses or mutate a normal save. Job state is not resumable after MCP-server restart. The tool result and guide disclose these limits. M2 complete-route construction, safe multi-operation native journaling, and arbitrary industry/site selection remain unproven.

## D025 — Retain a bounded native operation history before adding railway commands

- Date: 2026-10-23. Status: **implemented and real-engine verified as a bounded M2d rail-operation checkpoint**.
- User requirement: continue toward building a railway between existing businesses, preserving normal game rules, budget intent, and honest partial outcomes. Sequential commands need recoverable operation identity before adding stations, depots, and vehicle purchase.
- Design: retain up to 64 admitted flat-clear-tile rail operations per world, without eviction. At most one is pending; pending/uncertain state prevents another admission. Each distinct request must match the current successful-operation sequence and last-success operation ID. Rejected attempts consume history capacity but neither advance that position nor replace its head. Per-command caps still apply; this checkpoint does not introduce a whole-job budget.
- Replay: match both operation ID and actual immutable command fields/hash before returning a retained outcome. Old IDs cannot become new commands, including when the history is full. Response sequence/head and tile/company readback describe the current world; cost/error/completion frame describe the requested historical operation. Do not interpret historical readback as a saved snapshot.
- Persistence: COPL schema 2 stores the active record and chronological terminal history. Read schema-1 single-record saves and migrate in memory; validate record count/index, terminal-history states, unique operation IDs, and sequence progression. Pending loads remain uncertain. Older custom binaries are not expected to read schema 2; no stock-save round-trip claim is made.
- External intent remains an fsynced one-operation journal per file. Retain every file in the run/job directory; do not clear or overwrite an unresolved journal to continue. Unknown outcomes, loaded older saves, and the mutation/save crash gap still require reconciliation rather than automatic replay. This is a bounded prerequisite checkpoint, not M2 completion.
- Runtime result: clean engine `bded382135c91932c86f354f071b4f101af3b85e` built two native rail pieces for 90 units each, retained all 64 admitted records across individual reload queries, preserved historical exact replay without mutation, rejected conflict/stale/full-history requests, migrated a completed schema-1 record, and recognized the older source save. Loan and original source/profile fingerprints stayed unchanged. See [the report](M2D_SEQUENCE_REPORT.md) and [evidence](evidence/2026-10-23-native-sequence-probe.json). Pending-save and crash-gap fault injection remain open.

## D026 — Build bounded new rail stations and depots through normal commands

- Date: 2026-10-23. Status: **implemented and verified as a bounded M2d checkpoint**.
- User requirement: advance from native rail pieces toward a complete railway for the player's company, preserving normal cost, authority, ownership, and terrain rules.
- Scope: one new default single-platform rail station, length 1–7 on either axis, or one rail depot in a diagonal orientation. Require a clear flat footprint at one height. No joining/reuse/replacement, non-default station classes, terraforming, vehicle purchase, or complete route is added.
- Execute a typed wrapper through the normal synchronized command pipeline. Quote the normal station/depot primitive before execution and recheck the per-command cap in the wrapper. Capture the created asset ID immediately in the matching callback; absent identity after successful construction becomes uncertain and blocks continuation rather than reporting a fictitious asset.
- Protocol-v3 kinds 11/12 add infrastructure build/status. Their response extends the existing operation body with kind, length, and historical created-asset ID. The old rail status kind 2 refuses infrastructure records instead of returning an incomplete identity; old rail command kind 1 cannot replay a station/depot ID as a rail command. World/ID/hash and immutable fields remain bound. Independent existing-asset pages establish current geometry/ownership; a historical ID is not proof an asset still exists or that its numeric ID has not been reused.
- COPL schema 3 persists kind/length/created ID, migrates schema-1/2 rail records, and keeps D025's non-evicting 64-record cap and uncertain-state refusal. Existing rail wire layouts remain unchanged. Earlier custom binaries are not expected to load schema 3. External fsynced intent is retained per operation; no save/command atomicity, whole-job budget, or automatic uncertain retry is claimed.
- Runtime result: clean fork `2c4dfef1bdee73f9994323c8139afd25768db150` passed four copied-world runs covering both station axes and all four depot directions. Each two-tile station cost 750 and depot 540; created IDs, costs/frames, successful head, assets, cash/loan, replay, and reload matched. All 64 old schema-2 outcomes survived migration and schema-3 reload; the sequential regression also passed schema-1 migration. Other station lengths are permitted but not runtime-tested here. See [report](M2D_INFRASTRUCTURE_REPORT.md) and [evidence](evidence/2026-10-23-native-infrastructure-probe.json).

## D027 — Purchase rail vehicles with the command's returned identity

- Date: 2026-10-24. Status: **implemented and real-engine verified as a bounded purchase checkpoint**.
- User requirement: continue toward native operation of the player's railway without invented vehicles, prices, or successful results. A purchase must retain the actual vehicle ID before assembly/orders can safely target it.
- Scope: one currently available rail engine or wagon in an owned rail depot, default cargo only. Use normal `CMD_BUILD_VEHICLE` quote/execute validation; recheck the per-command cap at execution. Disable automatic locomotive adoption of free wagons. Stock wagon purchase can join a same-engine free wagon chain, so refuse that condition rather than silently modifying another chain. Assembly, refit, orders, start/stop, whole-job affordability, and complete route operation are not added.
- Return the underlying command's VehicleID through the typed tuple callback together with serialized operation identity. Confirm owner, engine type, and depot before marking completed; absent/mismatched returned identity becomes uncertain and blocks continuation. Independent existing train-part pages verify the resulting vehicle and chain. Historical created IDs are not proof of perpetual asset ownership or unreused IDs.
- Protocol-v3 requests 13/14 carry purchase/extended status with the immutable engine ID; old response layouts stay unchanged. Status 14 can read earlier rail/station/depot records; old rail/infrastructure status endpoints explicitly refuse purchase records. Bind replay to all actual immutable fields, including engine ID, not only the supplied hash.
- COPL schema 4 persists engine ID and migrates earlier retained records with an explicit non-purchase sentinel. Shared non-evicting 64-record cap, successful head, admitted-rejection retention, fsynced per-operation external intent, loaded-pending uncertainty, and no-automatic-uncertain-retry policies remain unchanged. No mutation/save atomicity or crash-recovery claim is added.
- Runtime result: clean fork `7252756e936740771bac43fa74b66b050b8c68ce` returned actual IDs 4/5/6 for two engine-0 locomotives (8,203 each) and an engine-29 coal wagon (1,031). Independent parts remained three separate chains; the second engine did not adopt the free wagon. Exact-cap success, one-unit-below/zero-cap rejection, wrong depot/unavailable engine/same-wagon-joining refusal, guards, immutable replay, all 12 outcomes after reload, and cash/loan/asset preservation passed. Four schema-3 outcomes migrated unchanged; rail/infrastructure regressions covered earlier schemas. See [report](M2D_TRAIN_PURCHASE_REPORT.md) and [evidence](evidence/2026-10-24-native-train-purchase-probe.json). Assembly/orders/start and M2 service remain open.

## D028 — Configure a train through explicit retained actions, not toggle replay

- Date: 2026-10-24. Status: **implemented and real-engine verified as a bounded configuration checkpoint**.
- User requirement: continue toward a runnable native-built railway. Keep assembly, configuration, and actual transport as distinct observable steps.
- Scope: attach an explicitly selected free wagon chain to the tail of an explicitly selected owned primary train, with both stopped in the same depot. Append at most two station orders to an unshared order list, checking the expected append index and an owned rail station. Fixed policies are full-load-all/no-unload at the source and no-load/unload-if-possible at the destination. Both order editing and attachment require a stopped depot train; no replacement/reordering/sharing/refit/automatic vehicle selection is added.
- Set an explicit desired running state, rather than expose a blind toggle. Starting requires a stopped depot train with two orders and normal engine start validation; stopping may target the live observed tile outside a depot. Already-desired state is a successful zero-cost action. Replaying a historical start after a later stop returns the original retained outcome and must not start the train again. A started train is not evidence of reachable stations, cargo catchment, or service.
- Typed wrapper commands quote and execute normal `CMD_MOVE_RAIL_VEHICLE`, `CMD_INSERT_ORDER`, and `CMD_START_STOP_VEHICLE`. Per-command caps, ownership, and normal game validation still apply. Matching callbacks verify the resulting chain, appended order, or stopped flag; postcondition failure becomes uncertain without advancing the successful sequence.
- Additive protocol-v3 requests 15/16 retain action, source vehicle, target, expected order index, and policy; old wire layouts are unchanged and old status endpoints refuse configuration records. Bind every immutable field on replay. Configuration creates no asset ID. COPL schema 5 migrates earlier records with explicit non-configuration sentinels and retains the shared 64-record bound. Fsynced per-operation intent, uncertain blocking, and the unresolved mutation/save crash gap are unchanged.
- Runtime result: clean engine `ff8bd20ef55b26505693e315d71d291967cce0a9` attached wagon 5 to locomotive 4 (30 coal capacity), appended exact policies for stations 0/1, started and stopped the primary, and preserved the spare locomotive. All 24 prior/new outcomes survived fresh-process reload and historical replay without restarting the stopped train. Seven completed actions and five rejections had zero command cost; cash 80,433 -> 80,431 includes two units of normal simulated running expense, with loan unchanged 100,000. The locomotive began leaving the depot before stopping, so unchanged in-depot status is not a valid start/stop postcondition. No reachable service is proven. See [report](M2D_TRAIN_CONFIGURATION_REPORT.md) and [evidence](evidence/2026-10-24-native-train-configuration-probe.json).

## D029 - Connect a bounded existing-business native railway before expanding scope

- Date: 2026-10-24. Status: **implemented; native service and visible MCP verified**.
- User requirement: reach a runnable map where an AI can construct a simple railway between existing businesses, not another disconnected primitive or a fixture that creates substitute industries.
- Add read-only request 17 for normal test-mode rail/station/depot pricing, retained-history capacity and selected-industry prospective coverage/acceptance. Count only actual tiles belonging to that industry, not its bounding rectangle or another nearby industry. No operation is admitted by quoting. Keep protocol 3 and COPL schema 5; existing layouts are unchanged.
- Provisional alpha defaults: newly generated 128-by-128 temperate map, seed 6, no initial trees, standard content, sole human company 0, one coal locomotive/wagon, two-tile stations and inline source depot. The deterministic planner uses observed flat-clear unowned equal-height tiles, at most 32 station proposals per end, 128 candidate pairs, 100,000 total directed-state expansions and 50 rail tiles. These are incomplete search limits, not proofs of infeasibility or optimum cost.
- Source finding and reproduced failure: `pf.forbid_90_deg` defaults true. Reciprocal tile edges alone permit adjacent curve transitions that the actual train rejects. Include the previous track in search state and reject OpenTTD's crossing-track transitions, without weakening the setting. The original seed-6 run stalled after loading; the corrected geometry transported the coal.
- Check the complete quoted infrastructure plus live vehicle prices, construction cap, existing cash plus disclosed reserve, and all required retained records before mutation. Recheck identity, normal command quotes, cash, loan and prices at execution. Normal commands still own legality. Preserve partial work and unknown sends; do not automatically roll back or retry them.
- Store a fsynced JSON job and separate fsynced operation journals before send, rather than add a second SQLite execution store at this checkpoint. Terminal job lookup checks the live world/head against the last retained outcome; an older save cannot inherit a cached completed result. This does not close the mutation/save crash gap.
- Source finding: native departure events omit empty cargo. Observe a third full source departure after two delivery cycles to establish both returns, rather than wait for nonexistent empty destination-departure events.
- Interface: isolated matching graphical client plus server; native MCP high-level tools accept only observed industry IDs and explicit cap/reserve/full-load intent. The optional local sentence parser is model-free. Cached status is not a health monitor. User play time does not consume the next job's deadline; orderly shutdown saves before closing.
- Runtime result: clean engine `96f960a3239e87837919414604a19e3eca9830b7`, naturally generated Canley source 10/destination 1, 44 native actions costing 14,979, train 2/wagon 3, three 30/30 departures and two accepted delivery cycles. Visible stdio MCP, duplicate calls, saved close, selected-industry nonmutation quotes, older-save refusal and all mixed outcomes across reload/replay passed. This is the M2 simple-profile path, not the M3 cohort or M4/M5 release gates. See [report](M2D_NATIVE_RAILWAY_REPORT.md).

## D030 - Use actual Copilot conversation with separate observation and authorization

- Date: 2026-10-24. Status: **implemented; bounded actual-host advice verified**.
- User requirement: talk naturally about game state, options and optimizations, not merely enter a fixed build sentence. The previous parser was insufficient.
- Provisional host choice: installed signed-in Copilot CLI, session-scoped additional MCP configuration and a game-only custom agent. No new provider/key, provider framework or global MCP modification. The user was unavailable for host selection; this is a documented default, not an explicit provider preference.
- Add fresh bounded live inspection and nonmutating route quotes, sharing existing native readers and deterministic planning. No new engine requests at this checkpoint. Do not serialize live reads concurrently with a build on the same Admin connection; reject them while the worker is active.
- Model scope: only native game tools and user clarification; no coding/shell tools. Autoallow only inspection/planning/cached status. Advice is not spending permission; explicit unambiguous construction intent binds observed businesses and understood cap/reserve/full-load policy. Host construction/lifecycle permissions remain separate.
- Live state is non-atomic and frame/epoch/gap bounded. The bridge currently lacks profit, actual speed, production, station queues and detailed income. Recommendations must not claim measured financial improvement or ongoing route health from historical deliveries.
- User failure reproduced: source 12 -> 1 exceeds the selected station candidates' lower bound (70 rails vs 50). Planning-only failures are `rejected`, not partial construction; changed explicit requests are allowed only before executor entry. All execution/verification failures retain the no-automatic-retry boundary.
- Runtime results: actual Copilot named-business advice invoked six game calls, including two live inspections/two plan comparisons, no build; source 10 quoted 14,979, source 12 rejected, empty assets/history and cash/loan preserved. Separate same-map rejection -> successful service and populated-train copied-save inspection passed. See [evidence](evidence/2026-10-24-native-game-chat.json). A single host scenario is not the M4 paraphrase/ambiguity cohort or a broad optimization acceptance claim.

## D031 - Add bounded town buses and ordinary maps without autonomous management

- Date: 2026-10-24. Status: **bounded clean-engine service and actual-host build verified**.
- User requirement: construct passenger buses between towns and play on an ordinary map, rather than the selected flat coal fixture. This explicitly expands transport scope, not authority for autonomous company management or arbitrary demolition.
- Provisional alpha defaults: new conversational games use randomly seeded 256x256 temperate maps with towns, trees, hills and water/rivers. `--map-style railway-fixture` preserves the selected seed-6 rail regression. Existing saves are copied and keep their settings; normal profiles/original saves remain untouched.
- Design: additive protocol-v3 JSON request 18 reads bounded towns/roads/engines/assets/orders, quotes normal commands and admits retained kinds 7-12. The same COPL schema-5 fields encode bus actions without a layout change. Preserve the shared non-evicting 64-record history, journal-before-send, actual returned asset identity, normal command validation and uncertain-state blocking.
- Deterministic code chooses two distinct producing/accepting roadside stops, a connected depot, bounded road links and one available standard passenger bus. The model supplies observed towns and explicit cap/reserve, never coordinates/prices. Ordinary pickup/unload is not a silent substitute for requested full load. New flat clear/tree road/depot footprints are disclosed; no houses/assets, borrowing, bridges, tunnels or terraforming.
- Share railway execution's identity/budget/loan/journal boundary. Build stops before any tree clearing can lower authority ratings; recheck selected-town production/acceptance before each stop. Verify actual vehicle, capacity and two ordinary orders independently, then require bus-attributed accepted passengers at both stops. Starting/moving alone is not completion.
- Different explicit services may follow verified operation within cash/history; identical payloads remain lookups. Failed/uncertain execution still blocks changed requests. Tool scope does not limit ordinary manual GUI construction.
- Source/runtime findings: sentinel validation, expanded-area lifetime, transport signature and callback registration defects were reproduced and corrected. Wire vehicle sentinel `0xFFFFFFFF` differs from native invalid ID `1048575`; normalize the boundary rather than weaken preconditions. Explicit `FarEnd` stop-location bits make ordinary orders legal for road vehicles. Reject above-cap quotes identically in test and execute phases; reject noncanonical kind fields before retaining records the loader would refuse. A host inspection exceeded its output bound; restrict passenger catalogs to available engines and prohibit shell/SQL fallback rather than grant coding permissions.
- Final runtime result: clean engine `2fb530eda610857329872eab1acaa9788de49f89` passed 27 actions costing 8,725, passengers accepted at both stops, duplicate/all-outcome reload/replay/older-save checks, canonical-shape nonadmission and zero-charge quote-150/cap-149 rejection retained across reload/replay. Actual Copilot built once, reached operating, independently inspected orders and saved/closed using only native tools. Coal/44-outcome legacy resave regressions and 263 Python tests passed. See [bus evidence](evidence/2026-10-24-native-town-buses.json). This is not a random-map feasibility cohort, measured financial optimization or M3/M5 release acceptance.
- Direction clarification, 2026-10-24: the next work packages are supported-world reliability, interruption/recovery, richer grounded observation/advice, conversational acceptance/authorized resumption and local-alpha packaging. Keep these inside M3/M4/M5 rather than expanding into autonomous company management or more modes before existing service/recovery gates. See the [sequenced plan](PROJECT_PLAN.md#next-milestone-sequencing).

## D032 - Host the native bridge in the single-player game process

- Date: 2026-10-24. Status: **accepted design; not implemented**. Supersedes the *transport and process topology* parts of D013/D014 (Admin packets 11/130 over an authenticated Admin connection to a dedicated server joined by a separate client). The D013 choice of a narrow native bridge, and all command, budget, journal, COPL and verification boundaries, remain.
- User requirement: "This is only for local games, I don't need a multiplayer at all. If it makes it simpler, then let's do it."
- Design: one visible OpenTTD process. Copilot requests reach a transport-neutral game-thread dispatcher through a loopback-only, per-launch-token local endpoint polled from `NetworkBackgroundLoop()`. Payloads keep their existing layouts; protocol v4 adds hello/capabilities, `local_company`, game mode/pause state, tick-based frames, typed refusals and bounded save/quit lifecycle requests. Mutations require the local company, an active normal game, an unpaused game and no networking. See the [M2f plan](M2F_LOCAL_BRIDGE_PLAN.md).
- Source findings (fork `2fb530eda6`): Admin listening and polling exist only in network-server mode; single-player `Post` runs synchronously; none of the `CMD_COPILOT_*` traits sets `NoEst`, so a held Shift would turn a mutation into an estimate and skip its callback; paused posts show a player popup; `_frame_counter` does not advance outside networking. Each needs an explicit change rather than reuse of the server-path assumptions.
- Tradeoff: runtime and user flow become simpler (one binary/process/port, no client keys, joins or console saves). Engine code grows modestly (listener plus single-player guards). Multiplayer use of Copilot is explicitly refused, not supported.
- Transition: keep the Admin adapter and server/client harness as a regression path until the M2f gate passes; then retire them from the product launcher. Historical evidence remains valid for the revisions it recorded.
- Sequencing: M2f precedes M3a/M3b because interruption, restart and packaging tests depend on the runtime topology.
- Cross-platform clarification, 2026-10-25: user requires a cross-platform solution. The endpoint is loopback TCP via OpenTTD's portable socket layer; Unix-domain sockets, named pipes and other OS-specific IPC are excluded. Python must remove macOS-only code (directory fsync that fails on Windows, `lsof`, `cocoa`, app-bundle paths). macOS remains the only tested platform until Windows/Linux runtime evidence is recorded (M5).

## D033 - Preserve one bus line across multiple towns and explicit stop insertion

- Date: 2026-10-25. Status: **implemented; bounded service/reload/replay and actual-host edit/inspection/saved close passed**.
- User requirement: address playtest limitations preventing a single bus line through more than two cities and adding stops to existing lines. Interpret "lane" as service/order list, not a new dedicated road type.
- Design: ordered observed towns (2-8), one bus/depot, shared intermediate stop geometry, merged road additions, whole-line cost/history admission and passenger acceptance at every stop. Eight is a provisional transport bound; no autonomous network expansion.
- Existing-line edits bind an observed vehicle and exact unshared ordinary station orders; insert new stops at an explicit order index, preserving old orders/vehicle/depot. Build only the required new roadside stops/links, then stop the running bus, recheck its orders, insert through normal commands and resume. Shared orders, nonordinary policies, crashes, unsupported geometry and stale edits are refused. The initial supported edit targets a running bus.
- Engine kinds 11/12 retain normal insert-order/desired-state command validation and the same schema-5 field layout. Widen kind-11 index admission/load validation together; bound order reads to eight. Updated builds can read old saves; old builds are not promised to read expanded-order saves.
- Failures after any mutation retain partial construction and possibly a stopped bus; no automatic rollback, retry or promised recovery. Existing budgets, no-loan policy and 64 shared retained records are unchanged. M2f topology remains planned, not silently included in this task.
- Runtime: final engine `faf823d8ab` built a three-town normal-density line with 54 retained actions and passenger acceptance at every stop; all-outcome reload/replay and older-save refusal passed. Separate explicit high-town-density seed 20261024 inserted Plontford into running bus 5's Pafingfield/Prarnway line for 3,182/23 new actions, preserving `[0,1]` as `[0,2,1]`, with passengers at all three stops and all 50 combined outcomes surviving reload/replay. Normal-density insertion of Drahill remained safely rejected at 48/37 records. These selected cases do not establish unrestricted map/history feasibility.
- Actual host: a separate copied-line gate called the add-stop tool once, observed accepted passengers 28/62/5 at stations 0/2/1, independently inspected the same running bus's exact orders, then saved/closed. Native tools only, no retry or extra construction. All 277 tests pass. See [evidence](evidence/2026-10-25-native-bus-lines.json).
