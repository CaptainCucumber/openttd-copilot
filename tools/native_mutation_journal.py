"""Durable external journal for the first native Copilot mutation.

The journal is deliberately a one-operation state machine.  A request must be
durable before the caller sends it, and an ambiguous response never becomes
permission to replay it automatically.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Mapping


SCHEMA = 1
_UINT64_MAX = (1 << 64) - 1
_TERMINAL_STATES = {2: "completed", 3: "rejected"}


class JournalError(RuntimeError):
    """The journal or a value supplied to it violates the recovery contract."""


class JournalWriteError(JournalError):
    """A journal write failed and this instance is no longer writable."""


def _integer(value: Any, name: str, *, maximum: int | None = None) -> int:
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        raise JournalError(f"invalid {name}")
    return value


def normalize_head(value: Any) -> tuple[int, int] | None:
    """Return a native operation identity as ``(hi, lo)`` or ``None``."""

    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"hi", "lo"}:
        raise JournalError("invalid native journal head")
    return (
        _integer(value["hi"], "native journal head hi", maximum=_UINT64_MAX),
        _integer(value["lo"], "native journal head lo", maximum=_UINT64_MAX),
    )


def _stored_head(value: tuple[int, int] | None) -> dict[str, int] | None:
    if value is None:
        return None
    return {"hi": value[0], "lo": value[1]}


def normalize_position(identity: Mapping[str, Any]) -> tuple[str, int, tuple[int, int] | None]:
    """Validate and normalize the persisted fields in a native identity reply."""

    if not isinstance(identity, Mapping):
        raise JournalError("invalid native identity")
    world = identity.get("world_id", identity.get("world"))
    if not isinstance(world, str) or not world:
        raise JournalError("invalid native world identity")
    sequence = _integer(identity.get("sequence"), "native journal sequence")
    head = normalize_head(identity.get("head"))
    if (sequence == 0) != (head is None):
        raise JournalError("native journal sequence and head are inconsistent")
    return world, sequence, head


def _position_record(position: tuple[str, int, tuple[int, int] | None]) -> dict[str, Any]:
    world, sequence, head = position
    return {"world": world, "sequence": sequence, "head": _stored_head(head)}


def _operation_id(request: Mapping[str, Any]) -> tuple[int, int]:
    for key in ("operation", "operation_id", "op"):
        if key in request:
            operation = request[key]
            if isinstance(operation, Mapping) and "id" in operation:
                operation = operation["id"]
            result = normalize_head(operation)
            if result is None:
                break
            return result
    raise JournalError("mutation request has no valid operation identity")


def _copy_json_object(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise JournalError(f"{name} must be an object")
    result = copy.deepcopy(dict(value))
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise JournalError(f"{name} is not valid JSON") from exc
    return result


def _operation_reply(reply: Mapping[str, Any]) -> Mapping[str, Any]:
    operation = reply.get("operation", reply)
    if not isinstance(operation, Mapping):
        raise JournalError("invalid operation reply")
    return operation


def _reply_state(reply: Mapping[str, Any]) -> str | None:
    operation = _operation_reply(reply)
    state_name = reply.get("state_name", operation.get("state_name"))
    if isinstance(state_name, str):
        normalized = state_name.lower().replace("-", "_")
        if normalized in {"completed", "rejected", "operation_not_found", "not_found"}:
            return "operation_not_found" if normalized in {"operation_not_found", "not_found"} else normalized
    state = reply.get("state", operation.get("state"))
    if type(state) is int:
        return _TERMINAL_STATES.get(state)
    status = reply.get("status")
    if isinstance(status, str) and status.lower().replace("-", "_") in {
        "operation_not_found", "not_found"
    }:
        return "operation_not_found"
    return None


class NativeMutationJournal:
    """An atomic, single-operation recovery journal.

    Construct with ``identity`` to create a new journal, or omit it to reopen
    an existing journal.  Once a write fails, mutation methods remain disabled
    on this object; reopening is required even if replacement may have happened.
    """

    def __init__(self, path: str | os.PathLike[str], identity: Mapping[str, Any] | None = None):
        self.path = Path(path)
        self._writable = True
        if self.path.exists():
            self.data = self._load()
            if identity is not None and self.classify_position(identity) != "current":
                raise JournalError("native identity does not match existing journal")
        elif identity is None:
            raise JournalError("journal does not exist")
        else:
            self.data = {
                "schema": SCHEMA,
                "position": _position_record(normalize_position(identity)),
                "operation": None,
            }
            self._write(self.data)

    @classmethod
    def create(cls, path: str | os.PathLike[str], identity: Mapping[str, Any]) -> "NativeMutationJournal":
        if Path(path).exists():
            raise JournalError("journal already exists")
        return cls(path, identity)

    @classmethod
    def open(cls, path: str | os.PathLike[str]) -> "NativeMutationJournal":
        return cls(path)

    @property
    def writable(self) -> bool:
        return self._writable

    @property
    def position(self) -> tuple[str, int, tuple[int, int] | None]:
        return normalize_position(self.data["position"])

    @property
    def operation(self) -> dict[str, Any] | None:
        return copy.deepcopy(self.data["operation"])

    def _load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise JournalError("cannot read mutation journal") from exc
        if not isinstance(value, dict) or value.get("schema") != SCHEMA:
            raise JournalError("unsupported mutation journal schema")
        if set(value) != {"schema", "position", "operation"}:
            raise JournalError("invalid mutation journal shape")
        normalize_position(value["position"])
        operation = value["operation"]
        if operation is not None:
            if not isinstance(operation, dict) or operation.get("state") not in {
                "pending", "completed", "rejected", "uncertain"
            }:
                raise JournalError("invalid journaled operation")
            request = operation.get("request")
            if not isinstance(request, dict):
                raise JournalError("journaled operation has no request")
            _operation_id(request)
            if operation["state"] in {"completed", "rejected"} and not isinstance(operation.get("reply"), dict):
                raise JournalError("terminal journaled operation has no reply")
            if operation["state"] == "uncertain" and not isinstance(operation.get("reason"), str):
                raise JournalError("uncertain journaled operation has no reason")
        return value

    def _require_writable(self) -> None:
        if not self._writable:
            raise JournalWriteError("journal writes are disabled; reopen and reconcile")

    def _write(self, value: dict[str, Any]) -> None:
        self._require_writable()
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except BaseException as exc:
            self._writable = False
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise JournalWriteError("mutation journal write failed; reopen and reconcile") from exc
        self.data = value

    def classify_position(self, identity: Mapping[str, Any]) -> str:
        remote = normalize_position(identity)
        local = self.position
        if remote[0] != local[0]:
            return "changed_world"
        if remote[1] < local[1]:
            return "older_save"
        if remote[1] > local[1]:
            return "ahead"
        if remote[2] != local[2]:
            return "diverged"
        return "current"

    # Concise alias for callers modelled after the earlier lifecycle fixture.
    classify = classify_position

    def record_pending(self, request: Mapping[str, Any]) -> bool:
        """Durably record intent before send; return False for an exact replay."""

        self._require_writable()
        request_copy = _copy_json_object(request, "mutation request")
        operation_id = _operation_id(request_copy)
        existing = self.data["operation"]
        if existing is not None:
            existing_id = _operation_id(existing["request"])
            if existing_id == operation_id and existing["request"] == request_copy:
                return False
            if existing_id == operation_id:
                raise JournalError("operation identity conflict")
            raise JournalError("journal already contains an operation")

        # If supplied, these request preconditions must bind to the durable
        # native position.  Alternate field names match the wire vocabulary.
        world, sequence, head = self.position
        requested_world = request_copy.get("world_id", request_copy.get("world"))
        if requested_world is not None and requested_world != world:
            raise JournalError("mutation request is bound to a different world")
        expected = request_copy.get("expect_sequence", request_copy.get("sequence"))
        if expected is not None and (type(expected) is not int or expected != sequence):
            raise JournalError("mutation request is bound to a stale sequence")
        if "expect_head" in request_copy and normalize_head(request_copy["expect_head"]) != head:
            raise JournalError("mutation request is bound to a stale head")

        value = copy.deepcopy(self.data)
        value["operation"] = {"state": "pending", "request": request_copy}
        self._write(value)
        return True

    # Compatibility with the earlier fixture's vocabulary.
    pending = record_pending

    def _mark_uncertain(self, reason: str, reply: Mapping[str, Any] | None = None) -> str:
        value = copy.deepcopy(self.data)
        value["operation"]["state"] = "uncertain"
        value["operation"]["reason"] = reason
        if reply is not None:
            value["operation"]["reply"] = _copy_json_object(reply, "operation reply")
        self._write(value)
        return "uncertain"

    def reconcile(
        self,
        identity: Mapping[str, Any] | None,
        reply: Mapping[str, Any] | None = None,
        *,
        transport_outcome: str = "received",
    ) -> str:
        """Persist a proven terminal reply or an explicit uncertain outcome.

        ``unknown`` transport outcome, operation-not-found, and a remote
        position that did not advance are deliberately terminal for automatic
        recovery: the operation becomes ``uncertain`` and cannot be replayed.
        """

        self._require_writable()
        local_operation = self.data["operation"]
        if local_operation is None:
            raise JournalError("no operation to reconcile")
        if local_operation["state"] != "pending":
            if local_operation["state"] in {"completed", "rejected", "uncertain"}:
                return local_operation["state"]
            raise JournalError("invalid local operation state")

        if transport_outcome == "unknown":
            return self._mark_uncertain("transport_outcome_unknown", reply)
        if transport_outcome != "received":
            raise JournalError("invalid transport outcome")
        if identity is None:
            return self._mark_uncertain("remote_position_unavailable", reply)

        remote = normalize_position(identity)
        local = self.position
        state = _reply_state(reply) if reply is not None else None
        if state == "operation_not_found":
            return self._mark_uncertain("operation_not_found", reply)
        operation_id = _operation_id(local_operation["request"])
        reply_id = None if reply is None else reply.get("operation")
        if isinstance(reply_id, Mapping) and "id" in reply_id:
            reply_id = reply_id["id"]
        if reply_id is not None and normalize_head(reply_id) != operation_id:
            raise JournalError("operation reply identity conflicts with pending request")

        if state == "rejected" and remote == local and reply is not None:
            value = copy.deepcopy(self.data)
            value["operation"] = {
                "state": "rejected",
                "request": copy.deepcopy(local_operation["request"]),
                "reply": _copy_json_object(reply, "operation reply"),
            }
            self._write(value)
            return "rejected"

        # The operation did not advance this world's sequence.  A mismatched
        # head at the same sequence is also unsafe, but it still cannot prove
        # that the pending mutation was absent and replayable.
        if remote[0] == local[0] and remote[1] == local[1]:
            return self._mark_uncertain("remote_position_did_not_advance", reply)

        expected = (local[0], local[1] + 1, operation_id)
        if remote != expected:
            raise JournalError(f"remote position is {self.classify_position(identity)}; manual reconciliation required")
        if state not in {"completed", "rejected"} or reply is None:
            return self._mark_uncertain("terminal_operation_reply_unavailable", reply)

        reply_operation = _operation_reply(reply)
        reply_id_value = reply_operation.get("id", reply_operation.get("operation_id"))
        if reply_id_value is not None and normalize_head(reply_id_value) != operation_id:
            raise JournalError("operation reply identity conflicts with pending request")

        value = copy.deepcopy(self.data)
        value["operation"] = {
            "state": state,
            "request": copy.deepcopy(local_operation["request"]),
            "reply": _copy_json_object(reply, "operation reply"),
        }
        value["position"] = _position_record(remote)
        self._write(value)
        return state


# The short name is convenient for probes while preserving a specific public
# name for integration code.
Journal = NativeMutationJournal
