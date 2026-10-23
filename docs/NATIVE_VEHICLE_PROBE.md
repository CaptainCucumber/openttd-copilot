# Run the M2c native vehicle-observation probe

Build the pinned fork from [engine/README.md](../engine/README.md), then run from the repository root:

```sh
python3 -B -m unittest discover -s tests
python3 -B tools/run_native_vehicle_probe.py
```

The run takes about three minutes. `--binary` selects another committed custom build; `--deadline` changes the default 600-second bound. The probe creates an isolated server and client, generates a disposable 128×128 temperate world using seed 20261021, builds the coal fixture through the retained GameScript, then reads vehicle-tagged service events from the native bridge. It checks two full mine departures and two accepted destination deliveries by the assigned train. The normal OpenTTD profile and saves are not used as construction targets.

Raw `manifest.json`, game logs, and copied saves remain under the printed `artifacts/native-vehicle-probe/<run>/` path. A failed run leaves artifacts for diagnosis. The probe requires a clean engine checkout and a binary revision naming that commit.
