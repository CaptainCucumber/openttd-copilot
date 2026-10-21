# First implementation checkpoint: company control

This developer probe creates a disposable OpenTTD world, connects a normal player client, and runs a small construction test for that player's company. It is the first S1/S2 checkpoint in [M1](PROJECT_PLAN.md#m1--prove-control-and-select-the-integration). It does not build a transport service yet.

Requirements: macOS, Python 3.10 or later, OpenTTD 15.3 at `/Applications/OpenTTD.app`, and an installed OpenGFX2 Classic base graphics archive. The harness copies the archive; it does not install content into your normal profile. No Python packages, model access, or AI credentials are needed.

From the repository directory:

```sh
python3 -m unittest discover -s tests -v
python3 tools/run_control_probe.py
python3 tools/check_probe_reload.py --run latest
```

Each run creates fresh directories under `.runtime/control-probe/` and `artifacts/control-probe/`. The latter holds the manifest, raw engine logs, assertion events, and saved-world evidence. A failed run exits unsuccessfully and retains its diagnostics. Do not treat a timeout as proof that no construction occurred.

The test discovers a company from the named connected client, reads industries and available trains, and finds a small suitable construction footprint. It checks test-mode cost estimates and lack of mutation, builds a rail piece and a two-tile station with normal engine commands, reads back ownership and geometry, then checks that repeating the same track command fails without a charge or asset change. Its construction cap and retained cash are each 10,000 internal engine money units; these are fixture limits, not the future product's reserve policy.

The generated world is 128 by 128 tiles, temperate, starting in 1950, with seed `20261021`, very flat terrain, very low sea level, no rivers or AI competitors, and inflation disabled. No gameplay NewGRFs are configured. The manifest records the exact binary, graphics, scripts, settings, and source hashes. A seed alone does not guarantee byte-identical saves across differing versions, timings, or content.

To open a fresh isolated copy of the latest saved result:

```sh
python3 tools/run_control_probe.py --inspect latest --open
```

Omit `--open` to print a direct command instead. The `--open` path protects the recorded save by copying the profile for each inspection.

Manual inspection should show company 0 (the first company in the UI) owning rail at (64,64) and a two-tile station at (65,64)–(66,64). Open that company's station list to locate the station. The measured construction cost is 840 engine money units; immediate post-build cash is 99,160 and the original 100,000 loan is unchanged. Normal game time may later incur loan interest. There is no locomotive, depot, or operating route at this stage.

The GameScript refuses to perform construction when a saved probe is loaded. The reload checker reads ownership, track geometry, cash, loan, and saved cost in a fresh engine process, and rejects any construction events. This is a one-shot fixture guard, not general restart recovery. Automated construction and reload pass; visual inspection is the user handoff. [Recorded evidence](evidence/2026-10-21-control-probe.json).

Your normal OpenTTD profile and original saves are outside the test directories. Run the provided inspection command rather than loading this fixture through your normal profile. Runtime directories and saves are ignored by Git; the scripts, test code, decisions, and concise evidence reports are versioned.

Next: external Admin/GameScript requests, pause/reconnect/save behavior, larger observation/construction measurements, vehicle/order and delivery telemetry, then an evidence-based adapter decision. Only after that comes the complete coal railway.
