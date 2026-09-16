"""Real pinned SOP scripts; only MPI/decomposition is simulated (no GPU).

Run in the source repository, or set LBPM_BOOTSTRAP_SOURCE when testing the
standalone Runner archive. Deliberately not a numerical decomposition test.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from runner.environment import snapshot_sop, runtime_env
from runner.frames import validate_prepared
from runner.protocol import default_protocol, render_input
from runner.util import atomic_json, sha256

SOP_BLOBS = {
    'prepare_case.sh':'e901d048f2eb33bcadb70e7f83f9450c1f754db4',
    'common.sh':'15825274ba2a7e517738ce657722bb150b7280eb',
    'prepare_rock_case.py':'481213d8238683372f1ac07831de1dff3244eaae',
    'state_reports.py':'f33942225855614d6381500746b019b95aee3523',
    'verify_case_contract.py':'f0ebfac6e504fe1ac7f04608173937ad7973dbba',
}


class BootstrapBridge(unittest.TestCase):
    def setUp(self):
        self.repo=Path(os.environ.get('LBPM_BOOTSTRAP_SOURCE',Path(__file__).resolve().parents[2]))
        self.sop=self.repo/'sop/bin'
        if not (self.sop/'prepare_case.sh').is_file():
            self.skipTest('Real SOP integration requires repository checkout or LBPM_BOOTSTRAP_SOURCE')
        self.temp=tempfile.TemporaryDirectory(prefix='actual SOP bridge ')
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)

    def test_pinned_sop_source_identity(self):
        for name,expected in SOP_BLOBS.items():
            data=(self.sop/name).read_bytes()
            digest=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            self.assertEqual(digest,expected,name)

    def test_real_sop_private_config_source_roi_and_reuse(self):
        # Work with an exact copy. The original repository SOP is never mutated.
        source=self.base/'selected SOP/bin'; source.mkdir(parents=True)
        for name in SOP_BLOBS: shutil.copy2(self.sop/name,source/name)
        (source/'prepare_case.sh').chmod(0o644)
        old_config=source.parent/'config.env'
        old_config.write_text('STACK_DIR=/intentionally/unusable\nVALIDATION_DIR=/intentionally/unusable\n')
        old_bytes=old_config.read_bytes()
        tools=self.base/'tools'; tools.mkdir()
        mpi=tools/'mpirun'
        mpi.write_text('#!'+sys.executable+'\n'+'''import json,sys
from pathlib import Path
assert sys.stdin.buffer.read()==b''
assert 'lbpm_serial_decomp' in sys.argv, sys.argv
m=json.loads(Path('case_manifest.json').read_text())
Path('ID.00000').write_bytes(b'\\0'*m['expected_bytes']['ID.00000'])
print('MOCK_DECOMPOSITION_ONLY; STDIN_BYTES=0')
''')
        mpi.chmod(0o755)
        env=self.base/'lbpm_env.sh'; env.write_text('export LBPM_BRIDGE_SENTINEL=original\n')
        accept=self.base/'acceptance_report.json'
        atomic_json(accept,{'schema_version':1,'status':'PASS','sop_version':'1.3.2'})
        root=self.base/'production'; root.mkdir()
        cases=self.base/'prepared'; cases.mkdir()
        c={'paths':{'prepare_case':str(source/'prepare_case.sh'),'env_script':str(env),
           'mpirun':str(mpi),'lbpm_binary':sys.executable,'acceptance_report':str(accept),'case_root':str(cases)}}
        adapter=snapshot_sop(c,root)
        self.assertEqual(old_config.read_bytes(),old_bytes)
        rock=np.zeros((128,128,128),dtype=np.uint8); rock[:,3:7,4:8]=1
        raw=self.base/'41_001.raw'; rock.tofile(raw); before=sha256(raw)
        case=cases/'41_001'
        run=subprocess.run(['bash',adapter,'--input',str(raw),'--case-id','41_001','--case-dir',str(case),
             '--voxel-length-um','1.0'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
             env=runtime_env(c),text=True,timeout=60)
        self.assertEqual(run.returncode,0,run.stdout)
        self.assertIn('CASE_PREPARATION_PASS',run.stdout)
        self.assertIn('STDIN_BYTES=0',run.stdout)
        self.assertEqual(sha256(raw),before)
        self.assertEqual(old_config.read_bytes(),old_bytes)
        p=default_protocol(); pore=validate_prepared(case,before,p)
        self.assertEqual(int(pore.sum()),int(rock.sum()))
        self.assertEqual((case/'ID.00000').stat().st_size,2298400)
        mark=json.loads((case/'CASE_PREPARED.json').read_text())
        self.assertTrue(mark['source_immutable']); self.assertTrue(mark['simulation_roi_preserved'])
        # Reuse must be byte-preserving and independent of the installed config.
        hashes={f.name:sha256(f) for f in case.iterdir() if f.is_file()}
        validate_prepared(case,before,p)
        self.assertEqual(hashes,{f.name:sha256(f) for f in case.iterdir() if f.is_file()})
        text=render_input(p)
        for item in ('BC = 4','InletLayersPhase = 2','OutletLayersPhase = 1','Restart = false'):
            self.assertIn(item,text)
        self.assertNotIn('__PLACEHOLDER__',text)

if __name__=='__main__': unittest.main()
