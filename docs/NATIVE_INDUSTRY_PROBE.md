# Run the M2d industry and tile-window probe

Build the clean fork at `5f8b9d56af8f03e7794ef941e0172cbdff85c0de`
with the instructions in [engine/README.md](../engine/README.md), then run
from the repository root:

```sh
python3 -B -m unittest discover -s tests
python3 -B tools/run_native_industry_probe.py
```

The default input is the ignored control fixture at
`artifacts/control-probe/20261021T180450Z-f8fc9132/control-probe-final.sav`.
The probe stages copied saves and isolated profiles. It requires a clean
engine checkout and a binary whose runtime revision names the checkout commit.
It checks industry pagination, wrong-world rejection, a four-page tile window
across rail/station/ordinary map tiles, and fresh-process reload. It also
checks that company balance, loan, operation sequence, original save, and
normal profile remain unchanged.

Raw manifests and logs are under `artifacts/native-industry-probe/<run>/`.
The successful baseline is summarized in
[the evidence JSON](evidence/2026-10-23-native-industry-probe.json). The
retained failed sweep at `20261023T181250Z-fce131d6` documents the corrected
house-tile assertion.
