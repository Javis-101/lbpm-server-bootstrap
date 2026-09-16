from __future__ import annotations
import contextlib
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from .util import Lock, proc_identity, processes, read_json, atomic_json, identity, token_processes, alive


def parse_ps(text):
    rows=[]; header=None
    for line in text.splitlines():
        words=line.split()
        if not words: continue
        if 'PID' in words and 'SERVER' in words:
            header=words; continue
        if not words[0].isdigit(): continue
        if not header: raise ValueError('MPS ps missing recognized header')
        try:
            row={key:words[header.index(key)] for key in ('PID','SERVER','NAMESPACE')}
            rows.append({'pid':int(row['PID']),'server':int(row['SERVER']),'namespace':int(row['NAMESPACE'])})
        except (ValueError,IndexError): raise ValueError('Unrecognized Legacy MPS ps layout')
    return rows


def termination_ok(text): return text.strip()=='0'


class MPS:
    def __init__(self,machine,root,env):
        self.machine=machine; self.root=Path(root); self.env=dict(env)
        base=machine['runtime']['mps_base'] or str(Path('/tmp')/('lbpm-runner-'+str(os.getuid())))
        self.dir=Path(base)/identity(str(self.root.resolve()))[:12]
        if len(os.fsencode(self.dir))>75: raise ValueError('MPS pipe path too long; set a short runtime.mps_base')
        self.pipe=self.dir/'pipe'; self.logs=self.root/'mps_logs'; self.bin=machine['paths']['mps_control']
        self.env['CUDA_MPS_PIPE_DIRECTORY']=str(self.pipe)
        self.env['CUDA_MPS_LOG_DIRECTORY']=str(self.logs)
        self.env['CUDA_MPS_PROTOCOL_VERSION']='2'
        self.env['CUDA_VISIBLE_DEVICES']=machine.get('_gpu',{}).get('uuid',machine['runtime']['gpu'])
        for k in ('CUDA_MPS_ACTIVE_THREAD_PERCENTAGE','CUDA_MPS_PINNED_DEVICE_MEM_LIMIT'):
            self.env.pop(k,None)
        self.timeout=machine['runtime']['mps_command_timeout']
    def request(self,command):
        self.dir.mkdir(parents=True,exist_ok=True)
        with Lock(self.dir/'control.lock',blocking=True):
            p=subprocess.run([self.bin],input=command+'\n',text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             env=self.env,timeout=self.timeout)
        if p.returncode!=0: raise RuntimeError('MPS_CONTROL_FAILED: '+p.stderr.strip()+' '+p.stdout.strip())
        if any(w in p.stdout.lower() for w in ('invalid command','unknown command','failed','error:')):
            raise RuntimeError('MPS_CONTROL_REJECTED: '+p.stdout.strip())
        return p.stdout
    def clients(self): return parse_ps(self.request('ps'))
    def start(self):
        self.dir.mkdir(parents=True,exist_ok=True,mode=0o700); os.chmod(self.dir,0o700)
        self.pipe.mkdir(exist_ok=True,mode=0o700); self.logs.mkdir(parents=True,exist_ok=True)
        owner_path=self.root/'mps_owner.json'; owner=read_json(owner_path,{})
        if owner.get('pipe')==str(self.pipe):
            try:
                self.clients()
                self.check_capability(); return 'REUSED_OWN_SERVICE'
            except Exception:
                pass
        others=[]
        for pid,args in processes():
            if Path(args[0]).name in ('nvidia-cuda-mps-control','nvidia-cuda-mps-server'):
                others.append((pid,args[0]))
        if others: raise RuntimeError('EXISTING_MPS_REFUSED (no unrelated daemon shutdown): '+str(others))
        p=subprocess.run([self.bin,'-d'],env=self.env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=self.timeout)
        if p.returncode: raise RuntimeError('MPS_START_FAILED: '+p.stderr.decode(errors='replace'))
        atomic_json(owner_path,{'pipe':str(self.pipe),'pid_namespace':os.readlink('/proc/self/ns/pid')})
        for _ in range(20):
            try:
                self.check_capability(); return 'STARTED'
            except Exception as exc: last=exc; time.sleep(.2)
        raise RuntimeError('MPS_CAPABILITY_UNAVAILABLE: '+str(last))
    def check_capability(self):
        try: helptext=self.request('help')
        except RuntimeError as exc:
            if not any(x in str(exc).lower() for x in ('invalid command','unknown command')): raise
            helptext=''
        if 'terminate_client' not in helptext:
            # Some releases omit the help listing. The binary must still expose the command name.
            if b'terminate_client' not in Path(self.bin).read_bytes():
                raise RuntimeError('MPS v2 terminate_client unavailable; refusing unsafe early-stop')
        self.clients()
    def find_client(self,token,run_dir,binary):
        namespace=int(os.readlink('/proc/self/ns/pid').split('[')[1][:-1])
        local=set(token_processes(token)); found=[]
        for row in self.clients():
            if row['namespace']!=namespace: continue
            pid=row['pid']
            if pid not in local: continue
            try:
                if Path('/proc',str(pid),'cwd').resolve()!=Path(run_dir).resolve(): continue
                if Path('/proc',str(pid),'exe').resolve()!=Path(binary).resolve(): continue
            except (FileNotFoundError,PermissionError): continue
            found.append(row)
        if len(found)!=1: raise RuntimeError('MPS_CLIENT_IDENTITY_NOT_UNIQUE: '+str(found))
        return found[0]
    def terminate(self,token,run_dir,binary):
        row=self.find_client(token,run_dir,binary); record=proc_identity(row['pid'])
        if record is None: raise RuntimeError('MPS_CLIENT_ALREADY_EXITED')
        answer=self.request('terminate_client %d %d'%(row['server'],row['pid']))
        if not termination_ok(answer):
            raise RuntimeError('MPS_TERMINATION_NOT_CONFIRMED: '+repr(answer))
        # NVIDIA requires successful CUDA context termination BEFORE host signals.
        if alive(record):
            with contextlib.suppress(ProcessLookupError): os.kill(row['pid'],signal.SIGTERM)
            for _ in range(20):
                if not alive(record): break
                time.sleep(.1)
            if alive(record):
                with contextlib.suppress(ProcessLookupError): os.kill(row['pid'],signal.SIGKILL)
        return {'server_pid':row['server'],'client_pid':row['pid'],'response':answer.strip(),'safe_context_termination':True}
    def stop_if_empty(self):
        if self.clients(): return False
        self.request('quit'); return True
