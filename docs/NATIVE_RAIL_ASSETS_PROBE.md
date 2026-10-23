# Run the M2d rail assets probe

Build the clean fork at `5f8b9d56af8f03e7794ef941e0172cbdff85c0de`
using [engine/README.md](../engine/README.md), then run:

```sh
python3 -B -m unittest discover -s tests
python3 -B tools/run_native_rail_assets_probe.py
```

The probe stages copies of two ignored fixture saves. The control save is
`artifacts/control-probe/20261021T180450Z-f8fc9132/control-probe-final.sav`;
the service save is
`artifacts/vehicle-probe/20261022T181426Z-4ac68dab/service-final.sav`.
The clean engine checkout and binary revision must match. It checks known
station geometry, empty control-world depot set, wrong-world and
missing-company rejection, fresh-process reload, and a real depot plus coal
acceptance in the service save. It does not mutate gameplay assets.

Raw manifests and logs are under `artifacts/native-rail-assets-probe/<run>/`.
The final baseline is in
[the evidence JSON](evidence/2026-10-23-native-rail-assets-probe.json).
