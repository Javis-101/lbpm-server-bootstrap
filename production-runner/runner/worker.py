from __future__ import annotations
import contextlib
import csv
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import numpy as np
from .util import (now, read_json, atomic_json, atomic_bytes, durable_copy, sha256,
                   identity, append_event, proc_identity, alive, Lock, fsync_dir, inside, atomic_immutable_link)
from .protocol import time_grid, render_input, evaluate
from .frames import validate_prepared, read_frame, read_rock, CloseWatcher, recover_owned_preparation
from .environment import runtime_env
from .mps import MPS

NUMERIC=re.compile(r'SubPhase\.cpp:\s*NaN encountered|Failed assertion:\s*err\s*==\s*false',re.I)
INFRA=re.compile(r'CUDA_ERROR_(?:MPS_SERVER|ILLEGAL_ADDRESS|LAUNCH_FAILED)|out of memory|no space left|input/output error|segmentation fault|CUDA.*(?:failed|error)',re.I)


def classify_exit(rc,text):
    if NUMERIC.search(text): return 'NUMERICAL_FAILED'
    if INFRA.search(text): return 'INFRA_FAILED'
    if rc==0: return 'EXIT_OK'
    if rc in (137,143,-9,-15,-1): return 'INTERRUPTED'
    return 'INFRA_FAILED'


def first_fault(path,value):
    """Atomic first-writer-wins marker; no reader sees half JSON."""
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.fault-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(json.dumps(value).encode()); f.flush(); os.fsync(f.fileno())
        try: os.link(tmp,path); fsync_dir(path.parent)
        except FileExistsError: pass
    finally:
        with contextlib.suppress(FileNotFoundError): os.unlink(tmp)


def logtext(path):
    try: return Path(path).read_text(errors='replace')
    except FileNotFoundError: return ''


def save_metrics(d,rows):
    if not rows: return
    fields=sorted(set().union(*(r.keys() for r in rows)))
    s=io.StringIO(newline=''); w=csv.DictWriter(s,fields,lineterminator='\n'); w.writeheader(); w.writerows(rows)
    atomic_bytes(Path(d)/'metrics.csv',s.getvalue().encode())


def finalize(root,d,task,p,rows,intent,mode,exit_code):
    """Result files stay inside attempt. Supervisor alone publishes the case commit."""
    root=Path(root); d=Path(d); src=d/'endpoint.raw'
    if not intent or sha256(src)!=intent['frame_sha256']: raise ValueError('ENDPOINT_IDENTITY_MISMATCH')
    if intent['protocol_sha256']!=identity(p) or sha256(d/'rock.raw')!=task['sha256']:
        raise ValueError('ENDPOINT_PROTOCOL_OR_INPUT_MISMATCH')
    pore=read_rock(d/'rock.raw',p); gas,sg,full=read_frame(src,pore,p)
    if abs(sg-intent['sg'])>1e-14: raise ValueError('ENDPOINT_SG_MISMATCH')
    final=d/'result'; final.mkdir(exist_ok=True)
    atomic_immutable_link(src,final/'phase_final_full.raw')
    r=p['domain']['reservoir_layers']; roi=full[r:r+p['domain']['nz']]
    b=io.BytesIO(); np.save(b,roi,allow_pickle=False); atomic_bytes(final/'phase_final_roi.npy',b.getvalue())
    save_metrics(d,rows)
    files={name:sha256(final/name) for name in ('phase_final_full.raw','phase_final_roi.npy')}
    result={'schema':1,'case_id':task['case_id'],'family':task['family'],'input_sha256':task['sha256'],
        'protocol_sha256':identity(p),'label_definition':'gas saturation at the protocol-defined endpoint; not proof of asymptotic residual equilibrium',
        'phase_labels':{'0':'solid','1':'gas_A','2':'water_B'},'roi_shape_zyx':list(roi.shape),
        'dtype':'uint8','x_fastest':True,'pore_voxels':int(pore.sum()),'gas_voxels':int(gas.sum()),
        'sg_endpoint':sg,'stop_reason':intent['reason'],'stop_timestep':intent['timestep'],
        'stop_nominal_pvi':intent['nominal_pvi'],'stop_pvi_from_logged_target_flux':intent.get('pvi_target_flux'),
        'termination_mode':mode,'raw_exit_code':exit_code,'created_at':now(),'files':files,
        'attempt_relative':str(d.relative_to(root)), 'all_generated_checkpoints_retained':True}
    atomic_json(final/'result.json',result)
    return result


def run_worker(root,attempt_rel):
    root=Path(root).resolve(); d=inside(root,attempt_rel); job=read_json(d/'job.json')
    p=read_json(root/'protocol.snapshot.json'); session=read_json(root/'sessions'/job['session_file']); c=session['machine']
    task=job['task']; grid=time_grid(p); cp=grid['checkpoint_steps']; cap=grid['max_steps']
    token=job['token']; epoch=inside(root,job['epoch_relative']); faultpath=epoch/'fault.json'
    env=runtime_env(c); mps=MPS(c,root,env); env=mps.env
    env['LBPM_RUNNER_ATTEMPT_TOKEN']=token
    start=time.time(); start_ns=time.time_ns(); process=None; watcher=None; rows=[]; intent=None; safe=None
    event=d/'events.jsonl'; interrupted=[False]
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda *_:interrupted.__setitem__(0,True))
    atomic_json(d/'process.json',{'worker':proc_identity(os.getpid()),'token':token,'epoch_relative':job['epoch_relative']})
    def state(status,**kw):
        atomic_json(d/'live.json',{'case_id':task['case_id'],'status':status,'updated_at':now(),
            'elapsed_seconds':round(time.time()-start,1),'checkpoint_count':len(rows),
            'last_nominal_pvi':rows[-1]['nominal_pvi'] if rows else 0,
            'sg':rows[-1]['sg'] if rows else None, **kw})
    def outcome(status,**kw):
        end_ns=time.time_ns(); save_metrics(d,rows)
        atomic_json(d/'outcome.json',{'schema':1,'case_id':task['case_id'],'status':status,
          'started_at':start,'started_ns':start_ns,'ended_ns':end_ns,'wall_seconds':time.time()-start,
          'raw_count':len(list(d.glob('id_t*.raw'))),'epoch_relative':job['epoch_relative'],**kw})
        state(status,**kw); append_event(event,'OUTCOME',status=status)
    try:
        state('PREPARING'); append_event(event,'WORKER_START',token=token)
        raw=Path(c['paths']['raw_root'])/task['raw_relative']
        if sha256(raw)!=task['sha256']: raise ValueError('ORIGINAL_RAW_CHANGED')
        prepared=Path(c['paths']['case_root'])/task['case_id']
        with Lock(Path(c['paths']['case_root'])/'.runner-locks'/(task['case_id']+'.lock')):
            recover_owned_preparation(prepared,Path(c['paths']['case_root'])/'.runner-locks'/(task['case_id']+'.owner.json'),
                read_json(root/'production_manifest.json')['production_id'],task['sha256'])
            if not prepared.exists():
                cmd=['bash',str(root/'sop-runtime/bin/prepare_case.sh'),'--input',str(raw),
                     '--case-id',task['case_id'],'--case-dir',str(prepared),
                     '--voxel-length-um',str(p['domain']['voxel_length_um'])]
                with (d/'prepare.log').open('wb') as log:
                    prep=subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                        env=env,timeout=c['runtime']['prepare_timeout_seconds'])
                if prep.returncode: raise ValueError('SOP_PREPARATION_FAILED; inspect prepare.log; existing partial prepared directory retained')
            pore=validate_prepared(prepared,task['sha256'],p)
            for name in ('rock.raw','rock_waterdrive.raw','ID.00000','CASE_PREPARED.json','case_manifest.json','connectivity_report.json'):
                if (prepared/name).is_file(): durable_copy(prepared/name,d/name)
        if sha256(raw)!=task['sha256']: raise ValueError('ORIGINAL_RAW_CHANGED_DURING_PREPARATION')
        atomic_bytes(d/'input.db',render_input(p).encode())
        if (root/'control/pause.json').exists() or faultpath.exists():
            outcome('INTERRUPTED',detail='Paused before GPU launch'); return
        watcher=CloseWatcher(d); state('STARTING'); known=set(); last_update=time.monotonic()
        args=[c['paths']['mpirun'],'--bind-to','none','--stdin','none','-np','1',c['paths']['lbpm_binary'],'input.db']
        if os.geteuid()==0: args.insert(1,'--allow-run-as-root')
        with (d/'run.log').open('wb') as log:
            process=subprocess.Popen(args,cwd=d,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        pr=read_json(d/'process.json'); pr['mpirun']=proc_identity(process.pid); atomic_json(d/'process.json',pr)
        append_event(event,'LBPM_START',pid=process.pid,argv=args)
        stopping=False; stop_control_error=None; stop_try_at=0.0; interrupted_reason=None; flux=None
        while True:
            text=logtext(d/'run.log'); rc=process.poll()
            numerical=bool(NUMERIC.search(text))
            if flux is None:
                mm=re.search(r'\bflux\s*=\s*([+\-\deE.]+)',text)
                if mm: flux=float(mm[1])
            if numerical:
                first_fault(faultpath,{'attempt_relative':attempt_rel,'time_ns':time.time_ns(),'reason':'NUMERICAL_FAILED'})
            fault=read_json(faultpath,{})
            other_fault=fault and fault.get('attempt_relative')!=attempt_rel
            if other_fault: interrupted_reason='MPS_PEER_ABORT_QUARANTINE'
            elif interrupted[0]: interrupted_reason='WORKER_SIGNAL'
            elif (epoch/'interrupt.json').exists(): interrupted_reason='SUPERVISOR_REQUEST'
            if time.monotonic()-last_update>c['runtime']['stall_seconds'] and rc is None:
                interrupted_reason='NO_CHECKPOINT_WATCHDOG'
                first_fault(faultpath,{'attempt_relative':attempt_rel,'time_ns':time.time_ns(),'reason':interrupted_reason})
            known.update(watcher.drain())
            if rc is not None:
                # No producer remains after mpirun exit; recover close events missed by a final race.
                known.update(q.name for q in d.glob('id_t*.raw'))
            while intent is None and not numerical and not interrupted_reason:
                idx=len(rows)+1; ts=idx*cp; name='id_t%d.raw'%ts
                if name not in known or ts>cap: break
                gas,sg,arr=read_frame(d/name,pore,p)
                flip=None if not rows else float(np.count_nonzero(gas ^ previous)/int(pore.sum()))
                row={'index':idx,'timestep':ts,'nominal_pvi':idx*p['stopping']['check_pvi'],'sg':sg,'flip':flip,
                     'pvi_target_flux':ts*flux/int(pore.sum()) if flux is not None else None,
                     'observed_at':now(),'wall_since_start_s':time.time()-start}
                # Consistency check against source's target flux, not a claim of measured injection.
                if flux is not None:
                    expected=int(pore.sum())/grid['steps_per_pvi_formula']
                    if not np.isfinite(flux) or flux<=0 or abs(flux/expected-1)>.005:
                        raise ValueError('LOGGED_TARGET_FLUX_DISAGREES_WITH_PVI_FORMULA')
                rows.append(row); previous=gas.copy(); stat,decision=evaluate(rows,p); row.update(stat)
                append_event(d/'metrics.jsonl','CHECKPOINT',**row)
                last_update=time.monotonic(); state('RUNNING',last_metrics=row)
                if decision:
                    durable_copy(d/name,d/'endpoint.raw')
                    intent={**decision,'sg':sg,'timestep':ts,'nominal_pvi':row['nominal_pvi'],
                      'pvi_target_flux':row['pvi_target_flux'],'frame_name':name,'frame_sha256':sha256(d/'endpoint.raw'),
                      'protocol_sha256':identity(p),'created_ns':time.time_ns(),
                      'log_prefix_bytes':(d/'run.log').stat().st_size}
                    atomic_json(d/'stop_intent.json',intent)
                    append_event(event,'STOP_DECISION',**intent)
                    break
            rc=process.poll()
            # Natural cap exit requires no MPS termination. Early decisions and interruptions do.
            need_stop=(intent is not None and intent['reason']!='CAP_REACHED') or bool(interrupted_reason)
            if need_stop and rc is None and safe is None and time.monotonic()>=stop_try_at:
                try:
                    safe=mps.terminate(token,d,c['paths']['lbpm_binary']); atomic_json(d/'mps_termination.json',safe)
                    append_event(event,'SAFE_MPS_TERMINATION',**safe); stopping=True
                except Exception as exc:
                    stop_control_error=str(exc); stop_try_at=time.monotonic()+5
                    state('STOP_CONTROL_BLOCKED',detail=stop_control_error)
                    atomic_json(root/'control/pause.json',{'reason':'STOP_CONTROL_BLOCKED','attempt':attempt_rel,'detail':stop_control_error})
                    # Never send an unsafe host signal. Keep monitoring the existing process.
            if safe and process.poll() is None:
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if alive(pr.get('mpirun')):
                        with contextlib.suppress(ProcessLookupError): os.killpg(process.pid,signal.SIGTERM)
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        if alive(pr.get('mpirun')):
                            with contextlib.suppress(ProcessLookupError): os.killpg(process.pid,signal.SIGKILL)
                        process.wait(timeout=3)
            rc=process.poll()
            if rc is not None: break
            if not stop_control_error: state('STOPPING' if stopping else 'RUNNING',last_metrics=rows[-1] if rows else None)
            time.sleep(c['runtime']['poll_seconds'])
        atomic_bytes(d/'exit_code.txt',(str(rc)+'\n').encode()); atomic_bytes(d/'wall_seconds.txt',(str(time.time()-start)+'\n').encode())
        text=logtext(d/'run.log'); classification=classify_exit(rc,text)
        if classification=='NUMERICAL_FAILED':
            first_fault(faultpath,{'attempt_relative':attempt_rel,'time_ns':time.time_ns(),'reason':classification})
            outcome(classification,exit_code=rc); return
        fault=read_json(faultpath,{})
        if interrupted_reason or (fault and fault.get('attempt_relative')!=attempt_rel):
            outcome('INTERRUPTED',exit_code=rc,detail=interrupted_reason or 'MPS_PEER_ABORT_QUARANTINE'); return
        if intent and (safe or rc==0):
            mode='MPS_SAFE_EARLY_STOP' if safe else 'NATURAL_EXIT'
            result=finalize(root,d,task,p,rows,intent,mode,rc)
            status={'STANDARD':'SUCCEEDED_STANDARD','ACCEPTED':'SUCCEEDED_ACCEPTED','CAP_REACHED':'CAP_REACHED'}[intent['reason']]
            outcome(status,exit_code=rc,result_sha256=sha256(d/'result/result.json'),stop_control_warning=stop_control_error)
        else:
            status=classification if classification!='EXIT_OK' else 'OUTPUT_FAILED'
            if status in ('INFRA_FAILED','INTERRUPTED'):
                first_fault(faultpath,{'attempt_relative':attempt_rel,'time_ns':time.time_ns(),'reason':status})
            outcome(status,exit_code=rc,detail='No valid committed endpoint' if status=='OUTPUT_FAILED' else '')
    except BaseException as exc:
        detail=type(exc).__name__+': '+str(exc)
        # Do not orphan an active CUDA producer and then pretend its slot is free.
        if process is not None and process.poll() is None:
            first_fault(faultpath,{'attempt_relative':attempt_rel,'time_ns':time.time_ns(),'reason':'WORKER_EXCEPTION'})
            atomic_json(root/'control/pause.json',{'reason':'WORKER_EXCEPTION','attempt':attempt_rel,'detail':detail})
            try:
                safe=mps.terminate(token,d,c['paths']['lbpm_binary']); atomic_json(d/'mps_termination.json',safe)
                process.wait(timeout=10)
            except Exception as stop_exc:
                state('ORPHAN_REQUIRES_RECOVERY',detail=detail+'; '+str(stop_exc))
                append_event(event,'LIVE_PROCESS_LEFT_UNSIGNALED',detail=str(stop_exc))
                return
        outcome('CONFIG_FAILED' if process is None else 'OUTPUT_FAILED',detail=detail)
    finally:
        if watcher: watcher.close()
