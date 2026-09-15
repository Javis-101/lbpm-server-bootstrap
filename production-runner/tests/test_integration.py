import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
import numpy as np
from runner.util import read_json, atomic_json, identity, sha256, proc_identity, alive
from runner.protocol import default_protocol

PACKAGE=Path(__file__).resolve().parents[1]
FIXTURE=PACKAGE/'tests/fixtures/mock_tools.py'

class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='lbpm runner integration ')
        self.base=Path(self.tmp.name); self.root=self.base/'production'
        for name in ['tools','pool','prepared','source/models','sop/bin','validation']:
            (self.base/name).mkdir(parents=True)
        for name in ('mpirun','nvidia-smi','nvidia-cuda-mps-control'):
            f=self.base/'tools'/name
            f.write_text('#!'+sys.executable+'\n'+FIXTURE.read_text().split('\n',1)[1]); f.chmod(0o755)
        self.envscript=self.base/'env.sh'; self.envscript.write_text('export MOCK_STATE='+str(self.base).replace(' ','\\ ')+'\n')
        self.prep=self.base/'sop/bin/prepare_case.sh'; self.prep.write_text('#!/usr/bin/env bash\nexit 88\n'); self.prep.chmod(0o644)
        (self.base/'source/models/ColorModel.cpp').write_text('if (outlet_layers_phase == 1) { outletA = 1.0; outletB = 0.0; }')
        (self.base/'build.txt').write_text('LBPM_COMMIT=6d686d354e5b8140841d3601e4c8c0e4e4b77e48\nPATCHSET_ID=outletlayersphase-fix-v1\n')
        atomic_json(self.base/'validation/acceptance_report.json',{'schema_version':1,'status':'PASS'})
        for i,case in enumerate(['41_001','41_002','44_001','44_002']):
            rock=np.zeros((128,128,128),np.uint8); rock[:,10:30+i,10:30]=1
            raw=self.base/'pool'/(case+'.raw'); rock.tofile(raw)
            d=self.base/'prepared'/case; d.mkdir(); shutil.copyfile(raw,d/'rock.raw')
            a=np.ones((134,128,128),np.uint8); a[:3]=2; a[3:131]=rock; a.tofile(d/'rock_waterdrive.raw')
            (d/'ID.00000').write_bytes(b'\0'*2298400)
            atomic_json(d/'CASE_PREPARED.json',{'status':'PREPARED','case_preparation':'PASS'})
        def q(s): return json.dumps(str(s))
        paths={'lbpm_binary':sys.executable,'mpirun':self.base/'tools/mpirun','env_script':self.envscript,
            'prepare_case':self.prep,'raw_root':self.base/'pool','case_root':self.base/'prepared','output_root':self.root,
            'acceptance_report':self.base/'validation/acceptance_report.json','source_root':self.base/'source',
            'build_manifest':self.base/'build.txt','mps_control':self.base/'tools/nvidia-cuda-mps-control','nvidia_smi':self.base/'tools/nvidia-smi'}
        self.config=self.base/'machine.toml'; self.config.write_text('[paths]\n'+''.join(k+'='+q(v)+'\n' for k,v in paths.items())+
            '\n[runtime]\nmax_jobs=2\npoll_seconds=0.1\nstall_seconds=30\nmps_base='+q(self.base/'mps')+
            '\n[dataset]\nexpected_count=4\nper_family=2\nfamilies=["41","44"]\n')
    def tearDown(self):
        # CPU-only fixture processes are safe to terminate; never touches a real GPU.
        if self.root.exists():
            for f in self.root.glob('cases/*/attempts/*/process.json'):
                with contextlib.suppress(Exception):
                    p=read_json(f)
                    for key in ['mpirun','worker']:
                        rec=p.get(key)
                        if alive(rec): os.kill(rec['pid'],15)
            rec=read_json(self.root/'controller.json',{}).get('process')
            if alive(rec):
                atomic_json(self.root/'control/pause.json',{'reason':'fixture cleanup'})
                for _ in range(50):
                    if not alive(rec): break
                    time.sleep(.1)
        self.tmp.cleanup()
    def cmd(self,*args,timeout=30):
        p=subprocess.run([sys.executable,str(PACKAGE/'runner_cli.py'),*args,'--config',str(self.config)],cwd=PACKAGE,
                         stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
        self.assertEqual(p.returncode,0,p.stdout)
        return p.stdout
    def wait_complete(self,seconds=30):
        end=time.time()+seconds
        while time.time()<end:
            s=read_json(self.root/'status.json',{})
            if s.get('mode') in ('COMPLETE','RECOVERY_REQUIRED','PAUSED'):
                self.assertEqual(s['mode'],'COMPLETE',json.dumps(s)+ '\n'+(self.root/'supervisor.log').read_text(errors='replace'))
                return s
            time.sleep(.2)
        self.fail('integration timeout '+(self.root/'supervisor.log').read_text(errors='replace'))
    def test_full_queue_earlystop_and_idempotent_resume(self):
        self.cmd('prepare'); self.cmd('start'); s=self.wait_complete()
        self.assertEqual(s['valid'],4); self.assertTrue(s['safe_to_stop'])
        commits=list(self.root.glob('cases/*/complete.json')); self.assertEqual(len(commits),4)
        counts=[]
        for f in commits:
            d=self.root/read_json(f)['attempt_relative']; r=read_json(d/'result/result.json')
            self.assertEqual(r['stop_reason'],'STANDARD'); self.assertAlmostEqual(r['stop_nominal_pvi'],1.5)
            self.assertEqual(r['termination_mode'],'MPS_SAFE_EARLY_STOP')
            self.assertIn('STDIN_BYTES=0',(d/'run.log').read_text()); counts.append(len(list(d.glob('id_t*.raw'))))
        before={str(f):sha256(f) for f in commits}
        self.cmd('resume'); self.wait_complete()
        self.assertEqual(before,{str(f):sha256(f) for f in commits})
        self.assertEqual(len(list(self.root.glob('cases/*/attempts/*/job.json'))),4)
    def test_nan_not_labeled_success_and_peer_recovery(self):
        atomic_json(self.base/'modes.json',{'41_002':'nan'})
        self.cmd('prepare'); self.cmd('start'); s=self.wait_complete(40)
        self.assertEqual(s['counts'].get('NUMERICAL_FAILED'),1)
        self.assertEqual(s['valid'],3)
        self.assertFalse((self.root/'cases/41_002/complete.json').exists())
    def test_supervisor_crash_adopts_existing_attempts(self):
        self.cmd('prepare'); self.cmd('start')
        controller=read_json(self.root/'controller.json')['process']
        # Only the CPU fixture supervisor is killed. Detached workers must not be duplicated.
        os.kill(controller['pid'],9)
        time.sleep(.3)
        self.cmd('resume'); s=self.wait_complete(40)
        self.assertEqual(s['valid'],4)
        self.assertEqual(len(list(self.root.glob('cases/*/attempts/*/job.json'))),4)

    def test_dead_worker_attempt_is_restarted_not_entire_queue(self):
        self.cmd('prepare'); self.cmd('start')
        deadline=time.time()+10; selected=None
        while time.time()<deadline:
            for f in self.root.glob('cases/*/attempts/*/process.json'):
                r=read_json(f)
                if r.get('mpirun') and len(list(f.parent.glob('id_t*.raw')))>=2:
                    selected=(f,r); break
            if selected: break
            time.sleep(.05)
        self.assertIsNotNone(selected)
        f,r=selected
        # CPU fixture only: emulate loss of a worker and its numerical process before a decision.
        os.kill(r['worker']['pid'],9)
        with contextlib.suppress(ProcessLookupError): os.kill(r['mpirun']['pid'],9)
        s=self.wait_complete(45)
        self.assertEqual(s['valid'],4)
        self.assertGreaterEqual(len(list(self.root.glob('cases/*/attempts/*/job.json'))),5)
        self.assertGreaterEqual(len(list(f.parent.glob('id_t*.raw'))),2)

    def test_storage_pressure_archives_all_without_discarding_frames(self):
        with self.config.open('a') as out:
            out.write('\n[storage]\ncompress_below_gib=10000.0\ncompress_until_gib=11000.0\npause_below_gib=0.1\nsafety_gib=0.1\n')
        self.cmd('prepare'); self.cmd('start'); s=self.wait_complete(60)
        self.assertEqual(s['valid'],4)
        for f in self.root.glob('cases/*/complete.json'):
            d=self.root/read_json(f)['attempt_relative']
            m=read_json(d/'archive_manifest.json')
            self.assertTrue(m['verified']); self.assertTrue(m['release_complete'])
            self.assertGreaterEqual(len(m['files']),15)
            self.assertFalse(list(d.glob('id_t*.raw')))
            self.assertTrue((d/'result/phase_final_roi.npy').exists())

    def test_pause_drain_keeps_current_results_then_resume(self):
        self.cmd('prepare'); self.cmd('start'); self.cmd('pause','--drain')
        end=time.time()+20
        while time.time()<end:
            s=read_json(self.root/'status.json',{})
            if s.get('mode')=='PAUSED': break
            time.sleep(.1)
        self.assertEqual(s.get('mode'),'PAUSED'); self.assertTrue(s.get('safe_to_stop'))
        self.cmd('resume'); s=self.wait_complete(40); self.assertEqual(s['valid'],4)

    def test_cap_reason_is_distinct(self):
        atomic_json(self.base/'modes.json',{c:'cap' for c in ['41_001','41_002','44_001','44_002']})
        self.cmd('prepare'); self.cmd('start'); s=self.wait_complete(40)
        self.assertEqual(s['counts'].get('CAP_REACHED'),4)

if __name__=='__main__': unittest.main()
