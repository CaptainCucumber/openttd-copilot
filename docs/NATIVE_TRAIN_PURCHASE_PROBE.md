# Native rail vehicle purchase probe

This developer gate buys rail vehicles in a copied test world. It does not
assemble, order, start, or operate a railway. Build the
[pinned custom engine](../engine/README.md), then run from the checkout:

```sh
python3 -B tools/run_native_train_purchase_probe.py --deadline 120
python3 -B -m unittest discover -s tests
```

The default source is the retained schema-3 infrastructure save at
`artifacts/native-infrastructure-probe/20261023T215235Z-f535454c/infrastructure-final.sav`.
Its adjacent manifest supplies the original four retained outcomes for
migration comparison. Missing source/evidence is an error, not a skipped gate.
See `--help` for explicit source/binary/cap/deadline options.

The probe uses disposable profiles and copied saves, live company-filtered
depot/catalog/train-part observations, and separate fsynced intent files.
This known standard temperate fixture uses coal cargo 1; the probe selects a
live compatible single-head locomotive and default coal wagon, not arbitrary
cargo labels or refits.
Artifacts go to `artifacts/native-train-purchase-probe/<run>/`, including
source/binary/content/settings fingerprints, raw replies, logs, and final save.
The normal profile and source save must remain unchanged.

## Protocol and execution

- Additive protocol-v3 request 13:
  `<HBIBIHqQQQQQQQ>` followed by the NUL-terminated world ID. Fields are
  version, request kind, request ID, company, depot tile, engine ID, max cost,
  expected sequence/head hi/head lo, operation hi/lo, payload hash hi/lo.
- Request 14 status: `<HBIQQ>` (version/kind/request ID/operation hi/lo)
  followed by the world ID.
- Replies use the unchanged base operation body followed by `<BBIH>`:
  operation kind, length, original created asset ID, original engine ID.
  Purchase kind 3 has length 0, base track 0, base rail type 255.
  Completed purchase requires an actual created vehicle ID. Other states
  use `0xffffffff`; non-purchase engine ID is `0xffff`.
- Extended status 14 reads rail/station/depot history too. Old status 2/12
  refuses purchase records with result 2. Replay through another build
  type conflicts rather than constructing another asset.
- The normal engine purchase command owns availability, ownership, rail
  compatibility, money, and cost validation. The wrapper rechecks the cap
  before execution, uses default cargo without refit, and disables engine
  adoption of free wagons. A same-engine free wagon in the depot causes a
  wagon purchase rejection, because stock purchase would otherwise join it.
- The callback retains the actual command-returned VehicleID, not a pool
  scan guess. Independent train-part pages verify engine, owner, depot,
  chain, cargo, and stopped/in-depot state. Numeric IDs in historical
  outcomes are not proof of perpetual live identity.

COPL schema 4 stores engine identity and migrates schemas 1–3. The shared
journal retains at most 64 admitted records without eviction; rejections use
capacity but preserve the successful sequence/head. Pending/uncertain work
blocks continuation. Do not automatically retry an uncertain purchase.
Per-command caps do not establish whole-job affordability or save/journal
atomicity. The next native gate is consist assembly and order/start control.
