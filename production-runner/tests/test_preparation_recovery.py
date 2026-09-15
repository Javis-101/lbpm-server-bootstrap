import tempfile
import unittest
import subprocess
from pathlib import Path
from runner import frames
from runner.util import atomic_json, read_json
from runner.environment import snapshot_sop
from runner.config import load_machine

class PreparationRecovery(unittest.TestCase):
    def test_owned_incomplete_preparation_is_preserved_and_requeued(self):
        self.assertTrue(hasattr(frames, 'recover_owned_preparation'), 'owned preparation recovery must exist')
        with tempfile.TemporaryDirectory() as td:
            b=Path(td); d=b/'41_001'; owner=b/'owners/41_001.json'
            frames.recover_owned_preparation(d,owner,'production','rawhash')
            d.mkdir(); (d/'half.raw').write_bytes(b'partial')
            frames.recover_owned_preparation(d,owner,'production','rawhash')
            self.assertFalse(d.exists())
            backups=list(b.glob('41_001.interrupted-prep-*'))
            self.assertEqual(len(backups),1); self.assertEqual((backups[0]/'half.raw').read_bytes(),b'partial')
    def test_unknown_existing_preparation_never_moved(self):
        self.assertTrue(hasattr(frames, 'recover_owned_preparation'))
        with tempfile.TemporaryDirectory() as td:
            b=Path(td); d=b/'41_001'; d.mkdir(); (d/'keep').write_text('original')
            with self.assertRaises(ValueError): frames.recover_owned_preparation(d,b/'owner.json','p','h')
            self.assertEqual((d/'keep').read_text(),'original')
    def test_completed_preparation_never_replaced(self):
        self.assertTrue(hasattr(frames, 'recover_owned_preparation'))
        with tempfile.TemporaryDirectory() as td:
            b=Path(td); d=b/'41_001'; d.mkdir(); atomic_json(d/'CASE_PREPARED.json',{'status':'PREPARED'})
            frames.recover_owned_preparation(d,b/'owner.json','p','h')
            self.assertTrue((d/'CASE_PREPARED.json').exists())
    def test_sop_honors_explicit_mpi_and_binary_directories(self):
        with tempfile.TemporaryDirectory() as td:
            b=Path(td); src=b/'old/bin'; src.mkdir(parents=True); (src/'prepare_case.sh').write_text('echo test')
            env=b/'env.sh'; env.write_text('export MPI_DIR=/wrong/old\nexport PATH=/usr/bin:/bin\n')
            report=b/'acceptance.json'; atomic_json(report,{'status':'PASS','schema_version':1})
            out=b/'prod'; out.mkdir(); c=load_machine(None,{},{}); c['paths'].update(prepare_case=str(src/'prepare_case.sh'),
                env_script=str(env),acceptance_report=str(report),case_root=str(b/'cases'),output_root=str(out),
                mpirun=str(b/'mpi path/bin/mpirun'),lbpm_binary=str(b/'lbpm path/bin/lbpm_color_simulator'))
            snapshot_sop(c,out)
            r=subprocess.run(['bash','-c','source "$1"; printf "%s\\n%s\\n" "$MPI_DIR" "$PATH"','bash',str(out/'sop-runtime/stack-env/lbpm_env.sh')],capture_output=True,text=True,check=True)
            self.assertEqual(r.stdout.splitlines()[0],str(b/'mpi path'))
            self.assertTrue(r.stdout.splitlines()[1].startswith(str(b/'lbpm path/bin')+':'+str(b/'mpi path/bin')+':'))

if __name__=='__main__': unittest.main()
