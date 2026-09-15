"""One fail-closed result trust boundary for commit, recovery and export.

This verifies recorded engineering evidence, not physical convergence or GPU
correctness. Files rejected here remain on disk for diagnosis.
"""
from __future__ import annotations
import os
import uuid
from functools import lru_cache
from pathlib import Path
from .util import (SUCCESS, atomic_json, fsync_dir, identity, inside, now,
                   read_json, safe_id, sha256)


class EpochRejected(ValueError):
    """An attempt cannot be trusted in its recorded MPS execution epoch."""


def _stamp(path):
    s = Path(path).stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


@lru_cache(maxsize=8192)
def _hash_unchanged(path, stamp):
    digest = sha256(path)
    if _stamp(path) != stamp:
        raise ValueError('RESULT_CHANGED_DURING_VERIFICATION: ' + path)
    return digest


def checked_hash(path):
    """Reuse hashes only in this process while inode/size/mtime/ctime match.

    A fresh resume process rehashes. The cache is not a defense against an
    adversarial filesystem; storage is assumed to provide truthful metadata.
    """
    path = str(Path(path).resolve())
    return _hash_unchanged(path, _stamp(path))


def verify_epoch(root, job, outcome):
    rel = job.get('epoch_relative')
    if not isinstance(rel, str) or Path(rel).parts[:1] != ('epochs',) or len(Path(rel).parts) != 2:
        raise EpochRejected('MPS_EPOCH_IDENTITY_MISSING')
    if outcome.get('epoch_relative') != rel:
        raise EpochRejected('MPS_EPOCH_IDENTITY_MISMATCH')
    epoch = inside(root, rel)
    if not epoch.is_dir():
        raise EpochRejected('MPS_EPOCH_DIRECTORY_MISSING')
    ended = outcome.get('ended_ns')
    if type(ended) is not int or ended <= 0:
        raise EpochRejected('MPS_OUTCOME_TIME_MISSING')
    fault_path = epoch / 'fault.json'
    try:
        fault_exists = fault_path.exists()
        fault = read_json(fault_path) if fault_exists else None
    except (OSError, ValueError) as exc:
        raise EpochRejected('MPS_FAULT_RECORD_UNREADABLE') from exc
    if fault_exists:
        when = fault.get('time_ns') if isinstance(fault, dict) else None
        if type(when) is not int or when <= 0:
            raise EpochRejected('MPS_FAULT_TIME_INVALID')
        if fault.get('attempt_relative') == job.get('attempt_relative') or ended >= when:
            raise EpochRejected('QUARANTINED_AFTER_PEER_MPS_ABORT')
    return rel


def verify_result(root, attempt_rel):
    root = Path(root).resolve(); d = inside(root, attempt_rel)
    job = read_json(d / 'job.json'); out = read_json(d / 'outcome.json')
    result = read_json(d / 'result/result.json')
    manifest = read_json(root / 'production_manifest.json')
    tasks = read_json(root / 'inputs.json')
    if identity(tasks) != manifest['inputs_sha256']:
        raise ValueError('FROZEN_INPUTS_CHANGED')
    case = safe_id(result['case_id'])
    matches = [t for t in tasks if t['case_id'] == case]
    if len(matches) != 1:
        raise ValueError('RESULT_INPUT_IDENTITY_MISSING')
    task = matches[0]
    expected = str(Path('cases') / case / 'attempts')
    if str(Path(attempt_rel).parent) != expected or job.get('attempt_relative') != attempt_rel:
        raise ValueError('RESULT_ATTEMPT_IDENTITY_MISMATCH')
    if result.get('attempt_relative') != attempt_rel or out.get('case_id') != case:
        raise ValueError('RESULT_CASE_IDENTITY_MISMATCH')
    if identity(job.get('task')) != identity(task) or result.get('input_sha256') != task['sha256']:
        raise ValueError('RESULT_INPUT_IDENTITY_MISMATCH')
    if any(obj.get('protocol_sha256') != manifest['protocol_sha256'] for obj in (job, result)):
        raise ValueError('RESULT_PROTOCOL_MISMATCH')
    if out.get('status') not in SUCCESS:
        raise ValueError('OUTCOME_NOT_SUCCESS')
    reasons = {'SUCCEEDED_STANDARD':'STANDARD', 'SUCCEEDED_ACCEPTED':'ACCEPTED', 'CAP_REACHED':'CAP_REACHED'}
    if result.get('stop_reason') != reasons[out['status']]:
        raise ValueError('RESULT_STOP_REASON_MISMATCH')
    if checked_hash(d / 'result/result.json') != out.get('result_sha256'):
        raise ValueError('OUTCOME_RESULT_HASH_MISMATCH')
    verify_epoch(root, job, out)
    files = result.get('files', {})
    required = {'phase_final_full.raw', 'phase_final_roi.npy'}
    if not isinstance(files, dict) or not required.issubset(files):
        raise ValueError('RESULT_REQUIRED_FILES_MISSING')
    for name, digest in files.items():
        path = inside(d / 'result', name)
        if checked_hash(path) != digest:
            raise ValueError('RESULT_HASH_MISMATCH: ' + str(path))
    return result


def verify_commit(root, case, commit):
    if commit.get('case_id') != case or commit.get('status') not in SUCCESS:
        raise ValueError('COMMIT_IDENTITY_MISMATCH')
    rel = commit['attempt_relative']; d = inside(root, rel)
    result = verify_result(root, rel); out = read_json(d / 'outcome.json')
    if result['case_id'] != case or out['status'] != commit['status']:
        raise ValueError('COMMIT_OUTCOME_MISMATCH')
    if checked_hash(d / 'result/result.json') != commit.get('result_json_sha256'):
        raise ValueError('COMMIT_HASH_MISMATCH')
    return result


def commit_result(root, case, attempt_rel, outcome):
    root = Path(root); result = verify_result(root, attempt_rel)
    d = inside(root, attempt_rel); recorded = read_json(d / 'outcome.json')
    if result['case_id'] != case or outcome != recorded:
        raise ValueError('COMMIT_CASE_OR_OUTCOME_MISMATCH')
    commit = {'schema':1, 'case_id':case, 'status':outcome['status'],
              'attempt_relative':attempt_rel,
              'result_json_sha256':checked_hash(d / 'result/result.json'),
              'committed_at':now()}
    # Recheck epoch immediately before publishing the durable completion marker.
    verify_epoch(root, read_json(d/'job.json'), recorded)
    atomic_json(root / 'cases' / case / 'complete.json', commit)
    return result


def quarantine_commit(root, case, reason):
    """Move a rejected completion marker, never erase endpoint evidence."""
    directory = Path(root) / 'cases' / safe_id(case)
    marker = directory / 'complete.json'
    if not marker.exists():
        return None
    target = directory / 'quarantine' / uuid.uuid4().hex
    target.mkdir(parents=True)
    atomic_json(target / 'reason.json', {'time':now(), 'reason':str(reason)})
    os.replace(marker, target / 'complete.json')
    fsync_dir(target); fsync_dir(directory)
    return str(target)
