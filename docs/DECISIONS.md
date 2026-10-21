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

- Date: 2026-10-20. Status: **user confirmed; adapter choice pending M1**.
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

- Date: 2026-10-20. Status: **proposed**.
- Initial service candidate: Python, SQLite, CLI; minimal Squirrel adapter or a narrow C++ engine bridge. External chat/model provider selected after the deterministic builder works. MCP is optional interface work.
- Reason: keep the first engineering effort on state/control and route construction, with few moving parts. No runtime dependencies installed yet.
- Revisit at M1 based on protocol integration and performance measurements.
