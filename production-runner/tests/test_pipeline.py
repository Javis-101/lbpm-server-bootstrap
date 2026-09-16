import importlib
import tempfile
import unittest
from pathlib import Path

class PipelineContracts(unittest.TestCase):
    def mod(self,name):
        self.assertIsNotNone(importlib.util.find_spec('runner.'+name), 'implementation missing '+name)
        return importlib.import_module('runner.'+name)
    def test_error_classifier(self):
        w=self.mod('worker')
        self.assertEqual(w.classify_exit(134,'SubPhase.cpp: NaN encountered'),'NUMERICAL_FAILED')
        self.assertEqual(w.classify_exit(1,'CUDA_ERROR_MPS_SERVER_NOT_READY'),'INFRA_FAILED')
        self.assertEqual(w.classify_exit(0,''),'EXIT_OK')
        self.assertEqual(w.classify_exit(137,''),'INTERRUPTED')
    def test_task_queue_family_interleaved(self):
        p=self.mod('production')
        tasks=[{'case_id':f'{f}_{i:03}', 'family':f} for f in ['41','44'] for i in range(4)]
        ordered=p.queue_order(tasks,42)
        self.assertEqual([r['family'] for r in ordered],['41','44']*4)
        self.assertEqual(p.queue_order(tasks,42),ordered)
    def test_fault_record_first_writer_wins(self):
        w=self.mod('worker'); from runner.util import read_json
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'fault.json'
            w.first_fault(f,{'a':1}); w.first_fault(f,{'a':2})
            self.assertEqual(read_json(f),{'a':1})

if __name__=='__main__': unittest.main()
