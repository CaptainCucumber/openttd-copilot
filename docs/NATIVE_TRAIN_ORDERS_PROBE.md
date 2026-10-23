# Run the M2d train-orders probe

Build the clean fork at `5f8e025d70c9eb6faeca1bc797b1377039ed0ca8`
using [engine/README.md](../engine/README.md), then run:

```sh
python3 -B -m unittest discover -s tests
python3 -B tools/run_native_train_orders_probe.py
```

The probe loads an isolated copy of the service save from
`artifacts/native-vehicle-probe/20261023T172550Z-485cd1fd/service-final.sav`.
It checks the primary train's full-load source order and unload destination
order, typed rejection of wrong-world/missing-company/missing-train requests,
and identical order data after copied-save reload. The harness verifies the
engine revision and modified source hashes, and checks source-save, normal
profile, and temporary-secret invariants.

Raw artifacts are under
`artifacts/native-train-orders-probe/<run>/`; see the concise
[evidence JSON](evidence/2026-10-23-native-train-orders-probe.json).
This is read-only configuration evidence, not proof of reachability or
transport.
