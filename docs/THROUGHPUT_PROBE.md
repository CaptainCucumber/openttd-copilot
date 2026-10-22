# M1 throughput probe

Status: the five-world cohort passes in OpenTTD 15.3. This probe does not select
the adapter or close M1. See the [concise evidence](evidence/2026-10-22-throughput-probe.json).

Measured results: 10,000 valid tile observations take 2.670s median / 2.678s
nearest-rank p95. The 100-piece sequence takes 2.752s median / 2.755s p95.
Every run read back all 100 pieces with the correct owner, stayed under its
20,000-unit cap, preserved the 100,000-unit loan, and left the normal profile
unchanged. The raw successful run is
`artifacts/throughput-probe/20261022T214622Z-2e240ab1/`.

## What it measures

`tools/run_throughput_probe.py` defaults to five independent disposable
OpenTTD 15.3 worlds. In every world it:

1. binds the normal client-created human company;
2. reads 10,000 valid tiles in GameScript (skipping OpenTTD's void border), including tile ID, owner, rail
   tracks, slope, height, water, and buildability, and returns a bounded
   aggregate rather than an oversized row dump;
3. searches for and dry-runs 100 legal flat rail pieces without mutation;
4. proves construction is refused while paused;
5. retests and builds the 100 pieces sequentially through
   `GSRail.BuildRailTrack`, enforcing the engine quote, a 20,000-unit total
   cap, a 10,000-unit cash reserve, and unchanged loan;
6. reads back all 100 pieces and their owner independently; and
7. records wall time, simulation ticks, request/response sizes, concurrent
   Admin ping and queued GameScript-response latency, and post-operation
   responsiveness.

The final manifest reports median and nearest-rank p95 for each metric. With
five samples, nearest-rank p95 is the slowest sample. A failed or partial run
prevents aggregate success; the harness never drops an inconvenient run.

## Safety and limits

- Worlds, profiles, client identity, and Admin password are disposable. Normal
  configuration and saves are fingerprinted before and after the cohort.
- Stock command test/execute behavior, company ownership, money, loan, and
  pause rules remain authoritative. The probe does not bypass validation.
- Candidate preparation is intentionally outside construction timing. The
  timed construction includes the required per-piece retest and readback after
  every mutation. The separate final readback is outside construction timing.
- A partial or accounting-mismatched construction is reported as partial and
  stops the cohort. It is not retried or described as rolled back.
- The stock GameScript opcode budget is not overridden. Start/end ticks expose
  suspension, but the fixture does not claim an exact opcode count.
- The pieces are simple independent rail tiles in a generated fixture, not a
  connected route or proof of arbitrary terrain performance.

## Run and inspect

```sh
python3 -B tools/run_throughput_probe.py
```

Artifacts are written below `artifacts/throughput-probe/<run>/`. The expected
successful console result is five `PASS throughput_run_N` lines plus
`PASS cohort_complete`. Review the manifest and raw logs before treating a new
run as comparable evidence.

For a non-acceptance smoke run, explicitly reduce the cohort with `--runs 1`;
such a run cannot supply the required five-run median/p95 evidence.
