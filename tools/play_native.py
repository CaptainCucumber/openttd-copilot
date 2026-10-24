#!/usr/bin/env python3
"""Open an isolated game with a deliberately constrained local text interface."""

import argparse
import re
import time

from mcp_server import ToolError
from native_mcp_server import NativeJob
from native_play_session import CLIENT_BINARY, SERVER_BINARY


def parse_request(text, discovery, job_id):
    """Bind an explicit supported sentence to observed IDs; never guess intent."""
    match = re.fullmatch(
        r"build (?:a )?coal railway from (.+?) to (.+?); full load; budget ([0-9]+); reserve ([0-9]+)",
        text.strip(), re.IGNORECASE)
    if match is None:
        raise ToolError("Use: build coal railway from SOURCE to DESTINATION; full load; budget 50000; reserve 10000")

    def bind(name):
        records = discovery["industries"]
        matches = [record["industry_id"] for record in records
                   if str(record["industry_id"]) == name or record["name"].casefold() == name.casefold()]
        if len(matches) != 1:
            raise ToolError(f"Business {name!r} is not one uniquely observed name or ID.")
        return matches[0]

    return {"job_id": job_id, "source_id": bind(match[1]), "destination_id": bind(match[2]),
            "construction_cap": int(match[3]), "operating_reserve": int(match[4]),
            "cargo": "coal", "wait_for_full_load": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=6)
    parser.add_argument("--save")
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.seed <= 0xFFFFFFFF:
        parser.error("--seed must be uint32")
    job = NativeJob(SERVER_BINARY, CLIENT_BINARY, 900, args.seed, not args.no_show)
    try:
        opened = job.open({"save": args.save} if args.save else {})
        print("OpenTTD native alpha: isolated profile, existing businesses, one railway per session.")
        print("This local parser is model-free; use native_mcp_server.py for an AI client.")
        print("Only flat clear unowned land, standard temperate coal, at most 50 rail tiles.")
        print("No automatic borrowing, clearing, rollback, or retry of partial/uncertain work.")
        print("Listed pairs are observed businesses, not confirmed buildable routes; choose a nearby pair.")
        for pair in opened["business_pairs"]:
            print(f"{pair['source_id']}: {pair['source']} -> {pair['destination_id']}: "
                  f"{pair['destination']} (anchor distance {pair['distance']})")
        if opened["business_pairs"]:
            pair = opened["business_pairs"][0]
            print(f"Try: build coal railway from {pair['source_id']} to {pair['destination_id']}; "
                  "full load; budget 50000; reserve 10000")
        print("Commands: status, save, quit. Keep this terminal open while playing.", flush=True)
        while True:
            try:
                text = input("> ").strip()
            except EOFError:
                break
            try:
                if text.casefold() == "quit":
                    break
                if text.casefold() == "status":
                    print(job.refresh({"job_id": opened["job_id"]}))
                    continue
                if text.casefold() == "save":
                    job.session.deadline = time.monotonic() + 20
                    print(job.session.save("player-manual"))
                    job.session.write()
                    continue
                payload = parse_request(text, opened, opened["job_id"])
                state = job.build(payload)
                previous = None
                while state["status"] in ("planning", "building", "verifying"):
                    if state["status"] != previous:
                        print(state["status"], flush=True)
                        previous = state["status"]
                    time.sleep(0.5)
                    state = job.refresh({"job_id": opened["job_id"]})
                if state["status"] == "operating":
                    result = state["result"]
                    print(f"Train {result['vehicle']} verified two full-load deliveries. "
                          f"Construction cost {result['spent']}; game remains open.")
                    print(f"Save: {result['completed_save']}")
                elif state["status"] == "rejected":
                    print(f"Not built: {state.get('failure')}. No construction was attempted. "
                          "You can submit a different request on this map. "
                          f"Details: {state['artifact_dir']}.")
                else:
                    print(f"Not completed: {state.get('failure')}. Inspect {state['artifact_dir']}. "
                          "Partial work is retained, not automatically undone or retried.")
            except (ToolError, ValueError) as exc:
                print(exc)
    finally:
        job.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
