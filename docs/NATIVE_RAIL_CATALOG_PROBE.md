# Run the M2d rail catalog probe

Build the clean fork at `5f8b9d56af8f03e7794ef941e0172cbdff85c0de`
using [engine/README.md](../engine/README.md), then run:

```sh
python3 -B -m unittest discover -s tests
python3 -B tools/run_native_rail_catalog_probe.py
```

The default input is the ignored copied control save at
`artifacts/control-probe/20261021T180450Z-f8fc9132/control-probe-final.sav`.
The probe requires a clean engine checkout and binary revision naming its
commit. It reads paged train definitions for company 0, checks current
buildability and response bounds, rejects wrong-world and invalid-company
queries, and compares the catalog after a fresh-process reload. It makes no
gameplay mutation. Raw manifests and logs are under
`artifacts/native-rail-catalog-probe/<run>/`; the final baseline is in
[the evidence JSON](evidence/2026-10-23-native-rail-catalog-probe.json).
