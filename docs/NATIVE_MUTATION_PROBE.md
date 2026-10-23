# Run the M2b native mutation probe

Build the pinned fork as described in [engine/README.md](../engine/README.md). From the repository root:

```sh
python3 -B -m unittest discover -s tests
python3 -B tools/run_native_mutation_probe.py
```

The default source is the ignored `artifacts/control-probe/20261021T180450Z-f8fc9132/control-probe-final.sav`; supply `--save /absolute/path/to/copied-fixture.sav` if it is absent. The selected tile must be flat and clear; the default is 8255. The probe requires a clean engine checkout at commit `8b8f3d7bad64fb01fc2a216b35e8070be95f51d8` and a rebuilt binary whose runtime revision names that commit. `--binary` can select a different path to that build.

The probe creates isolated disposable server profiles, stages application resources, and loads copies only. It tests cap rejection, one 90-unit rail build under the default cap, duplicate replay, save/reload replay, and older-save detection. Its final `manifest.json`, logs, copied saves, and external journal live in the printed `artifacts/native-mutation-probe/<run>/` directory. A failed run leaves its artifacts for diagnosis. Do not use a normal game save as a construction target; use a copy and inspect the chosen tile first. This probe is not the end-to-end railway acceptance test.
