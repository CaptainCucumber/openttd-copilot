# Custom OpenTTD engine

M2 uses a narrow fork of OpenTTD 15.3. The current engine branch is
[`copilot/m2d-industry-snapshot`](https://github.com/CaptainCucumber/OpenTTD/tree/copilot/m2d-industry-snapshot), commit
`211e780180c021b208a87d2612f4c24be9f743a6`. It descends from the M2d
tile commit `bf789a968cdf47ac54237a917402821d24e6dff6`, the M2c commit
`37f88cc03d88a99273297b2691f88c16f6926fc4`, earlier M2b/M2a commits,
and upstream `14ec60f248547d4d062a1160f0fc26d742319888`.

All twelve commits are retained as mail patches in [`patches/`](patches/). Apply
0001 through 0012 in order to the upstream revision if not using the fork branch.

## Build

```sh
git clone --branch copilot/m2d-industry-snapshot \
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
vehicle-event requests. An additive read-only request returns up to 32 contiguous
tile records per page with tile validity/type, ownership, slope, height, and
plain/crossing rail geometry. A later fix treats house and industry tiles as
unowned, avoiding an OpenTTD owner-lookup assertion. A second read-only request
returns up to 16 industry IDs, types, anchor tiles, and produced/accepted cargo
IDs per page. See [tile probe instructions](../docs/NATIVE_TILE_PROBE.md),
[industry probe instructions](../docs/NATIVE_INDUSTRY_PROBE.md), and the
[industry report](../docs/M2D_INDUSTRY_REPORT.md).
An additional read-only request returns up to eight industries per page with
their UTF-8 cached name, explicit truncation marker, `TileArea` width/height,
anchor, and cargo lists. The rectangle bounds the industry location but does
not claim that every enclosed tile is occupied. See the
[industry details report](../docs/M2D_INDUSTRY_DETAILS_REPORT.md).
Another additive query returns up to 16 company-specific train engine records
per page with buildability, rail/cargo compatibility, default capacity, and
prices; see the [catalog report](../docs/M2D_RAIL_CATALOG_REPORT.md) and
[probe](../docs/NATIVE_RAIL_CATALOG_PROBE.md).
Read-only asset pages report existing company rail station platforms, current
acceptance masks, and depots. A separate bounded vehicle-pool scan reports
owned train consist parts and their links, cargo, and capacity. See the
[assets report](../docs/M2D_RAIL_ASSETS_REPORT.md) and
[train-parts report](../docs/M2D_TRAIN_PARTS_REPORT.md). A separate bounded
read-only request reports up to 16 engine-decoded orders for an explicit
primary train, including type, destination, load/unload policy, and non-stop
flags. Pages are frame-stamped and do not prove route reachability. See the
[train-orders report](../docs/M2D_TRAIN_ORDERS_REPORT.md) and
[probe instructions](../docs/NATIVE_TRAIN_ORDERS_PROBE.md).
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
