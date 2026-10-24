# M2d native existing-business railway

Date: 2026-10-24. **The narrow M2 simple-profile exit is demonstrated.**
This is not the M3 reliability cohort or a packaged general-purpose release.

## Measured result

Clean engine `96f960a3239e87837919414604a19e3eca9830b7` on
`CaptainCucumber/OpenTTD:copilot/m2d-native-railway`, upstream OpenTTD 15.3.
Both dedicated server and matching software-Cocoa graphical client were built
with assertions. No GameScript constructs or funds this railway.

Default seed 6 generates Canley Coal Mine, industry 10, and Canley Power
Station, industry 1, 37 anchor-Manhattan tiles apart. The planner binds those
observations, rather than creating test industries. The final native gate:

| Property | Evidence |
|---|---|
| Complete plan | Two two-tile stations, one inline depot, 35 rail tiles, locomotive and coal wagon |
| Construction | 44 native actions, quoted and actual cost **14,979**, cap 50,000, reserve 10,000 |
| Budget refusal | Cap 1 rejected before any mutation; assets, cash, loan and operation position unchanged |
| Actual assets | Stations 0/1, depot 0, locomotive 2 and wagon 3; independent parts and exact full-load/delivery orders |
| Service | Three **30/30** coal departures and two vehicle-tagged accepted delivery cycles to industry 1 |
| Return evidence | Third loaded departure proves the train returned after both deliveries |
| Finances | Cash 100,000 -> 85,021 from construction; 85,505 at service verification including normal operating costs/revenue; loan unchanged 100,000 |
| Replay/reload | All 44 mixed immutable outcomes retained; exact replay leaves sequence/head, infrastructure, consist and running state unchanged |
| Preservation | Normal profile and copied source saves unchanged; ephemeral secrets removed; no structured engine errors |

Final gate: `artifacts/native-railway/20261024T230856Z-d0747072/`, **228.091
seconds**, all seven checks passed. Inspect
`native-service-final.sav` with the matching custom client. Hashes and source
provenance are in [published evidence](evidence/2026-10-24-native-railway.json);
large saves, journals and logs remain local ignored artifacts.

A separate **visible stdio MCP** run,
`20261024T230513Z-b1a76996`, passed in 204.944 seconds: initialize/tools,
open map, build, ping/status during the worker, verified operation, identical
duplicate request without another build, and saved close. Its
`mcp-transcript.json` contains the actual JSON-RPC exchange. No paid model call
was used; this proves the AI-facing tools, not a conversational-model cohort.

The final copied-world regression, `20261024T231101Z-6ddf298f`, passed in
4.465 seconds. Prospective quotes covered only the selected producer/acceptor,
not an observed unrelated coal producer; wrong-world quote was rejected,
all quotes were nonmutating, older-save completed-job lookup was refused, and
all 44 outcomes replayed after reload with independent infrastructure/rail
geometry, orders and consist checks. The reference run had verified service
but failed its first replay verifier; it is not relabeled a fully passed run.

## Implementation and limits

Request 17 adds read-only normal command quotes and selected-industry
catchment. Python owns bounded directed search, whole-job pricing and cash
reserve, live catalog selection, fsynced job/operation intent, sequential
revalidation and service verification. The engine retains normal ownership,
terrain, authority, vehicle and money validation. The existing 64-record,
non-evicting history is checked before the first mutation.

The playable entry points are `tools/play_native.py` and
`tools/native_mcp_server.py`; see [operator guide](NATIVE_PLAYABLE_ALPHA.md).
The former is a constrained model-free sentence parser; an external MCP host
supplies AI conversation. One railway per session, company 0, standard
temperate coal, flat clear unowned equal-height land, at most 50 rail tiles.
No optimal-route or arbitrary-seed guarantee. Partial/uncertain jobs are kept
and not retried automatically. Cached status is not continuous health
monitoring. No crash-window, cancellation, arbitrary existing-save build,
general terrain or release-cohort claim is added.

## Failures retained and corrected

- Initial startup queried company 0 before it existed; changed the join wait
  to observe all companies before enforcing the one-human-company boundary.
- Default seed 20261021 and alternatives 1/2 exceeded the bounded route/pair
  search; seeds 3/4/5 were discovery-only trials (distances 56/90/110).
  Seed 6's naturally generated nearest pair has distance 37. These results
  remain in artifacts; selecting seed 6 does not establish a success rate.
- First seed-6 route `20261024T225224Z-f86c4e85` stalled after loading.
  Adjacent reciprocal curves were not enough: default `pf.forbid_90_deg=true`
  prohibits their transition. Search now tracks the previous piece and
  rejects crossing-track transitions without changing the game setting.
- `20261024T225832Z-8c968d3d` transported coal but its verifier waited for
  empty destination departures that the event seam does not emit. Its isolated
  server was stopped and failure retained. Verification now requires the
  third full source departure.
- Visible run `20261024T230214Z-8078b7dc` passed service but its mixed replay
  verifier assumed old endpoints included `engine_id`. Normalize only the
  old-layout non-applicable sentinels; immutable values still must match.
  Subsequent copied-world and final full gates pass.
- The macOS default graphical link missed CGL symbols. Disabling optional
  OpenGL package discovery builds the software Cocoa client. The attempted
  `OPTION_USE_OPENGL=OFF` was not a real CMake option.

All **206 Python tests** pass. Clean-engine configuration/schema-4,
purchase/schema-3 and sequence/schema-1/full-history regressions passed in
`20261024T225800Z-0e4410ff`, `20261024T225812Z-d72fb39e` and
`20261024T225817Z-46efdad0`. Patch 0017 was reverse-checked against the clean
fork; its branch and remote SHA were verified.
