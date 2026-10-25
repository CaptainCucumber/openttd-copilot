# M2e town buses and ordinary maps

Status: **bounded M2e exit passed**, 2026-10-24 America/Vancouver.
Published engine: `2fb530eda610857329872eab1acaa9788de49f89`,
branch `copilot/m2e-town-buses`; matching binaries rebuilt.

The user requested passenger buses between towns and an ordinary playable map.
The launcher now generates a randomly seeded 256x256 temperate world with
towns, trees, hills and water/rivers. The selected seed-6 flat coal world is
retained only as `--map-style railway-fixture`; original profiles and saves
remain untouched.

## Final clean-engine result

Clean-engine gate `artifacts/native-railway/20261025T003710Z-042103ac` passed
all ten checks in 219.779 seconds. Naturally generated Dudinghall (town 0) and Hudinghattan
Ridge (town 13) were selected on ordinary seed 20261024; the endpoints were
not created or moved. This is one selected normal-world pair, not evidence
that every random world has a supported route.

The deterministic plan and actual commands cost 8,725 under construction cap
50,000 and reserve 10,000: two new drive-through bus stops, connected depot,
20 road tiles and a standard passenger bus. All 27 actions used normal
command validation. Bus 6, engine 116, had 31 passenger capacity and two
ordinary load/unload orders. Vehicle/company/cargo-attributed acceptance
recorded 31 passengers at station 1 and five at station 0. Loan stayed
100,000; normal service expenses/revenue are not construction charges.

The same run passed read-only planning, whole-job low-budget nonmutation,
independent commissioning, duplicate lookup, fresh-process reload and exact
replay of all 27 retained outcomes, and refusal to inherit completion from
the older initial save. Source saves/normal profile were unchanged and
temporary credentials removed.

Development Copilot host advice run `20261025T002629Z-15b74b59` used only five
native calls: open, inspect, plan bus, inspect, saved close. Both inspections
returned cash/loan 100,000, 19 towns, no bus assets and sequence 0/head null.
The plan quoted 8,725/20 roads/27 actions without building. No SQL, shell or
coding fallback was attempted with the compact catalog and explicit host
restrictions. Its raw local transcript is
`.runtime/native-bus-chat-compact.jsonl`, not a published personal/model log.

Final actual-host build `20261025T003929Z-33e9b3d4` passed in 219.919 seconds
on the clean engine: plan, one authorized build, bounded status polling to
`operating`, independent inspection and saved close. Bus 6 had capacity 31,
ordinary orders to stations 0/1, was running and not crashed; actual accepted
passengers were 31 and five. Only native game tools were called. Its first
read-only plan used an unknown job ID, was rejected without construction,
and was corrected before the single build. This observed error is retained,
not a claim that the model never supplies invalid arguments.

## Command guards and regressions

Final review found two command-boundary defects: over-cap commands needed
explicit rejection, and malformed kind-specific fields needed refusal before
retaining records that the save loader cannot read. Malformed-field
nonadmission now passes; the below-cap runtime guard exposed a test/execute
consistency assertion. Reject above-cap quotes identically in both phases.
Corrected guard-only run `20261025T003554Z-109b6ad8` passed zero-charge rejection,
unchanged assets/finances/head, healthy process and rejected-record reload/replay.
The final full clean-engine gate repeated both guards and passed:
malformed stop fields consumed no retained record, and quote 150/cap 149
produced a zero-charge rejection that survived fresh-process reload/replay.
No assets, finances or successful operation position changed.

Fresh coal regression `20261025T003710Z-a294e820` passed in 228.179 seconds:
44 actions, cost 14,979, three full departures, two accepted deliveries,
duplicate lookup and exact retained reload/replay. Legacy check
`20261025T004058Z-afa8b7ec` passed all 44 old outcomes after replay, resave and
another fresh-process load, plus selected-industry nonmutation and older-save
refusal. Source saves and normal profiles stayed unchanged; temporary
credentials were removed in all final runs. All 263 Python tests pass.

Exact binary/source/content/config/manifest/save/transcript hashes and bounds
are recorded in [concise evidence](evidence/2026-10-24-native-town-buses.json)
and the ignored run manifests. Patch 0018 reproduces the published engine
commit; historical failed runs/root causes remain in [the work log](WORK_LOG.md).

## Testing point and next milestones

Run `python3 -B tools/game_chat.py` for a random normal world. Ask for nearby
town bus plans with a cap/reserve, then explicitly authorize one. Use
`--seed 20261024` to reproduce this tested world and discuss Dudinghall and
Hudinghattan Ridge; those names/IDs are observations, not universal constants.
The AI opens the matching visible client and leaves it open for play.

M2e is a bounded service/testing point, not a general reliability or packaged
release claim. Next are M3 supported-map fixtures and interruption/recovery,
M4 richer grounded observations/advice and conversational resumption, then
M5 reproducible setup/restart/packaging. See [sequencing](PROJECT_PLAN.md#next-milestone-sequencing).

## Scope and retained limits

One standard passenger bus per explicit service, two distinct observed towns,
actual selected-town production/acceptance at both stops, existing ordinary
two-way roads and bounded new flat clear/tree road/depot footprints. No house
or asset demolition, borrowing, bridges, tunnels, trams, freight/refits,
terraforming or autonomous expansion. Ordinary loading is not full load.

The planner reads at most a 192x192 corridor, searches at most 100,000 states
and accepts paths of at most 160 tiles. Its cheapest available supported bus
is not a proven financial optimum. All rail/bus actions share 64 retained
records without eviction. Partial/uncertain execution blocks changed requests
and is never automatically undone or retried. Save/command atomicity,
fault-injected recovery, the random-map cohort and packaged release remain
open. The bridge still lacks profit, production-rate and station-queue data.
