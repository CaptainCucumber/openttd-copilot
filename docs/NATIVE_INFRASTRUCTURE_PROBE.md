# Native station/depot probe

This is a developer construction gate, not an existing-business railway job.
It uses the dedicated custom engine, copied test saves, and disposable profiles.
The normal configuration and original saves are fingerprinted, not overwritten.

## Run

Build [the pinned engine](../engine/README.md), then run from the repository:

```sh
python3 -B tools/run_native_infrastructure_probe.py --deadline 120
python3 -B tools/run_native_sequence_probe.py --deadline 120
python3 -B -m unittest discover -s tests
```

The infrastructure gate requires the retained control fixture save and the
published schema-2 sequential-operation save. Missing fixtures are an error,
not a skipped migration test. Each run writes its source/binary hashes,
engine settings/content, raw responses, saves, logs, and manifest under
`artifacts/native-infrastructure-probe/<run>/`. See `--help` for source paths
and station/depot orientation options. Only development experiments should use
`--allow-dirty-engine`; acceptance evidence requires a clean pinned revision.

## Boundary

- Build request 11 carries company, tile, rail type, orientation, infrastructure
  kind (1 station, 2 depot), length, cap, expected sequence/head, operation ID,
  payload hash, and world ID. The model must not supply invented world values.
- Stations are new default single-platform stations, length 1–7, axis 0/1.
  Depots occupy one tile, direction 0–3, length 1. All tiles must be clear,
  flat, valid, and at one elevation; normal OpenTTD validation also applies.
  No joining, replacement, terraforming, or loan increase is added.
- Request 12 reads infrastructure or retained rail outcomes. Its extension is
  `kind:u8, length:u8, created_asset_id:u32`, after the existing operation body.
  `0xffffffff` means no created asset. Rail outcomes have kind/length 0/0.
  Only completed station/depot outcomes have a created ID.
- Old rail status request 2 refuses infrastructure records (result 2).
  Reusing an infrastructure ID through old rail build request 1 conflicts
  (result 8), rather than constructing rail or returning a misleading success.
- Historical cost/error/completion frame/created ID are immutable outcome
  fields. Sequence/head, company cash, and tile readback are current.
  Station/depot tiles intentionally do not set the plain-rail `has_rail` bit;
  independent asset pages must establish current ownership and geometry.
- Intent is fsynced before send; terminal status is reconciled before the next
  operation. Admitted rejections consume history but do not advance the
  successful sequence/head. The shared journal has 64 non-evicting records.

COPL schema 3 migrates schema-1/2 rail history and persists infrastructure
identity. Exact replay returns retained outcomes rather than constructing
again. Pending/uncertain outcomes block new admissions. This does not close
the mutation/save/journal crash windows, reserve a whole-job budget, build a
train, prove station catchment, or demonstrate a connected operating route.
