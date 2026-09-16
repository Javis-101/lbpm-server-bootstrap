from __future__ import annotations
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

GIB = 1024 ** 3
TERMINAL = {'SUCCEEDED_STANDARD', 'SUCCEEDED_ACCEPTED', 'CAP_REACHED',
            'NUMERICAL_FAILED', 'CONFIG_FAILED', 'RETRY_LIMIT', 'OUTPUT_FAILED'}
SUCCESS = {'SUCCEEDED_STANDARD', 'SUCCEEDED_ACCEPTED', 'CAP_REACHED'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def identity(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def fsync_dir(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def atomic_bytes(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.partial', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(name, path); fsync_dir(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError): os.unlink(name)


def atomic_json(path, value):
    atomic_bytes(path, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False).encode() + b'\n')


def read_json(path, default=None):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        if default is not None: return default
        raise


def durable_copy(src, dst):
    dst = Path(dst); dst.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+dst.name, suffix='.partial', dir=dst.parent)
    try:
        with open(src, 'rb') as a, os.fdopen(fd, 'wb') as b:
            shutil.copyfileobj(a, b, 1024 * 1024); b.flush(); os.fsync(b.fileno())
        os.replace(name, dst); fsync_dir(dst.parent)
    finally:
        with contextlib.suppress(FileNotFoundError): os.unlink(name)


def append_event(path, kind, **fields):
    line = {'time':now(), 'event':kind, **fields}
    with Path(path).open('a', encoding='utf-8') as f:
        f.write(json.dumps(line, ensure_ascii=False, allow_nan=False)+'\n'); f.flush(); os.fsync(f.fileno())


class Lock:
    def __init__(self, path, blocking=False): self.path=Path(path); self.blocking=blocking; self.f=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.f=self.path.open('a+')
        try: fcntl.flock(self.f,fcntl.LOCK_EX | (0 if self.blocking else fcntl.LOCK_NB))
        except BaseException: self.f.close(); self.f=None; raise RuntimeError('LOCKED: '+str(self.path))
        return self
    def __exit__(self,*args):
        if self.f: fcntl.flock(self.f,fcntl.LOCK_UN); self.f.close(); self.f=None


def proc_identity(pid):
    try:
        s=Path('/proc',str(pid),'stat').read_text()
        rest=s[s.rfind(')')+2:].split()
        if rest[0]=='Z': return None
        return {'pid':int(pid),'start_ticks':rest[19],
                'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'pid_namespace':os.readlink('/proc/self/ns/pid')}
    except (FileNotFoundError, ProcessLookupError, PermissionError, IndexError): return None


def alive(record):
    if not record: return False
    return proc_identity(record['pid']) == record


def processes():
    for p in Path('/proc').iterdir():
        if not p.name.isdigit(): continue
        try:
            args=(p/'cmdline').read_bytes().split(b'\0'); args=[x.decode(errors='replace') for x in args if x]
            if not args: continue
            yield int(p.name),args
        except (FileNotFoundError, ProcessLookupError, PermissionError): continue


def token_processes(token):
    needle=('LBPM_RUNNER_ATTEMPT_TOKEN='+token).encode()
    found=[]
    for pid,_ in processes():
        try:
            if needle in Path('/proc',str(pid),'environ').read_bytes().split(b'\0'): found.append(pid)
        except (FileNotFoundError,ProcessLookupError,PermissionError): pass
    return found


def safe_id(s):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',s) or s in {'.','..'}:
        raise ValueError('UNSAFE_CASE_ID: '+repr(s))
    return s


def inside(root, relative):
    root=Path(root).resolve(); p=(root/relative).resolve()
    if p==root or root not in p.parents: raise ValueError('PATH_ESCAPE: '+str(relative))
    return p


def atomic_immutable_link(src, dst):
    """Two names for the same immutable endpoint, avoiding another full-volume copy."""
    dst=Path(dst); dst.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+dst.name,dir=dst.parent); os.close(fd); os.unlink(tmp)
    try:
        os.link(src,tmp); os.replace(tmp,dst); fsync_dir(dst.parent)
    finally:
        with contextlib.suppress(FileNotFoundError): os.unlink(tmp)
