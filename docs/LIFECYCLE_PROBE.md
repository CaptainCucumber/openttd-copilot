# Second checkpoint: Admin transport and lifecycle

This S3a experiment controls a human company through versioned Admin/GameScript requests in disposable OpenTTD 15.3 worlds. It builds two rail pieces and tests recovery. It does not build a railway service or purchase trains.

Requirements match the [first control probe](CONTROL_PROBE.md): macOS, Python 3.10+, installed OpenTTD 15.3, and OpenGFX2 Classic. No Python dependencies or AI credentials are required. Run from the repository:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B tools/run_lifecycle_probe.py
```

Expected: 36 unit tests pass; the engine probe prints 12 `PASS` lines followed by `lifecycle probe success: ...`. It writes fresh profiles to `.runtime/lifecycle-probe/` and logs, manifests, external journal, and saves to `artifacts/lifecycle-probe/`. Failure retains diagnostics and exits nonzero. A timeout does not prove that a mutation did not happen.

The default deadline is 120 seconds; `--deadline` and `--seed` override it. The measured seed is `20261021` on a 128×128 temperate 1950 map. The changed-world phase uses seed `20261022`. Game and Admin ports bind to loopback. Legacy Admin password authentication is restricted to this disposable local experiment.

## What passed

| Check | Observed result |
|---|---|
| Human company and protocol | Requests resolve the named human client's company 0; unsupported protocol versions are rejected |
| Paging | A 17-tile capture returns five pages with stable repeat reads and no skipped/duplicate tiles |
| Lost response | Close the Admin connection after sending rail construction; reconnect, query status, read back the tile, and reconcile the externally persisted intent |
| Operation identity | Repeating the same operation returns its stored result; a changed payload with the same ID is rejected without spending |
| Second mutation | Two distinct rail pieces cost 90 each; cash 100,000 → 99,820 and loan remains 100,000 |
| Pause | Queries and ping respond while paused; a new build is refused and does not execute after unpause |
| Latest save | Reload restores world/sequence/head and outcomes; stale session is rejected; replay after rebinding changes no cash, loan, or sequence |
| Older save | Sequence 0 is recognized as older than the external sequence 2; later rail is absent; no bind or replay is attempted |
| Changed world | A fresh world has no inherited identity; the controller detects the new identity and rejects old-world status requests |

Final integrated run: `20261022T173734Z-4c01df51`, 6.749 seconds including setup and all four worlds. Largest observed Admin packet: 448 bytes, including framing. Normal-profile configuration and all three original saves retain identical hashes and modification times. [Source-hashed evidence](evidence/2026-10-22-lifecycle-probe.json).

## Protocol and persistence limits

The fixture exposes only `hello`, `init`, `bind`, `candidate`, `scan`, `page`, `build`, and `status`. It accepts at most 1,449 JSON bytes per request, scans at most 32 tiles, returns four tile rows per page, and keeps at most 32 game-side journal entries. Rail construction retains a 10,000 cash reserve and uses a per-command cap no larger than 10,000 engine money units. These are experimental limits, not the final product budget policy.

A write failure, partial network send, response-buffer overflow, unknown outcome, or divergent journal must stop automatic continuation. This probe deliberately has no retry executor or operator workflow for resolving rejected/uncertain operations. Disk-write failure tests exercise external intent durability; they do not prove safety across a game crash between its command and journal/save updates.

Temporary Admin credentials and the stable test-client key are kept out of logs/evidence and removed at shutdown. The key is reused across the run's reloads because a fresh client identity cannot automatically rejoin the saved company's allow-list. A new probe run creates new secrets.

The world token and high-water comparison are single-controller evidence. Binding is not a server-enforced atomic lease, and arbitrary copied saves or coexistence with a different GameScript are not covered. This rail fixture does not satisfy M1's duplicate-purchase or delivery-telemetry gates. Next is S3b vehicle/order/delivery evidence and throughput measurement, then the adapter decision.
