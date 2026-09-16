#!/usr/bin/env python3
"""CPU-only integration fixture. This is NOT LBPM and never opens a CUDA device."""
import json, os, re, sys, time
from pathlib import Path

def proc_live(pid):
    try:
        s=Path('/proc',str(pid),'stat').read_text(); return s[s.rfind(')')+2:].split()[0]!='Z'
    except OSError: return False

mode=Path(sys.argv[0]).name
state=Path(os.environ.get('MOCK_STATE','/tmp/lbpm-fixture-unused'))
if mode=='nvidia-smi':
    if any('query-gpu=index' in a for a in sys.argv): print('0, GPU-fixture-uuid, CPU ONLY MOCK GPU, MOCK, 24564')
    else: print('80, 1000, 24564, 100')
elif mode=='nvidia-cuda-mps-control':
    pipe=Path(os.environ.get('CUDA_MPS_PIPE_DIRECTORY',str(state/'pipe'))); pipe.mkdir(parents=True,exist_ok=True)
    if '-v' in sys.argv: print('CPU fixture Legacy MPS v2; not GPU validated')
    elif '-d' in sys.argv: (pipe/'mock_daemon').write_text('running')
    else:
        cmd=sys.stdin.read().strip()
        if cmd=='help': print('ps terminate_client get_server_list quit')
        elif cmd=='ps':
            print('PID ID SERVER DEVICE NAMESPACE COMMAND')
            for f in pipe.glob('client-*.json'):
                x=json.loads(f.read_text())
                if proc_live(x['pid']): print(x['pid'],0,98765,'GPU-fixture-uuid',x['namespace'],'CPU_ONLY_MOCK')
        elif cmd.startswith('terminate_client '):
            code='1' if (state/'reject_termination').exists() else '0'
            with (state/'control_calls.log').open('a') as f: f.write(cmd+' -> '+code+'\n')
            print(code)
        elif cmd=='quit':
            (pipe/'mock_daemon').unlink(missing_ok=True)
        elif cmd=='get_server_list': print(98765)
        else: print('Invalid command'); sys.exit(1)
elif mode=='mpirun':
    import numpy as np
    cwd=Path.cwd(); text=Path('input.db').read_text(); cp=int(re.search(r'analysis_interval\s*=\s*(\d+)',text)[1]); cap=int(re.search(r'timestepMax\s*=\s*(\d+)',text)[1])
    pore=np.fromfile('rock.raw',dtype=np.uint8).reshape(128,128,128)==1
    pipe=Path(os.environ['CUDA_MPS_PIPE_DIRECTORY']); reg=pipe/('client-%d.json'%os.getpid())
    reg.write_text(json.dumps({'pid':os.getpid(),'namespace':int(os.readlink('/proc/self/ns/pid').split('[')[1][:-1])}))
    case=cwd.parents[1].name
    modes=json.loads((state/'modes.json').read_text()) if (state/'modes.json').exists() else {}
    behavior=modes.get(case,'stable')
    gas_vox=np.flatnonzero(pore.ravel()); roi=np.zeros(pore.shape,dtype=np.uint8); roi[pore]=2
    roi.ravel()[gas_vox[:max(1,len(gas_vox)//5)]]=1
    a=np.ones((134,128,128),dtype=np.uint8); a[:3]=2; a[3:131]=roi
    print('CPU_ONLY_MOCK, NOT PHYSICS DATA',flush=True)
    print('flux=%.12g'%(int(pore.sum())/(128*(.1*(.92-.5)/3)/(6*.009*.0002))),flush=True)
    print('STDIN_BYTES='+str(len(sys.stdin.read())),flush=True)
    for idx in range(1,cap//cp+1):
        if behavior=='nan' and idx==3:
            print('SubPhase.cpp: NaN encountered',flush=True); reg.unlink(missing_ok=True); sys.exit(134)
        if behavior=='nan_wait' and idx==3:
            print('SubPhase.cpp: NaN encountered',flush=True)
            # Keep this CPU-only mock client registered briefly so the Runner can
            # exercise targeted MPS containment before an abnormal client exit.
            time.sleep(5)
            reg.unlink(missing_ok=True); sys.exit(134)
        if behavior=='stall': time.sleep(120)
        if behavior=='cap':
            a[3:131][pore]=1 if idx%2 else 2
        with open('id_t%d.raw'%(idx*cp),'wb') as f: a.tofile(f)
        time.sleep(.08)
    reg.unlink(missing_ok=True)
else:
    print('fixture tool name not recognized',mode,file=sys.stderr); sys.exit(2)
