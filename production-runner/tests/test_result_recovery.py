"""Regression tests for review F-01/F-02. Uses CPU fixtures, not a GPU."""
import csv
import unittest
import test_integration as fixtures
from runner.util import read_json, atomic_json
from runner.production import export_results, commit_result
from runner.state import Store


class ResultRecovery(unittest.TestCase):
    setUp = fixtures.Integration.setUp
    tearDown = fixtures.Integration.tearDown
    cmd = fixtures.Integration.cmd
    wait_complete = fixtures.Integration.wait_complete

    def complete_fixture(self):
        self.cmd('prepare'); self.cmd('start'); self.wait_complete(60)
        marker = next(self.root.glob('cases/*/complete.json'))
        com = read_json(marker)
        return marker, com, self.root / com['attempt_relative']

    def test_corrupt_phase_resume_never_exports_valid(self):
        marker, com, d = self.complete_fixture()
        phase = d / 'result/phase_final_roi.npy'
        original = phase.read_bytes(); payload = bytearray(original); payload[-1] ^= 1
        phase.write_bytes(payload)
        # Ordinary (non-explicit-verify) exports must be safe too.
        row = next(r for r in export_results(self.root) if r['case_id'] == com['case_id'])
        self.assertFalse(row['valid'])
        self.cmd('resume'); self.wait_complete(60)
        with (self.root / 'dataset_index.csv').open() as f:
            rows = {r['case_id']: r for r in csv.DictReader(f)}
        self.assertEqual(rows[com['case_id']]['valid'], 'False')
        self.assertEqual(rows[com['case_id']]['status'], 'OUTPUT_FAILED')
        self.assertFalse(marker.exists())
        self.assertTrue(list(marker.parent.glob('quarantine/*/complete.json')))
        self.assertEqual(phase.read_bytes(), bytes(payload))  # preserve evidence

    def test_faulted_outcome_resume_restarts_attempt(self):
        marker, com, d = self.complete_fixture(); out = read_json(d/'outcome.json')
        atomic_json(self.root/out['epoch_relative']/'fault.json', {
            'time_ns': out['ended_ns']-1, 'attempt_relative':'peer', 'reason':'NUMERICAL_FAILED'})
        marker.unlink()
        db=Store(self.root); db.set(com['case_id'],'RUNNING'); db.close()
        self.cmd('resume'); self.wait_complete(60)
        self.assertNotEqual(read_json(marker)['attempt_relative'], com['attempt_relative'])
        self.assertEqual(read_json(d/'outcome.json')['status'], 'INTERRUPTED')

    def test_existing_commit_in_faulted_epoch_is_quarantined(self):
        marker, com, d = self.complete_fixture(); out = read_json(d/'outcome.json')
        atomic_json(self.root/out['epoch_relative']/'fault.json', {
            'time_ns': out['ended_ns']-1, 'attempt_relative':'peer', 'reason':'NUMERICAL_FAILED'})
        with self.assertRaises(ValueError):
            commit_result(self.root, com['case_id'], com['attempt_relative'], out)
        row = next(r for r in export_results(self.root) if r['case_id']==com['case_id'])
        self.assertFalse(row['valid'])
        self.cmd('resume'); self.wait_complete(60)
        self.assertNotEqual(read_json(marker)['attempt_relative'], com['attempt_relative'])
        self.assertTrue(list(marker.parent.glob('quarantine/*/complete.json')))


if __name__ == '__main__': unittest.main()
