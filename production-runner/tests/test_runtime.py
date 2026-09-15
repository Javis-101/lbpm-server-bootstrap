import importlib
import os
import tempfile
import unittest
from pathlib import Path
import numpy as np

class RuntimeContracts(unittest.TestCase):
    def mod(self,name):
        self.assertIsNotNone(importlib.util.find_spec('runner.'+name), 'implementation missing '+name)
        return importlib.import_module('runner.'+name)

    def test_read_frame_geometry_mismatch(self):
        f=self.mod('frames'); from runner.protocol import default_protocol
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'id_t2.raw'; pore=np.ones((128,128,128),dtype=bool)
            a=np.ones((134,128,128),dtype=np.uint8); a[5,0,0]=0; a.tofile(p)
            with self.assertRaises(ValueError): f.read_frame(p,pore,default_protocol())

    def test_read_frame_bad_label(self):
        f=self.mod('frames'); from runner.protocol import default_protocol
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'id_t2.raw'; pore=np.ones((128,128,128),dtype=bool)
            a=np.ones((134,128,128),dtype=np.uint8); a[5,0,0]=9; a.tofile(p)
            with self.assertRaises(ValueError): f.read_frame(p,pore,default_protocol())

    def test_close_event_is_not_open_event(self):
        f=self.mod('frames')
        with tempfile.TemporaryDirectory() as td:
            with f.CloseWatcher(Path(td)) as w:
                p=Path(td)/'id_t2.raw'
                out=p.open('wb'); out.write(b'abc'); out.flush()
                self.assertNotIn(p.name,w.drain())
                out.close()
                self.assertIn(p.name,w.drain())

    def test_mps_ps_parser(self):
        m=self.mod('mps')
        v=m.parse_ps('PID ID SERVER DEVICE NAMESPACE COMMAND\n123 0 55 GPU-abcd 4026 /a space/lbpm\n')
        self.assertEqual(v[0]['server'],55); self.assertEqual(v[0]['pid'],123)

    def test_mps_success_requires_explicit_zero(self):
        m=self.mod('mps')
        self.assertTrue(m.termination_ok('0\n'))
        for s in ['', '1\n', 'ERROR\n0\n','Invalid command']:
            self.assertFalse(m.termination_ok(s))

    def test_state_transition_and_reopen(self):
        s=self.mod('state')
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); db=s.Store(d)
            db.seed([{'case_id':'41_001','family':'41'}]); db.set('41_001','RUNNING',attempt='x')
            db.close(); db=s.Store(d)
            self.assertEqual(db.rows()[0]['status'],'RUNNING')
            db.seed([{'case_id':'41_001','family':'41'}]); self.assertEqual(db.rows()[0]['status'],'RUNNING')
            db.close()

if __name__=='__main__': unittest.main()
