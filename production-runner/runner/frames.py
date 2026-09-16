from __future__ import annotations
import ctypes
import os
import re
import struct
from pathlib import Path
import numpy as np
from .util import sha256, read_json, atomic_json, fsync_dir


def read_rock(path,p):
    d=p['domain']; shape=(d['nz'],d['ny'],d['nx']); expected=int(np.prod(shape))
    if Path(path).stat().st_size!=expected: raise ValueError('RAW_SIZE_MISMATCH')
    a=np.fromfile(path,dtype=np.uint8).reshape(shape)
    if not np.all((a==0)|(a==1)): raise ValueError('RAW_LABELS_NOT_BINARY')
    pore=a==1
    if not pore.any(): raise ValueError('NO_PORE_VOXELS')
    return pore


def read_frame(path,pore,p):
    d=p['domain']; r=d['reservoir_layers']; shape=(d['nz']+2*r,d['ny'],d['nx'])
    if Path(path).stat().st_size!=int(np.prod(shape)): raise ValueError('INCOMPLETE_FRAME: '+str(path))
    before=Path(path).stat()
    a=np.fromfile(path,dtype=np.uint8).reshape(shape)
    after=Path(path).stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns): raise ValueError('FRAME_CHANGED_DURING_READ')
    if not np.all(a<=2): raise ValueError('INVALID_PHASE_LABEL')
    roi=a[r:r+d['nz']]
    if not np.array_equal(roi==0,~pore): raise ValueError('SOLID_GEOMETRY_CHANGED')
    gas=(roi==1)&pore; water=(roi==2)&pore; count=int(pore.sum())
    if int(gas.sum())+int(water.sum())!=count: raise ValueError('PHASE_ACCOUNTING_FAILED')
    return gas,float(gas.sum()/count),a


def validate_prepared(path,raw_hash,p):
    d=Path(path); mark=read_json(d/'CASE_PREPARED.json')
    if mark.get('status')!='PREPARED' or mark.get('case_preparation')!='PASS':
        raise ValueError('CASE_PREPARED marker is not PREPARED/PASS')
    if sha256(d/'rock.raw')!=raw_hash: raise ValueError('PREPARED_RAW_IDENTITY_MISMATCH')
    pore=read_rock(d/'rock.raw',p); x=p['domain']; r=x['reservoir_layers']
    a=np.fromfile(d/'rock_waterdrive.raw',dtype=np.uint8)
    if a.size!=x['nx']*x['ny']*(x['nz']+2*r): raise ValueError('PREPARED_DOMAIN_SIZE')
    a=a.reshape(x['nz']+2*r,x['ny'],x['nx'])
    if not np.array_equal(a[r:r+x['nz']],pore.astype(np.uint8)):
        raise ValueError('Initial ROI must be immutable geometry and all gas in pores')
    if not (np.all(a[:r]==2) and np.all(a[-r:]==1)): raise ValueError('RESERVOIR_PHASE_CONTRACT')
    expected=(x['nx']+2)*(x['ny']+2)*(x['nz']+2*r+2)
    if (d/'ID.00000').stat().st_size!=expected: raise ValueError('ID_SIZE_MISMATCH')
    hashes=mark.get('artifact_sha256',{})
    for name in ('case_manifest.json','connectivity_report.json','ID.00000'):
        if name in hashes and sha256(d/name)!=hashes[name]: raise ValueError('PREPARED_ARTIFACT_HASH_CHANGED: '+name)
    return pore


class CloseWatcher:
    """Linux inotify: do not consume a visible-but-still-open RAW as a checkpoint."""
    def __init__(self,directory):
        self.lib=ctypes.CDLL(None,use_errno=True)
        self.lib.inotify_init1.argtypes=[ctypes.c_int]; self.lib.inotify_init1.restype=ctypes.c_int
        self.lib.inotify_add_watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32]
        self.lib.inotify_add_watch.restype=ctypes.c_int
        self.fd=self.lib.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
        if self.fd<0: raise OSError(ctypes.get_errno(),'inotify_init1')
        self.wd=self.lib.inotify_add_watch(self.fd,os.fsencode(directory),0x8|0x80) # CLOSE_WRITE, MOVED_TO
        if self.wd<0:
            os.close(self.fd); raise OSError(ctypes.get_errno(),'inotify_add_watch')
    def drain(self):
        names=set()
        while True:
            try: data=os.read(self.fd,65536)
            except BlockingIOError: break
            if not data: break
            off=0
            while off<len(data):
                wd,mask,cookie,n=struct.unpack_from('iIII',data,off); off+=16
                name=data[off:off+n].split(b'\0')[0].decode(errors='surrogateescape'); off+=n
                if mask&0x4000: raise RuntimeError('INOTIFY_OVERFLOW: cannot certify complete live outputs')
                if mask&(0x8|0x80) and re.fullmatch(r'id_t[0-9]+\.raw',name): names.add(name)
        return names
    def close(self):
        if self.fd is not None: os.close(self.fd); self.fd=None
    def __enter__(self): return self
    def __exit__(self,*args): self.close()


def recover_owned_preparation(prepared, owner_file, production_id, raw_hash):
    """Preserve a interrupted SOP directory only when this production owns it.

    Called under the per-case preparation lock. Unknown existing data is never
    moved or removed. No geometry bytes are modified.
    """
    import uuid
    d=Path(prepared); owner=Path(owner_file)
    expected={'production_id':production_id,'raw_sha256':raw_hash}
    if d.is_symlink(): raise ValueError('PREPARED_SYMLINK_REFUSED')
    if d.exists():
        if (d/'CASE_PREPARED.json').is_file(): return
        if read_json(owner,{})!=expected:
            raise ValueError('UNOWNED_INCOMPLETE_PREPARED_DIRECTORY: '+str(d))
        backup=d.with_name(d.name+'.interrupted-prep-'+uuid.uuid4().hex)
        os.rename(d,backup); fsync_dir(d.parent)
    atomic_json(owner,expected)
