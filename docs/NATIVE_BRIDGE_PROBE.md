# M2a native bridge probe

Status: passed in the custom OpenTTD 15.3 engine on 2026-10-23. See the
[concise evidence](evidence/2026-10-23-native-bridge-probe.json) and
[M2a report](M2A_REPORT.md).

## What it proves

The probe performs two independent read-only gates:

1. It loads a byte-identical isolated copy of the representative user autosave,
   rejects an unsupported bridge version, then reads the world and the sole
   human company through the native packet family.
2. It creates and saves a disposable world with `Foreign Environment Fixture`,
   reloads a copy, reads native world state twice, and confirms the saved
   foreign GameScript remains loaded, mutation-free, and advancing.

Together these establish that the bridge attaches to an ordinary existing save
and operates independently of the one GameScript slot. The source autosave and
normal OpenTTD profile remain unchanged.

The fixture-creation phase issues one save command. No bridge gameplay mutation
exists or is sent in M2a.

## Run

Build the engine as described in [`engine/README.md`](../engine/README.md), then:

```sh
python3 -B tools/run_native_bridge_probe.py \
  --save "/path/to/copied-source/autosave.sav"
```

The argument names the source to copy; the original path is never passed to
OpenTTD. If a save contains more than one human company, add `--company-id N`.
The probe refuses to select a company by display name.

Full logs, disposable saves, configs, and manifests are written under
`artifacts/native-bridge-probe/`. Those runtime artifacts are ignored by Git.

## Expected checks

```text
PASS read_only_identity_on_copied_save
PASS native_bridge_coexists_with_saved_foreign_gamescript
environment probe success: .../artifacts/native-bridge-probe/<run>
```

The first failed M2a attempt is intentionally retained. It stopped before
loading a save because the standalone binary had no adjacent application
resources. The corrected harness explicitly stages resources from the installed
15.3 app while executing the custom binary.

## Not proved

M2a does not provide construction, authoritative mutation costs, persistent
world or operation identity, vehicle-tagged cargo events, stock-build save
round trips, or exactly-once recovery. Those remain M2b, M2c, and M3 work.
