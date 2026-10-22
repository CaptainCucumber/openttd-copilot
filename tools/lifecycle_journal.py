"""Small durable external journal for the S3a experiment, not a job executor.

Persist intent before sending, and compare the loaded game's journal position
before binding a new mutation session. Never treat an absent outcome as failure.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path


class JournalError(RuntimeError):
    pass


def position(reply: dict) -> dict:
    world, seq, head = reply.get("world"), reply.get("seq"), reply.get("head")
    if not isinstance(world, str) or not world or type(seq) is not int or seq < 0:
        raise JournalError("invalid remote world position")
    if (seq == 0 and head is not None) or (seq > 0 and (not isinstance(head, str) or not head)):
        raise JournalError("invalid remote journal head")
    return {"world": world, "seq": seq, "head": head}


class Journal:
    def __init__(self, path: Path, initial: dict | None = None):
        self.path = path
        self._writable = True
        if path.exists():
            self.data = json.loads(path.read_text())
            if self.data.get("schema") != 1:
                raise JournalError("unsupported journal schema")
            position(self.data["position"])
        elif initial is not None:
            self.data = {"schema": 1, "position": position(initial), "operations": {}}
            self._write()
        else:
            raise JournalError("journal does not exist")

    def _require_writable(self):
        if not self._writable:
            raise JournalError("journal write failed; reopen and reconcile before continuing")

    def _write(self, data=None):
        self._require_writable()
        data = self.data if data is None else data
        temporary = self.path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except BaseException:
            # Replacement might already have happened. Never let an in-memory
            # retry stand in for durable intent after an uncertain disk write.
            self._writable = False
            raise
        self.data = data

    def classify(self, reply: dict) -> str:
        remote = position(reply)
        local = self.data["position"]
        if remote["world"] != local["world"]:
            return "changed_world"
        if remote["seq"] < local["seq"]:
            return "older_save"
        if remote["seq"] > local["seq"]:
            return "ahead_requires_reconciliation"
        if remote["head"] != local["head"]:
            return "diverged"
        return "current"

    def pending(self, request: dict):
        self._require_writable()
        op = request["op"]
        if request["world"] != self.data["position"]["world"]:
            raise JournalError("cannot record operation in a different world")
        if request["expect_seq"] != self.data["position"]["seq"]:
            raise JournalError("cannot record operation at a stale sequence")
        existing = self.data["operations"].get(op)
        if existing:
            if existing["request"] != request:
                raise JournalError("operation identity conflict")
            return
        if any(item["state"] == "pending" for item in self.data["operations"].values()):
            raise JournalError("reconcile pending operation before sending another")
        data = copy.deepcopy(self.data)
        data["operations"][op] = {"state": "pending", "request": copy.deepcopy(request)}
        self._write(data)

    def complete(self, op: str, remote: dict, outcome: dict):
        self._require_writable()
        item = self.data["operations"][op]
        target = position(remote)
        expected = item["request"]["expect_seq"] + 1
        if target != {"world": item["request"]["world"], "seq": expected, "head": op}:
            raise JournalError("unexpected remote position; reconciliation required")
        if (outcome.get("state") != "completed" or outcome.get("op") != op
                or type(outcome.get("seq")) is not int or outcome["seq"] != expected):
            raise JournalError("operation was not proven complete")
        if item["state"] == "completed":
            if item["outcome"] != outcome:
                raise JournalError("completed outcome changed")
            return
        if item["state"] != "pending":
            raise JournalError("operation is not pending")
        if self.data["position"]["seq"] != expected - 1:
            raise JournalError("refusing to move journal backwards or skip work")
        data = copy.deepcopy(self.data)
        data["operations"][op].update(state="completed", outcome=copy.deepcopy(outcome))
        data["position"] = target
        self._write(data)
