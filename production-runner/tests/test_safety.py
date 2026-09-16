import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from runner.util import atomic_json, read_json, sha256, identity
from runner.archive import archive_attempt, restore_attempt
from runner.environment import snapshot_sop
from runner.config import load_machine
from runner.protocol import default_protocol, validate

class Safety(unittest.TestCase):
    def test_archive_resume_release_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); (d/'id_t2.raw').write_bytes(b'012'*1000); (d/'id_t4.raw').write_bytes(b'0012'*1000)
            m=archive_attempt(d,False); (d/'id_t2.raw').unlink()
            m2=archive_attempt(d,True)
            self.assertTrue(m2['release_complete']); self.assertFalse(list(d.glob('id_t*.raw')))
            self.assertEqual(m['archive_sha256'],m2['archive_sha256'])
    def test_truncated_archive_does_not_release(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); raw=d/'id_t2.raw'; raw.write_bytes(b'012'*1000)
            archive_attempt(d,False); z=d/'checkpoints.tar.zst'; z.write_bytes(z.read_bytes()[:-1])
            with self.assertRaises(ValueError): archive_attempt(d,True)
            self.assertTrue(raw.exists())
    def test_no_release_on_modified_raw(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); raw=d/'id_t2.raw'; raw.write_bytes(b'012'*1000)
            archive_attempt(d,False); raw.write_bytes(b'222'*1000)
            with self.assertRaises(ValueError): archive_attempt(d,True)
            self.assertTrue(raw.exists())
    def test_restore_never_overwrites(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)/'a'; d.mkdir(); (d/'id_t2.raw').write_bytes(b'012')
            archive_attempt(d,True); out=Path(td)/'out'; out.mkdir(); (out/'important').write_text('keep')
            with self.assertRaises(ValueError): restore_attempt(d,out)
            self.assertEqual((out/'important').read_text(),'keep')
    def test_sop_uses_external_env_without_editing_source(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); sop=base/'old/bin'; sop.mkdir(parents=True); (sop/'prepare_case.sh').write_text('echo test')
            original=base/'old/config.env'; original.write_text('STACK_DIR=/old/machine\n'); h=sha256(original)
            env=base/'other-environment.sh'; env.write_text('export EXAMPLE=1\n')
            report=base/'proof.json'; atomic_json(report,{'schema_version':1,'status':'PASS'})
            root=base/'production'; root.mkdir()
            c=load_machine(None,{},{}); c['paths'].update(prepare_case=str(sop/'prepare_case.sh'),env_script=str(env),
                acceptance_report=str(report),case_root=str(base/'cases'),output_root=str(root))
            entry=snapshot_sop(c,root)
            self.assertTrue(Path(entry).exists()); self.assertEqual(sha256(original),h)
            self.assertIn(str(env),(root/'sop-runtime/stack-env/lbpm_env.sh').read_text())
            self.assertEqual(read_json(root/'sop-runtime/validation/acceptance_report.json')['status'],'PASS')
    def test_mps_refusal_never_sends_signal(self):
        from runner.mps import MPS
        m=object.__new__(MPS); m.find_client=lambda *a:{'pid':123,'server':55}
        m.request=lambda cmd:'1\n'
        with patch('runner.mps.proc_identity',return_value={'pid':123}), patch('runner.mps.os.kill') as kill:
            with self.assertRaises(RuntimeError): m.terminate('token','/x','/bin/x')
            kill.assert_not_called()

    def test_mps_signal_only_after_successful_response(self):
        from runner.mps import MPS
        order=[]; m=object.__new__(MPS); m.find_client=lambda *a:{'pid':123,'server':55}
        def request(cmd): order.append('context_terminated'); return '0\n'
        m.request=request
        with patch('runner.mps.proc_identity',return_value={'pid':123}), patch('runner.mps.alive',side_effect=[True,False,False]), patch('runner.mps.os.kill',side_effect=lambda *a:order.append('signal')):
            m.terminate('token','/x','/bin/x')
        self.assertEqual(order,['context_terminated','signal'])

    def test_endpoint_link_is_byte_identical_without_extra_copy(self):
        from runner.util import atomic_immutable_link
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'endpoint.raw'; src.write_bytes(b'012'*500)
            dst=Path(td)/'result/phase_final_full.raw'; atomic_immutable_link(src,dst)
            self.assertEqual(src.stat().st_ino,dst.stat().st_ino)
            self.assertEqual(sha256(src),sha256(dst))

    def test_nonfinite_tau_rejected(self):
        p=default_protocol(); p['physics']['tauA']=float('nan')
        with self.assertRaises(ValueError): validate(p)

if __name__=='__main__': unittest.main()
