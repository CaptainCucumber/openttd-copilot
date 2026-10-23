# M2c — vehicle-tagged native service observation

Status: **complete for the observation checkpoint**, 2026-10-23. M2 remains in progress.

The OpenTTD 15.3 fork adds protocol v3's read-only, authenticated, loopback-only vehicle-event query. The engine records a train's cargo load and capacity as it leaves a station, and records cargo actually accepted by each industry while retaining the paying vehicle ID. Each event includes world-scoped runtime epoch, sequence, frame, company, vehicle, station, cargo, amount, and destination industry where applicable. A 256-event runtime ring returns at most 16 matching events per page; a stale cursor reports a gap. The ring resets on world load and is **not saved**. The epoch changes on process start and world load so callers can detect a reset.

## Real-engine result

The clean fork commit `37f88cc03d88a99273297b2691f88c16f6926fc4` produced runtime revision `20261023-m2c-vehicle-observation-g37f88cc03d`. The final isolated run was `artifacts/native-vehicle-probe/20261023T172550Z-485cd1fd/manifest.json` (160.388 seconds); [source-hashed evidence](evidence/2026-10-23-native-vehicle-probe.json) retains the nine native events. OpenTTD 15.3 used the 128×128 temperate generated world, seed 20261021, standard OpenGFX, company 0, and a GameScript-built one-train coal fixture.

- Train 2 left source station 0 at frames 3268 and 5052 carrying **30/30 coal** each time.
- The same train delivered coal to destination station 1 and power-station industry 11. The first visit accepted six 5-unit chunks; the second had accepted one 5-unit chunk by the end of the observation gate. The verifier counts delivery visits, not packet chunks.
- The stock fixture's two-cycle gate, purchase replay after reload, orders, loan preservation, normal-profile hash check, and temporary-secret cleanup also passed. Eighty-five Python tests passed separately.

The GameScript still builds the disposable fixture, buys the train, and configures orders. M2c proves native observation of its service, **not** native end-to-end construction or general route reliability. The event ring is runtime-only; a reader must detect epoch changes and gaps, then stop claiming continuous observation. The 256-event overflow path is implemented but has not been exercised in a real game. Complete route planning and native execution remain M2d; crash-gap fault injection remains M3.
