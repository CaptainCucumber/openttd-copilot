# M2d checkpoint — native tile pages

Status: **read-only checkpoint complete, M2d and M2 remain in progress**, 2026-10-23.

The OpenTTD 15.3 fork adds request kind 4 to Copilot protocol v3. An
authenticated loopback Admin client supplies the persisted world ID, start
tile, and count (1–32). The game-thread handler rejects a wrong world or
invalid range, and returns frame, contiguous tile IDs, validity, tile type,
owner, slope, height, and plain/crossing rail bits/type. Each page is bounded
to 32 records. Separate pages may observe different simulation frames; the
planner must recheck dependencies before it mutates the world.

## Real-engine result

The clean fork commit `bf789a968cdf47ac54237a917402821d24e6dff6` produced
runtime revision `20261023-m2d-tile-snapshot-gbf789a968c`. The final isolated
run `artifacts/native-tile-probe/20261023T174736Z-1b7db921/manifest.json`
passed in 1.654 seconds; the [source-hashed evidence](evidence/2026-10-23-native-tile-probe.json)
records the binary and source hashes. OpenTTD used the copied 128×128 temperate
control save, seed 20261021, company 0, and standard OpenGFX resources.

- Tile 8255 was clear and unowned; 8256 was owned plain rail with track bits;
  8257 and 8258 were owned station tiles. All were flat at height 1.
- Tile 127 was a void border tile and marked invalid. A wrong-world request
  returned typed status 5.
- A fresh-process reload returned the same page. Company cash was 99,160,
  loan 100,000, and saved operation sequence 0 before and after both phases.
  The original source save and normal profile were unchanged; temporary Admin
  secrets were removed. No gameplay mutation request was sent.

This page does not expose industry identity/cargo, station/depot geometry,
vehicle catalog, or general rail traversal. The native bridge still accepts
only one flat clear rail-piece mutation per world. M2d needs the rest of the
snapshot, a deterministic planner, sequential typed commands, whole-job
accounting, and two native-built full-load delivery cycles before its exit gate
can pass. The mutation/save crash gap remains an M3 recovery test.
