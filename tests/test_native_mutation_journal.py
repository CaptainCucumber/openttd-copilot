from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from native_mutation_journal import (  # noqa: E402
    Journal,
    JournalError,
    JournalWriteError,
    normalize_head,
    normalize_position,
)


ZERO = {"world": "world-a", "sequence": 0, "head": None}
OP1 = {"hi": 10, "lo": 20}
ONE = {"world": "world-a", "sequence": 1, "head": OP1}


class NativeMutationJournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "mutation.json"
        self.journal = Journal.create(self.path, ZERO)
        self.request = {
            "world": "world-a",
            "expect_sequence": 0,
            "expect_head": None,
            "operation": OP1,
            "kind": "build_rail",
            "tile": 123,
        }

    def test_native_position_is_strict_and_uses_head_tuple(self):
        self.assertEqual(("world-a", 1, (10, 20)), normalize_position(ONE))
        self.assertEqual((10, 20), normalize_head(OP1))
        for invalid in (
            {"world": "world-a", "sequence": True, "head": None},
            {"world": "world-a", "sequence": 0, "head": OP1},
            {"world": "world-a", "sequence": 1, "head": None},
            {"world": "world-a", "sequence": 1, "head": {"hi": 1}},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(JournalError):
                normalize_position(invalid)

    def test_classifies_all_remote_positions(self):
        self.assertEqual("current", self.journal.classify_position(ZERO))
        self.assertEqual("changed_world", self.journal.classify_position({**ZERO, "world": "world-b"}))
        self.assertEqual("ahead", self.journal.classify_position(ONE))

        self.journal.record_pending(self.request)
        self.journal.reconcile(ONE, {"operation": {"state_name": "completed", "id": OP1}})
        self.assertEqual("older_save", self.journal.classify_position(ZERO))
        self.assertEqual(
            "diverged",
            self.journal.classify_position({"world": "world-a", "sequence": 1, "head": {"hi": 9, "lo": 9}}),
        )

    def test_pending_is_durable_before_send_and_exact_duplicate_is_idempotent(self):
        self.assertTrue(self.journal.record_pending(self.request))
        reopened = Journal.open(self.path)
        self.assertEqual("pending", reopened.operation["state"])
        self.assertEqual(self.request, reopened.operation["request"])
        self.assertFalse(reopened.record_pending(self.request))

    def test_same_operation_conflict_and_second_operation_are_rejected(self):
        self.journal.record_pending(self.request)
        with self.assertRaisesRegex(JournalError, "identity conflict"):
            self.journal.record_pending({**self.request, "tile": 124})
        with self.assertRaisesRegex(JournalError, "already contains"):
            self.journal.record_pending({**self.request, "operation": {"hi": 10, "lo": 21}})

    def test_reconciles_named_completion_and_numeric_rejection(self):
        self.journal.record_pending(self.request)
        reply = {"operation": {"state_name": "completed", "id": OP1, "cost": 90}}
        self.assertEqual("completed", self.journal.reconcile(ONE, reply))
        reopened = Journal.open(self.path)
        self.assertEqual("completed", reopened.operation["state"])
        self.assertEqual(("world-a", 1, (10, 20)), reopened.position)
        self.assertEqual("completed", reopened.reconcile(ONE, reply))

        other_path = self.path.with_name("rejected.json")
        rejected = Journal.create(other_path, ZERO)
        rejected.record_pending(self.request)
        self.assertEqual("rejected", rejected.reconcile(ONE, {"operation": {"state": 3, "id": OP1}}))
        self.assertEqual("rejected", Journal.open(other_path).operation["state"])

    def test_reconciles_native_transport_reply_and_zero_cost_rejection(self):
        identity = {"world_id": "world-a", "sequence": 0, "head": None}
        journal = Journal.create(self.path.with_name("transport.json"), identity)
        journal.record_pending({**self.request, "world_id": "world-a"})
        completed = {"world_id": "world-a", "sequence": 1, "head": OP1,
                     "operation": OP1, "state": 2, "state_name": "completed", "actual_cost": 90}
        self.assertEqual("completed", journal.reconcile(completed, completed))

        rejected = Journal.create(self.path.with_name("rejected-current.json"), identity)
        rejected.record_pending(self.request)
        rejection = {"world_id": "world-a", "sequence": 0, "head": None,
                     "operation": OP1, "state": 3, "state_name": "rejected", "actual_cost": 0}
        self.assertEqual("rejected", rejected.reconcile(rejection, rejection))
        self.assertEqual(0, Journal.open(rejected.path).position[1])

    def test_uncertain_cases_are_durable_and_never_replayable(self):
        cases = (
            ("not-found.json", ONE, {"operation": {"state_name": "operation-not-found"}}, "received", "operation_not_found"),
            ("no-advance.json", ZERO, {"operation": {"state": 2, "id": OP1}}, "received", "remote_position_did_not_advance"),
            ("unknown.json", None, None, "unknown", "transport_outcome_unknown"),
        )
        for filename, position, reply, transport, reason in cases:
            with self.subTest(filename=filename):
                journal = Journal.create(self.path.with_name(filename), ZERO)
                journal.record_pending(self.request)
                self.assertEqual(
                    "uncertain",
                    journal.reconcile(position, reply, transport_outcome=transport),
                )
                reopened = Journal.open(journal.path)
                self.assertEqual("uncertain", reopened.operation["state"])
                self.assertEqual(reason, reopened.operation["reason"])
                self.assertFalse(reopened.record_pending(self.request))
                with self.assertRaises(JournalError):
                    reopened.record_pending({**self.request, "operation": {"hi": 99, "lo": 99}})

    def test_same_sequence_divergence_is_uncertain_not_replayable(self):
        initial = {"world": "world-a", "sequence": 1, "head": {"hi": 1, "lo": 1}}
        journal = Journal.create(self.path.with_name("same-sequence.json"), initial)
        request = {
            **self.request,
            "expect_sequence": 1,
            "expect_head": {"hi": 1, "lo": 1},
        }
        journal.record_pending(request)
        remote = {"world": "world-a", "sequence": 1, "head": {"hi": 2, "lo": 2}}
        self.assertEqual(
            "uncertain",
            journal.reconcile(remote, {"operation": {"state": 3, "id": OP1}}),
        )
        self.assertEqual("remote_position_did_not_advance", journal.operation["reason"])

    def test_unexpected_advanced_position_requires_manual_reconciliation(self):
        self.journal.record_pending(self.request)
        with self.assertRaisesRegex(JournalError, "manual reconciliation"):
            self.journal.reconcile(
                {"world": "world-a", "sequence": 2, "head": {"hi": 1, "lo": 2}},
                {"operation": {"state": 2, "id": OP1}},
            )
        self.assertEqual("pending", Journal.open(self.path).operation["state"])

    def test_file_and_directory_are_synced_before_pending_returns(self):
        calls = []

        def record_fsync(fd):
            calls.append(fd)

        with mock.patch("native_mutation_journal.os.fsync", side_effect=record_fsync):
            self.journal.record_pending(self.request)
        self.assertEqual(2, len(calls))
        self.assertEqual("pending", Journal.open(self.path).operation["state"])

    def test_any_write_failure_disables_writes_until_reopen(self):
        with mock.patch("native_mutation_journal.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(JournalWriteError):
                self.journal.record_pending(self.request)
        self.assertFalse(self.journal.writable)
        with self.assertRaisesRegex(JournalWriteError, "disabled"):
            self.journal.record_pending(self.request)
        self.assertIsNone(Journal.open(self.path).operation)

    def test_directory_sync_failure_requires_reopen_and_reconcile(self):
        with mock.patch(
            "native_mutation_journal.os.fsync",
            side_effect=[None, OSError("directory sync failed")],
        ):
            with self.assertRaises(JournalWriteError):
                self.journal.record_pending(self.request)
        self.assertFalse(self.journal.writable)
        reopened = Journal.open(self.path)
        self.assertEqual("pending", reopened.operation["state"])
        self.assertFalse(reopened.record_pending(self.request))


if __name__ == "__main__":
    unittest.main()
