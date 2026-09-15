from __future__ import annotations
import csv
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from .config import discover
from .util import sha256, atomic_json, atomic_bytes, read_json, now
from .zstd_stream import library


def runtime_env(c):
    env=dict(os.environ); script=c['paths'].get('env_script')
    if script:
        p=subprocess.run(['bash','-c','set -e; source "$1" >/dev/null; exec env -0','bash',script],
                         stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=20)
        if p.returncode: raise RuntimeError('ENV_SCRIPT_FAILED: '+p.stderr.decode(errors='replace')[-2000:])
        env={}
        for item in p.stdout.split(b'\0'):
            if b'=' in item:
                k,v=item.split(b'=',1); env[os.fsdecode(k)]=os.fsdecode(v)
    # The Python interpreter used for the runner must also be the SOP Python.
    env['PATH']=str(Path(sys.executable).parent)+os.pathsep+env.get('PATH','')
    env['OMP_NUM_THREADS']='1'; env['OPENBLAS_NUM_THREADS']='1'; env['MKL_NUM_THREADS']='1'
    env['OMPI_ALLOW_RUN_AS_ROOT']='1'; env['OMPI_ALLOW_RUN_AS_ROOT_CONFIRM']='1'
    return env


def sop_defaults(prep):
    f=Path(prep).parent.parent/'config.env'
    if not f.is_file(): return {}
    # This is the user's explicitly selected, trusted SOP config; never source auto-found arbitrary files.
    p=subprocess.run(['bash','-c','set -e; source "$1" >/dev/null; printf "%s\\0%s\\0" "${VALIDATION_DIR:-}" "${STACK_DIR:-}"','bash',str(f)],
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
    if p.returncode: raise RuntimeError('SOP_CONFIG_READ_FAILED')
    v=p.stdout.split(b'\0')
    return {'validation':os.fsdecode(v[0]),'stack':os.fsdecode(v[1])}


def preflight(c):
    c=discover(c); p=c['paths']; facts={'time':now(),'python':sys.version.split()[0], 'real_gpu_production_validation':'NOT_YET_PERFORMED'}
    if sys.platform!='linux': raise RuntimeError('Linux is required (inotify/procfs/Legacy MPS adapter)')
    if sys.version_info<(3,9): raise RuntimeError('Python >=3.9 required')
    import numpy as np
    facts['numpy']=np.__version__; facts['zstd_version']=library(p['libzstd']).ZSTD_versionNumber()
    for key in ('lbpm_binary','mpirun','mps_control','nvidia_smi'):
        f=Path(p[key]) if p[key] else None
        if not f or not f.is_file() or not os.access(f,os.X_OK): raise RuntimeError(key.upper()+'_NOT_EXECUTABLE: '+p[key])
    for key in ('prepare_case','env_script','build_manifest'):
        if not p[key] or not Path(p[key]).is_file() or not os.access(p[key],os.R_OK):
            raise RuntimeError(key.upper()+'_NOT_READABLE: '+p[key])
    if not Path(p['raw_root']).is_dir(): raise RuntimeError('RAW_ROOT_MISSING')
    out=Path(p['output_root']).resolve(); raw=Path(p['raw_root']).resolve(); cases=Path(p['case_root']).resolve()
    if out==raw or out in raw.parents or raw in out.parents or out==cases:
        raise RuntimeError('OUTPUT_ROOT must be distinct from and outside original RAW tree and existing case root')
    probe=out if out.exists() else out.parent
    while not probe.exists(): probe=probe.parent
    if not os.access(probe,os.W_OK): raise RuntimeError('OUTPUT_PARENT_NOT_WRITABLE')
    if not p['acceptance_report']:
        sd=sop_defaults(p['prepare_case'])
        if sd.get('validation'): p['acceptance_report']=str(Path(sd['validation'])/'acceptance_report.json')
    if not p['acceptance_report'] or not Path(p['acceptance_report']).is_file():
        raise RuntimeError('ACCEPTANCE_REPORT_MISSING: set paths.acceptance_report to existing SOP acceptance_report.json')
    report=read_json(p['acceptance_report'])
    if report.get('schema_version')!=1 or report.get('status')!='PASS':
        raise RuntimeError('Existing SOP acceptance report is not schema1 PASS')
    kv={}
    for line in Path(p['build_manifest']).read_text(errors='replace').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1); kv[k.strip()]=v.strip().strip('"\'')
    expected=c['identity']['expected_commit']; commit=kv.get('LBPM_COMMIT','')
    if len(commit)<7 or not expected.startswith(commit): raise RuntimeError('LBPM_COMMIT_MISMATCH: '+repr(commit))
    patch=c['identity']['expected_patchset']
    if patch not in kv.values() and not any(patch in v for k,v in kv.items() if 'PATCH' in k):
        raise RuntimeError('BUILD_MANIFEST_PATCHSET_NOT_CONFIRMED: '+patch)
    model=Path(p['source_root'])/'models/ColorModel.cpp'
    if not model.is_file(): raise RuntimeError('SOURCE_REQUIRED_TO_VERIFY_OUTLET_PATCH: set paths.source_root')
    text=model.read_text(errors='replace')
    block=re.search(r'if\s*\(\s*outlet_layers_phase\s*==\s*1\s*\)\s*\{([^}]+)',text)
    if not block or not re.search(r'outletA\s*=\s*1',block[1]) or not re.search(r'outletB\s*=\s*0',block[1]):
        raise RuntimeError('OUTLET_PHASE_PATCH_NOT_CONFIRMED: no source change will be made')
    bh=sha256(p['lbpm_binary'])
    if c['identity']['expected_binary_sha256'] and bh!=c['identity']['expected_binary_sha256']:
        raise RuntimeError('LBPM_BINARY_SHA256_MISMATCH')
    env=runtime_env(c)
    ldd=subprocess.run(['ldd',p['lbpm_binary']],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=15)
    if 'not found' in ldd.stdout: raise RuntimeError('LBPM_MISSING_SHARED_LIBRARY:\n'+ldd.stdout)
    gpu=subprocess.run([p['nvidia_smi'],'--query-gpu=index,uuid,name,driver_version,memory.total','--format=csv,noheader,nounits'],
        env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=20)
    if gpu.returncode: raise RuntimeError('NVIDIA_SMI_FAILED: '+gpu.stderr)
    rows=list(csv.reader(io.StringIO(gpu.stdout))); target=str(c['runtime']['gpu']); found=[]
    for row in rows:
        row=[x.strip() for x in row]
        if len(row)>=5 and target in (row[0],row[1]): found.append(dict(zip(['index','uuid','name','driver','memory_mib'],row)))
    if len(found)!=1: raise RuntimeError('GPU_SELECTION_NOT_UNIQUE: '+target)
    c['_gpu']=found[0]
    v=subprocess.run([p['mps_control'],'-v'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=10)
    facts.update(lbpm_binary_sha256=bh,mpirun_sha256=sha256(p['mpirun']),env_script_sha256=sha256(p['env_script']),
        build_manifest_sha256=sha256(p['build_manifest']),lbpm_commit=commit,patchset=patch,
        color_model_sha256=sha256(model),sop_prepare_sha256=sha256(p['prepare_case']),
        acceptance_sha256=sha256(p['acceptance_report']),gpu=c['_gpu'],mps_version=v.stdout.strip(),
        evidence_scope='Existing build manifest + source patch + binary hashes; not a fresh GPU execution certificate')
    return c,facts


def snapshot_sop(c,root):
    """Private adapter copy: never edit the installed SOP config.env."""
    root=Path(root); dst=root/'sop-runtime'; source=Path(c['paths']['prepare_case']).parent
    if dst.exists():
        # The source identity is frozen separately; refreshing is only while scheduler is stopped.
        shutil.rmtree(dst)
    dst.mkdir()
    shutil.copytree(source,dst/'bin',ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.log'))
    p=c['paths']
    (dst/'stack-env').mkdir(); (dst/'validation').mkdir()
    script='#!/usr/bin/env bash\nsource '+shlex.quote(p['env_script'])+'\n'
    if p.get('mpirun'):
        script+='export MPI_DIR='+shlex.quote(str(Path(p['mpirun']).parent.parent))+'\n'
    bin_dirs=[str(Path(p[k]).parent) for k in ('lbpm_binary','mpirun') if p.get(k)]
    if bin_dirs: script+='export PATH='+shlex.quote(':'.join(bin_dirs))+':"${PATH}"\n'
    atomic_bytes(dst/'stack-env/lbpm_env.sh',script.encode())
    shutil.copy2(p['acceptance_report'], dst/'validation/acceptance_report.json')
    vals={'STACK_DIR':str(dst/'stack-env'),'DATA_DIR':str(root),
          'VALIDATION_DIR':str(dst/'validation'),'SIMULATION_DIR':p['case_root']}
    atomic_bytes(dst/'config.env',''.join(k+'='+shlex.quote(v)+'\n' for k,v in vals.items()).encode())
    return str(dst/'bin'/Path(c['paths']['prepare_case']).name)
