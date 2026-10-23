# Run the M2d read-only tile probe

Build the pinned custom OpenTTD commit in [engine/README.md](../engine/README.md),
then run from the repository root:

```sh
python3 -B -m unittest discover -s tests
python3 -B tools/run_native_tile_probe.py
```

The default input is the ignored control fixture at
`artifacts/control-probe/20261021T180450Z-f8fc9132/control-probe-final.sav`.
The probe loads copies only. It requires the clean engine checkout at
`bf789a968cdf47ac54237a917402821d24e6dff6` and a binary whose runtime
revision names that commit. `--save` and `--binary` can select alternate paths,
but the tile assertions require the same control fixture geometry.

It reads tile IDs 8255–8258 and 127–128, checks the known rail/station/void
types and ownership, rejects a different world ID, and reloads a fresh copy to
compare the page. The output manifest and logs are under
`artifacts/native-tile-probe/<run>/`. The committed [evidence summary](evidence/2026-10-23-native-tile-probe.json)
names the final run. This is a read-only planner-data seam; it does not build a
railway or prove the M2 gate.
