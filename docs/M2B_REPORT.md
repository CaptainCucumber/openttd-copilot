# M2b — bounded native rail mutation

Status: **complete for the one-piece checkpoint**, 2026-10-23. M2 as a whole remains in progress.

The committed OpenTTD 15.3 fork adds protocol v2 to the authenticated, loopback-only Admin bridge. A request names the world, human company, one flat clear tile, rail type/track, cost cap, expected operation position, and unique operation ID. The engine posts a typed wrapper through its normal game-thread command pipeline, quotes before mutation, rejects a quote above the cap, and returns actual command cost and tile/company readback. No direct tile edit or arbitrary command transport is exposed.

The versioned `COPL` save chunk retains world ID, successful-operation sequence/head, and one operation record. The Python client writes and fsyncs an external intent journal before send and reconciles the engine position on reconnect. Repeating the same operation/payload reads the stored outcome; a conflicting or different second operation is refused. A loaded pending operation is marked uncertain rather than retried.

## Real-engine result

Final run: `artifacts/native-mutation-probe/20261023T163704Z-fb8cb770/manifest.json`, summarized in [source-hashed evidence](evidence/2026-10-23-native-mutation-probe.json). The clean engine checkout was `8b8f3d7bad64fb01fc2a216b35e8070be95f51d8`; the executable reported `20261023-m2b-typed-rail-mutation-g8b8f3d7bad`. The probe loaded only a copy of the control fixture's final save, in an isolated profile, on a 128×128 temperate world with seed 20261021 and standard OpenGFX resources.

- Zero maximum cost rejected the same tile with zero charge, no track, unchanged cash/loan, and sequence 0.
- A 1,000-unit cap allowed one rail piece at tile 8255 for actual cost **90**. Company 0 owned rail type 0 with track bit 2; cash went **99,160 → 99,070**, loan stayed **100,000**, and sequence advanced **0 → 1**.
- Same-ID request returned the completed record without another charge. After saving and reloading the copied world, the world ID, sequence, track readback, and completed outcome remained; another duplicate again had no effect.
- Reloading the older source save was classified as `older_save` against the external journal. The source save, normal profile configuration/saves, and temporary-secret cleanup checks passed.

The run took 3.252 seconds. Eighty Python unit tests passed separately. The fork commit is published on `copilot/m2b-typed-rail-mutation`; the corresponding mail patch is retained under `engine/patches/`.

## Open boundaries

This is deliberately **one operation per world** on a flat clear tile. It cannot build stations, a connected route, depot, train, or service. A loaded pending-save conversion is implemented but not fault-injection-tested. Execution and saving are not atomic: after a crash, a mutation can exist only in memory or a newer save than the one subsequently loaded. The journal must stop uncertain rather than infer that retry is safe. Multiplayer client synchronization and compatibility of custom-written saves with a stock build were not tested. Vehicle-tagged loading/delivery observations and whole-job budgeting remain M2c/M2d work.
