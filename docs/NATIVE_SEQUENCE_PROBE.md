# Native sequential rail-operation probe

This M2d checkpoint exercises multiple native flat-clear-tile rail commands,
not a complete railway. It runs a dedicated custom OpenTTD 15.3 server against
copies of the earlier control and M2b mutation saves.

## Run

Build the engine using [the engine instructions](../engine/README.md), then:

```sh
python3 -B -m unittest discover -s tests
python3 -B tools/run_native_sequence_probe.py --deadline 120
```

The default binary is `build/openttd-m2a/openttd`. Use `--binary` to select a
different build. A normal run requires a clean engine checkout and a binary
revision matching it. `--allow-dirty-engine` is for diagnostic source-hashed
runs, not the final committed-revision gate.

The default source saves are retained local artifacts from the control and
M2b probes. They are not distributed with the repository. Use `--save` and
`--legacy-save` to supply equivalent disposable source fixtures; the latter
must contain a completed schema-1 native operation to exercise migration.
The normal profile and source saves must remain unchanged.

## Required evidence

The probe records:

- Two sequential native rail builds with engine cost, cash/loan, ownership,
  and successful sequence/head checks.
- Historical status and exact replay after a later build, preserving the
  original outcome without a second charge or command.
- Rejection of an ID reused with a different payload and of a stale new
  request.
- Consecutive zero-cap rejections preserving the successful position.
- The 64-record non-evicting capacity boundary and continued access to old
  records after it fills.
- Saved outcomes and old-ID replay after fresh-process reload, recognition
  of an older source save, and migration of a completed schema-1 record.

Every admitted operation gets a separate fsynced external journal before
send. Raw manifests, logs, journals, and copied saves remain in ignored
`artifacts/native-sequence-probe/`. `--no-capacity-gate` is a diagnostic
shortcut; a run using it does not establish the capacity boundary.

## Limits

Each command still supports only one rail piece on a clear flat tile and has
its own cost cap. There is no station/depot/vehicle command, route planner,
whole-job budget, history eviction, automatic rollback, or retry of uncertain
mutations. Rejections consume records too. A full journal requires a future
explicit safe retention design, not deleting evidence to continue.

COPL schema 2 saves are not expected to load in the earlier custom binaries.
Stock-build compatibility, multiplayer synchronization, pending-save fault
injection, and the mutation/save crash gap remain unproven. Completing this
probe does not complete M2's transport-service acceptance gate.
