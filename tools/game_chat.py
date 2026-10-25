#!/usr/bin/env python3
"""Launch actual Copilot conversation with the local native game tools."""

import argparse
import json
from pathlib import Path
import shutil
import secrets
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "tools/native_mcp_server.py"


def launch_command(copilot, *, seed=None, save=None, visible=True, map_style="normal"):
    if map_style not in ("normal", "railway-fixture"):
        raise ValueError("map_style must be normal or railway-fixture")
    if seed is None:
        seed = secrets.randbits(32) if map_style == "normal" else 6
    if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF:
        raise ValueError("seed must be uint32")
    args = ["-B", str(SERVER), "--seed", str(seed), "--map-style", map_style]
    if save is not None:
        save = Path(save).expanduser().resolve()
        if save.suffix != ".sav" or not save.is_file():
            raise ValueError("save must identify an existing .sav file")
        args += ["--save", str(save)]
    if not visible:
        args.append("--no-show")
    config = {"mcpServers": {"openttd-copilot-native": {
        "type": "local", "command": sys.executable, "args": args,
        "tools": ["open_native_map", "inspect_native_game", "plan_native_railway",
                  "build_native_railway", "plan_native_bus", "build_native_bus",
                  "get_native_status", "close_native_map"],
        "timeout": 180000,
    }}}
    prompt = (
        "I want to play OpenTTD with you as my conversational game companion. "
        + ("Inspect the map loaded from my copied save. " if save is not None else
           "Open a new isolated native map and inspect its live state. ")
        + "Tell me briefly what is there and what we can discuss or compare. "
          "Do not construct anything yet. Do not require rigid command syntax. "
          "Be explicit about observations you cannot currently read."
    )
    return [str(copilot), "-C", str(ROOT), "--agent", "openttd",
            "--no-custom-instructions", "--disable-builtin-mcps",
            "--additional-mcp-config", json.dumps(config),
            "--deny-tool=shell", "--deny-tool=write",
            "--excluded-tools=shell", "--excluded-tools=bash", "--excluded-tools=sql",
            "--excluded-tools=skill", "--excluded-tools=read", "--excluded-tools=edit",
            "--excluded-tools=write",
            "--allow-tool=openttd-copilot-native(inspect_native_game)",
            "--allow-tool=openttd-copilot-native(plan_native_railway)",
            "--allow-tool=openttd-copilot-native(plan_native_bus)",
            "--allow-tool=openttd-copilot-native(get_native_status)",
            "-i", prompt]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--map-style", choices=("normal", "railway-fixture"), default="normal")
    parser.add_argument("--save")
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    copilot = shutil.which("copilot")
    if copilot is None:
        parser.error("GitHub Copilot CLI is required; install it and sign in with copilot /login.")
    try:
        command = launch_command(copilot, seed=args.seed, save=args.save, visible=not args.no_show,
                                 map_style=args.map_style)
    except ValueError as exc:
        parser.error(str(exc))
    print("Starting AI game chat using your signed-in Copilot CLI account.", flush=True)
    print("This uses your Copilot allowance. No separate provider key or global MCP change is made.", flush=True)
    print("Ask normally about the game; advice/inspection never authorizes construction.", flush=True)
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
