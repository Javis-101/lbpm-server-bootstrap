from __future__ import annotations
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import math


def default_protocol():
    return {'name':'GW-Ca2e4-R1-v1',
      'physics':{'capillary_number':.0002,'rhoA':.1,'rhoB':.1,'tauA':.78,'tauB':.92,
                 'alpha':.009,'beta':.90,'affinity':.2588190451,'wetting_convention':'SCAL',
                 'nominal_water_contact_angle_deg':75.0},
      'domain':{'nx':128,'ny':128,'nz':128,'reservoir_layers':3,'voxel_length_um':1.0,'bc':4},
      'stopping':{'check_pvi':.1,'max_pvi':4.0,'window_points':5,
        'standard':{'start_pvi':1.2,'max_dsg':.0005,'range_sg':.001,'max_flip':.001,'consecutive':4},
        'accepted':{'start_pvi':3.0,'max_dsg':.008,'range_sg':.025,'max_flip':.03,'consecutive':3}}}


def validate(p):
    d=p['domain']; x=p['physics']; s=p['stopping']
    if [d[k] for k in ('nx','ny','nz')]!=[128]*3 or d['reservoir_layers']!=3 or d['bc']!=4:
        raise ValueError('v1 supports the validated 128³ + 3+3 / BC4 geometry only')
    if x['wetting_convention']!='SCAL': raise ValueError('SCAL convention required by this adapter')
    if not (-1<=x['affinity']<=1): raise ValueError('affinity out of range')
    for k in ('capillary_number','rhoA','rhoB','alpha','beta'):
        if not math.isfinite(x[k]) or x[k]<=0: raise ValueError('Invalid '+k)
    if not all(math.isfinite(x[k]) for k in ('tauA','tauB')) or min(x['tauA'],x['tauB'])<=.5: raise ValueError('tau must exceed .5')
    if s['check_pvi']<=0 or s['max_pvi']<s['check_pvi'] or s['window_points']<2:
        raise ValueError('Invalid stopping grid')
    for k in ('standard','accepted'):
        q=s[k]
        if q['consecutive']<1 or q['start_pvi']<0: raise ValueError('Invalid confirmation')
        for key in ('max_dsg','range_sg','max_flip'):
            if not 0<=q[key]<=1: raise ValueError('Threshold must be a fraction, not percent')
    return p


def time_grid(p):
    validate(p); x=p['physics']; d=p['domain']; s=p['stopping']; D=lambda v:Decimal(str(v))
    mu=D(x['rhoB'])*(D(x['tauB'])-D('.5'))/D(3)
    n=D(d['nz'])*mu/(D(6)*D(x['alpha'])*D(x['capillary_number']))
    cp=int((n*D(s['check_pvi'])/2).to_integral_value(rounding=ROUND_HALF_UP))*2
    intervals=D(s['max_pvi'])/D(s['check_pvi'])
    if intervals!=intervals.to_integral_value(): raise ValueError('max_pvi must be on the nominal check grid')
    if cp<2: raise ValueError('check interval too small')
    count=int(intervals)
    return {'checkpoint_steps':cp,'max_steps':cp*count,'max_checkpoints':count,
      'steps_per_pvi_formula':float(n),'nominal_check_pvi':float(s['check_pvi']),
      'actual_check_pvi_formula':float(D(cp)/n),'actual_max_pvi_formula':float(D(cp*count)/n),
      'pvi_basis':'target flux / original ROI pore volume; nominal grid for rule thresholds'}


def step_number(pvi, dpvi):
    return int((Decimal(str(pvi))/Decimal(str(dpvi))).to_integral_value(rounding=ROUND_HALF_UP))


def evaluate(rows,p):
    """Replay causal R1 on complete contiguous checkpoints only. Returns last metrics and decision."""
    s=p['stopping']; n=s['window_points']; sc=ac=0; decision=None; last={}
    cap=step_number(s['max_pvi'],s['check_pvi'])
    for j,row in enumerate(rows):
        idx=j+1
        if row['index']!=idx: raise ValueError('Non-contiguous checkpoint sequence')
        if not (math.isfinite(row['sg']) and 0<=row['sg']<=1): raise ValueError('Invalid Sg')
        if row.get('flip') is not None and not 0<=row['flip']<=1: raise ValueError('Invalid flip')
        stat={'index':idx,'standard_count':sc,'accepted_count':ac,'standard_pass':False,'accepted_pass':False}
        if idx>=n:
            w=rows[j-n+1:j+1]; vals=[v['sg'] for v in w]
            delta=max(abs(vals[k]-vals[k-1]) for k in range(1,n))
            spread=max(vals)-min(vals); fl=max(v['flip'] for v in w[1:])
            def passed(q):
                return idx>=step_number(q['start_pvi'],s['check_pvi']) and delta<=q['max_dsg'] and spread<=q['range_sg'] and fl<=q['max_flip']
            sp=passed(s['standard']); ap=passed(s['accepted'])
            sc=sc+1 if sp else 0; ac=ac+1 if ap else 0
            stat.update(max_adjacent_dsg=delta,window_sg_range=spread,max_adjacent_flip=fl,
                        standard_count=sc,accepted_count=ac,standard_pass=sp,accepted_pass=ap)
            if sc>=s['standard']['consecutive']: decision={'index':idx,'reason':'STANDARD'}
            elif ac>=s['accepted']['consecutive']: decision={'index':idx,'reason':'ACCEPTED'}
        if decision is None and idx>=cap: decision={'index':idx,'reason':'CAP_REACHED'}
        last=stat
        if decision: break
    return last,decision


def replay(rows,p): return evaluate(rows,p)[1]


def render_input(p):
    g=time_grid(p); d=p['domain']; x=p['physics']; r=d['reservoir_layers']; nz=d['nz']+2*r
    return f'''// Generated from frozen production protocol. Do not edit in a running job.
Domain {{
 Filename = "rock_waterdrive.raw"
 ReadType = "8bit"
 N = {d['nx']}, {d['ny']}, {nz}
 n = {d['nx']}, {d['ny']}, {nz}
 nproc = 1, 1, 1
 ReadValues = 0, 1, 2
 WriteValues = 0, 1, 2
 BC = 4
 voxel_length = {d['voxel_length_um']:.12g}
 InletLayers = 0, 0, {r}
 OutletLayers = 0, 0, {r}
 InletLayersPhase = 2
 OutletLayersPhase = 1
}}
Color {{
 protocol = "core flooding"
 capillary_number = {x['capillary_number']:.12g}
 rhoA = {x['rhoA']:.12g}
 rhoB = {x['rhoB']:.12g}
 tauA = {x['tauA']:.12g}
 tauB = {x['tauB']:.12g}
 alpha = {x['alpha']:.12g}
 beta = {x['beta']:.12g}
 F = 0, 0, 0
 din = 1
 dout = 1
 ComponentLabels = 0
 ComponentAffinity = {x['affinity']:.12g}
 WettingConvention = "SCAL"
 Restart = false
 timestepMax = {g['max_steps']}
}}
Analysis {{
 N_threads = 1
 load_balance = "default"
 analysis_interval = {g['checkpoint_steps']}
 visualization_interval = {g['checkpoint_steps']}
 subphase_analysis_interval = 100000000
 restart_interval = 100000000
 restart_file = "Restart"
}}
Visualization {{
 save_8bit_raw = true
 save_phase_field = false
 save_pressure = false
 save_velocity = false
 write_silo = false
}}
FlowAdaptor {{
}}
'''
