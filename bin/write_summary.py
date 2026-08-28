#!/usr/bin/env python3
"""Atomically record Bootstrap stage state and render final summaries."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BOOTSTRAP_VERSION = "1.0.3"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def load_object(path: Path, *, optional: bool = False) -> dict[str, Any]:
    if not path.is_file():
        if optional:
            return {}
        raise RuntimeError(f"JSON file is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root must be an object: {path}")
    return payload


def record(args: argparse.Namespace) -> None:
    state_path = Path(args.state).resolve()
    if state_path.exists():
        state = load_object(state_path)
    else:
        state = {
            "schema_version": 1,
            "bootstrap_version": BOOTSTRAP_VERSION,
            "run_id": args.run_id,
            "started_at_utc": now_utc(),
            "stages": {},
        }
    if state.get("run_id") != args.run_id:
        raise RuntimeError("run_id does not match the existing state file")
    stages = state.setdefault("stages", {})
    if not isinstance(stages, dict):
        raise RuntimeError("state stages must be an object")
    stage: dict[str, Any] = {"status": args.status, "recorded_at_utc": now_utc()}
    if args.detail:
        stage["detail"] = args.detail
    if args.log:
        stage["log"] = str(Path(args.log).resolve())
    stages[args.stage] = stage
    atomic_json(state_path, state)


def stage_statuses(state: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for name, value in state.get("stages", {}).items():
        if isinstance(value, dict):
            statuses[name] = str(value.get("status", "NOT_RUN"))
        else:
            statuses[name] = "INVALID"
    return statuses


def render_text(summary: dict[str, Any]) -> str:
    package = summary.get("package_identity", {})
    raw = summary.get("raw", {})
    acceptance = summary.get("sop_acceptance", {})
    ready = summary.get("first_rock", {})
    host_prerequisites = summary.get("host_prerequisites", {})
    gfortran = (
        host_prerequisites.get("gfortran", {})
        if isinstance(host_prerequisites, dict)
        else {}
    )
    checks = acceptance.get("required_checks", {}) if isinstance(acceptance, dict) else {}
    evidence = summary.get("evidence", {})
    lines = [
        "============================================================",
        " LBPM SERVER END-TO-END VALIDATION",
        "============================================================",
        f"Bootstrap                 {summary['bootstrap_version']}",
        f"Run ID                    {summary['run_id']}",
        f"Installer                 {package.get('installer_version', 'NOT_PRODUCED')}",
        f"Install action            {summary.get('install_action') or 'NOT_RUN'}",
        f"GFortran                 {gfortran.get('version', 'NOT_PRODUCED')}",
        f"libgfortran link          {gfortran.get('link_test', 'NOT_PRODUCED')}",
        f"LBPM commit               {package.get('lbpm_commit', 'NOT_PRODUCED')}",
        f"Local patch               {package.get('patchset_id', 'NOT_PRODUCED')}",
        f"SOP                       {package.get('sop_version', 'NOT_PRODUCED')}",
        f"Post-install acceptance   {acceptance.get('status', 'NOT_PRODUCED')}",
        f"TestSetDevice             {checks.get('testsetdevice', 'NOT_PRODUCED')}",
        f"Piston                    {checks.get('piston', 'NOT_PRODUCED')}",
        f"First RAW                 {raw.get('filename', 'NOT_PRODUCED')}",
        f"RAW SHA256                {raw.get('hash_status', 'NOT_PRODUCED')}",
        f"RAW contract              {raw.get('status', 'NOT_PRODUCED')}",
        f"Z connectivity            {ready.get('z_connectivity', 'NOT_PRODUCED')}",
        f"Source immutable          {'PASS' if ready.get('source_immutable') is True else 'NOT_PRODUCED'}",
        f"ROI preserved             {'PASS' if ready.get('simulation_roi_preserved') is True else 'NOT_PRODUCED'}",
        f"First-rock smoke          {ready.get('smoke_test', 'NOT_PRODUCED')}",
        "------------------------------------------------------------",
        f"OVERALL RESULT            {summary['status']}",
        "------------------------------------------------------------",
    ]
    if summary.get("failed_stage"):
        lines.extend(
            [
                f"FAILED STAGE              {summary['failed_stage']}",
                f"FAIL REASON               {summary.get('fail_reason') or 'unspecified'}",
            ]
        )
    lines.extend(
        [
            "PRODUCTION PHYSICAL VALIDATION: NOT PERFORMED",
            "PRODUCTION PHYSICAL PARAMETERS: NOT DECIDED",
            "RUNNER: NOT DEVELOPED",
            f"Evidence archive:         {evidence.get('archive', 'NOT_PRODUCED')}",
            f"Evidence SHA256:          {evidence.get('sha256', 'NOT_PRODUCED')}",
            "============================================================",
            "",
        ]
    )
    return "\n".join(lines)


def render_markdown(summary: dict[str, Any], plain_text: str) -> str:
    return (
        "# LBPM server end-to-end validation\n\n"
        f"- Bootstrap: `{summary['bootstrap_version']}`\n"
        f"- Run ID: `{summary['run_id']}`\n"
        f"- Overall result: **{summary['status']}**\n"
        f"- Failed stage: `{summary.get('failed_stage') or 'NONE'}`\n"
        "- Production physical validation: **NOT PERFORMED**\n"
        "- Production physical parameters: **NOT DECIDED**\n"
        "- Runner: **NOT DEVELOPED**\n\n"
        "```text\n" + plain_text.rstrip() + "\n```\n"
    )


def render(args: argparse.Namespace) -> None:
    state_path = Path(args.state).resolve()
    state = load_object(state_path)
    run_root = Path(args.run_root).resolve()
    state_dir = run_root / "state"
    package = load_object(state_dir / "package-identity.json", optional=True)
    raw = load_object(state_dir / "raw-check.json", optional=True)
    acceptance = load_object(state_dir / "acceptance-check.json", optional=True)
    ready = load_object(state_dir / "ready-check.json", optional=True)
    host_prerequisites = load_object(
        run_root / "host" / "prerequisites.json", optional=True
    )
    summary: dict[str, Any] = {
        "schema_version": 1,
        "bootstrap_version": BOOTSTRAP_VERSION,
        "status": args.status,
        "run_id": state["run_id"],
        "started_at_utc": state.get("started_at_utc"),
        "completed_at_utc": now_utc(),
        "stages": stage_statuses(state),
        "install_action": args.install_action or None,
        "package_identity": package,
        "raw": raw,
        "sop_acceptance": acceptance,
        "first_rock": ready,
        "host_prerequisites": host_prerequisites,
        "failed_stage": args.failed_stage or None,
        "fail_reason": args.fail_reason or None,
        "infrastructure_validation": (
            "PASS"
            if acceptance.get("status") == "PASS"
            else ("FAIL" if acceptance else "NOT_PRODUCED")
        ),
        "first_real_rock_smoke": ready.get("smoke_test", "NOT_PRODUCED"),
        "production_physical_validation": False,
        "production_parameters_decided": False,
        "runner_developed": False,
        "evidence": {
            "archive": args.archive or "NOT_PRODUCED",
            "sha256": args.archive_sha256 or "NOT_PRODUCED",
            "archive_hash_contract": "SIDECAR_SHA256",
        },
    }
    atomic_json(run_root / "summary.json", summary)
    plain = render_text(summary)
    atomic_text(run_root / "summary.txt", plain)
    atomic_text(run_root / "summary.md", render_markdown(summary, plain))
    print(plain, end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--state", required=True)
    record_parser.add_argument("--run-id", required=True)
    record_parser.add_argument("--stage", required=True)
    record_parser.add_argument("--status", required=True, choices=("PASS", "FAIL", "SKIPPED"))
    record_parser.add_argument("--detail", default="")
    record_parser.add_argument("--log", default="")
    record_parser.set_defaults(handler=record)

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--state", required=True)
    render_parser.add_argument("--run-root", required=True)
    render_parser.add_argument("--status", required=True, choices=("PASS", "FAIL"))
    render_parser.add_argument("--failed-stage", default="")
    render_parser.add_argument("--fail-reason", default="")
    render_parser.add_argument("--install-action", default="")
    render_parser.add_argument("--archive", default="")
    render_parser.add_argument("--archive-sha256", default="")
    render_parser.set_defaults(handler=render)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        args.handler(args)
        return 0
    except (OSError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
