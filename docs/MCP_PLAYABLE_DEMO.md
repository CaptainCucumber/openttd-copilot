# Playable MCP demo

The local stdio server exposes a small AI-facing flow for trying the project
inside a disposable OpenTTD 15.3 world. It does not connect to a normal save or
use a model/API key itself: the MCP host supplies conversation and model
access, while the local demo owns the narrow action validation and game
fixture.

## Configure an MCP host

Register this server in the MCP host's local server configuration, using the
absolute path to this checkout:

```json
{
  "mcpServers": {
    "openttd-copilot-demo": {
      "command": "python3",
      "args": ["-B", "/absolute/path/to/openttd-copilot/tools/mcp_server.py"]
    }
  }
}
```

The demo defaults to `/Applications/OpenTTD.app/Contents/MacOS/openttd`, seed
20261021, a visible game window, and a 600-second service deadline. Override
those defaults in the host's `args` if required:

```json
{
  "mcpServers": {
    "openttd-copilot-demo": {
      "command": "python3",
      "args": [
        "-B",
        "/absolute/path/to/openttd-copilot/tools/mcp_server.py",
        "--binary",
        "/Applications/OpenTTD.app/Contents/MacOS/openttd",
        "--seed",
        "20261021",
        "--deadline",
        "600"
      ]
    }
  }
}
```

Restart or reload the MCP host after changing its configuration. On macOS the
server requires Python 3 and the installed OpenTTD 15.3 app/resources used by
the existing probe.

## Use it

Ask the connected AI to:

1. Call `open_demo_map`. This launches a new disposable map and returns a job
   ID plus the coal businesses observed on that map. The game opens before the
   route is built; the listed businesses are informational and are not the
   endpoints used by this controlled fixture.
2. Call `build_coal_railway` with `cargo: "coal"`, an origin identifying a
   coal mine, a destination identifying a power station/plant, and
   `wait_for_full_load: true`. These names validate the supported request
   shape but do not select specific map industries.
3. Poll `get_build_status` with the returned job ID. Successful completion
   means the existing real-engine fixture observed two full-load departures
   and two deliveries. The completed save is opened for inspection.

The build tool call is the authorization to run this bounded fixture. Do not
send arbitrary commands or unsupported cargo/mode requests; the local server
rejects them. Keep the MCP process running until the job reaches a terminal
status. Raw run logs and saves are retained under ignored `artifacts/`.

## Important scope

This is a **playable controlled demo, not the promised general railway
builder**. The fixture creates a test coal mine and power station after the
build request and constructs a prevalidated straight route. The AI cannot
select arbitrary existing businesses, ask for different cargo, route around
obstacles, or build on a normal map. It does not use the native bridge for the
multi-command railway job. The successful train service and cost/operation
evidence come from the disposable GameScript fixture, not from native
end-to-end construction.

The next engineering gate is to resolve existing industries from the opened
world, find and validate station/route candidates, and replace fixture-only
construction with a bounded execution path whose partial outcomes and
spending are reported honestly. M2 complete-route acceptance remains open.
