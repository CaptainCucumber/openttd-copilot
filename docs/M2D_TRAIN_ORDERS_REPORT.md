# M2d checkpoint — company train-order readback

Status: **read-only checkpoint passed; M2 remains in progress**, 2026-10-23.

Protocol-v3 request kind 9 reads at most 16 records from an explicit primary
train's order list. Each response carries world, frame, human company, train,
total-order count, and page offset. Records report OpenTTD's order type,
destination ID (when applicable), load policy, unload policy, and non-stop
flags. The query does not add a gameplay command, change the COPL save chunk,
or expand the mutation allowlist.

## Real-engine result

The clean OpenTTD 15.3 fork commit
`5f8e025d70c9eb6faeca1bc797b1377039ed0ca8` produced the matching runtime
revision. The final copied-save run
`artifacts/native-train-orders-probe/20261023T200530Z-4dd7b9ba/manifest.json`
passed in 1.612 seconds. Its
[source-hashed evidence](evidence/2026-10-23-native-train-orders-probe.json)
records the engine/binary/source hashes and raw order values.

- Train 2 returned two orders: order type 1 to station 0 with load type 2
  (full load), followed by order type 1 to station 1 with load type 4
  (no load) and unload type 1 (unload).
- Fresh-process copied-save reload returned the same two values. Wrong-world,
  missing-company, and missing-train queries returned typed errors.
- For order types without station loading policy, the wire record marks
  load/unload and non-stop fields unavailable instead of interpreting
  overlapping conditional/depot flag bits as those policies.
- The original service save and normal profile were unchanged; the company
  money and loan were the same before and after each query; temporary secrets
  were removed. No gameplay mutation request was sent.

This confirms the fixture's persisted order configuration, not that the route
is reachable, the train was purchased by Copilot, or that cargo was delivered.
Order and vehicle IDs are observations that can change in a running world;
multi-page reads are not atomic. Revalidate before acting.
