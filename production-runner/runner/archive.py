from __future__ import annotations
import hashlib
import io
import os
import re
import tarfile
from pathlib import Path
from .util import Lock, sha256, read_json, atomic_json, fsync_dir, token_processes
from .zstd_stream import Writer, Reader


def pressure(free_gib,active,low=10,high=15): return free_gib < (high if active else low)


def safe_member(name):
    if not re.fullmatch(r'id_t[0-9]+\.raw',name): raise ValueError('Unsafe checkpoint member: '+repr(name))
    return name


def inventory(directory):
    out=[]
    for p in sorted(Path(directory).glob('id_t*.raw'),key=lambda x:int(safe_member(x.name)[4:-4])):
        if p.is_symlink() or not p.is_file(): raise ValueError('Checkpoint must be a regular file')
        out.append({'name':p.name,'size':p.stat().st_size,'sha256':sha256(p)})
    return out


def verify_archive(path,entries,libpath=''):
    expected={x['name']:x for x in entries}; seen=set()
    if len(expected)!=len(entries): raise ValueError('Duplicate archive inventory')
    with Path(path).open('rb') as f, Reader(f,libpath) as r, io.BufferedReader(r) as stream:
        with tarfile.open(fileobj=stream,mode='r|') as tar:
            for member in tar:
                safe_member(member.name)
                if not member.isfile() or member.name in seen or member.name not in expected:
                    raise ValueError('Unexpected/duplicate/non-file member')
                e=expected[member.name]
                if member.size!=e['size']: raise ValueError('Archived size mismatch')
                h=hashlib.sha256(); count=0
                with tar.extractfile(member) as data:
                    for b in iter(lambda:data.read(1024*1024),b''): h.update(b); count+=len(b)
                if count!=e['size'] or h.hexdigest()!=e['sha256']: raise ValueError('Archived hash mismatch')
                seen.add(member.name)
        while stream.read(1024*1024): pass  # validate checksum, frame termination and truncation
    if seen!=set(expected): raise ValueError('Archive missing checkpoint(s)')
    return True


def archive_attempt(directory,release=True,level=3,libpath=''):
    d=Path(directory)
    with Lock(d/'.archive.lock'):
        process=read_json(d/'process.json',{})
        if process.get('token') and token_processes(process['token']):
            raise RuntimeError('Refusing to archive an active attempt')
        final=d/'checkpoints.tar.zst'; meta=d/'archive_manifest.json'; partial=d/'checkpoints.tar.zst.partial'
        m=read_json(meta,{})
        if m:
            if not final.is_file() or sha256(final)!=m['archive_sha256']:
                raise ValueError('Committed archive missing/corrupt; RAW files retained')
            entries=m['files']; verify_archive(final,entries,libpath)
        else:
            entries=inventory(d)
            if not entries: return {'verified':True,'files':[],'saved_bytes':0}
            if final.exists():
                # Crash between archive rename and manifest commit. Raw files still exist.
                verify_archive(final,entries,libpath)
            else:
                with partial.open('wb') as f:
                    with Writer(f,level,libpath) as compressor:
                        with tarfile.open(fileobj=compressor,mode='w|',format=tarfile.USTAR_FORMAT) as tar:
                            for e in entries:
                                info=tarfile.TarInfo(e['name']); info.size=e['size']; info.mode=0o600; info.mtime=0
                                with (d/e['name']).open('rb') as raw: tar.addfile(info,raw)
                    f.flush(); os.fsync(f.fileno())
                verify_archive(partial,entries,libpath)
                if inventory(d)!=entries: raise ValueError('Input changed during archive; not committed')
                os.replace(partial,final); fsync_dir(d)
            m={'schema':1,'codec':'zstd','verified':True,'files':entries,
               'archive_sha256':sha256(final),'original_bytes':sum(e['size'] for e in entries),
               'archive_bytes':final.stat().st_size,'release_complete':False}
            atomic_json(meta,m)
        known={e['name'] for e in entries}
        if any(p.name not in known for p in d.glob('id_t*.raw')):
            raise ValueError('New checkpoints after archive freeze; refusing release')
        if release:
            # Verify ALL remaining duplicates before releasing even one.
            remaining=[]
            for e in entries:
                p=d/e['name']
                if p.exists():
                    if p.is_symlink() or p.stat().st_size!=e['size'] or sha256(p)!=e['sha256']:
                        raise ValueError('RAW changed; not deleting it')
                    remaining.append(p)
            for p in remaining: p.unlink()
            fsync_dir(d); m['release_complete']=True; atomic_json(meta,m)
        m['saved_bytes']=m['original_bytes']-m['archive_bytes'] if release else 0
        return m


def restore_attempt(directory,target,libpath=''):
    d=Path(directory); target=Path(target); m=read_json(d/'archive_manifest.json')
    archive=d/'checkpoints.tar.zst'
    if sha256(archive)!=m['archive_sha256']: raise ValueError('Archive hash mismatch')
    verify_archive(archive,m['files'],libpath)
    if target.exists() and any(target.iterdir()): raise ValueError('Restore target must be empty')
    target.mkdir(parents=True,exist_ok=True)
    with archive.open('rb') as f, Reader(f,libpath) as r, io.BufferedReader(r) as stream:
        with tarfile.open(fileobj=stream,mode='r|') as tar:
            for member in tar:
                safe_member(member.name)
                tmp=target/(member.name+'.partial'); dest=target/member.name
                with tar.extractfile(member) as src, tmp.open('xb') as out:
                    for b in iter(lambda:src.read(1024*1024),b''): out.write(b)
                    out.flush(); os.fsync(out.fileno())
                os.replace(tmp,dest)
        while stream.read(1024*1024): pass
    fsync_dir(target)
    for e in m['files']:
        if sha256(target/e['name'])!=e['sha256']: raise ValueError('Restore verification failed')
    return len(m['files'])
