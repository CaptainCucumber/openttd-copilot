# Native playable alpha

This is the existing-business native railway path, not the older controlled
GameScript demo. The opened map contains naturally generated industries;
construction uses their observed IDs and never creates replacement businesses.

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
Approve opening the game when Copilot requests permission. Default seed **6**
contains the tested Canley Coal Mine (10) and Canley Power Station (1).
Ask normally, for example:

```text
What businesses are on this map, and how much money do I have?
Compare Canley and Hunninghead for supplying Canley Power Station.
Use a 50000 cap and keep 10000 reserve, full load. Don't build yet.
Build the Canley option.
What is my train carrying, and what are its orders?
What optimization ideas would you suggest, and what can't you measure yet?
```

Only live inspection, read-only planning and cached status are automatically
allowed. Construction requires your explicit request and the host's tool
permission; opening/closing also retain host permission prompts. Do not enable
blanket approval just to get advice. The game-only custom agent has no coding
or shell tools. It is not an autonomous company manager.

Live observations include cash/loan, named industries, owned stations/depots,
train parts/cargo/stopped state/orders, recent vehicle-tagged events and the
available engine purchase/running-cost catalog. Pages are not an atomic
snapshot. Events are bounded and reset on loading a world; missing events do
not establish inactivity. Cached completed service is not continuous monitoring.
Live inspection/planning is unavailable while a construction worker is active.

**The current bridge does not expose train profit, actual speed, production
rates, station waiting cargo, reliability or detailed company income.** OpenTTD
itself has additional information. Advice must distinguish measured facts,
general suggestions and unknowns; a cost quote is not a profitability forecast.
No vehicle replacement, extra trains, order optimization or track removal tool
is implemented.

Allow several minutes for construction verification and actual coal travel.
The train keeps running and the game stays open after verification. Keep the
terminal open while playing; ask the AI to save and close when finished.
Closing writes `player-save.sav` into the reported artifact directory. Session
shutdown also attempts saved close and waits for an active bounded job.
Never interrupt a mutation and then assume it is safe to retry.

Use `--seed INTEGER` for another newly generated map or
`--save /absolute/path/world.sav` to load a **copy**. These options do not
guarantee a supported route exists. Loading arbitrary old saves is not the
alpha acceptance cohort; maps larger than 128 by 128 are rejected for planning.

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
      "args": ["-B", "/absolute/path/openttd-copilot/tools/native_mcp_server.py"]
    }
  }
}
```

Ask the AI to open a native map, then build the coal railway between the
**discovered** Canley businesses, full load, construction cap 50,000 and reserve
10,000. It must call `open_native_map`, bind the returned business and job IDs,
then call `build_native_railway` with:

```json
{
  "job_id": "<returned job ID>",
  "source_id": 10,
  "destination_id": 1,
  "cargo": "coal",
  "wait_for_full_load": true,
  "construction_cap": 50000,
  "operating_reserve": 10000
}
```

The IDs above are seed-6 observations, not universal constants. Poll
`get_native_status` with `job_id`. `operating` means the verifier observed two
accepted deliveries and a third full-load departure, proving both returns.
The returned paths include a commissioned save, verified service save and
durable job record. Duplicate identical calls return cached job status; changed
payloads are rejected after execution starts. A planning-only `rejected` result
has `construction_started: false`: no construction was attempted and a changed
explicit request may be submitted on that same map. Partial/uncertain/execution
failures do not authorize a changed request or automatic retry.
`inspect_native_game` reads fresh state with no arguments.
`plan_native_railway` takes the same seven fields as building but only returns
a quote; it does not launch execution or replace the active job.
Status is not continuous health monitoring after the
player edits the railway. `close_native_map` saves/closes an idle session.

## Supported boundary

One railway per session, one human company 0, standard temperate coal,
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
