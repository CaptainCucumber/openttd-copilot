# M1 adapter report

Status: complete on 2026-10-22 for OpenTTD 15.3. Production adapter choice:
**a narrow native OpenTTD bridge behind the deterministic Python service**.

## Exit evidence

| M1 check | Result | Evidence |
|---|---|---|
| Human company and live world observation | Pass in isolated worlds | [Control probe](CONTROL_PROBE.md) |
| Test, build, cost, ownership, and rejection readback | Pass | [Control evidence](evidence/2026-10-21-control-probe.json) |
| Purchase/order/readback and delivery attribution determination | Pass as a capability determination | [Vehicle evidence](evidence/2026-10-22-vehicle-probe.json); delivery attribution is only by exclusion in the isolated one-train fixture |
| 10,000 observations and 100 commands over five runs | Pass | [Throughput evidence](evidence/2026-10-22-throughput-probe.json) |
| Save/reload, lost response, duplicate purchase prevention, older/new world | Pass within declared fixtures | [Lifecycle evidence](evidence/2026-10-22-lifecycle-probe.json) and vehicle evidence |
| Pause, copied existing save, and GameScript coexistence boundary | Pass as a capability/limitation determination | [Environment evidence](evidence/2026-10-22-environment-probe.json) |
| Evidence-based adapter selection | Complete | [D013](DECISIONS.md#d013--select-a-narrow-native-openttd-bridge) |

## What stock OpenTTD proved

GameScript plus Admin is fast enough for the measured simple workload and uses
normal company-context command validation. The fixtures demonstrated bounded
transport, authoritative costs and ownership, pause refusal, reconnect and
save identity, duplicate-purchase prevention, and an operating one-train coal
service. These fixtures remain useful regression tests.

## Why stock is not the production adapter

The representative existing save loaded successfully from an isolated copy,
but its saved no-script state overrode the configured Copilot GameScript; no
Copilot response arrived while Admin stayed responsive. A save containing a
different GameScript likewise resumed that saved script, not Copilot, even
with both packages installed. OpenTTD has one GameScript slot. Replacing the
scenario script is not acceptable coexistence and cannot be an installation
step for ordinary saves.

Stock CargoMonitor also does not supply vehicle identity. The current delivery
gate is valid only because the disposable world contains exactly one train.
That is insufficient for an assistant operating in a real company.

## Selected boundary

The external service continues to own language interpretation, deterministic
planning, budgets, operation IDs, recovery policy, and verification. The
custom engine component remains deliberately thin:

- versioned, authenticated, loopback-only Copilot Admin messages;
- bounded typed observations and mutations, never arbitrary model code;
- game-thread execution through OpenTTD's normal command pipeline;
- authoritative cost and asset readback;
- vehicle-tagged loading, departure, and delivery observations;
- versioned world/operation state that can be reconciled after reconnect/load;
- independence from the scenario GameScript slot.

This choice does not close the mutation-before-journal/save crash window or
prove custom-save compatibility. Those remain explicit M2/M3 tests. All bridge
development uses generated worlds or copied saves.

## M2 entry point

Implement the smallest vertical bridge slice first: identify world/company on
a copied existing save while a foreign GameScript continues running, then
test/execute/read back one capped rail command. Add vehicle-tagged cargo events
before moving the complete coal job from the stock fixture to the bridge.
