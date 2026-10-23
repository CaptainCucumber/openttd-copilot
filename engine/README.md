# Custom OpenTTD engine

M2 uses a narrow fork of OpenTTD 15.3. The current engine branch is
[`CaptainCucumber/OpenTTD:copilot/m2c-vehicle-observation`](https://github.com/CaptainCucumber/OpenTTD/tree/copilot/m2c-vehicle-observation),
commit `37f88cc03d88a99273297b2691f88c16f6926fc4`. It extends the M2b
commit `8b8f3d7bad64fb01fc2a216b35e8070be95f51d8`, itself based on M2a and upstream
`14ec60f248547d4d062a1160f0fc26d742319888`.

All three commits are retained as mail patches in [`patches/`](patches/). Apply
0001, 0002, then 0003 to the upstream revision if not using the fork branch.

## Build

```sh
git clone --branch copilot/m2c-vehicle-observation \
  https://github.com/CaptainCucumber/OpenTTD.git vendor/openttd-copilot-engine
cmake -S vendor/openttd-copilot-engine -B build/openttd-m2a \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DOPTION_DEDICATED=ON \
  -DOPTION_USE_ASSERTS=ON
cmake --build build/openttd-m2a --target openttd -j 8
```

The M2 binary is a dedicated build. The probes stage language, compatibility,
and base-set resources from the installed OpenTTD 15.3 application into a
disposable profile. It never uses the normal profile for execution.

## Boundary

Protocol version 3 keeps the authenticated, loopback-only Admin boundary and
includes identity, one typed single-rail mutation, operation-status, and paged
vehicle-event requests.
The wrapper posts through OpenTTD's normal command pipeline and rejects costs
above the supplied cap before execution. A versioned COPL save chunk stores
world/operation identity and the terminal outcome; an external fsynced journal
records intent before send. The first slice allows one operation on a flat,
clear tile per world. It is not a general command transport or route builder.
See [M2b probe instructions](../docs/NATIVE_MUTATION_PROBE.md) and
[report](../docs/M2B_REPORT.md) for tested and untested recovery boundaries.
The runtime-only event ring reports train station departures and accepted
industry deliveries with vehicle identity. It declares gaps on overflow and
changes its runtime epoch on world reload. See [M2c probe instructions](../docs/NATIVE_VEHICLE_PROBE.md)
and [report](../docs/M2C_REPORT.md).
