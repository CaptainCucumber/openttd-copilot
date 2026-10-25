# Native playable alpha

This is the native town-bus/existing-business railway path, not the older controlled
GameScript demo. The opened map contains naturally generated industries;
construction uses observed town/business IDs and never creates replacement endpoints.

**Bounded bus alpha:** actual clean-engine construction, passenger acceptance
at both towns, retained replay and conversational construction have passed.
See [bus evidence and limits](M2E_TOWN_BUS_REPORT.md); this does not establish
general random-map reliability or profitability.

## Run locally

Prerequisites: Python 3, installed and signed-in GitHub Copilot CLI, the
installed OpenTTD 15.3 application/resources and
OpenGFX archive used by the probes, and both custom binaries built using
[engine instructions](../engine/README.md). On this development checkout they
are already built.

From the repository root:

```sh
python3 -B tools/game_chat.py
```

This is actual interactive AI conversation, using your Copilot account and its
allowance. No separate provider key or global MCP configuration change is needed.
Approve opening the game when Copilot requests permission. New games now use a
randomly seeded **normal 256x256 temperate map** with ordinary towns, hills,
water/rivers and trees. It is not a prebuilt route or a specially placed pair.
Ask normally, for example:

```text
What towns and businesses are here, and how much money do I have?
Compare passenger bus options between nearby towns.
Use a 50000 cap and keep 10000 reserve. Don't build yet.
Build the option we just discussed.
What is my bus carrying, and what are its orders?
What optimization ideas would you suggest, and what can't you measure yet?
```

Only live inspection, read-only planning and cached status are automatically
allowed. Construction requires your explicit request and the host's tool
permission; opening/closing also retain host permission prompts. Do not enable
blanket approval just to get advice. The game-only custom agent has no coding
or shell tools. It is not an autonomous company manager.

Live observations include towns/populations, passenger bus availability,
road vehicles/stops/depots/orders, cash/loan, named industries, owned rail stations/depots,
train parts/cargo/stopped state/orders, recent vehicle-tagged events and the
available engine purchase/running-cost catalog. Pages are not an atomic
snapshot. Events are bounded and reset on loading a world; missing events do
not establish inactivity. Cached completed service is not continuous monitoring.
Live inspection/planning is unavailable while a construction worker is active.

**The current bridge does not expose train profit, actual speed, production
rates, station waiting cargo, reliability or detailed company income.** OpenTTD
itself has additional information. Advice must distinguish measured facts,
general suggestions and unknowns; a cost quote is not a profitability forecast.
No vehicle replacement, extra-vehicle optimization, order optimization or track removal tool
is implemented.

Allow several minutes for construction verification and actual coal travel.
The train keeps running and the game stays open after verification. Keep the
terminal open while playing; ask the AI to save and close when finished.
Closing writes `player-save.sav` into the reported artifact directory. Session
shutdown also attempts saved close and waits for an active bounded job.
Never interrupt a mutation and then assume it is safe to retry.

Use `--seed INTEGER` for a reproducible newly generated normal map or
`--save /absolute/path/world.sav` to load a **copy**. These options do not
guarantee a supported route exists. Loading arbitrary old saves is not the
alpha acceptance cohort. Bus planning reads a bounded corridor, at most
192x192 tiles and a 160-tile path, not an unrestricted whole-map search.
Coal railway planning remains limited to maps no larger than 128x128.

## Passenger buses

`plan_native_bus` and `build_native_bus` accept `job_id`, observed
`source_town_id`/`destination_town_id`, `construction_cap` and `operating_reserve`.
The plan supplies actual normal-command prices for road additions, two new
drive-through stops and a connected roadside depot, plus a currently buildable
standard passenger bus. Stops must have actual acceptance and production from
the specified town. Buses load/unload ordinarily at both ends, **not full load**.
Service verification requires passenger acceptance attributed to that bus at
both stops, not merely a successful start command.

Roads are ordinary two-way standard roads. Existing roads can be reused,
including traversable slopes; new links are currently flat clear/tree tiles.
Trees may be cleared only on the quoted road/depot footprint. Houses, existing
assets, rails and water are not cleared; no bridges, tunnels, trams,
terraforming or automatic loans. Normal authority/ownership/money rules still
apply. The cheapest observed available supported bus is chosen, not a proven
optimal vehicle or profitable network.

After verified service, a different explicit request starts a separate durable
job if remaining cash and retained history permit. An identical request returns
cached status. Partial/uncertain execution blocks further construction.
The shared **64-operation world history** has no automatic eviction: a new bus
service needs seven operations before any new road tiles. An obstructed,
distant or record-heavy pair is rejected rather than silently changing towns.

## What comes next

The bounded clean-engine bus gate is complete, with the existing coal path
preserved. Following work targets varied supported roads
and normal maps, interruption/cancellation and honest recovery; then live
production, waiting-cargo and financial observations for more useful advice.
Held-out conversational cases, restart/resume and reproducible packaging
remain separate release gates. No automatic network expansion or unsupported
terrain work is implied. See the [milestone sequence](PROJECT_PLAN.md#next-milestone-sequencing)
and [current status](STATUS.md).

## Explicit railway fixture

The old flat selected scenario remains reproducible:

```sh
python3 -B tools/game_chat.py --map-style railway-fixture
```

Its default seed **6** contains Canley Coal Mine (10) and Canley Power Station
(1). Ask for a full-load coal railway with cap 50000/reserve 10000. These IDs
are fixture observations, not universal constants. A normal hilly map does not
guarantee a supported coal railway.

This starts a new isolated session, **not** an attachment to a running
`play_native.py` game. To continue that world, first enter `save`, note its save
path, and `quit`; then run:

```sh
python3 -B tools/game_chat.py --save /absolute/path/player-save.sav
```

The original save remains unchanged. The copied map is loaded before the first
inspection, so the AI must not open a second map.

## Fixed-command alternative

`python3 -B tools/play_native.py` remains available without model calls. Enter
`build coal railway from 10 to 1; full load; budget 50000; reserve 10000` on
default seed 6. Names also work in that sentence shape. It is deliberately
model-free, not unrestricted chat. `save` saves; `quit` or EOF saves/closes.

## Other MCP hosts

Register this local stdio MCP server in a compatible host:

```json
{
  "mcpServers": {
    "openttd-copilot-native": {
      "command": "python3",
      "args": ["-B", "/absolute/path/openttd-copilot/tools/native_mcp_server.py", "--seed", "20261024"]
    }
  }
}
```

This example selects the tested normal seed explicitly; the interactive
launcher chooses a random seed instead. Ask the AI to open the map, bind the
returned job and **observed** Dudinghall/Hudinghattan Ridge town IDs, quote the
service with `plan_native_bus`, then build only when authorized.
`build_native_bus` takes:

```json
{
  "job_id": "<returned job ID>",
  "source_town_id": 0,
  "destination_town_id": 13,
  "construction_cap": 50000,
  "operating_reserve": 10000
}
```

The IDs above are seed-20261024 observations, not universal constants. Poll
`get_native_status` with `job_id` and `wait_seconds: 10`. For buses,
`operating` means vehicle-attributed passenger acceptance at both stops.
For the separate railway fixture, add `--map-style railway-fixture --seed 6`
to the server arguments and use `plan_native_railway`/`build_native_railway`
with the seven coal/full-load fields. Railway operation requires two accepted
deliveries and a third full-load departure, proving both returns.
The returned paths include a commissioned save, verified service save and
durable job record. Duplicate identical calls return cached job status; changed
requests are blocked during execution and after partial/uncertain failures.
After verified operation, another explicit service can begin if cash/history
permit. A planning-only `rejected` result
has `construction_started: false`: no construction was attempted and a changed
explicit request may be submitted on that same map. Partial/uncertain/execution
failures do not authorize a changed request or automatic retry.
`inspect_native_game` reads fresh state with no arguments.
`plan_native_railway` takes the same seven fields as building but only returns
a quote; it does not launch execution or replace the active job.
Status is not continuous health monitoring after the
player edits the railway. `close_native_map` saves/closes an idle session.

## Supported boundary

Railway boundary: one human company 0, standard temperate coal,
single-head locomotive plus one default coal wagon, two-tile platforms,
flat clear unowned equal-height land, at most 50 rail tiles and 64 retained
operations including prior records. No trees, roads, slopes, bridges, tunnels,
signals, refits or existing-rail reuse. Candidate and search bounds can reject
a feasible map; no optimal-route or broad seed success-rate claim is made.
The default seed was selected after retaining failed distant-pair trials.
Listed cargo-compatible pairs are not guaranteed buildable routes. For example,
Hunninghead (12) -> Canley Power Station (1) needs at least 70 intermediate
rail tiles among the selected valid station candidates; the alpha limit is 50.
It is rejected before construction, not repaired by raising the search budget.

Normal OpenTTD rules remain authoritative. Full infrastructure and train cost,
existing cash and the disclosed reserve are checked before construction.
Cap/reserve numbers are integral engine money units, not formatted GUI currency.
Prices, cash and identity are checked again during execution. No borrowing or
automatic rollback. Rejected, partial and uncertain work is preserved and
reported, not automatically retried. Crash-window recovery, cancellation,
broader terrain, conversational acceptance and packaged-release gates remain
open. Actual Copilot advice and populated-train inspection have bounded
[runtime evidence](evidence/2026-10-24-native-game-chat.json), not a broad
paraphrase/reliability acceptance cohort. See also
[the construction checkpoint](M2D_NATIVE_RAILWAY_REPORT.md).
