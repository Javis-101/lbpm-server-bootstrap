from __future__ import annotations
import csv
import io
import random
import uuid
from collections import defaultdict, Counter
from pathlib import Path
from . import __version__
from .util import Lock, atomic_json, read_json, atomic_bytes, identity, sha256, now, safe_id, SUCCESS, inside
from .frames import read_rock
from .protocol import time_grid
from .environment import preflight, snapshot_sop
from .state import Store
from .results import (commit_result, verify_result, verify_commit, EpochRejected)


def queue_order(tasks,seed):
    groups=defaultdict(list)
    for t in tasks: groups[t['family']].append(t)
    rng=random.Random(seed)
    for family in sorted(groups):
        groups[family].sort(key=lambda t:t['case_id']); rng.shuffle(groups[family])
    result=[]
    for i in range(max(map(len,groups.values()),default=0)):
        for family in sorted(groups):
            if i<len(groups[family]): result.append(groups[family][i])
    return result


def enumerate_inputs(c,p):
    raw=Path(c['paths']['raw_root']); config=c['dataset']; files=sorted(raw.glob('*.raw')); tasks=[]
    for f in files:
        case=safe_id(f.stem); fam=case.split('_')[0]
        if fam not in config['families']: raise ValueError('Unexpected family in pool: '+f.name)
        error=''
        try: pore=read_rock(f,p); count=int(pore.sum())
        except Exception as exc: error=str(exc); count=0
        tasks.append({'case_id':case,'family':fam,'raw_relative':f.name,'bytes':f.stat().st_size,
                      'sha256':sha256(f),'pore_voxels':count,'input_error':error})
    if len(tasks)!=config['expected_count']: raise ValueError('INPUT_COUNT: expected %d, got %d'%(config['expected_count'],len(tasks)))
    counts=Counter(t['family'] for t in tasks)
    if any(counts[f]!=config['per_family'] for f in config['families']): raise ValueError('FAMILY_COUNTS: '+str(dict(counts)))
    seen={}
    for t in tasks:
        if t['sha256'] in seen: t['input_error']='DUPLICATE_RAW_OF_'+seen[t['sha256']]
        else: seen[t['sha256']]=t['case_id']
    return queue_order(tasks,c['runtime']['queue_seed'])


def prepare(c,p):
    c,facts=preflight(c); root=Path(c['paths']['output_root']); root.mkdir(parents=True,exist_ok=True)
    with Lock(root/'.supervisor.lock'), Lock(root/'.prepare.lock'):
        manfile=root/'production_manifest.json'; existing=read_json(manfile,{})
        if existing:
            if existing['protocol_sha256']!=identity(p): raise ValueError('PROTOCOL_ALREADY_FROZEN: use a new output root')
            print('PRODUCTION_ALREADY_PREPARED: no queue reset; use start/resume'); return existing
        initfile=root/'.initializing.json'
        init=read_json(initfile,{})
        init_id=identity({'protocol':p,'raw_root':c['paths']['raw_root'],'dataset':c['dataset']})
        allowed={'.supervisor.lock','.prepare.lock','.initializing.json','preflight_report.json'}
        if init.get('identity')==init_id:
            allowed.update({'protocol.snapshot.json','inputs.json','machine.snapshot.json','cases','sessions','epochs','control','diagnostics','sop-runtime','state.sqlite3','state.sqlite3-journal','inputs.tsv','tasks_status.tsv'})
        elif init:
            raise ValueError('INCOMPLETE_PREPARE_IDENTITY_MISMATCH')
        if any(q.name not in allowed for q in root.iterdir()):
            raise ValueError('NONEMPTY_UNRECOGNIZED_OUTPUT_ROOT: nothing was overwritten')
        atomic_json(initfile,{'time':now(),'runner':__version__,'identity':init_id})
        tasks=enumerate_inputs(c,p)
        manifest={'schema':1,'production_id':uuid.uuid4().hex,'runner_version':__version__,'created_at':now(),
          'protocol_sha256':identity(p),'inputs_sha256':identity(tasks),'n_inputs':len(tasks),
          'time_grid':time_grid(p),'initial_environment':facts,
          'validation_scope':'local engineering tests; target GPU online early-stop still requires first production execution evidence'}
        atomic_json(root/'protocol.snapshot.json',p); atomic_json(root/'inputs.json',tasks)
        atomic_json(root/'machine.snapshot.json',c); atomic_json(root/'preflight_report.json',facts)
        for name in ('cases','sessions','epochs','control','diagnostics'): (root/name).mkdir(exist_ok=True)
        snapshot_sop(c,root)
        db=Store(root); db.seed(tasks)
        for t in tasks:
            if t['input_error']: db.set(t['case_id'],'CONFIG_FAILED',detail={'input_error':t['input_error']})
        db.export(); db.close()
        s=io.StringIO(newline=''); w=csv.DictWriter(s,tasks[0].keys(),delimiter='\t',lineterminator='\n')
        w.writeheader(); w.writerows(tasks); atomic_bytes(root/'inputs.tsv',s.getvalue().encode())
        atomic_json(manfile,manifest)
        print('INPUTS=%d  INVALID_OR_DUPLICATE=%d'%(len(tasks),sum(bool(t['input_error']) for t in tasks)))
        print('CHECKPOINT_STEPS=%d  MAX_STEPS=%d'%(manifest['time_grid']['checkpoint_steps'],manifest['time_grid']['max_steps']))
        print('OUTPUT_ROOT='+str(root)); print('READY_FOR_PRODUCTION (not a scientific stability certificate)')
        return manifest


def verify_frozen(root,c=None,p=None,check_inputs=True,allow_runtime_change=False):
    root=Path(root); m=read_json(root/'production_manifest.json'); frozen=read_json(root/'protocol.snapshot.json'); tasks=read_json(root/'inputs.json')
    if identity(frozen)!=m['protocol_sha256'] or identity(tasks)!=m['inputs_sha256']: raise ValueError('FROZEN_MANIFEST_CHANGED')
    if p is not None and identity(p)!=m['protocol_sha256']: raise ValueError('PROTOCOL_CHANGED: choose new output root')
    c=c or read_json(root/'machine.snapshot.json'); c,facts=preflight(c)
    if c['paths']['output_root']!=str(root.resolve()): raise ValueError('OUTPUT_ROOT binding mismatch')
    if not allow_runtime_change:
        for key in ('lbpm_binary_sha256','mpirun_sha256','color_model_sha256','sop_prepare_sha256'):
            if facts[key]!=m['initial_environment'][key]:
                raise ValueError('RUNTIME_IDENTITY_CHANGED: '+key+'; explicit --accept-runtime-change required, and no bitwise equivalence is implied')
    if check_inputs:
        for t in tasks:
            f=Path(c['paths']['raw_root'])/t['raw_relative']
            if not f.is_file() or f.stat().st_size!=t['bytes'] or sha256(f)!=t['sha256']:
                raise ValueError('INPUT_IDENTITY_CHANGED: '+t['case_id'])
    return c,facts,frozen,tasks


def export_results(root,verify=False):
    root=Path(root); m=read_json(root/'production_manifest.json'); tasks=read_json(root/'inputs.json'); rows=[]
    state={x['case_id']:x for x in StoreRead(root)}
    for t in tasks:
        r={'case_id':t['case_id'],'family':t['family'],'valid':False,'status':state.get(t['case_id'],{}).get('status','PENDING'),
           'input_relative':t['raw_relative'],'input_sha256':t['sha256'],'sg_endpoint':'','stop_pvi':'','stop_reason':'',
           'phase_roi_relative':'','attempt_relative':'','protocol_sha256':m['protocol_sha256']}
        r['validation_error']=''
        try:
            com=read_json(root/'cases'/t['case_id']/'complete.json',{})
            if com:
                rowstate=state.get(t['case_id'],{})
                if rowstate.get('status') not in SUCCESS or rowstate.get('attempt')!=com.get('attempt_relative'):
                    raise ValueError('COMMIT_DATABASE_STATE_MISMATCH')
                if rowstate['status']!=com.get('status'):
                    raise ValueError('COMMIT_DATABASE_STATUS_MISMATCH')
                result=verify_commit(root,t['case_id'],com)
                d=inside(root,com['attempt_relative'])
                r.update(valid=True,status=com['status'],sg_endpoint=result['sg_endpoint'],stop_pvi=result['stop_nominal_pvi'],
                    stop_reason=result['stop_reason'],phase_roi_relative=str((d/'result/phase_final_roi.npy').relative_to(root)),
                    attempt_relative=com['attempt_relative'])
        except EpochRejected as exc:
            r.update(valid=False,status='INTERRUPTED',validation_error=str(exc))
        except (OSError,ValueError,KeyError,TypeError) as exc:
            r.update(valid=False,status='OUTPUT_FAILED',validation_error=str(exc))
        rows.append(r)
    text=io.StringIO(newline=''); w=csv.DictWriter(text,rows[0].keys(),lineterminator='\n'); w.writeheader(); w.writerows(rows)
    atomic_bytes(root/'dataset_index.csv',text.getvalue().encode())
    return rows


def StoreRead(root):
    # CLI and reports read only; never create a writer alongside the supervisor.
    import sqlite3
    uri=(Path(root)/'state.sqlite3').resolve().as_uri()+'?mode=ro'
    db=sqlite3.connect(uri,uri=True,timeout=30); db.row_factory=sqlite3.Row
    try: return [dict(r) for r in db.execute('SELECT * FROM tasks ORDER BY ordinal')]
    finally: db.close()
