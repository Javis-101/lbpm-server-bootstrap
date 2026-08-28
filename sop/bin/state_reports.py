#!/usr/bin/env python3
"""Atomic, machine-readable acceptance and case readiness state transitions."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

SCHEMA_VERSION = 1
SOP_VERSION = "1.3.2"
SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    )
    tmp = Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def atomic_json(path: Path, payload: dict) -> None:
    atomic_write(path, (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode())


def atomic_text(path: Path, text: str) -> None:
    atomic_write(path, text.encode())


def remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def load_pass(path: Path, label: str) -> dict:
    if not path.is_file():
        raise SystemExit(f"{label} is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("status") != "PASS":
        raise SystemExit(f"{label} is not a schema_version=1 PASS: {path}")
    return payload


def validate_case_id(case_id: str) -> None:
    if not case_id:
        return
    if (
        case_id in {".", ".."}
        or not SAFE_CASE_ID.fullmatch(case_id)
        or Path(case_id).is_absolute()
        or PureWindowsPath(case_id).is_absolute()
        or "/" in case_id
        or "\\" in case_id
    ):
        raise SystemExit(f"CASE_ID_INVALID: must be a safe basename, got {case_id!r}")


def acceptance_start(args: argparse.Namespace) -> None:
    directory = args.validation_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    for relative in (
        "acceptance_report.json",
        "POSTINSTALL_PASS.txt",
        "software-verification.json",
        "TestSetDevice.PASS.json",
        "piston_result.json",
    ):
        remove_file(directory / relative)
    print("ACCEPTANCE_STATE_INVALIDATED")


def acceptance_fail(args: argparse.Namespace) -> None:
    directory = args.validation_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    remove_file(directory / "POSTINSTALL_PASS.txt")
    atomic_json(
        directory / "acceptance_report.json",
        {
            "schema_version": SCHEMA_VERSION,
            "sop_version": SOP_VERSION,
            "status": "FAIL",
            "failed_check": args.failed_check,
            "exit_code": args.exit_code,
            "completed_at": now(),
            "checks": {},
        },
    )
    print("ACCEPTANCE_FAIL_RECORDED")


def acceptance_pass(args: argparse.Namespace) -> None:
    directory = args.validation_dir.resolve()
    software = load_pass(args.software_report.resolve(), "software verification report")
    testset = load_pass(args.testsetdevice_report.resolve(), "TestSetDevice report")
    piston = load_pass(args.piston_report.resolve(), "Piston report")
    checks = dict(software.get("checks", {}))
    required = {"lbpm_identity", "patch", "dynamic_linking", "gpu", "cuda", "mpi"}
    if set(checks) < required or any(checks[name] != "PASS" for name in required):
        raise SystemExit("software verification checks are missing or not PASS")
    if piston.get("numerical_sanity") != "PASS":
        raise SystemExit("Piston numerical sanity is not PASS")
    checks.update({"testsetdevice": "PASS", "piston": "PASS"})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "sop_version": SOP_VERSION,
        "status": "PASS",
        "completed_at": now(),
        "checks": checks,
        "provenance": software.get("provenance", {}),
        "reports": {
            "software_verification": str(args.software_report.resolve()),
            "testsetdevice": str(args.testsetdevice_report.resolve()),
            "piston": str(args.piston_report.resolve()),
        },
    }
    report_path = directory / "acceptance_report.json"
    marker_path = directory / "POSTINSTALL_PASS.txt"
    try:
        atomic_text(
            marker_path,
            "LBPM post-install acceptance PASS\n"
            f"SOP_VERSION={SOP_VERSION}\n"
            f"VALIDATED_AT={payload['completed_at']}\n"
            "MACHINE_REPORT=acceptance_report.json\n",
        )
        atomic_json(report_path, payload)
    except Exception:
        remove_file(report_path)
        remove_file(marker_path)
        raise
    print("ACCEPTANCE_REPORT_PASS")


def case_start(args: argparse.Namespace) -> None:
    validate_case_id(args.case_id)
    case = args.case_dir.resolve()
    case.mkdir(parents=True, exist_ok=True)
    for name in (
        "READY_FOR_PARAMETERIZATION.txt",
        "READY_FOR_PARAMETERIZATION.json",
        "CASE_PREPARED.json",
    ):
        remove_file(case / name)
    remaining = sorted(item.name for item in case.iterdir())
    if remaining:
        raise SystemExit(
            f"CASE_DIRECTORY_NOT_EMPTY: {case}; existing entries are preserved: {remaining}"
        )
    print(f"CASE_TARGET_READY={case}")


def case_prepared(args: argparse.Namespace) -> None:
    case = args.case_dir.resolve()
    acceptance = load_pass(args.acceptance_report.resolve(), "acceptance report")
    manifest_path = case / "case_manifest.json"
    connectivity_path = case / "connectivity_report.json"
    if not manifest_path.is_file() or not connectivity_path.is_file():
        raise SystemExit("case manifest or connectivity report is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    connectivity = json.loads(connectivity_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("sop_version") != SOP_VERSION:
        raise SystemExit("case manifest version mismatch")
    if connectivity.get("status") != "PASS" or connectivity.get("geometry_modified") is not False:
        raise SystemExit("connectivity validation is not a non-mutating PASS")
    if manifest.get("source_roi", {}).get("geometry_modified") is not False:
        raise SystemExit("source ROI geometry_modified must be false")
    if manifest.get("simulation", {}).get("roi_preserved") is not True:
        raise SystemExit("simulation ROI preservation is not true")
    source_roi = manifest.get("source_roi", {})
    source_path = Path(source_roi.get("source_file", ""))
    source_sha256_before = source_roi.get("sha256")
    if not source_path.is_file():
        raise SystemExit(f"SOURCE_ROCK_IMMUTABILITY_FAILED: source RAW is missing: {source_path}")
    source_sha256_after = sha256(source_path)
    if not source_sha256_before or source_sha256_after != source_sha256_before:
        raise SystemExit(
            "SOURCE_ROCK_IMMUTABILITY_FAILED: source SHA256 changed before PREPARED publication"
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "sop_version": SOP_VERSION,
        "status": "PREPARED",
        "prepared_at": now(),
        "environment": "ACCEPTED",
        "case_preparation": "PASS",
        "smoke_test": "PENDING",
        "source_sha256": source_sha256_before,
        "source_sha256_before": source_sha256_before,
        "source_sha256_after": source_sha256_after,
        "source_immutable": True,
        "simulation_roi_preserved": True,
        "artifact_sha256": {
            "case_manifest.json": sha256(manifest_path),
            "connectivity_report.json": sha256(connectivity_path),
            "acceptance_report.json": sha256(args.acceptance_report.resolve()),
        },
    }
    id_path = case / "ID.00000"
    if id_path.is_file():
        payload["artifact_sha256"]["ID.00000"] = sha256(id_path)
    atomic_json(case / "CASE_PREPARED.json", payload)
    print("CASE_PREPARATION_PASS")


def case_ready(args: argparse.Namespace) -> None:
    case = args.case_dir.resolve()
    load_pass(args.acceptance_report.resolve(), "acceptance report")
    prepared_path = case / "CASE_PREPARED.json"
    if not prepared_path.is_file():
        raise SystemExit("CASE_PREPARED.json is missing")
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    if prepared.get("status") != "PREPARED" or prepared.get("case_preparation") != "PASS":
        raise SystemExit("case preparation state is not PASS")
    if args.smoke_status == "PASS":
        smoke = load_pass(case / "engineering-smoke-2000" / "PASS.json", "first-case smoke report")
        if smoke.get("numerical_sanity") != "PASS":
            raise SystemExit("first-case smoke numerical sanity is not PASS")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "sop_version": SOP_VERSION,
        "status": "READY",
        "ready_at": now(),
        "environment": "ACCEPTED",
        "case_preparation": "PASS",
        "smoke_test": args.smoke_status,
        "final": "READY",
        "source_immutable": True,
        "simulation_roi_preserved": True,
    }
    report_path = case / "READY_FOR_PARAMETERIZATION.json"
    marker_path = case / "READY_FOR_PARAMETERIZATION.txt"
    try:
        atomic_text(
            marker_path,
            "LBPM case READY_FOR_PARAMETERIZATION\n"
            f"SOP_VERSION={SOP_VERSION}\n"
            "CASE_PREPARATION=PASS\n"
            f"SMOKE_TEST={args.smoke_status}\n"
            "MACHINE_REPORT=READY_FOR_PARAMETERIZATION.json\n",
        )
        atomic_json(report_path, payload)
    except Exception:
        remove_file(report_path)
        remove_file(marker_path)
        raise
    print("CASE_READY")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    cmd = sub.add_parser("acceptance-start")
    cmd.add_argument("--validation-dir", required=True, type=Path)
    cmd.set_defaults(func=acceptance_start)

    cmd = sub.add_parser("acceptance-fail")
    cmd.add_argument("--validation-dir", required=True, type=Path)
    cmd.add_argument("--failed-check", required=True)
    cmd.add_argument("--exit-code", required=True, type=int)
    cmd.set_defaults(func=acceptance_fail)

    cmd = sub.add_parser("acceptance-pass")
    cmd.add_argument("--validation-dir", required=True, type=Path)
    cmd.add_argument("--software-report", required=True, type=Path)
    cmd.add_argument("--testsetdevice-report", required=True, type=Path)
    cmd.add_argument("--piston-report", required=True, type=Path)
    cmd.set_defaults(func=acceptance_pass)

    cmd = sub.add_parser("case-start")
    cmd.add_argument("--case-dir", required=True, type=Path)
    cmd.add_argument("--case-id", default="")
    cmd.set_defaults(func=case_start)

    cmd = sub.add_parser("case-prepared")
    cmd.add_argument("--case-dir", required=True, type=Path)
    cmd.add_argument("--acceptance-report", required=True, type=Path)
    cmd.set_defaults(func=case_prepared)

    cmd = sub.add_parser("case-ready")
    cmd.add_argument("--case-dir", required=True, type=Path)
    cmd.add_argument("--acceptance-report", required=True, type=Path)
    cmd.add_argument("--smoke-status", required=True, choices=("PASS", "NOT_REQUIRED"))
    cmd.set_defaults(func=case_ready)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
