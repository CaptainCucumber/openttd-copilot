# Native train configuration probe

This developer gate configures purchased vehicles in a disposable copy of a
known test save. It does not plan or build a connected railway between
businesses. Build the [pinned custom engine](../engine/README.md), then run:

```sh
python3 -B tools/run_native_train_configuration_probe.py --deadline 120
python3 -B -m unittest discover -s tests
```

The default source is
`artifacts/native-train-purchase-probe/20261024T221240Z-89c4c574/train-purchase-final.sav`.
The adjacent successful manifest supplies all 12 prior outcomes and the
source save fingerprint. Missing or mismatched evidence is an error, not a
skipped migration gate. `--save`, `--binary`, and `--deadline` permit explicit
paths/bounds. `--allow-dirty-engine` is for source-hashed development only;
acceptance uses the exact clean engine revision.

The probe selects IDs from retained purchase evidence, revalidates them
against independent parts/assets/orders, attaches the free coal wagon,
appends two station policies, and starts then stops the primary. It verifies
no-op desired states, original-outcome replay after later changes, guards,
all prior/new outcomes after fresh-process reload, and no replay mutation.
The spare locomotive remains unchanged. Each admitted intent is fsynced to
its own journal before sending; pending is polled and terminal is reconciled
before the next action. Unknown results stop the gate.

Artifacts, source/binary/content/settings hashes, raw replies, journals, and
the final save are under `artifacts/native-train-configuration-probe/<run>/`.
Normal profile and source save fingerprints must be unchanged. Private
runtime credentials are removed by the harness.

## Wire and action contract

Protocol v3 request 15 is `<HBIBIBIIHBqQQQQQQQ>` followed by the NUL-terminated
world ID: version, request kind, request ID, company, tile, action, vehicle ID,
target ID, expected append index, policy, max cost, expected sequence, head
hi/lo, operation hi/lo, payload hash hi/lo. Request 16 status is `<HBIQQ>`
(version/kind/request ID/operation hi/lo) followed by the world ID.

Replies extend the unchanged base operation with `<BBIHIIHB>`: kind, length,
created asset ID, engine ID, vehicle ID, target ID, append index, policy.
Configuration has length/track 0, rail type 255, no created ID (`0xffffffff`),
and no engine ID (`0xffff`). Older records use configuration sentinels:
vehicle/target `0xffffffff`, index/policy 0. Status 16 reads kinds 0-6;
status 2/12/14 explicitly refuses configuration instead of truncating identity.

| Kind | Action | Preconditions and payload |
|---|---|---|
| 4 | Attach free wagon chain | Source vehicle is a free chain head; target is an owned primary; both stopped in the same depot. Append after the target's actual tail. Index/policy 0. |
| 5 | Append station order | Owned primary stopped in depot, unshared orders, expected current index 0 or 1, owned rail station target. Policy 0: full-load-all/no-unload; policy 1: no-load/unload-if-possible. Default non-stop flags 0. |
| 6 | Set running state | Target `0xffffffff`, index 0, policy 0 stopped/1 running. Starting requires a stopped depot primary with two orders and normal engine start validation. Stopping may use its observed tile outside a depot. Already-desired state is a successful no-op. |

Normal OpenTTD commands remain authoritative. The wrapper quotes and rechecks
the per-command cap before execution; callbacks verify the actual resulting
chain/order/stopped state. Postcondition failure becomes uncertain. All
immutable fields, not merely the hash, are bound on replay.

COPL schema 5 migrates earlier retained histories. Shared 64-record capacity,
no eviction, pending/uncertain blocking, and no automatic uncertain retry
remain unchanged. These commands do not refit, replace/share/reorder human
orders, reserve a whole-job budget, or solve crash-gap recovery.

## Interpreting start/stop and money

Successful start is not successful transport. The fixture's stations do not
cover coal businesses; there is no tested traversable route. The primary
begins leaving the depot before stopping on its tile, so it need not retain
the original `in_depot` flag. Only actual independent state is reported.

Configuration command charges are zero, but a running locomotive accrues
ordinary simulation expense. The gate separately records balance movement,
requires no loan change, and compares unchanged money before starting.
After stopping it waits at least the standard fixture's 74-tick economy day
to settle the engine's accumulated `running_ticks`, then checks stable
state/finances across replay and reload. This fixture-specific wait is not a
generic settings-independent accounting API. See the
[measured report](M2D_TRAIN_CONFIGURATION_REPORT.md).
