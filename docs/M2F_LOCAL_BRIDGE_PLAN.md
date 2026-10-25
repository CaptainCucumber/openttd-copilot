# M2f plan — single-process local bridge

Status: **planned, 2026-10-24. Nothing in this document is implemented yet.**
Decision: [D032](DECISIONS.md#d032---host-the-native-bridge-in-the-single-player-game-process).

## Why

User requirement (2026-10-24): Copilot is for local games only; multiplayer is
not needed. If dropping it simplifies the product, do so.

Today every Copilot game is a dedicated server process plus a visible client
process that joins it, and the bridge rides on OpenTTD's authenticated Admin
connection. That topology was inherited from the stock GameScript/Admin spike
(M1); D013 replaced the gameplay adapter but kept the transport. It costs:

- two engine builds (dedicated + GUI) and two processes per game;
- client key allow-lists, Admin password, company-join waits, two ports;
- saves through the dedicated server's stdin console;
- no path to attach Copilot to a game the player opened themselves.

Target: **one visible OpenTTD process, one local endpoint.** The native
request/response semantics, COPL save chunk, journals, planners, budget rules
and MCP tools stay the same.

## Is it actually simpler?

Runtime and user experience: yes — one binary, one process, one port/token,
no client identity, no join wait. Engine code: slightly more, not less. We add
a small listener and must handle single-player command semantics that the
server path hid. The plan below accounts for that cost honestly.

## Source findings this design depends on

Checked against fork `2fb530eda610857329872eab1acaa9788de49f89`:

| Finding | Location | Consequence |
|---|---|---|
| Admin listener starts only in `NetworkServerStart`; admin sockets are polled only while `_networking` | `network.cpp` ~L911, `NetworkSend`, `NetworkGameLoop` | Single-player has no Admin endpoint; we need our own listener |
| `NetworkBackgroundLoop()` runs every `GameLoop` when `_network_available`, including paused and menu | `openttd.cpp` ~L1374 | Safe game-thread poll point for the new listener |
| Single-player `Command::Post` executes synchronously and invokes the callback before returning | `command_func.h` `Post`/`InternalPostBefore` | Operations reach a terminal state inside the request; audit post-`Post` state writes |
| Estimate-only mode applies when `_shift_pressed && IsLocalCompany()` unless `CommandFlag::NoEst` | `command.cpp` `InternalPostBefore` | None of the five `CMD_COPILOT_*` traits has `NoEst`; a player holding Shift would turn a mutation into an estimate and skip the callback, leaving a pending record |
| Posting while paused shows `STR_ERROR_NOT_ALLOWED_WHILE_PAUSED` to the player | `InternalPostBefore` | Check pause before admission and return a typed result |
| Failure popups require a non-zero `err_message`; Copilot posts use `Post(callback, ...)` (message 0) | `InternalPostResult` | No failure popups as long as message stays 0; success shows normal cost animation |
| `_frame_counter` only advances in network server/client loops | `network.cpp` L1246, `network_client.cpp` L226 | In single-player every completion/observation/event frame would be 0; switch to a tick counter that advances in all modes |
| Saves today: `send_console(server, 'save ...')` to the dedicated server's stdin | `tools/run_lifecycle_probe.py`, `native_play_session.py` | GUI process has no console channel; add a typed bounded save request |

## Design

### Engine

1. **Transport-neutral dispatcher.** Move the Copilot request handlers out of
   `ServerNetworkAdminSocketHandler` (~1,500 lines in `network_admin.cpp`)
   into `src/copilot_bridge.{h,cpp}`: `bytes request -> bytes response`,
   executed on the game thread. Payload layouts of request 11 / response 130
   stay byte-identical. The Admin handler becomes a thin adapter so existing
   probes keep working during transition.
2. **Local endpoint.** New `src/copilot_endpoint.{h,cpp}` using OpenTTD's TCP
   socket/`Packet` helpers:
   - bind `127.0.0.1` only; reject non-loopback peers; one connection at a time;
   - per-launch 32-byte random token from the isolated profile's private
     settings (the same secrets mechanism previously used for `admin_password`);
     constant-time compare; no token ⇒ endpoint disabled;
   - minimal hello: client sends protocol version + token, endpoint replies
     with bridge version and capabilities; then request/response frames
     reuse the existing Copilot payloads; bounded frame size; idle/oversize
     disconnect without partial writes;
   - polled from `NetworkBackgroundLoop()`; never executes on another thread.
   - default off. Only the launcher's isolated profile enables it.
3. **Single-player semantics.**
   - Refuse all requests while `_networking` (typed `MULTIPLAYER_UNSUPPORTED`).
     This build does not attempt desync-safe multiplayer use.
   - Refuse unless `_game_mode == GM_NORMAL` (typed `NO_ACTIVE_GAME` for menu,
     editor, generation, loading).
   - Mutations require `company_id == _local_company`; report `local_company`
     in identity. A company the player switched away from is refused.
   - Pause: reads allowed; mutations rejected **before admission** with typed
     `GAME_PAUSED`, so no history record is consumed and no popup appears.
   - Add `CommandFlag::NoEst` to all `CMD_COPILOT_*` traits.
   - Audit the post-`Post` `if (!accepted)` writes so a synchronous callback's
     terminal outcome (cost, error, created ID) is never overwritten.
   - Replace `_frame_counter` in Copilot code with `TimerGameTick::counter`
     (advances in all modes, saved with the game). Record the semantic change:
     frames are now game ticks and survive reload.
4. **Lifecycle requests** (bridge-only, not gameplay): `save` to a validated
   bare filename inside the profile save directory (no paths, no overwrite of
   other files) returning the written name after completion; `quit` for
   launcher-owned processes. No console, RCON or arbitrary command access.
5. **Protocol version 4.** Additive: hello/capabilities, `local_company`,
   `game_mode`, `paused`, tick-based frames, new typed results, save/quit.
   v3 request kinds keep their payloads. Admin transport keeps v1–v3 behavior
   until retired.

### Python

1. Split `admin_transport.py` into framing/handshake versus Copilot codec.
   New `LocalBridgeClient` reuses the codec with the token hello. No Admin
   password, update-frequency registration or welcome parsing.
2. `native_play_session.py`: launch one GUI process (`-v cocoa` visible or
   `-v null:ticks=…` headless) with the isolated profile; wait for endpoint
   readiness and `GM_NORMAL`; take company from `local_company`; save/quit
   via bridge requests. Remove client-key generation from the product path.
3. `native_mcp_server.py`, `game_chat.py`, planners, executors and journals:
   tool surface unchanged. Map `GAME_PAUSED` / `NO_ACTIVE_GAME` /
   `MULTIPLAYER_UNSUPPORTED` to honest tool errors ("game is paused; unpause
   to continue", etc.). Verification waits treat pause as suspended time.
4. Provenance: manifests hash one binary instead of server + client.

### Retirement

Keep the Admin adapter and server/client harness only until the M2f gate
passes on the local path. Then remove them from the product launcher and
record that existing probe scripts are historical (their evidence stays
valid for the revision they recorded). Dropping the dedicated build is a
separate, explicit step after the gate.

## Work packages

Execute in order; each ends at a checkable point.

| # | Package | Exit evidence | Suggested routing |
|---|---|---|---|
| F1 | Engine dispatcher refactor (no behavior change) | Clean build; existing Admin-path coal + bus gates still pass on the refactored binary | Sol, medium |
| F2 | Single-player semantics: `NoEst`, tick frames, pause/game-mode/multiplayer/local-company guards, post-`Post` audit | Unit-level source checks; engine builds; Admin regressions still pass | High-end review of the diff |
| F3 | Local endpoint + token hello + save/quit + protocol v4 | GUI build starts with endpoint only when token configured; loopback/token/oversize/second-connection refusals | Sol, medium |
| F4 | Python `LocalBridgeClient` + single-process session + codec split | All Python tests pass; new transport unit tests incl. bad token, typed refusals | Luna, medium |
| F5 | Real-engine M2f gate (see [acceptance](ACCEPTANCE.md#m2f-single-process-gate)) | Evidence JSON with binary/source hashes | Parent agent only |
| F6 | Switch `game_chat.py` / MCP to local path; actual Copilot build/inspect/save/close | Actual-host transcript hash; one visible process | Parent agent only |
| F7 | Retire server/client from product path; update guides, engine README, patch 0019 | Records updated; publication verified | Luna for docs; parent publishes |

## Risks

| Risk | Mitigation |
|---|---|
| Refactor silently changes a request's bytes | F1 must pass existing gates before any behavior change |
| Shift/pause/menu edge cases leave a pending record | Pre-admission checks + `NoEst`; explicit gate cases |
| Tick-frame semantics break Python freshness/epoch comparisons | Bump to v4; adjust and test comparisons; never mix v3 and v4 frames |
| Headless `null` video runs unpaced (faster than real time) | Record pacing in evidence; acceptance includes one visible paced run |
| Player and Copilot edit the same company simultaneously | Unchanged: per-operation revalidation and normal command validation already own this |
| GUI build without `OPTION_DEDICATED` lacks something tests relied on | Inventory probe dependencies in F4; keep dedicated build until F7 |

## Out of scope

Multiplayer support, attaching to the stock OpenTTD app, in-game chat UI,
Windows/Linux packaging, new transport modes or planner scope. Attaching to a
custom-build game the player started manually becomes possible after M2f but
is an M5 packaging decision, not part of this gate.
