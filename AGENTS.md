# Working on OpenTTD Copilot

The user explicitly asked for careful planning and a durable record of plans and actions because this is a long-running project.

## Continuity

- Read `docs/STATUS.md`, then the relevant plan, architecture, decision, and acceptance sections before starting work.
- Keep `docs/STATUS.md` current. Append meaningful actions, evidence, failures, and next steps to `docs/WORK_LOG.md` during each work session.
- Record significant architectural changes in `docs/DECISIONS.md`; distinguish user requirements, provisional defaults, source findings, and runtime results.
- Mark a milestone complete only when its exit criteria have evidence. Keep planned capabilities separate from implemented capabilities.
- When interrupted, leave exact commands or artifact paths needed to resume. Keep credentials out of records.

## Git identity

- The user explicitly prohibits using their work email for this project.
- Use repository-local Git identity `CaptainCucumber <37813159+CaptainCucumber@users.noreply.github.com>` for both author and committer.
- Do not change global Git settings. Check the effective author and committer identity before creating commits, and verify commit metadata before pushing.

## Engineering priorities

- Build for the user's company and preserve the user's budget and transport intent.
- Natural language produces constrained goals. Deterministic code owns track geometry, costs, vehicle selection, execution, and verification.
- Do not make the model invent map IDs, construction coordinates, engine availability, prices, or command success.
- Use normal OpenTTD command validation. Do not bypass ownership, money, authority, terrain, or vehicle rules.
- Construction is not an atomic transaction. Track partial work and uncertain outcomes explicitly; never claim automatic rollback or exactly-once execution without evidence.
- Game state and operation identity must survive reconnects and distinguish a loaded older save from the latest world.
- Use isolated development worlds and copied saves. Do not overwrite the user's normal OpenTTD configuration or original saves as an installation shortcut.
- Match verification to the change. Engine-facing changes require real-engine evidence; mocks alone do not establish buildability or transport success.
- Record the engine version, relevant content/settings, scenario or seed, build revision, and raw evidence for game tests.
- Test end-to-end construction before spending substantial effort on chat UI or additional transport types.

## Scope and communication

- The immediate plan is in `docs/PROJECT_PLAN.md`; do not silently expand the first version into an autonomous company manager.
- Report unsupported conditions, search limits, budget failures, partial construction, and unverified operation honestly.
- Existing source findings do not prove why the user's previous attempts failed. Reproduce failures before claiming causes or comparative reliability.
- Continue routine implementation within the authorized task; documentation is not an extra approval requirement.
- Implement in bounded pieces and stop a session at a useful user testing point. State exactly what is ready to inspect and which milestone gates remain open.
- User authorized committing and pushing implementation and project records together. Preserve the required no-reply identity and verify the remote result.
- Use model effort proportionally. Keep the strongest available model for architecture, ambiguous engine failures, security/recovery decisions, and final integration review. Route routine implementation, test additions, source lookup, documentation, and bounded fixture edits to a cheaper capable model (prefer GPT-5.6 Luna at low/medium effort; use GPT-5.6 Sol when the task needs broader reasoning). Do not spend high-end reasoning on mechanical edits or ordinary test runs. The primary agent remains responsible for integration and real-engine evidence.

### Default model routing

- **High-end model, medium/high effort:** architecture changes, milestone/adapter decisions, contradictory runtime evidence, security or durability boundaries, and final review of engine-facing changes.
- **GPT-5.6 Sol, medium effort:** bounded design reviews, cross-file debugging, test strategy, and changes with several interacting invariants.
- **GPT-5.6 Luna, low/medium effort:** routine coding, fixture implementation, unit tests, source/API lookup, documentation, formatting, and evidence extraction.
- **Do not delegate:** final claims about real-engine success, release acceptance, Git identity, or whether an uncertain mutation is safe to retry.
