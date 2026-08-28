#!/usr/bin/env python3
"""Collect a bounded LBPM validation evidence snapshot and archive it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def safe_copy(source: Path | None, destination: Path, statuses: dict[str, str], key: str) -> None:
    if source is not None and source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        statuses[key] = "COPIED"
    else:
        statuses[key] = "NOT_PRODUCED"


def find_optional(root: Path | None, relative: str) -> Path | None:
    if root is None:
        return None
    return root / relative


def load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def collect(args: argparse.Namespace) -> dict[str, Any]:
    run_root = Path(args.run_root).resolve()
    if not run_root.is_dir():
        raise RuntimeError(f"run root does not exist: {run_root}")
    evidence = run_root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, str] = {}

    for filename in ("summary.json", "summary.txt", "summary.md"):
        safe_copy(run_root / filename, evidence / filename, statuses, filename)
    for filename in (
        "host-info.txt",
        "gpu-info.txt",
        "cuda-info.txt",
        "compiler-info.txt",
        "prerequisites.json",
        "disk-info.txt",
        "lbpm-runtime-identity.txt",
    ):
        safe_copy(run_root / "host" / filename, evidence / "host" / filename, statuses, f"host/{filename}")

    installer_root = Path(args.installer_root).resolve() if args.installer_root else None
    stack_manifest = Path(args.stack_manifest).resolve() if args.stack_manifest else None
    safe_copy(
        find_optional(installer_root, "sources/BUNDLE_MANIFEST.txt"),
        evidence / "installer" / "BUNDLE_MANIFEST.txt",
        statuses,
        "installer/BUNDLE_MANIFEST.txt",
    )
    safe_copy(
        stack_manifest,
        evidence / "installer" / "LBPM_BUILD_MANIFEST.txt",
        statuses,
        "installer/LBPM_BUILD_MANIFEST.txt",
    )
    safe_copy(
        run_root / "logs" / "03-source-verification.log",
        evidence / "installer" / "verify-sources.log",
        statuses,
        "installer/verify-sources.log",
    )

    validation = run_root / "validation"
    for filename in (
        "acceptance_report.json",
        "software-verification.json",
        "TestSetDevice.PASS.json",
        "piston_result.json",
    ):
        safe_copy(
            validation / filename,
            evidence / "acceptance" / filename,
            statuses,
            f"acceptance/{filename}",
        )

    case_dir = Path(args.case_dir).resolve() if args.case_dir else None
    case_files = {
        "READY_FOR_PARAMETERIZATION.json": "READY_FOR_PARAMETERIZATION.json",
        "connectivity_report.json": "connectivity_report.json",
        "case_manifest.json": "case_manifest.json",
        "engineering-smoke-2000/PASS.json": "smoke.PASS.json",
    }
    for source_name, destination_name in case_files.items():
        safe_copy(
            find_optional(case_dir, source_name),
            evidence / "first-rock" / destination_name,
            statuses,
            f"first-rock/{destination_name}",
        )
    safe_copy(
        run_root / "state" / "raw-check.json",
        evidence / "first-rock" / "raw.sha256.json",
        statuses,
        "first-rock/raw.sha256.json",
    )
    raw_check_path = run_root / "state" / "raw-check.json"
    if raw_check_path.is_file():
        raw_check = load_object(raw_check_path)
        raw_hash = raw_check.get("sha256_before")
        raw_name = raw_check.get("filename")
        if isinstance(raw_hash, str) and isinstance(raw_name, str):
            atomic_text(evidence / "first-rock" / "raw.sha256", f"{raw_hash}  {raw_name}\n")
            statuses["first-rock/raw.sha256"] = "GENERATED"
        else:
            statuses["first-rock/raw.sha256"] = "NOT_PRODUCED"
    else:
        statuses["first-rock/raw.sha256"] = "NOT_PRODUCED"

    smoke_report = find_optional(case_dir, "engineering-smoke-2000/PASS.json")
    final_metadata_path = evidence / "first-rock" / "final-raw-metadata.json"
    if smoke_report is not None and smoke_report.is_file():
        report = load_object(smoke_report)
        final_raw = report.get("final_raw", {})
        filename = final_raw.get("file") if isinstance(final_raw, dict) else None
        raw_path = case_dir / "engineering-smoke-2000" / str(filename) if filename else None
        if raw_path is not None and raw_path.is_file():
            atomic_json(
                final_metadata_path,
                {
                    "schema_version": 1,
                    "filename": raw_path.name,
                    "size": raw_path.stat().st_size,
                    "sha256": sha256_file(raw_path),
                    "raw_copied_to_evidence": False,
                },
            )
            statuses["first-rock/final-raw-metadata.json"] = "GENERATED"
        else:
            statuses["first-rock/final-raw-metadata.json"] = "NOT_PRODUCED"
    else:
        statuses["first-rock/final-raw-metadata.json"] = "NOT_PRODUCED"

    logs = run_root / "logs"
    if logs.is_dir():
        for source in sorted(logs.glob("*.log")):
            safe_copy(source, evidence / "logs" / source.name, statuses, f"logs/{source.name}")

    inventory = {
        "schema_version": 1,
        "run_id": run_root.name,
        "bounded_evidence": True,
        "source_raw_copied": False,
        "simulation_raw_copied": False,
        "excluded_patterns": ["*.raw", "Restart.*", "*.h5", "*.hdf5", "stack/build trees"],
        "statuses": statuses,
    }
    atomic_json(evidence / "evidence_inventory.json", inventory)

    ledger_files = sorted(
        path for path in evidence.rglob("*") if path.is_file() and path.name != "EVIDENCE_SHA256SUMS"
    )
    ledger = "".join(
        f"{sha256_file(path)}  {path.relative_to(evidence).as_posix()}\n" for path in ledger_files
    )
    atomic_text(evidence / "EVIDENCE_SHA256SUMS", ledger)

    artifacts = run_root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    archive = artifacts / f"LBPM-validation-evidence-{run_root.name}.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(evidence, arcname="evidence", recursive=True)
    archive_sha = sha256_file(archive)
    sidecar = Path(str(archive) + ".sha256")
    atomic_text(sidecar, f"{archive_sha}  {archive.name}\n")
    return {
        "schema_version": 1,
        "status": "PASS",
        "evidence_directory": str(evidence),
        "archive": str(archive),
        "archive_sha256": archive_sha,
        "sidecar": str(sidecar),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--installer-root", default="")
    parser.add_argument("--stack-manifest", default="")
    parser.add_argument("--case-dir", default="")
    return parser


def main() -> int:
    try:
        result = collect(build_parser().parse_args())
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, RuntimeError, ValueError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
