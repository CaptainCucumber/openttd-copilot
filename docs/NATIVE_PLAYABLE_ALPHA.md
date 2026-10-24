# Native playable alpha

This is the existing-business native railway path, not the older controlled
GameScript demo. The opened map contains naturally generated industries;
construction uses their observed IDs and never creates replacement businesses.

## Run locally

Prerequisites: Python 3, the installed OpenTTD 15.3 application/resources and
OpenGFX archive used by the probes, and both custom binaries built using
[engine instructions](../engine/README.md). On this development checkout they
are already built.

From the repository root:

```sh
python3 -B tools/play_native.py
```

The visible game opens before construction. Default seed **6** has the tested
Canley Coal Mine (10) and Canley Power Station (1). Enter:

```text
build coal railway from Canley Coal Mine to Canley Power Station; full load; budget 50000; reserve 10000
```

Names or the displayed numeric IDs work. This standalone parser is deliberately
model-free and accepts that exact sentence shape, not unrestricted chat. It
reports planning, building and verification; allow several minutes for actual
coal production and train travel. The train remains running and the game stays
open after verification. Keep the terminal open while playing. `save` saves
under that run's artifact directory; `quit` saves and closes only this session.
EOF also saves/closes; shutdown waits for an active bounded job to finish.
Never interrupt a mutation and then assume it is safe to retry.

Use `--seed INTEGER` for another newly generated map or
`--save /absolute/path/world.sav` to load a **copy**. These options do not
guarantee a supported route exists. Loading arbitrary old saves is not the
alpha acceptance cohort; maps larger than 128 by 128 are rejected for planning.

## Connect an AI

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
payloads are rejected. Status is not continuous health monitoring after the
player edits the railway. `close_native_map` saves/closes an idle session.

## Supported boundary

One railway per session, one human company 0, standard temperate coal,
single-head locomotive plus one default coal wagon, two-tile platforms,
flat clear unowned equal-height land, at most 50 rail tiles and 64 retained
operations including prior records. No trees, roads, slopes, bridges, tunnels,
signals, refits or existing-rail reuse. Candidate and search bounds can reject
a feasible map; no optimal-route or broad seed success-rate claim is made.
The default seed was selected after retaining failed distant-pair trials.

Normal OpenTTD rules remain authoritative. Full infrastructure and train cost,
existing cash and the disclosed reserve are checked before construction.
Cap/reserve numbers are integral engine money units, not formatted GUI currency.
Prices, cash and identity are checked again during execution. No borrowing or
automatic rollback. Rejected, partial and uncertain work is preserved and
reported, not automatically retried. Crash-window recovery, cancellation,
broader terrain, conversational acceptance and packaged-release gates remain
open. See [the measured checkpoint](M2D_NATIVE_RAILWAY_REPORT.md).
