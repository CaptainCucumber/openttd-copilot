# Work log

Append meaningful actions and outcomes by session. Include failed experiments when they affect the next step. Do not describe planned behavior as delivered functionality.

## 2026-10-20 — Project inception and research

### Request

Niko introduced OpenTTD Copilot: chat-driven construction in OpenTTD, beginning with a coal railway between named industries, full-load operation, and use of the player's available budget. External chat is acceptable. Reliability and persistent planning/action records are priorities. Two existing implementations were supplied for review.

### Actions and evidence

1. Inspected the workspace: empty, no existing project files or Git repository. Checked parent instruction locations; no applicable parent `AGENTS.md` was found.
2. Performed a quick project-memory keyword lookup. No relevant prior OpenTTD project context was found; no memory-derived design decisions used.
3. Read both supplied repository pages and then used the GitHub connector to inspect pinned code, repository trees, and metadata. Reviewed OpenTTD 15.3 API and command-processing source. The exact revisions and findings are recorded in `RESEARCH.md`.
4. Confirmed from source that GameScript supports scoped company commands, normal money charging, rail/vehicle/order APIs, command test mode, and cost accounting. Identified the small GameScript Admin message limit and the need for request paging/lifecycle handling.
5. Identified scoped limitations in Directorate's construction program and test fixture; noted its existing real-engine test rather than assuming it only has mocks. Found the nonportable AI-directory symlink in the public openttd-llm tree. These are source findings, not reproduced runtime failures.
6. Inventoried the local installation read-only: OpenTTD app metadata 15.3; OpenGFX2 Classic archive present; toolchain versions recorded in `STATUS.md`. Located but did not load original saves.
7. Asked two optional product questions. Niko confirmed that a custom build is acceptable to prioritize reliable control, and that full load means leaving the mine fully loaded. Updated requirements, status, and decisions accordingly.
8. Wrote the README, contributor continuity instructions, plan, architecture proposal, acceptance plan, research record, decision log, current status, work log, and runtime-artifact ignore rules.

### Research corrections / limits

- Initial guessed OpenTTD paths `src/game/game.cpp` and `src/script/script_object.cpp` returned 404. Directory/API inspection located `src/game/game_core.cpp` and `src/script/api/script_object.cpp`; subsequent source inspection used those paths.
- The GitHub file reader rejected the AI symlink as a normal file; reading its Git blob confirmed an absolute author-local path. The underlying AI code was not available in that public tree.
- Public API documentation can track master, so architectural findings were checked against the 15.3 source baseline.
- No runtime installation, game launch, construction, engine build, or reference-project benchmark was attempted. No paid model calls were configured.

### Verification

- Ran a Python documentation check across all nine Markdown files: local link targets, local heading anchors, fenced-block balance, and trailing whitespace all passed.
- Checked the requirement/status/decision text for stale unanswered-question language; both user confirmations are reflected in the current baseline.
- No application tests were run: this session produced a planning baseline, not executable Copilot code. Research claims remain distinguished from runtime evidence.

### Handoff

M0's initial planning baseline is complete. Begin M1 with S1–S4 in `STATUS.md`: isolated harness, human-company control, observation/transport/lifecycle measurements, and adapter selection. The user has already accepted a custom build; further permission is not needed merely to choose that architecture within the authorized project. Runtime/environment permission requirements still apply to individual tools.

## 2026-10-20 — GitHub repository and commit identity

- User requested a new GitHub repository and publication of all project files.
- Created private repository `CaptainCucumber/openttd-copilot` through the authenticated GitHub CLI. The connected account and repository owner match.
- Before any local commit or push, the user prohibited use of their work email. Verified that the local workspace still had no Git repository and the remote repository was empty.
- Selected the account's GitHub no-reply identity, `CaptainCucumber <37813159+CaptainCucumber@users.noreply.github.com>`, for local author and committer settings. Global Git settings remain unchanged.
- Added the identity requirement to `AGENTS.md` and the repository link to the project records. Preparing the planning baseline for its initial commit and push; verify author/committer metadata before publication.

## 2026-10-21 — Planning baseline published

- Initialized local Git on `main`, configured the repository-local no-reply author/committer identity, and added the private GitHub repository as `origin`.
- Created and pushed initial commit `26c96823b46bdeb7b384e1fa9b3d0e4996196bc1`, containing all ten project files. `main` now tracks `origin/main`.
- Verified the initial commit through GitHub's API: its author and committer both use `37813159+CaptainCucumber@users.noreply.github.com`; the expected ten files are present. Confirmed repository visibility is private.
- Checked project file contents for work email addresses before committing; none were present. No work email was used in commit metadata. Global Git identity was not changed.
- Updated the current status and this log to record publication. The next engineering task remains M1's isolated game-control prototype.

## 2026-10-21 — AI connection and MCP architecture discussion

- User asked how the game connects to AI, whether an in-game experience requires an API key, and whether MCP with a player's own AI app/plan is the better and more reliable approach.
- Read current status, plan, architecture, decisions, and acceptance gates. A quick memory lookup found no relevant prior OpenTTD record. The repository already separates the model from deterministic construction and allows external chat; MCP was previously optional later interface work.
- Used the OpenAI Docs skill and read official Codex MCP/authentication documentation plus the MCP architecture documentation. Sources and scoped findings are recorded in D010. Markdown versions of the OpenAI pages failed web retrieval with unsupported-content-type errors; the HTML pages supplied the relevant evidence.
- Recommended local MCP as the first conversational interface, backed by the same deterministic service that could later serve an in-game UI. Distinguished AI-provider credentials from local control authorization, client subscription limits from MCP connectivity, and protocol support from construction reliability.
- Recorded D010 as a recommendation only; did not treat the user's question as approval to replace M4. Updated status with that distinction. No implementation, game launch, credential configuration, or runtime reliability test occurred.
- Validation: `git diff --check` and a local Markdown link/heading-anchor check over the three changed records. Next engineering work remains S1–S4 in `docs/STATUS.md`; any eventual MCP interface must preserve the existing budget, world identity, partial-work, and recovery contracts.

## 2026-10-21 — Implementation session: isolated company-control probe

- User authorized incremental implementation, stopping at useful manual testing points, commits and pushes including project records, and model routing: strongest available reasoning for architecture, cheaper models for coding. Root retains architecture/integration review; two GPT-5.6 Luna coding agents own the harness and GameScript respectively.
- Read current status, plan, architecture, decisions, acceptance gates, and existing uncommitted MCP discussion records. Preserve those records in the implementation commit. Memory confirmed the original emphasis on a working player-company route; current checkout is authoritative.
- Scope: S1/S2 disposable profile and normal human-company rail/station construction probe. S3 transport/lifecycle/performance and S4 adapter selection remain open. This is not a railway service or conversational interface.
- Verified installed executable reports OpenTTD 15.3 and supports `-X`, `-x`, `-c`, dedicated and null video modes. Downloaded pinned upstream revision `14ec60f248547d4d062a1160f0fc26d742319888` into ignored `vendor/openttd-15.3/` for exact API/config review. Initial sandbox download failed DNS; approved network retry succeeded.
- Design under implementation: isolated dedicated server plus normal headless game client; discover the client-associated human company; observe industries and available rail vehicles; bounded dry-run and execution with command accounting; reject duplicate track with no charge/mutation; save a disposable inspection world and refuse to build again on reload.
- Checked effective Git author and committer: both use the repository-local CaptainCucumber no-reply identity. No global configuration changes.
- First runtime attempts: sandbox denied the loopback bind (`Operation not permitted`); the user approved running the scoped harness outside it. The first unrestricted run (`artifacts/control-probe/20261021T160025Z-e703ae97/`) then timed out before its listener opened. Source inspection shows `-X` excludes the app-bundle resource search path, while language loading occurs before video initialization. Staging only OpenGFX is insufficient on this macOS installation; the harness is being corrected to copy language and built-in base resources as well. Retain this failed run rather than reporting a pass from unit tests.
- A second engine attempt (`20261021T160248Z-82a3d76c`) started the server but failed to start the GameScript. The log showed the unquoted multi-word script name parsed as `Copilot`; missing `ini_version` also caused the legacy config reader to ignore the split private settings. Corrected the quoted script key, pinned `ini_version = 7`, and selected `english.lng`. Both failures are preserved in ignored artifacts.
- First construction pass: `20261021T160334Z-0a973c32`, 4.620 seconds including setup, startup, queries, construction, saving and shutdown. The script built rail and station in human company 0 for 90 + 750 = 840; exact command accounting matched test estimates and cash deltas. The duplicate command returned `ERR_ALREADY_BUILT` with zero cost and unchanged observed assets/cash/loan.
- Review cleanup filtered unavailable/future rail IDs before engine-property queries, retained partial-state fields in GameScript saves, preserved attribution on repeated inspection saves, and rejected non-integral protocol versions/random-seed sentinel/non-finite deadlines. These are fixture correctness changes, not production recovery guarantees.
- Final-source construction pass: `artifacts/control-probe/20261021T180450Z-f8fc9132/`, 4.153 seconds, same seed and footprint/cost. Observed 13 industries and 14 available rail engines/wagons. Cash 100,000 → 99,160; loan 100,000 unchanged. Rail tile 8256 (64,64); station 0 tiles 8257–8258 (65,64)–(66,64). Initial save captured before the human client joins; final save includes the completed probe. The initial save is not an initial human-company fixture.
- Added `tools/check_probe_reload.py`. A fresh null-video engine process loaded an isolated copy; readback matched exact tile ownership/geometry, recorded cost, cash and loan. No construction events were emitted, and the original final save hash stayed unchanged. Script ticks reset on load, so they are not compared as world-time identity. This establishes the one-shot reload guard only; S3 lifecycle/reconciliation remains open.
- Compared the normal profile configuration and three original saves with pre-run fingerprints: all content hashes and modification times identical. A read-only native-app selection returned an OpenTTD window, but no UI inspection assertions were made; graphical inspection remains the user's next test.
- User clarified that their reset concerned the AI usage limit only; no game or development state was reset. Continued the existing session and scope.
- Published concise engine/content/source hashes and selected raw events in `docs/evidence/2026-10-21-control-probe.json`; full logs, manifests and saves remain under the ignored run directory. Updated status, architecture/acceptance capability labels, D011, instructions, and future-session model/commit cadence in `AGENTS.md`.
- Resume/test commands: `python3 tools/run_control_probe.py`; `python3 tools/check_probe_reload.py --run latest`; `python3 tools/run_control_probe.py --inspect latest --open`. The last command opens a copied inspection profile. Next implementation is S3a/S3b, followed by the M1 adapter decision; no full railway, train operation, MCP interface, or reliability-suite claim is made.
- Final pre-publication validation: 15 local tests pass (including corrupt/replayed reload evidence rejection), Python compilation passes, `git diff --check` passes, Markdown local links/code fences pass, and the evidence report's executing-source hashes match the files being committed. Rechecked effective author/committer identities and checked tracked deliverables for work-email/private-key/token patterns; no prohibited values found.

## 2026-10-21 — S1/S2 checkpoint published; ready for user inspection

- Committed and pushed `57be13a979c7d8c927a0f5dc96fe9a77a6b73876` (`Add isolated OpenTTD human-company control probe`) to `origin/main`. It includes code, tests, test instructions, source-hashed evidence, and project records, preserving the preceding MCP discussion changes.
- Verified committed author and committer both use `CaptainCucumber <37813159+CaptainCucumber@users.noreply.github.com>` before pushing. Verified GitHub `main` resolves to this commit and contains all 15 changed files. Runtime saves, copied resources, upstream source checkout, and credentials are not committed.
- Git index writes and GitHub networking were blocked by the sandbox; approved scoped retries performed staging, commit, and push. No global Git configuration was changed.
- Stopping at the user inspection point described in `docs/CONTROL_PROBE.md`. The saved test can be reopened using `python3 tools/run_control_probe.py --inspect 20261021T180450Z-f8fc9132 --open`. Follow-up development starts at S3 in `docs/STATUS.md`; M1 remains in progress.

## 2026-10-21 — S3a transport and lifecycle session started

- User accepted the first checkpoint and requested the next step. Read status, plan, architecture, acceptance criteria, and decisions; the current checkout supersedes the older planning-only memory record.
- Scope: bounded S3a Admin/GameScript request, paging, reconnect, save/reload, older-save/changed-world, and pause tests. Vehicle purchase/delivery attribution, throughput cohorts, existing-save coexistence, and final adapter selection remain subsequent M1 work.
- Root owns protocol/lifecycle design, harness, integration review, and real-engine evidence. Two GPT-5.6 Luna agents own bounded Admin transport and GameScript implementation tasks, following the repository's model-routing instruction.
- Design under test: persist world identity and bounded operation journal with the game; persist external pending intent before sending; use runtime-only mutation sessions reset on load; compare external high-water sequence/head before binding to a loaded game. An unknown/pending outcome is uncertain, never an automatic retry. This does not claim exactly-once effects or close the command/save/journal crash gap.
- Pinned source review confirms Admin JSON transport and GameScript's 1450-byte outbound ceiling; source also calls the GameScript loop during game pause. Runtime tests will determine actual behavior. A GitHub web fetch of the pinned header failed with a cache miss; the existing pinned local source is available for review.
- Admin authentication is limited to a disposable loopback-only listener with a fresh local secret, excluded from logs/evidence and removed on shutdown. Legacy password login is a spike implementation choice, not a production network-security design.

## 2026-10-22 — S3a resumed, corrected, and verified

- User requested continuation and confirmed OpenTTD Copilot after the chat opened in the separate Directorate checkout. Continued the existing uncommitted S3a work; no Directorate changes. Used its latest source/log evidence over the older planning-only memory record.
- Recovered prior failures: sandbox loopback denial; initial Admin timeout; an earlier paused-request failure; and the latest reload failure (`20261021T203820Z-e631ef92`) where the client joined but never associated with company 0. Retained those failed artifacts.
- Verified the pinned 15.3 source: `src/network/network_server.cpp` checks `allow_list.Contains(peer_public_key)` and falls back to spectator; `src/table/settings/network_secrets_settings.ini` defines `client_secret_key`. The staged fixture now reuses a generated temporary key across reloads. It never reads the user's key. A web fetch of the corresponding source failed with a cache miss; the existing pinned local checkout supplied the evidence.
- Staged changes in `/private/tmp/copilot-s3a-osp89zw3/` because the actual repository was outside this chat's writable root. A staged sandbox engine run failed to bind; scoped approval allowed the disposable loopback test. Its initial successful run (`20261022T165819Z-f97e8cce`) passed 12 checks in 6.266 seconds. Approved integration copied only checked files into the actual Copilot repository.
- Root owned integration and runtime verification; a GPT-5.6 Luna agent reviewed transport/journal correctness and implemented bounded send/overflow fixes under the repository's delegation instruction. Fixed partial-send socket reuse, silent response eviction, inconsistent outcome sequence acceptance, and failed durable-write reuse. Added fault-injection regressions and temporary-client-identity cleanup checks.
- Extended latest-save testing to replay the original operation after rebinding a fresh session; it returns the saved outcome and changes no company balance, loan, or journal position.
- Final integrated real-engine run `artifacts/lifecycle-probe/20261022T173734Z-4c01df51/`: all 12 assertions pass in 6.749 seconds. Two rail pieces cost 90 each, total 180; cash ends at 99,820; loan stays at 100,000. Maximum observed framed Admin packet is 448 bytes. Current save, older save, and changed world are distinguished. All temporary secret files were removed. Normal configuration and three original saves retain identical content hashes and mtimes.
- All 36 unit tests pass in the actual repository, including send failure, overflow, inconsistent outcome, failed intent write, and uncertain directory-sync cases. Source-hashed evidence and lifecycle instructions are retained with status, architecture, acceptance, plan, and D012 updates.
- Scope remains rail-only: no train purchase, delivery/revenue observation, throughput cohort, another-GameScript coexistence, or command/save crash-gap proof. M1 remains in progress. Resume S3b vehicle/order/readback and attributable delivery telemetry, then throughput and adapter selection.
- Handoff command: `python3 -B tools/run_lifecycle_probe.py`; expect 12 PASS lines and a success manifest. The prior graphical control probe can still be inspected independently. Commit/push use only the repository-local GitHub no-reply author and committer; no global Git changes.

## 2026-10-22 — Model routing adjusted

- User asked to avoid using the most expensive model for routine programming. Updated `AGENTS.md` with explicit proportional routing: high-end reasoning for architecture, ambiguous engine failures, security/recovery decisions, and final review; GPT-5.6 Sol for cross-file debugging and bounded design review; GPT-5.6 Luna at low/medium effort for routine implementation, tests, source lookup, documentation, and evidence extraction.
- Final integration, real-engine claims, release acceptance, Git identity, and uncertain-mutation retry decisions remain with the primary agent regardless of model cost.

## 2026-10-22 — S3b vehicle and purchase lifecycle checkpoint

- Added `tools/run_vehicle_probe.py`, `game/copilot_vehicle/`, and `tests/test_vehicle_evidence.py`. The fixture uses the existing Admin transport and external journal, then checks purchase guards, pause refusal, lost purchase response reconciliation, duplicate/conflict rejection, copied-save replay, consist/order readback, and train start.
- Staged real-engine run reached all of those checks successfully. The observed purchase cost was 8,203, wagon/configuration cost 1,031, the loan stayed at 100,000, and replay after reload returned the stored vehicle outcome without buying another vehicle. The run is retained under the temporary S3b staging artifacts; no public evidence JSON is claimed yet.
- The same run did not prove delivery. The fixture source reported production level 16, last-month production 0, and station waiting cargo 0, so the train remained at the source station with no full-load departure. A deity-only production-setting attempt was rejected by the stock GameScript context and is not treated as a capability.
- Stock delivery monitoring still has no vehicle ID. The fixture requires one isolated primary train and records that scope explicitly; this cannot establish per-train attribution in an arbitrary existing company. The next S3b task is to make the source production deterministic or use a known producing industry, then rerun the two-departure/two-delivery gate.

## 2026-10-22 — S3b delivery gate passes in isolated fixture

- After allowing a full simulation window, the committed S3b probe passed all lifecycle checks plus two full-load departures and two destination-industry delivery deltas. Run: `artifacts/vehicle-probe/20261022T181426Z-4ac68dab/`; concise evidence: [vehicle probe evidence](evidence/2026-10-22-vehicle-probe.json).
- Added `tools/copilot_chat.py` as the first local chat seam. It accepts only the supported coal railway/full-load request, emits a structured intent, rejects unsupported requests before game mutation, and delegates `build` to the disposable S3b fixture. Added parser coverage in `tests/test_copilot_chat.py`; the full suite now passes 46 tests. This is an interim test seam, not the M2 route planner or normal-save adapter.
- Extended the chat seam to open the successful `service-final.sav` in a visible Cocoa OpenTTD window after the disposable job completes. The handoff was tested against the real 15.3 evidence artifact; `--no-show` remains available for headless runs.
- Corrected the chat experience so `build` passes `--visible` to the live disposable client. The Cocoa OpenTTD window now appears during the vehicle probe and remains the real-time view while the train completes its delivery cycles; the completed save handoff remains afterward.
- OpenTTD 15.3, seed `20261021`, elapsed 160.829 seconds. The one train carried 30 coal capacity, departed full twice, and delivered 5 units on each observed destination-industry delta. The company loan remained 100,000; the normal profile was unchanged and temporary secrets were removed.
- This is deliberately scoped evidence. Stock CargoMonitor has no vehicle ID, so attribution is by exclusion in a fresh world with one company train and `fleet_count = 1`. It does not establish per-vehicle delivery attribution on arbitrary existing saves.
- The first run stopped early because the source needed a production cycle; the successful rerun was allowed to continue until the two-cycle gate completed. No false completion was recorded for the earlier no-cargo observation.
