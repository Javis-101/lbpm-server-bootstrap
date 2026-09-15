from __future__ import annotations
import argparse
import contextlib
import io
import json
import os
import platform
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path
from . import __version__
from .config import load_machine, load_protocol, discover
from .util import atomic_json, read_json, now, Lock, alive, proc_identity, sha256, inside, SUCCESS, TERMINAL
from .production import prepare, verify_frozen, export_results, StoreRead
from .environment import snapshot_sop, runtime_env
from .supervisor import run_supervisor
from .worker import run_worker
from .archive import restore_attempt

PACKAGE=Path(__file__).resolve().parent.parent


def overrides(a):
    d={}
    for k in ('output_root','raw_root','case_root','lbpm_root','lbpm_binary','mpirun','env_script','prepare_case','acceptance_report'):
        if getattr(a,k,None) is not None: d['paths.'+k]=getattr(a,k)
    for k in ('max_jobs','gpu'):
        if getattr(a,k,None) is not None: d['runtime.'+k]=getattr(a,k)
    return d


def machine(a):
    return load_machine(a.config or PACKAGE/'config/rivermind.toml',overrides(a))


def output_root(a):
    # Read-only commands never source scripts or require a working GPU.
    return Path(machine(a)['paths']['output_root']).resolve()


def verify_package():
    manifest=read_json(PACKAGE/'PACKAGE_FILES.json')
    bad=[]
    for name,h in manifest.items():
        f=inside(PACKAGE,name)
        if not f.is_file() or sha256(f)!=h: bad.append(name)
    if bad: raise RuntimeError('PACKAGE_CODE_HASH_MISMATCH: '+', '.join(bad))
    return len(manifest)


def launch(a):
    root=output_root(a)
    if not (root/'production_manifest.json').is_file(): raise RuntimeError('PREPARE_REQUIRED: run prepare first')
    with Lock(root/'.launch.lock'):
        controller=read_json(root/'controller.json',{})
        if alive(controller.get('process')):
            print('ALREADY_RUNNING pid=%d; no duplicate launch'%controller['process']['pid']); return 0
        # Assert no other supervisor owns the dataset lock before changing runtime snapshots.
        with Lock(root/'.supervisor.lock'):
            c,facts,p,tasks=verify_frozen(root,machine(a),load_protocol(a.protocol or PACKAGE/'config/protocol.toml'),
                   check_inputs=True,allow_runtime_change=a.accept_runtime_change)
            # Runtime migration is not allowed while old workers or CUDA clients remain alive.
            old=read_json(root/'machine.snapshot.json')
            active=False
            for f in (root/'cases').glob('*/attempts/*/process.json'):
                pr=read_json(f)
                if alive(pr.get('worker')) or alive(pr.get('mpirun')): active=True; break
            if active and (c['paths']!=old['paths'] or c['runtime']!=old['runtime']):
                raise RuntimeError('Cannot migrate paths/runtime while attempts are alive; recover using original binding first')
            if not active: snapshot_sop(c,root)
            atomic_json(root/'machine.snapshot.json',c)
            session_file=uuid.uuid4().hex+'.json'
            atomic_json(root/'sessions'/session_file,{'created_at':now(),'machine':c,'environment':facts,
                'runtime_change_explicitly_accepted':a.accept_runtime_change,'runner_version':__version__})
            # Clear a manual/error pause only on an explicit start/resume, never from a worker.
            with contextlib.suppress(FileNotFoundError): (root/'control/pause.json').unlink()
        if a.foreground: return run_supervisor(root,session_file)
        with (root/'supervisor.log').open('ab') as log:
            proc=subprocess.Popen([sys.executable,'-m','runner.cli','_daemon','--output-root',str(root),'--session',session_file],
                cwd=PACKAGE,env=runtime_env(c),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        for _ in range(150):
            ready=read_json(root/'ready.json',{})
            if ready.get('session_file')==session_file:
                print('PRODUCTION_STARTED pid=%d\nOUTPUT_ROOT=%s'%(proc.pid,root))
                print('查看: bash run.sh status --watch --config '+str(a.config or 'config/rivermind.toml'))
                return 0
            if proc.poll() is not None:
                status=read_json(root/'status.json',{}); raise RuntimeError('START_FAILED: '+status.get('error','see supervisor.log'))
            time.sleep(.2)
        print('START_PENDING pid=%d; inspect supervisor.log / status. Do not start another runner.'%proc.pid)
        return 0


def status(a):
    root=output_root(a)
    while True:
        s=read_json(root/'status.json',{}); controller=read_json(root/'controller.json',{})
        if a.watch and sys.stdout.isatty(): print('\033[2J\033[H',end='')
        print('LBPM Production Runner '+__version__+' | '+str(root))
        print('快照时间: '+str(s.get('time','尚未启动'))+' | 调度器: '+('存活' if alive(controller.get('process')) else '未运行'))
        print('状态: '+str(s.get('mode','PREPARED' if (root/'production_manifest.json').exists() else 'NOT_PREPARED')))
        if s.get('error'): print('需要处理: '+s['error'])
        counts=s.get('counts',{}); total=s.get('total',read_json(root/'production_manifest.json',{}).get('n_inputs',0))
        print('输入处理: %d/%d | 有效标签: %d | 数值失败: %d | 中断/重试: %d | 活跃: %d'%(
            s.get('terminal',0),total,s.get('valid',0),counts.get('NUMERICAL_FAILED',0),
            counts.get('INTERRUPTED',0)+counts.get('INFRA_FAILED',0),len(s.get('active',[]))))
        if 'free_gib' in s: print('数据盘可用: %.2f GiB | GPU: %s'%(s['free_gib'],json.dumps(s.get('gpu',{}),ensure_ascii=False)))
        arc=s.get('archive',{}); print('归档: '+str(arc.get('attempt') or '空闲')+' | 保留所有已产生检查点')
        eta=s.get('eta_seconds_estimate')
        if eta is not None and alive(controller.get('process')):
            print('全输入处理完毕 ETA（粗估）: %.1f～%.1f 小时；不是保证1200个有效标签'%(eta*.8/3600,eta*1.3/3600))
        else: print('ETA: 暂无足够实时吞吐数据，或生产已暂停/结束')
        print('CASE       WORKER_STATE             PVI(last)   Sg       STD ACC   elapsed(min)')
        for r in s.get('active',[]):
            m=r.get('last_metrics') or {}; sg=r.get('sg')
            print('%-10s %-23s %7.2f %8s   %s/4 %s/3 %8.1f'%(r['case_id'],r.get('status','STARTING'),
                r.get('last_nominal_pvi',0),'--' if sg is None else '%.3f%%'%(sg*100),
                m.get('standard_count',0),m.get('accepted_count',0),r.get('elapsed_seconds',0)/60))
        if s.get('safe_to_stop'): print('SAFE_TO_STOP: 当前受管任务已结束；不会自动关机。')
        print('只读面板；Ctrl+C 仅退出查看。')
        if not a.watch: return 0
        try: time.sleep(a.interval)
        except KeyboardInterrupt: return 0


def diagnose(a):
    root=output_root(a); target=root/'diagnostics'/('diagnose-'+time.strftime('%Y%m%dT%H%M%S')+'.tar.gz')
    target.parent.mkdir(exist_ok=True)
    with tarfile.open(target,'w:gz') as tar:
        for name in ('production_manifest.json','preflight_report.json','status.json','archive_status.json','tasks_status.tsv','dataset_index.csv','events.jsonl','master.log','supervisor.log'):
            f=root/name
            if not f.is_file(): continue
            data=f.read_bytes()[-256*1024:]; info=tarfile.TarInfo(name); info.size=len(data); tar.addfile(info,io.BytesIO(data))
        for row in StoreRead(root):
            if row['status'] in SUCCESS or not row['attempt']: continue
            d=inside(root,row['attempt'])
            for name in ('outcome.json','live.json','worker.log','run.log','prepare.log'):
                f=d/name
                if f.is_file():
                    data=f.read_bytes()[-8192:]; info=tarfile.TarInfo(row['case_id']+'/'+name); info.size=len(data); tar.addfile(info,io.BytesIO(data))
    print('DIAGNOSTIC='+str(target)); print('不含RAW、密钥或整份环境变量；日志可能含用户名和绝对路径，分享前可检查。')
    return 0


def parser():
    p=argparse.ArgumentParser(description='LBPM task-level resumable production runner (no solver source modification)')
    p.add_argument('--version',action='version',version=__version__)
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('prepare','show-config','start','resume','status','pause','export','diagnose','restore','verify-package','selftest','_worker','_daemon'):
        q=sub.add_parser(name)
        q.add_argument('--config',type=Path); q.add_argument('--protocol',type=Path)
        for key in ('output_root','raw_root','case_root','lbpm_root','lbpm_binary','mpirun','env_script','prepare_case','acceptance_report'):
            q.add_argument('--'+key.replace('_','-'))
        q.add_argument('--gpu'); q.add_argument('--max-jobs',type=int)
        if name in ('start','resume'):
            q.add_argument('--accept-runtime-change',action='store_true'); q.add_argument('--foreground',action='store_true')
        if name=='status':
            q.add_argument('--watch',action='store_true'); q.add_argument('--interval',type=float,default=5)
        if name=='pause': q.add_argument('--drain',action='store_true',help='Always drains; there is no unsafe kill option')
        if name in ('restore','_worker'): q.add_argument('--attempt',required=True,help='Relative attempt path shown in index/status')
        if name=='restore': q.add_argument('--dest',type=Path,required=True)
        if name=='_daemon': q.add_argument('--session',required=True)
    return p


def main(argv=None):
    os.umask(0o077)
    a=parser().parse_args(argv)
    try:
        if a.command=='verify-package': print('PACKAGE_CODE_FILES_VERIFIED='+str(verify_package())); return 0
        if a.command=='selftest':
            return subprocess.call([sys.executable,'-m','unittest','discover','-s',str(PACKAGE/'tests'),'-v'],cwd=PACKAGE)
        if a.command in ('prepare','start','resume'): verify_package()
        if a.command=='show-config': print(json.dumps(discover(machine(a)),indent=2,ensure_ascii=False)); return 0
        if a.command=='prepare': prepare(machine(a),load_protocol(a.protocol or PACKAGE/'config/protocol.toml')); return 0
        if a.command in ('start','resume'): return launch(a)
        if a.command=='status': return status(a)
        if a.command=='pause':
            root=output_root(a)
            if not (root/'production_manifest.json').exists(): raise RuntimeError('PREPARE_REQUIRED')
            atomic_json(root/'control/pause.json',{'time':now(),'reason':'USER_REQUESTED_DRAIN'})
            print('DRAIN_REQUESTED: 不再接新任务；已有任务自然收尾。用 status 查看 SAFE_TO_STOP。'); return 0
        if a.command=='export':
            rows=export_results(output_root(a),verify=True); print('INDEX_ROWS=%d VALID=%d'%(len(rows),sum(r['valid'] for r in rows))); return 0
        if a.command=='diagnose': return diagnose(a)
        if a.command=='restore':
            root=output_root(a); c=read_json(root/'machine.snapshot.json')
            n=restore_attempt(inside(root,a.attempt),a.dest,c['paths']['libzstd']); print('RESTORED_CHECKPOINTS='+str(n)); return 0
        if a.command=='_worker': run_worker(Path(a.output_root),a.attempt); return 0
        if a.command=='_daemon': return run_supervisor(Path(a.output_root),a.session)
    except KeyboardInterrupt:
        print('Command interrupted; detached production workers are not killed.',file=sys.stderr); return 130
    except Exception as exc:
        print('ERROR: '+type(exc).__name__+': '+str(exc),file=sys.stderr); return 2
    return 0

if __name__=='__main__': raise SystemExit(main())
