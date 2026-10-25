# M2e town buses and ordinary maps

Status: final clean-build acceptance in progress, 2026-10-24 America/Vancouver.
Published engine: `2fb530eda610857329872eab1acaa9788de49f89`,
branch `copilot/m2e-town-buses`; matching binaries rebuilt.

The user requested passenger buses between towns and an ordinary playable map.
The launcher now generates a randomly seeded 256x256 temperate world with
towns, trees, hills and water/rivers. The selected seed-6 flat coal world is
retained only as `--map-style railway-fixture`; original profiles and saves
remain untouched.

## Measured development result

Dirty-engine gate `artifacts/native-railway/20261025T002814Z-4145a74f` passed
in 216.867 seconds. Naturally generated Dudinghall (town 0) and Hudinghattan
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

Actual Copilot host advice run `20261025T002629Z-15b74b59` used only five
native calls: open, inspect, plan bus, inspect, saved close. Both inspections
returned cash/loan 100,000, 19 towns, no bus assets and sequence 0/head null.
The plan quoted 8,725/20 roads/27 actions without building. No SQL, shell or
coding fallback was attempted with the compact catalog and explicit host
restrictions. Its raw local transcript is
`.runtime/native-bus-chat-compact.jsonl`, not a published personal/model log.

## Open acceptance gates

Final review found two command-boundary defects: over-cap commands needed
explicit rejection, and malformed kind-specific fields needed refusal before
retaining records that the save loader cannot read. Malformed-field
nonadmission now passes; the below-cap runtime guard exposed a test/execute
consistency assertion. Reject above-cap quotes identically in both phases.
Corrected guard-only run `20261025T003554Z-109b6ad8` passed zero-charge rejection,
unchanged assets/finances/head, healthy process and rejected-record reload/replay.
Do not treat the earlier service run as acceptance of those later changes.

Before marking M2e complete: rerun the complete bus gate on the matching clean engine/client,
the accepted coal service and legacy resave/reload regression; exercise the
final conversational integration; publish exact pins, patches and hashes.

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
