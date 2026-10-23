# Run the M2d train-parts probe

Build the clean fork at `5f8b9d56af8f03e7794ef941e0172cbdff85c0de`
using [engine/README.md](../engine/README.md), then run:

```sh
python3 -B -m unittest discover -s tests
python3 -B tools/run_native_train_parts_probe.py
```

The probe stages copies of the control save
`artifacts/control-probe/20261021T180450Z-f8fc9132/control-probe-final.sav`
and native vehicle service save
`artifacts/native-vehicle-probe/20261023T172550Z-485cd1fd/service-final.sav`.
It requires a clean engine checkout and a binary revision naming that commit.
It checks the empty control result, the service train's primary/wagon links,
typed wrong-world/missing-company rejection, source save hashes, and read-only
world/operation identity. Raw artifacts are under
`artifacts/native-train-parts-probe/<run>/`; see the final
[evidence JSON](evidence/2026-10-23-native-train-parts-probe.json).
