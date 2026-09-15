from __future__ import annotations
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
from .util import (Lock, atomic_json, read_json, atomic_bytes, append_event, now, identity,
                   proc_identity, alive, token_processes, sha256, inside, TERMINAL, SUCCESS, GIB)
from .state import Store
from .production import export_results
from .results import (commit_result, verify_commit, verify_epoch, EpochRejected, quarantine_commit)
from .environment import runtime_env
from .mps import MPS
from .protocol import time_grid
from .archive import archive_attempt, pressure
from .worker import finalize, logtext, NUMERIC


def reconcile_result(root, db, case, attempt_rel, outcome, existing=None):
    """Identical acceptance policy for startup, normal completion and rollback."""
    d=inside(root,attempt_rel)
    try:
        if existing is not None: verify_commit(root,case,existing)
        else: commit_result(root,case,attempt_rel,outcome)
    except EpochRejected as exc:
        quarantine_commit(root,case,exc)
        atomic_json(d/('outcome.rejected-'+uuid.uuid4().hex+'.json'),outcome)
        outcome={**outcome,'status':'INTERRUPTED','detail':str(exc)}
        atomic_json(d/'outcome.json',outcome)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        quarantine_commit(root,case,exc)
        outcome={**outcome,'status':'OUTPUT_FAILED','detail':str(exc)}
        # Keep original outcome/result bytes for diagnosis; DB rejects reuse.
    db.set(case,outcome['status'],attempt=attempt_rel,detail=outcome)
    return outcome


def recover_orphan(root,d,c,mps):
    """A dead Python watcher is not permission to launch a duplicate CUDA client."""
    pr=read_json(d/'process.json',{}); token=pr.get('token','')
    if token and token_processes(token):
        # Target only a positively identified CUDA process. Never broad pkill.
        clients=mps.clients()
        known_context=any(r['pid'] in token_processes(token) for r in clients)
        if known_context:
            record=mps.terminate(token,d,c['paths']['lbpm_binary']); atomic_json(d/'orphan_termination.json',record)
        else:
            for pid in token_processes(token):
                try: is_solver=Path('/proc',str(pid),'exe').resolve()==Path(c['paths']['lbpm_binary']).resolve()
                except (OSError, RuntimeError): is_solver=False
                if is_solver:
                    raise RuntimeError('ORPHAN_SOLVER_NOT_IDENTIFIABLE_IN_MPS; refusing host signal')
        launcher=pr.get('mpirun')
        if alive(launcher):
            with contextlib.suppress(ProcessLookupError): os.killpg(launcher['pid'],signal.SIGTERM)
            for _ in range(30):
                if not alive(launcher): break
                time.sleep(.1)
            if alive(launcher):
                with contextlib.suppress(ProcessLookupError): os.killpg(launcher['pid'],signal.SIGKILL)
        if token_processes(token): raise RuntimeError('ORPHAN_PROCESSES_REMAIN: '+str(d))
    if (d/'outcome.json').exists(): return
    job=read_json(d/'job.json'); p=read_json(Path(root)/'protocol.snapshot.json')
    intent=read_json(d/'stop_intent.json',{}); fault=read_json(inside(root,job['epoch_relative'])/'fault.json',{})
    if intent and not fault and not NUMERIC.search(logtext(d/'run.log')):
        rows=[]
        for line in logtext(d/'metrics.jsonl').splitlines():
            try: row=json.loads(line)
            except ValueError: continue
            if row.get('event')=='CHECKPOINT': rows.append(row)
        result=finalize(root,d,job['task'],p,rows,intent,'RECOVERED_DURABLE_ENDPOINT',None)
        status={'STANDARD':'SUCCEEDED_STANDARD','ACCEPTED':'SUCCEEDED_ACCEPTED','CAP_REACHED':'CAP_REACHED'}[intent['reason']]
        atomic_json(d/'outcome.json',{'status':status,'case_id':job['task']['case_id'],'ended_ns':time.time_ns(),
          'epoch_relative':job['epoch_relative'],'wall_seconds':0,'recovered_endpoint':True,
          'result_sha256':sha256(d/'result/result.json')})
    else:
        atomic_json(d/'outcome.json',{'case_id':job['task']['case_id'],'status':'INTERRUPTED','ended_ns':time.time_ns(),
           'epoch_relative':job['epoch_relative'],'wall_seconds':0,'detail':'No complete certified endpoint; task restarts from immutable initial state'})


def gpu_sample(c,env):
    p=subprocess.run([c['paths']['nvidia_smi'],'-i',c.get('_gpu',{}).get('uuid',c['runtime']['gpu']),
      '--query-gpu=utilization.gpu,memory.used,memory.total,power.draw','--format=csv,noheader,nounits'],
      env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=10)
    if p.returncode: return {'error':p.stderr.strip()}
    vals=[x.strip() for x in p.stdout.strip().split(',')]
    return dict(zip(['utilization_percent','memory_used_mib','memory_total_mib','power_watts'],vals))


def run_supervisor(root,session_file):
    root=Path(root).resolve(); session=read_json(root/'sessions'/session_file); c=session['machine']
    tasks=read_json(root/'inputs.json'); taskmap={t['case_id']:t for t in tasks}
    p=read_json(root/'protocol.snapshot.json'); grid=time_grid(p); env=runtime_env(c); mps=MPS(c,root,env)
    logs=root/'events.jsonl'; master=root/'master.log'; control=root/'control'; launched={}
    started=time.time(); gpu={}; gpu_time=0; arch_future=None; archdir=None; pressure_active=False; archived_bytes=0; archive_failed=False
    executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='lossless-archive')
    def event(kind,**kw):
        append_event(logs,kind,**kw)
        with master.open('a',encoding='utf-8') as f: f.write('['+now()+'] '+kind+' '+json.dumps(kw,ensure_ascii=False)+'\n'); f.flush()
    def request_pause(reason): atomic_json(control/'pause.json',{'time':now(),'reason':reason})
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda *_:request_pause('SUPERVISOR_SIGNAL_DRAIN'))
    db=None; mode='STARTING'; epoch=None
    try:
      with Lock(root/'.supervisor.lock'):
        atomic_json(root/'controller.json',{'process':proc_identity(os.getpid()),'session_file':session_file,'started_at':now()})
        initial=read_json(root/'status.json',{}); initial.update(mode='STARTING',safe_to_stop=False,time=now(),controller=proc_identity(os.getpid()))
        initial.pop('error',None); atomic_json(root/'status.json',initial)
        db=Store(root); db.seed(tasks); base_terminal=sum(r['status'] in TERMINAL for r in db.rows())
        mps.start(); event('MPS_READY',pipe=str(mps.pipe))
        # Reconcile durable per-case markers and attempt outcomes, not stale PID files alone.
        live_epochs=set()
        for row in db.rows():
            case=row['case_id']; case_dir=root/'cases'/case
            try: com=read_json(case_dir/'complete.json',{})
            except (OSError,ValueError) as exc:
                quarantine_commit(root,case,exc); db.set(case,'OUTPUT_FAILED',detail={'error':str(exc)}); continue
            if com:
                try:
                    rel=com['attempt_relative']; d=inside(root,rel); out=read_json(d/'outcome.json')
                    reconcile_result(root,db,case,rel,out,existing=com)
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    quarantine_commit(root,case,exc); db.set(case,'OUTPUT_FAILED',detail={'error':str(exc)})
                continue
            if row['status']=='OUTPUT_FAILED': continue
            if not row['attempt']:
                attempts=sorted((case_dir/'attempts').glob('attempt_*'))
                attempts=[a for a in attempts if (a/'job.json').is_file()]
                if not attempts: continue
                row['attempt']=str(attempts[-1].relative_to(root)); row['attempts']=len(attempts)
                db.set(case,'RUNNING',attempt=row['attempt'],attempts=row['attempts'])
            d=inside(root,row['attempt']); pr=read_json(d/'process.json',read_json(d/'worker_spawn.json',{})); job=read_json(d/'job.json',{})
            if alive(pr.get('worker')):
                db.set(case,'RUNNING'); live_epochs.add(job['epoch_relative']); continue
            if not (d/'outcome.json').exists(): recover_orphan(root,d,c,mps)
            out=read_json(d/'outcome.json',{})
            if out.get('status') in SUCCESS:
                out=reconcile_result(root,db,case,row['attempt'],out)
            else: db.set(case,out.get('status','INTERRUPTED'),detail=out)
        if len(live_epochs)>1: raise RuntimeError('MULTIPLE_LIVE_MPS_EPOCHS; refusing ambiguous takeover')
        if live_epochs: epoch=inside(root,next(iter(live_epochs)))
        else:
            if mps.clients(): raise RuntimeError('UNCLAIMED_MPS_CLIENTS; no duplicate work will be launched')
            epoch=root/'epochs'/uuid.uuid4().hex; epoch.mkdir()
        event('SUPERVISOR_READY',adopted_epochs=len(live_epochs),max_jobs=c['runtime']['max_jobs'])
        atomic_json(root/'ready.json',{'pid':os.getpid(),'time':now(),'session_file':session_file})
        last_export=0; seen_outcomes=set()
        while True:
            rows=db.rows(); active=[]
            for row in rows:
                if row['status']!='RUNNING' or not row['attempt']: continue
                d=inside(root,row['attempt']); pr=read_json(d/'process.json',read_json(d/'worker_spawn.json',{})); child=launched.get(row['attempt'])
                child_live=child is not None and child.poll() is None
                if child_live or alive(pr.get('worker')): active.append(row); continue
                if not (d/'outcome.json').exists():
                    recover_orphan(root,d,c,mps)
                out=read_json(d/'outcome.json')
                if out['status'] in SUCCESS:
                    out=reconcile_result(root,db,row['case_id'],row['attempt'],out)
                else: db.set(row['case_id'],out['status'],detail=out)
                event('TASK_END',case_id=row['case_id'],status=out['status'],wall_seconds=round(out.get('wall_seconds',0),1))
            # Roll back any recent commit newer than an abnormal GPU-client exit in this epoch.
            ft=read_json(epoch/'fault.json',{})
            if ft:
                for row in db.rows():
                    if row['status'] not in SUCCESS or not row['attempt']: continue
                    d=inside(root,row['attempt']); out=read_json(d/'outcome.json',{})
                    if out.get('epoch_relative')==str(epoch.relative_to(root)):
                        com=read_json(root/'cases'/row['case_id']/'complete.json',{})
                        reconcile_result(root,db,row['case_id'],row['attempt'],out,existing=com)
                mode='MPS_RECOVERY_DRAIN'
            rows=db.rows(); active=[r for r in rows if r['status']=='RUNNING']
            free=shutil.disk_usage(root).free/GIB; storage=c['storage']
            pressure_active=pressure(free,pressure_active,storage['compress_below_gib'],storage['compress_until_gib'])
            if arch_future and arch_future.done():
                try:
                    result=arch_future.result(); archived_bytes+=max(result.get('saved_bytes',0),0)
                    event('ARCHIVE_VERIFIED',attempt=str(archdir.relative_to(root)),files=len(result['files']),saved_bytes=result.get('saved_bytes',0))
                except Exception as exc:
                    archive_failed=True; request_pause('ARCHIVE_ERROR: '+str(exc)); event('ARCHIVE_FAILED',detail=str(exc))
                arch_future=None; archdir=None
            if pressure_active and arch_future is None and not archive_failed:
                for d in sorted((root/'cases').glob('*/attempts/*')):
                    if not (d/'outcome.json').exists() or not list(d.glob('id_t*.raw')): continue
                    pr=read_json(d/'process.json',{})
                    if alive(pr.get('worker')) or (pr.get('token') and token_processes(pr['token'])): continue
                    archdir=d
                    arch_future=executor.submit(archive_attempt,d,True,storage['compression_level'],c['paths']['libzstd'])
                    break
            atomic_json(root/'archive_status.json',{'active':arch_future is not None,'attempt':str(archdir.relative_to(root)) if archdir else None,
               'pressure_active':pressure_active,'session_released_bytes':archived_bytes,'free_gib':free})
            pause=(control/'pause.json').exists()
            if ft and not active:
                if not mps.stop_if_empty(): raise RuntimeError('MPS_CLIENTS_REMAIN_AFTER_FAULT_DRAIN')
                event('MPS_EPOCH_RESET',fault=ft)
                if pause: mode='PAUSED'; break
                epoch=root/'epochs'/uuid.uuid4().hex; epoch.mkdir(); mps.start(); ft={}
            # Reserve worst-case pending writes, plus one archive and safety headroom.
            bytes_per_case=grid['max_checkpoints']*128*128*134+12*1024*1024
            reserve=storage['safety_gib']+(len(active)+1)*bytes_per_case/GIB+2*bytes_per_case/GIB
            storage_block=free<max(storage['pause_below_gib'],reserve)
            if free<.25 and active:
                atomic_json(epoch/'interrupt.json',{'reason':'EMERGENCY_LOW_DISK'}); request_pause('EMERGENCY_LOW_DISK'); pause=True
            if pause: mode='DRAINING'
            elif ft: mode='MPS_RECOVERY_DRAIN'
            elif storage_block: mode='WAITING_FOR_STORAGE'
            else: mode='RUNNING'
            if not pause and not ft and not storage_block:
                candidates=[r for r in rows if r['status'] in ('PENDING','INTERRUPTED','INFRA_FAILED')]
                candidates.sort(key=lambda r:(r['status']!='PENDING',r['ordinal']))
                for row in candidates[:max(0,c['runtime']['max_jobs']-len(active))]:
                    if row['attempts']>=c['runtime']['retry_interrupted_max']:
                        db.set(row['case_id'],'RETRY_LIMIT',detail={'note':'interruption retry limit; not classified as a numerical failure'}); continue
                    t=taskmap[row['case_id']]
                    if t.get('input_error'): db.set(row['case_id'],'CONFIG_FAILED',detail={'error':t['input_error']}); continue
                    base=root/'cases'/row['case_id']/'attempts'; base.mkdir(parents=True,exist_ok=True)
                    number=max([int(x.name[8:]) for x in base.glob('attempt_*') if x.name[8:].isdigit()]+[0])+1
                    d=base/('attempt_%04d'%number); d.mkdir(); rel=str(d.relative_to(root))
                    job={'task':t,'token':uuid.uuid4().hex,'session_file':session_file,'epoch_relative':str(epoch.relative_to(root)),
                         'protocol_sha256':identity(p),'attempt_relative':rel}
                    atomic_json(d/'job.json',job)
                    db.set(row['case_id'],'RUNNING',attempt=rel,attempts=row['attempts']+1)
                    worker_env=dict(env); worker_env['LBPM_RUNNER_ATTEMPT_TOKEN']=job['token']
                    with (d/'worker.log').open('ab') as out:
                        child=subprocess.Popen([sys.executable,'-m','runner.cli','_worker','--output-root',str(root),'--attempt',rel],
                            cwd=Path(__file__).resolve().parent.parent,env=worker_env,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
                    atomic_json(d/'worker_spawn.json',{'worker':proc_identity(child.pid),'token':job['token']})
                    launched[rel]=child; event('TASK_START',case_id=row['case_id'],attempt=rel,worker_pid=child.pid)
            rows=db.rows(); counts=Counter(r['status'] for r in rows); terminal=sum(counts[s] for s in TERMINAL)
            completed_session=max(0,terminal-base_terminal); elapsed=time.time()-started
            eta=(len(tasks)-terminal)*elapsed/completed_session if completed_session>=8 and mode=='RUNNING' else None
            active_details=[]
            for row in rows:
                if row['status']=='RUNNING':
                    live=read_json(inside(root,row['attempt'])/'live.json',{})
                    active_details.append({'case_id':row['case_id'],'attempt':row['attempt'],**live})
            if time.time()-gpu_time>10:
                try: gpu=gpu_sample(c,env)
                except Exception as exc: gpu={'error':str(exc)}
                gpu_time=time.time()
            atomic_json(root/'status.json',{'time':now(),'mode':mode,'total':len(tasks),'terminal':terminal,
                'valid':sum(counts[s] for s in SUCCESS),'counts':dict(counts),'active':active_details,
                'session_elapsed_seconds':elapsed,'eta_seconds_estimate':eta,'eta_scope':'all inputs processed, not all valid labels; rough session throughput',
                'free_gib':free,'gpu':gpu,'archive':read_json(root/'archive_status.json',{}),'controller':proc_identity(os.getpid())})
            if time.time()-last_export>30: db.export(); export_results(root); last_export=time.time()
            if terminal==len(tasks) and not active_details:
                if arch_future is not None:
                    mode='ARCHIVE_DRAIN'
                else:
                    mode='COMPLETE'; break
            if pause and not active_details: mode='PAUSED'; break
            time.sleep(c['runtime']['poll_seconds'])
        if arch_future:
            try: arch_future.result()
            except Exception as exc: event('ARCHIVE_FAILED_ON_DRAIN',detail=str(exc))
        if not mps.stop_if_empty(): raise RuntimeError('UNEXPECTED_LIVE_MPS_CLIENTS_ON_DRAIN')
        db.export(); exported=export_results(root)
        status=read_json(root/'status.json',{}); status.update(mode=mode,time=now(),safe_to_stop=True,active=[])
        atomic_json(root/'status.json',status)
        event('SUPERVISOR_'+mode,valid=sum(r['valid'] for r in exported),total=len(tasks))
    except BaseException as exc:
        request_pause(type(exc).__name__+': '+str(exc)); event('SUPERVISOR_ERROR',detail=str(exc))
        status=read_json(root/'status.json',{}); status.update(mode='RECOVERY_REQUIRED',error=str(exc),time=now(),safe_to_stop=False)
        atomic_json(root/'status.json',status)
        # Workers are detached and self-contained. Do not kill their GPU contexts unsafely.
        return 2
    finally:
        executor.shutdown(wait=True)
        if db: db.close()
    return 0
