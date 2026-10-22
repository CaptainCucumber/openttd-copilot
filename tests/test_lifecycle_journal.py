from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from lifecycle_journal import Journal, JournalError, position


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'journal.json'
        self.j = Journal(self.path, {'world': 'a', 'seq': 0, 'head': None})
        self.request = {'world': 'a', 'expect_seq': 0, 'op': 'op1', 'tile': 10}
        self.remote = {'world': 'a', 'seq': 1, 'head': 'op1'}
        self.outcome = {'state': 'completed', 'op': 'op1', 'seq': 1, 'cost': 90}

    def test_restart_preserves_pending_before_send_and_verified_outcome(self):
        self.j.pending(self.request)
        restarted = Journal(self.path)
        self.assertEqual('pending', restarted.data['operations']['op1']['state'])
        self.assertEqual('ahead_requires_reconciliation', restarted.classify(self.remote))
        restarted.complete('op1', self.remote, self.outcome)
        self.assertEqual('current', Journal(self.path).classify(self.remote))

    def test_old_and_different_worlds_do_not_change_highwater(self):
        self.j.pending(self.request)
        self.j.complete('op1', self.remote, self.outcome)
        self.assertEqual('older_save', self.j.classify({'world': 'a', 'seq': 0, 'head': None}))
        self.assertEqual('changed_world', self.j.classify({'world': 'b', 'seq': 1, 'head': 'op1'}))
        self.assertEqual('diverged', self.j.classify({'world': 'a', 'seq': 1, 'head': 'different'}))
        self.assertEqual(self.remote, Journal(self.path).data['position'])

    def test_uncertain_unknown_and_wrong_identity_never_complete(self):
        self.j.pending(self.request)
        for outcome in ({'state': 'unknown'}, {'state': 'uncertain'}, {'state': 'completed', 'op': 'other'}):
            with self.subTest(outcome=outcome), self.assertRaises(JournalError):
                self.j.complete('op1', self.remote, outcome)
        self.assertEqual(0, Journal(self.path).data['position']['seq'])

    def test_conflict_and_second_pending_are_rejected(self):
        self.j.pending(self.request)
        with self.assertRaises(JournalError):
            self.j.pending({**self.request, 'tile': 11})
        with self.assertRaises(JournalError):
            self.j.pending({**self.request, 'op': 'op2'})

    def test_boolean_sequence_is_not_valid_integer(self):
        with self.assertRaises(JournalError):
            position({'world': 'a', 'seq': True, 'head': 'op1'})

    def test_completion_requires_consistent_sequence_and_pending_state(self):
        self.j.pending(self.request)
        for seq in (None, True, 99):
            with self.subTest(seq=seq), self.assertRaises(JournalError):
                self.j.complete('op1', self.remote, {**self.outcome, 'seq': seq})
        self.j.data['operations']['op1']['state'] = 'uncertain'
        with self.assertRaises(JournalError):
            self.j.complete('op1', self.remote, self.outcome)
        self.assertEqual(0, Journal(self.path).data['position']['seq'])

    def test_failed_intent_write_cannot_be_reused_as_durable_permission(self):
        with mock.patch('lifecycle_journal.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.j.pending(self.request)
        with self.assertRaises(JournalError):
            self.j.pending(self.request)
        self.assertNotIn('op1', self.j.data['operations'])
        self.assertNotIn('op1', Journal(self.path).data['operations'])

    def test_uncertain_directory_sync_requires_reopen_and_reconciliation(self):
        with mock.patch('lifecycle_journal.os.fsync', side_effect=[None, OSError('directory sync failed')]):
            with self.assertRaises(OSError):
                self.j.pending(self.request)
        with self.assertRaises(JournalError):
            self.j.pending(self.request)
        reopened = Journal(self.path)
        self.assertEqual('pending', reopened.data['operations']['op1']['state'])
        with self.assertRaises(JournalError):
            reopened.pending({**self.request, 'op': 'op2'})


if __name__ == '__main__':
    unittest.main()
