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
