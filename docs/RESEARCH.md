# Source research

Inspected: 2026-10-20. This is a source/documentation review and a read-only local environment inventory. **Neither reference project nor our proposed adapter was run.** Source findings must not be presented as a measured explanation of the user's past failures.

## Pinned references

| Project | Revision inspected | Scope |
|---|---|---|
| OpenTTD | 15.3, `14ec60f248547d4d062a1160f0fc26d742319888` | Admin documentation; company, rail, vehicle, order, engine, accounting, test-mode and admin script APIs; command processing and GameScript lifecycle excerpts |
| OVER99K/openttd-directorate-mcp | `b6eda7f433f28c86602181f059c8ae768e4d8579` | README, tree, planner, station survey, construction program, CI, verification document, integration-gate excerpts |
| jplattel/openttd-llm | `992ab8a0e12aabf861793ce83878518e52d0bf0e` | README, tree, decision loop, runtime paths, and AI symlink target |

The official latest-release API returned **15.3** at inspection. The installed application's `CFBundleShortVersionString` also reports 15.3. That is installation metadata, not runtime validation or a binary checksum. [Release](https://github.com/OpenTTD/OpenTTD/releases/tag/15.3), [pinned engine commit](https://github.com/OpenTTD/OpenTTD/commit/14ec60f248547d4d062a1160f0fc26d742319888).

## What OpenTTD provides

### Acting for the player is possible in the stock API

`ScriptCompanyMode` explicitly executes scoped actions for the selected company and charges that company. Insufficient funds cause rejection. This supports a GameScript experiment in a human company; it does not prove our whole adapter works. [Company-mode source](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_companymode.hpp).

The shared script APIs expose rail/station/depot construction, vehicle purchase/refit, and orders to GameScript as well as AI scripts. These APIs are sufficient to investigate the core coal-route sequence. [Rail](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_rail.hpp), [vehicles](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_vehicle.hpp), [orders](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_order.hpp).

Full-load-all and full-load-any are distinct order flags. For an all-coal consist, require the requested coal capacity to be full before departure; verify actual vehicle capacity/load and installed orders. The engine API also exposes price, capacity, running cost, power, weight, and tractive effort for train selection. [Order flags](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_order.hpp#L43-L79), [engine properties](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_engine.hpp).

### The transport has concrete constraints

The Admin protocol supports external connections, company information, chat, and console administration. Clients remain connected across new games/save loads, so a live socket cannot establish that entity IDs still refer to the same world. Its documentation also says the old password join is disabled by default and describes secure authentication. Plan protocol/version handling explicitly. [Admin network documentation](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/docs/admin_network.md).

`GSAdmin.Send` documents a **1,450-byte JSON limit** for a script-to-admin message. Paging/chunking and bounded queries are necessary for map data on that path. This limit should be checked against the built adapter, including UTF-8 framing and overhead. [Admin script API](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_admin.hpp).

### Test mode is not a whole-plan transaction

Script test mode checks commands and estimates their costs without applying changes. Script accounting tracks command costs in test and execute modes. Therefore we need dependency-aware sequence validation and actual command accounting rather than a sum of catalogue prices or bank-balance deltas. [Test mode](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_testmode.hpp), [accounting](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_accounting.hpp).

The script command result path handles estimates separately and can suspend scripts for actual command completion. The engine command pipeline validates test/execute results and money. These are important boundaries for either adapter; a custom bridge should preserve them. [Script command results](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/script/api/script_object.cpp#L285-L334), [engine command processing](https://github.com/OpenTTD/OpenTTD/blob/14ec60f248547d4d062a1160f0fc26d742319888/src/command.cpp).

Do not infer a throughput figure or paused-game capability from these source excerpts. Measure those in M1.

## Reference project: OpenTTD Directorate MCP

This project already separates observation, planning, application, commissioning, and verification, and describes persisted operations and replay handling. Merely adopting those architectural names would not establish an improvement. [README](https://github.com/OVER99K/openttd-directorate-mcp/blob/b6eda7f433f28c86602181f059c8ae768e4d8579/README.md).

Concrete findings from inspected code:

- The construction-program validator accepts station rectangles, rail connections, depots, and signals; it rejects other operation kinds. There are no bridge, tunnel, or terrain-modification operations in this program format.
- Its legal-centerline search uses bounded path length (default 160, maximum 384) and search/frontier limits. Those are understandable implementation bounds, but they constrain the route family.
- Its program preflight acknowledges that signals on planned track cannot be tested as if that track already existed. Operation cost results in the inspected dispatcher use rail build-cost constants, which must not be mistaken for complete actual job charges without further accounting review.

These observations are specific to the inspected program, not a claim that every other command in the repository lacks related capabilities. [Construction program](https://github.com/OVER99K/openttd-directorate-mcp/blob/b6eda7f433f28c86602181f059c8ae768e4d8579/game/openttd_directorate/build_program.nut#L639-L974).

Station survey rejects sloped station tiles and water in reserved blueprint space, uses a bounded industry-centered search, and keeps a limited set of candidates per orientation. This suggests station footprint/terrain variety should be explicit regression cases in our project. [Site survey](https://github.com/OVER99K/openttd-directorate-mcp/blob/b6eda7f433f28c86602181f059c8ae768e4d8579/game/openttd_directorate/site_survey.nut).

There is a real-engine integration gate, including two-train operating observations and save/restart checks. Its inspected fixture config uses a 128×128 map, flat terrain setting, and no sea/lakes; this is narrower evidence than varied real terrain. Do not describe the project as lacking engine tests. [Integration gate](https://github.com/OVER99K/openttd-directorate-mcp/blob/b6eda7f433f28c86602181f059c8ae768e4d8579/tests/integration/directorate-real-engine-gate.mjs).

The checked-in CI workflow runs the package checks/audit but does not directly invoke that separate real-engine gate. The release-verification document requires it. This review did not inspect published run artifacts or execute either suite, so it establishes neither a passing nor a failing release. [CI](https://github.com/OVER99K/openttd-directorate-mcp/blob/b6eda7f433f28c86602181f059c8ae768e4d8579/.github/workflows/ci.yml), [verification policy](https://github.com/OVER99K/openttd-directorate-mcp/blob/b6eda7f433f28c86602181f059c8ae768e4d8579/docs/verification.md).

**Design implication:** build and measure broader route capability, exact budget handling, and failure recovery. Do not claim that a new MCP wrapper fixes the user's problem.

## Reference project: openttd-llm

The inspected Python decision loop selects named commands from structured model output, including passenger and freight rail commands. It is not simply unrestricted generated Squirrel code. Its controller is an autonomous company-growth loop; its prompt counts unused loan as spendable money. That policy differs from this project's cash-only default and player-directed tasks. [Decision loop](https://github.com/jplattel/openttd-llm/blob/992ab8a0e12aabf861793ce83878518e52d0bf0e/src/llm.py).

The public Git tree's `OpenTTDLLM` entry is a symlink (mode `120000`) whose blob contains an absolute path under the author's local Documents directory. The actual AI implementation directory is therefore not present as source files at this revision. This is a concrete reproducibility gap for a fresh checkout and prevents a complete review of its construction algorithms from this public tree. [Symlink entry](https://github.com/jplattel/openttd-llm/blob/992ab8a0e12aabf861793ce83878518e52d0bf0e/OpenTTDLLM), [tree](https://api.github.com/repos/jplattel/openttd-llm/git/trees/992ab8a0e12aabf861793ce83878518e52d0bf0e?recursive=1).

Its README describes a bus-route proof of concept, while the inspected Python command set includes more transport actions. Treat the README as an incomplete capability description; we did not execute or verify those additional actions. [README](https://github.com/jplattel/openttd-llm/blob/992ab8a0e12aabf861793ce83878518e52d0bf0e/README.md).

**Design implication:** ship every required adapter component, use an isolated reproducible launcher, separate user requests from autonomous expansion, and enforce budget rules in code.

## Conclusions and open questions

Source evidence supports attempting stock GameScript company control. It does **not** establish that stock integration will satisfy performance, lifecycle, save compatibility, or telemetry needs. The user accepts a custom build and prioritizes reliability, so a narrow engine bridge is a valid outcome of M1.

Our proposed improvement is a complete, tested construction service: legal railway geometry, whole-job money handling, sequential validation, recoverable execution, and observed transport. The model supplies intent and explanations. Comparative reliability remains unmeasured until the same tasks are run against a common observer.

Before implementation grows, prove: human-company operation; observation volume; command cost precision; full-load/departure/delivery telemetry; request reconciliation; save lineage; game pause behavior; and existing-save/GameScript coexistence. [Next tasks](STATUS.md#next-work-in-order).

No third-party source has been copied into the implementation. Record attribution and applicable license files if code is later reused; keep engine patch provenance with its pinned upstream source.
