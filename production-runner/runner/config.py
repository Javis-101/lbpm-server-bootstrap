from __future__ import annotations
import copy
import os
import shutil
from pathlib import Path
try: import tomllib
except ImportError: from third_party import tomli as tomllib
from .protocol import default_protocol, validate

DEFAULTS={
 'paths':{'lbpm_root':'','lbpm_binary':'','mpirun':'','env_script':'','prepare_case':'',
          'raw_root':'','case_root':'','output_root':'','acceptance_report':'',
          'build_manifest':'','source_root':'','mps_control':'','nvidia_smi':'','libzstd':''},
 'runtime':{'gpu':'0','max_jobs':8,'poll_seconds':1.0,'refresh_seconds':5,
            'stall_seconds':900,'retry_interrupted_max':3,'prepare_timeout_seconds':300,
            'mps_base':'','mps_command_timeout':30,'queue_seed':20260915},
 'storage':{'compress_below_gib':10.0,'compress_until_gib':15.0,'pause_below_gib':5.0,
            'safety_gib':2.0,'compression_level':3,'release_verified_raw':True},
 'dataset':{'expected_count':1200,'families':['41','44','46','49','57','60'],'per_family':200},
 'identity':{'expected_commit':'6d686d354e5b8140841d3601e4c8c0e4e4b77e48',
             'expected_patchset':'outletlayersphase-fix-v1', 'expected_binary_sha256':''}}

ENV_KEYS={
 'LBPM_ROOT':('paths','lbpm_root'),'LBPM_BINARY':('paths','lbpm_binary'),
 'MPIRUN':('paths','mpirun'),'ENV_SCRIPT':('paths','env_script'),
 'PREPARE_CASE':('paths','prepare_case'),'RAW_ROOT':('paths','raw_root'),
 'CASE_ROOT':('paths','case_root'),'OUTPUT_ROOT':('paths','output_root'),
 'ACCEPTANCE_REPORT':('paths','acceptance_report'),'BUILD_MANIFEST':('paths','build_manifest'),
 'SOURCE_ROOT':('paths','source_root'),'MPS_CONTROL':('paths','mps_control'),
 'NVIDIA_SMI':('paths','nvidia_smi'),'LIBZSTD':('paths','libzstd'),
 'GPU':('runtime','gpu'),'MAX_JOBS':('runtime','max_jobs'),'MPS_BASE':('runtime','mps_base'),
 'COMPRESS_BELOW_GIB':('storage','compress_below_gib'),
 'COMPRESS_UNTIL_GIB':('storage','compress_until_gib')}


def strict_merge(dst,src,prefix=''):
    for k,v in src.items():
        if k not in dst: raise ValueError('Unknown config key: '+prefix+k)
        if isinstance(dst[k],dict):
            if not isinstance(v,dict): raise ValueError('Expected table: '+prefix+k)
            strict_merge(dst[k],v,prefix+k+'.')
        else: dst[k]=v
    return dst


def read_toml(path):
    with Path(path).open('rb') as f: return tomllib.load(f)


def expanded(value,base,environ):
    value=str(value)
    # Explicit env placeholders only; unresolved variables are errors.
    import re
    def sub(m):
        key=m.group(1) or m.group(2)
        if key not in environ: raise ValueError('Unset variable in path: '+key)
        return environ[key]
    value=re.sub(r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)',sub,value)
    p=Path(value).expanduser()
    return str((base/p).resolve()) if not p.is_absolute() else str(p.resolve())


def load_machine(path=None,overrides=None,environ=None):
    env=dict(os.environ if environ is None else environ); c=copy.deepcopy(DEFAULTS)
    provenance={}; base=Path.cwd()
    if path:
        path=Path(path).resolve(); base=path.parent; data=read_toml(path)
        strict_merge(c,data)
        for sec,table in data.items():
            for key in table: provenance[sec+'.'+key]='config'
    for suffix,(sec,key) in ENV_KEYS.items():
        var='LBPM_RUNNER_'+suffix
        if var in env:
            old=DEFAULTS[sec][key]; v=env[var]
            c[sec][key]=int(v) if type(old)==int else float(v) if type(old)==float else v
            provenance[sec+'.'+key]='environment'
    for dotted,v in (overrides or {}).items():
        if v is None: continue
        sec,key=dotted.split('.',1)
        if sec not in c or key not in c[sec]: raise ValueError('Unknown CLI key '+dotted)
        c[sec][key]=v; provenance[dotted]='CLI'
    for k,v in c['paths'].items():
        if v: c['paths'][k]=expanded(v,base,env)
    if c['runtime']['mps_base']: c['runtime']['mps_base']=expanded(c['runtime']['mps_base'],base,env)
    r=c['runtime']; s=c['storage']; d=c['dataset']
    if not isinstance(r['max_jobs'],int) or not 1<=r['max_jobs']<=8:
        raise ValueError('max_jobs must be an integer in 1..8 for this release')
    if not 0<s['pause_below_gib']<s['compress_below_gib']<s['compress_until_gib']:
        raise ValueError('Require 0 < pause < compress_below < compress_until')
    if not 1<=s['compression_level']<=9: raise ValueError('compression_level must be 1..9')
    if s['release_verified_raw'] is not True:
        raise ValueError('Space policy requires releasing ONLY verified redundant raw copies')
    if r['poll_seconds']<.1 or r['stall_seconds']<30: raise ValueError('Invalid poll/stall interval')
    if d['expected_count']!=d['per_family']*len(d['families']): raise ValueError('Dataset count mismatch')
    if len(set(d['families']))!=len(d['families']): raise ValueError('Duplicate families')
    c['_provenance']=provenance
    return c


def load_protocol(path=None):
    p=default_protocol()
    if path: strict_merge(p,read_toml(path))
    return validate(p)


def unique_existing(candidates,label):
    vals=sorted(set(str(Path(p).resolve()) for p in candidates if Path(p).exists()))
    if len(vals)>1: raise ValueError('MULTIPLE_'+label+': specify explicitly: '+', '.join(vals))
    return vals[0] if vals else ''


def discover(c):
    c=copy.deepcopy(c); p=c['paths']; root=Path(p['lbpm_root']) if p['lbpm_root'] else None
    if not p['lbpm_binary']:
        choices=[]
        if root: choices += [root/'install/LBPM/bin/lbpm_color_simulator',root/'bin/lbpm_color_simulator']
        elif shutil.which('lbpm_color_simulator'): choices=[Path(shutil.which('lbpm_color_simulator'))]
        p['lbpm_binary']=unique_existing(choices,'LBPM_BINARY')
    if root:
        for k,rel in [('env_script','lbpm_env.sh'),('mpirun','deps/openmpi/bin/mpirun'),
                      ('build_manifest','LBPM_BUILD_MANIFEST.txt'),('source_root','src/LBPM')]:
            if not p[k] and (root/rel).exists(): p[k]=str(root/rel)
    for key,cmd in [('mpirun','mpirun'),('mps_control','nvidia-cuda-mps-control'),('nvidia_smi','nvidia-smi')]:
        if not p[key]: p[key]=shutil.which(cmd) or ''
    # Only search a scoped sibling workspace, never an arbitrary root filesystem.
    if not p['prepare_case'] and root:
        workspace=root.parent
        p['prepare_case']=unique_existing(workspace.glob('lbpm-bootstrap-runs/*/work/LBPM-postinstall-SOP-*/bin/prepare_case.sh'),'SOP')
    for k in ['raw_root','output_root']:
        if not p[k]: raise ValueError('Specify paths.'+k+' (no data directory guessing)')
    if not p['case_root']: p['case_root']=str(Path(p['output_root'])/'prepared')
    return c
