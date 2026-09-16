#!/usr/bin/env python3
"""Build a deterministic source-only Runner ZIP; never bundle simulation data."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES={'runner','third_party','config','docs','tests','tools'}
FILES={'LICENSE','VERSION','README.md','README.zh-CN.md','CHANGELOG.md','run.sh','runner_cli.py','PACKAGE_FILES.json'}


def digest(data): return hashlib.sha256(data).hexdigest()


def build(out):
    out=Path(out).resolve()
    if out==ROOT or ROOT in out.parents:
        raise ValueError('Build artifacts must be outside the Runner source tree')
    inventory=json.loads((ROOT/'PACKAGE_FILES.json').read_text())
    for name,expected in inventory.items():
        path=(ROOT/name).resolve()
        if ROOT not in path.parents or digest(path.read_bytes())!=expected:
            raise ValueError('Source identity mismatch: '+name)
    data={}
    for path in sorted(ROOT.rglob('*')):
        rel=path.relative_to(ROOT)
        if '__pycache__' in rel.parts or '.pytest_cache' in rel.parts or path.suffix=='.pyc': continue
        if not path.is_file(): continue
        if len(rel.parts)==1 and rel.name not in FILES: continue
        if len(rel.parts)>1 and rel.parts[0] not in DIRECTORIES: continue
        if path.is_symlink(): raise ValueError('No symlinks in release payload: '+str(rel))
        data[rel.as_posix()]=path.read_bytes()
    data['SHA256SUMS']=''.join(digest(payload)+'  '+name+'\n' for name,payload in sorted(data.items())).encode()
    version=data['VERSION'].decode().strip()
    name='LBPM-Production-Runner-v'+version
    out.mkdir(parents=True,exist_ok=True)
    target=out/(name+'.zip')
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for relative,payload in sorted(data.items()):
            info=zipfile.ZipInfo(name+'/'+relative,date_time=(2026,9,15,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED; info.create_system=3
            info.external_attr=(0o100755 if relative.endswith('.sh') else 0o100644)<<16
            z.writestr(info,payload,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    checksum=digest(target.read_bytes())
    target.with_suffix('.zip.sha256').write_text(checksum+'  '+target.name+'\n')
    print(str(target)); print('SHA256='+checksum)
    return target


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',type=Path,required=True)
    build(p.parse_args().out)
