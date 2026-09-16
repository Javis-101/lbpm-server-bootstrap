"""Small durable-evidence fixtures. Not physical field validation."""
import tempfile
import unittest
from pathlib import Path
from runner.results import verify_result, verify_commit, commit_result, checked_hash, EpochRejected
from runner.production import export_results
from runner.state import Store
from runner.util import atomic_json, read_json, sha256, identity


class ResultGuard(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.rel='cases/41_001/attempts/attempt_0001'
        self.d=self.root/self.rel; (self.d/'result').mkdir(parents=True)
        (self.root/'epochs/e1').mkdir(parents=True)
        t={'case_id':'41_001','family':'41','raw_relative':'41_001.raw','sha256':'input-digest'}
        atomic_json(self.root/'inputs.json',[t])
        atomic_json(self.root/'production_manifest.json',{'protocol_sha256':'p','inputs_sha256':identity([t])})
        atomic_json(self.d/'job.json',{'task':t,'protocol_sha256':'p','attempt_relative':self.rel,'epoch_relative':'epochs/e1'})
        files={}
        for name in ('phase_final_full.raw','phase_final_roi.npy'):
            (self.d/'result'/name).write_bytes(b'small hash-test fixture, not LBM output')
            files[name]=sha256(self.d/'result'/name)
        result={'case_id':'41_001','family':'41','input_sha256':t['sha256'],'protocol_sha256':'p',
          'attempt_relative':self.rel,'stop_reason':'STANDARD','files':files,'sg_endpoint':.2,'stop_nominal_pvi':1.5}
        atomic_json(self.d/'result/result.json',result)
        self.out={'case_id':'41_001','epoch_relative':'epochs/e1','status':'SUCCEEDED_STANDARD',
                  'ended_ns':100,'result_sha256':sha256(self.d/'result/result.json')}
        atomic_json(self.d/'outcome.json',self.out)
        db=Store(self.root); db.seed([t]); db.set('41_001','SUCCEEDED_STANDARD',attempt=self.rel); db.close()
        commit_result(self.root,'41_001',self.rel,self.out)

    def test_clean_result_is_exported(self):
        self.assertTrue(export_results(self.root)[0]['valid'])

    def test_corrupt_same_size_file_invalidates_cached_hash(self):
        self.assertTrue(export_results(self.root)[0]['valid'])
        p=self.d/'result/phase_final_roi.npy'; data=bytearray(p.read_bytes()); data[-1]^=1; p.write_bytes(data)
        row=export_results(self.root)[0]
        self.assertFalse(row['valid']); self.assertEqual(row['status'],'OUTPUT_FAILED')

    def test_known_output_failure_never_overruled_by_marker(self):
        db=Store(self.root); db.set('41_001','OUTPUT_FAILED'); db.close()
        self.assertFalse(export_results(self.root)[0]['valid'])

    def test_bad_commit_hash_is_not_exported(self):
        path=self.root/'cases/41_001/complete.json'; com=read_json(path); com['result_json_sha256']='wrong'; atomic_json(path,com)
        self.assertFalse(export_results(self.root)[0]['valid'])

    def test_malformed_completion_marker_is_invalid_not_whole_export_crash(self):
        (self.root/'cases/41_001/complete.json').write_text('{broken')
        self.assertFalse(export_results(self.root)[0]['valid'])

    def test_missing_required_output_is_rejected(self):
        (self.d/'result/phase_final_roi.npy').unlink()
        self.assertFalse(export_results(self.root)[0]['valid'])

    def test_fault_before_or_at_end_blocks_commit(self):
        for when in (99,100):
            with self.subTest(when=when):
                atomic_json(self.root/'epochs/e1/fault.json',{'time_ns':when,'attempt_relative':'peer'})
                with self.assertRaises(EpochRejected): commit_result(self.root,'41_001',self.rel,self.out)
                self.assertFalse(export_results(self.root)[0]['valid'])

    def test_fault_after_completed_result_does_not_reject_it(self):
        atomic_json(self.root/'epochs/e1/fault.json',{'time_ns':101,'attempt_relative':'peer'})
        self.assertTrue(export_results(self.root)[0]['valid'])

    def test_missing_epoch_and_unknown_fault_time_fail_closed(self):
        atomic_json(self.root/'epochs/e1/fault.json',{'reason':'missing time'})
        with self.assertRaises(EpochRejected): verify_result(self.root,self.rel)
        (self.root/'epochs/e1/fault.json').unlink(); (self.root/'epochs/e1').rmdir()
        with self.assertRaises(EpochRejected): verify_result(self.root,self.rel)

    def test_existing_empty_fault_record_is_not_treated_as_absent(self):
        for payload in ({}, None, [], False):
            with self.subTest(payload=payload):
                atomic_json(self.root/'epochs/e1/fault.json',payload)
                with self.assertRaises(EpochRejected): verify_result(self.root,self.rel)

    def test_outcome_epoch_cannot_be_substituted(self):
        out=dict(self.out,epoch_relative='epochs/other'); atomic_json(self.d/'outcome.json',out)
        with self.assertRaises(EpochRejected): verify_result(self.root,self.rel)

    def test_original_input_identity_is_required(self):
        j=read_json(self.d/'job.json'); j['task']['sha256']='different'; atomic_json(self.d/'job.json',j)
        with self.assertRaises(ValueError): verify_result(self.root,self.rel)

    def test_in_memory_outcome_cannot_override_disk_evidence(self):
        with self.assertRaises(ValueError):
            commit_result(self.root,'41_001',self.rel,dict(self.out,status='CAP_REACHED'))

if __name__=='__main__': unittest.main()
