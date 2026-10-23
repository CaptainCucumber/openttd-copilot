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
