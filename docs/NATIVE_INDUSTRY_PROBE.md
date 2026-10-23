# Run the M2d industry details and tile-window probe

Build the clean fork at `211e780180c021b208a87d2612f4c24be9f743a6`
with the instructions in [engine/README.md](../engine/README.md), then run
from the repository root:

```sh
python3 -B -m unittest discover -s tests
python3 -B tools/run_native_industry_probe.py
```

The probe reads both the original kind-5 industry pages and the additive
kind-10 details pages. It checks industry IDs, types, anchors, and cargo
against the existing snapshot; validates nonempty names and positive
`TileArea` bounds within the map; checks wrong-world rejection and unchanged
company/operation state; and compares both pages after fresh-process reload.
The bounds are rectangles around industry locations, not a per-tile footprint.

The default input is the ignored control fixture at
`artifacts/control-probe/20261021T180450Z-f8fc9132/control-probe-final.sav`.
The probe stages copied saves and isolated profiles. It requires a clean
engine checkout and a binary whose runtime revision names the checkout commit.
It also checks a four-page tile window across rail/station/ordinary map tiles
and verifies that company balance, loan, operation sequence, original save,
and normal profile remain unchanged.

Raw manifests and logs are under `artifacts/native-industry-probe/<run>/`.
The latest source-hashed run is summarized in
[the details evidence JSON](evidence/2026-10-23-native-industry-details-probe.json).
The original cargo/tile baseline remains in
[the initial evidence JSON](evidence/2026-10-23-native-industry-probe.json).
The retained failed sweep at `20261023T181250Z-fce131d6` documents the
corrected house-tile assertion.
