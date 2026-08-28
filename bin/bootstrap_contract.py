#!/usr/bin/env python3
"""Fail-closed contract checks for LBPM server bootstrap v1.0.3."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


BOOTSTRAP_VERSION = "1.0.3"
EXPECTED_BUILDER_VERSION = "2.0.7"
EXPECTED_INSTALLER_VERSION = "2.0.7-offline"
EXPECTED_SOP_VERSION = "1.3.2"
EXPECTED_LBPM_BUNDLE_REPO = "OPM/LBPM"
EXPECTED_LBPM_INSTALL_REPO = "https://github.com/OPM/LBPM"
EXPECTED_LBPM_COMMIT = "6d686d354e5b8140841d3601e4c8c0e4e4b77e48"
EXPECTED_PATCHSET_ID = "outletlayersphase-fix-v1"
EXPECTED_PATCH_FILE = "0001-fix-OutletLayersPhase.patch"
EXPECTED_PATCH_SHA256 = (
    "fbce8ac8f101c5f5ff3764c4e6e71f98d5a478e54609f3d63864dbc8e7d1c2b8"
)
EXPECTED_OPENMPI_VERSION = "4.1.8"
EXPECTED_ZLIB_VERSION = "1.3.2"
EXPECTED_HDF5_VERSION = "1.14.6"
EXPECTED_ACCEPTANCE_CHECKS = (
    "lbpm_identity",
    "patch",
    "dynamic_linking",
    "gpu",
    "cuda",
    "mpi",
    "testsetdevice",
    "piston",
)


class ContractError(RuntimeError):
    """A validation failure that must stop orchestration."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def emit(payload: dict[str, Any], output: str | None) -> None:
    if output:
        atomic_json(Path(output), payload)
    else:
        json.dump(payload, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError(f"{label} is missing or is not a regular file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"{label} is not valid UTF-8 JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{label} root must be a JSON object: {path}")
    return payload


def parse_key_values(text: str, label: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ContractError(f"{label}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in values:
            raise ContractError(f"{label}:{line_number}: invalid or duplicate key {key!r}")
        values[key] = value
    return values


def parse_shell_assignments(text: str, required: tuple[str, ...], label: str) -> dict[str, str]:
    wanted = set(required)
    values: dict[str, str] = {}
    assignment = re.compile(
        r"^([A-Za-z_][A-Za-z0-9_]*)=(?:\"([^\"]*)\"|'([^']*)'|([A-Za-z0-9._/:+-]+))\s*$"
    )
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        match = assignment.match(raw_line.strip())
        if not match or match.group(1) not in wanted:
            continue
        key = match.group(1)
        if key in values:
            raise ContractError(f"{label}:{line_number}: duplicate assignment for {key}")
        values[key] = next(part for part in match.groups()[1:] if part is not None)
    missing = sorted(wanted - values.keys())
    if missing:
        raise ContractError(f"{label}: missing literal assignments: {', '.join(missing)}")
    return values


def read_unique_zip_suffix(archive: zipfile.ZipFile, suffix: str, label: str) -> tuple[str, str]:
    matches = [
        name for name in archive.namelist() if name.replace("\\", "/").endswith(suffix)
    ]
    if len(matches) != 1:
        raise ContractError(
            f"{label}: expected exactly one ZIP member ending with {suffix!r}; found {len(matches)}"
        )
    name = matches[0]
    try:
        return name.replace("\\", "/"), archive.read(name).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError(f"{label}: ZIP member is not UTF-8: {name}") from exc


def require_equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ContractError(f"{label} mismatch: expected {expected!r}, found {actual!r}")


def inspect_packages(args: argparse.Namespace) -> None:
    installer_zip = Path(args.installer_zip).resolve()
    sop_zip = Path(args.sop_zip).resolve()
    for path, label in ((installer_zip, "Installer ZIP"), (sop_zip, "SOP ZIP")):
        if not path.is_file():
            raise ContractError(f"{label} is missing or is not a regular file: {path}")

    installer_sha = sha256_file(installer_zip)
    sop_sha = sha256_file(sop_zip)
    require_equal(installer_sha, args.expected_installer_sha256.lower(), "Installer ZIP SHA256")
    require_equal(sop_sha, args.expected_sop_sha256.lower(), "SOP ZIP SHA256")

    try:
        with zipfile.ZipFile(installer_zip) as archive:
            manifest_name, manifest_text = read_unique_zip_suffix(
                archive, "/sources/BUNDLE_MANIFEST.txt", "Installer ZIP"
            )
            installer_name, installer_text = read_unique_zip_suffix(
                archive, "/install_lbpm_offline.sh", "Installer ZIP"
            )
            installer_entries = [name.replace("\\", "/") for name in archive.namelist()]
        with zipfile.ZipFile(sop_zip) as archive:
            version_name, version_text = read_unique_zip_suffix(archive, "/VERSION", "SOP ZIP")
            sop_entries = [name.replace("\\", "/") for name in archive.namelist()]
    except zipfile.BadZipFile as exc:
        raise ContractError(f"Invalid ZIP package: {exc}") from exc

    installer_root = manifest_name.split("/", 1)[0]
    sop_root = version_name.split("/", 1)[0]
    require_equal(installer_root, "LBPM-portable-offline-installer", "Installer ZIP root")
    require_equal(sop_root, "LBPM-postinstall-SOP-v1.3.2", "SOP ZIP root")
    if any(not name.startswith(installer_root + "/") for name in installer_entries):
        raise ContractError("Installer ZIP contains entries outside its pinned root")
    if any(not name.startswith(sop_root + "/") for name in sop_entries):
        raise ContractError("SOP ZIP contains entries outside its pinned root")

    manifest = parse_key_values(manifest_text, manifest_name)
    expected_manifest = {
        "BUNDLE_FORMAT": "2",
        "BUILDER_VERSION": EXPECTED_BUILDER_VERSION,
        "LBPM_REPO": EXPECTED_LBPM_BUNDLE_REPO,
        "LBPM_COMMIT": EXPECTED_LBPM_COMMIT,
        "LBPM_LOCAL_PATCHSET": EXPECTED_PATCHSET_ID,
        "LBPM_LOCAL_PATCH": EXPECTED_PATCH_FILE,
        "LBPM_LOCAL_PATCH_SHA256": EXPECTED_PATCH_SHA256,
        "OPENMPI_VERSION": EXPECTED_OPENMPI_VERSION,
        "ZLIB_VERSION": EXPECTED_ZLIB_VERSION,
        "HDF5_VERSION": EXPECTED_HDF5_VERSION,
    }
    for key, expected in expected_manifest.items():
        require_equal(manifest.get(key), expected, key)

    install_keys = (
        "INSTALLER_VERSION",
        "LBPM_REPO",
        "LBPM_COMMIT",
        "PATCHSET_ID",
        "PATCH_SHA256",
        "OPENMPI_VERSION",
        "ZLIB_VERSION",
        "HDF5_VERSION",
    )
    installer = parse_shell_assignments(installer_text, install_keys, installer_name)
    expected_installer = {
        "INSTALLER_VERSION": EXPECTED_INSTALLER_VERSION,
        "LBPM_REPO": EXPECTED_LBPM_INSTALL_REPO,
        "LBPM_COMMIT": EXPECTED_LBPM_COMMIT,
        "PATCHSET_ID": EXPECTED_PATCHSET_ID,
        "PATCH_SHA256": EXPECTED_PATCH_SHA256,
        "OPENMPI_VERSION": EXPECTED_OPENMPI_VERSION,
        "ZLIB_VERSION": EXPECTED_ZLIB_VERSION,
        "HDF5_VERSION": EXPECTED_HDF5_VERSION,
    }
    for key, expected in expected_installer.items():
        require_equal(installer.get(key), expected, key)

    sop_version = version_text.strip()
    require_equal(sop_version, EXPECTED_SOP_VERSION, "SOP VERSION")
    payload = {
        "schema_version": 1,
        "bootstrap_version": BOOTSTRAP_VERSION,
        "status": "PASS",
        "builder_version": manifest["BUILDER_VERSION"],
        "installer_version": installer["INSTALLER_VERSION"],
        "sop_version": sop_version,
        "lbpm_repo": installer["LBPM_REPO"],
        "lbpm_commit": installer["LBPM_COMMIT"],
        "patchset_id": installer["PATCHSET_ID"],
        "patch_file": manifest["LBPM_LOCAL_PATCH"],
        "patch_sha256": installer["PATCH_SHA256"],
        "openmpi_version": installer["OPENMPI_VERSION"],
        "zlib_version": installer["ZLIB_VERSION"],
        "hdf5_version": installer["HDF5_VERSION"],
        "installer_zip": {
            "path": str(installer_zip),
            "size": installer_zip.stat().st_size,
            "sha256": installer_sha,
        },
        "sop_zip": {
            "path": str(sop_zip),
            "size": sop_zip.stat().st_size,
            "sha256": sop_sha,
        },
    }
    emit(payload, args.output)


def check_stack(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest).resolve()
    identity = load_json(Path(args.package_identity), "Package identity")
    require_equal(identity.get("status"), "PASS", "Package identity status")
    if not manifest_path.exists():
        if args.require_present:
            raise ContractError(
                f"POST_INSTALL_STACK_MISSING: required manifest is absent: {manifest_path}"
            )
        emit(
            {
                "schema_version": 1,
                "status": "PASS",
                "manifest": str(manifest_path),
                "manifest_present": False,
                "compatible": False,
                "install_action": "INSTALL",
            },
            args.output,
        )
        return
    if not manifest_path.is_file():
        raise ContractError(f"Existing stack manifest is not a regular file: {manifest_path}")
    original = manifest_path.read_text(encoding="utf-8")
    values = parse_key_values(original, str(manifest_path))
    expected = {
        "INSTALLER_VERSION": identity["installer_version"],
        "LBPM_REPO": identity["lbpm_repo"],
        "LBPM_COMMIT": identity["lbpm_commit"],
        "PATCHSET_ID": identity["patchset_id"],
        "PATCH_SHA256": identity["patch_sha256"],
        "OPENMPI_VERSION": identity["openmpi_version"],
        "ZLIB_VERSION": identity["zlib_version"],
        "HDF5_VERSION": identity["hdf5_version"],
    }
    mismatches = [
        f"{key}: expected {value!r}, found {values.get(key)!r}"
        for key, value in expected.items()
        if values.get(key) != value
    ]
    if mismatches:
        raise ContractError("FAIL_EXISTING_STACK_MISMATCH: " + "; ".join(mismatches))
    emit(
        {
            "schema_version": 1,
            "status": "PASS",
            "manifest": str(manifest_path),
            "manifest_present": True,
            "compatible": True,
            "install_action": (
                "VERIFIED_INSTALLED_COMPATIBLE"
                if args.require_present
                else "SKIP_EXISTING_COMPATIBLE"
            ),
            "validated_fields": sorted(expected),
        },
        args.output,
    )


def check_raw(args: argparse.Namespace) -> None:
    raw = Path(args.raw).resolve()
    if not raw.is_file():
        raise ContractError(f"RAW is missing or is not a regular file: {raw}")
    actual_size = raw.stat().st_size
    if actual_size != args.expected_bytes:
        raise ContractError(
            f"RAW byte size mismatch: expected {args.expected_bytes}, found {actual_size}: {raw}"
        )
    actual_sha = sha256_file(raw)
    expected_sha = args.expected_sha256.lower() if args.expected_sha256 else ""
    if expected_sha and actual_sha != expected_sha:
        raise ContractError(
            f"RAW SHA256 mismatch: expected {expected_sha}, found {actual_sha}: {raw}"
        )
    emit(
        {
            "schema_version": 1,
            "status": "PASS",
            "source_file": str(raw),
            "filename": raw.name,
            "size": actual_size,
            "expected_bytes": args.expected_bytes,
            "sha256_before": actual_sha,
            "expected_sha256": expected_sha or None,
            "hash_status": "PASS" if expected_sha else "RECORDED",
        },
        args.output,
    )


def check_acceptance(args: argparse.Namespace) -> None:
    path = Path(args.report).resolve()
    report = load_json(path, "Acceptance report")
    require_equal(report.get("schema_version"), 1, "Acceptance schema_version")
    require_equal(report.get("sop_version"), EXPECTED_SOP_VERSION, "Acceptance sop_version")
    require_equal(report.get("status"), "PASS", "Acceptance status")
    checks = report.get("checks")
    if not isinstance(checks, dict):
        raise ContractError("Acceptance required checks are missing or not an object")
    missing_or_failed = [name for name in EXPECTED_ACCEPTANCE_CHECKS if checks.get(name) != "PASS"]
    if missing_or_failed:
        raise ContractError(
            "Acceptance required checks are not all PASS: " + ", ".join(missing_or_failed)
        )
    emit(
        {
            "schema_version": 1,
            "status": "PASS",
            "report": str(path),
            "sop_version": report["sop_version"],
            "required_checks": {name: checks[name] for name in EXPECTED_ACCEPTANCE_CHECKS},
            "provenance": report.get("provenance", {}),
        },
        args.output,
    )


def check_ready(args: argparse.Namespace) -> None:
    ready = load_json(Path(args.ready), "READY report")
    manifest = load_json(Path(args.case_manifest), "Case manifest")
    connectivity = load_json(Path(args.connectivity), "Connectivity report")
    smoke = load_json(Path(args.smoke_report), "Smoke report")
    raw_check = load_json(Path(args.raw_check), "RAW check")

    required_ready = {
        "schema_version": 1,
        "sop_version": EXPECTED_SOP_VERSION,
        "status": "READY",
        "environment": "ACCEPTED",
        "case_preparation": "PASS",
        "smoke_test": "PASS",
        "final": "READY",
        "source_immutable": True,
        "simulation_roi_preserved": True,
    }
    for key, expected in required_ready.items():
        require_equal(ready.get(key), expected, f"READY {key}")

    require_equal(manifest.get("schema_version"), 1, "Case manifest schema_version")
    require_equal(manifest.get("sop_version"), EXPECTED_SOP_VERSION, "Case manifest sop_version")
    source_roi = manifest.get("source_roi")
    simulation = manifest.get("simulation")
    if not isinstance(source_roi, dict) or not isinstance(simulation, dict):
        raise ContractError("Case manifest must contain source_roi and simulation objects")
    require_equal(source_roi.get("geometry_modified"), False, "Case source_roi geometry_modified")
    require_equal(simulation.get("roi_preserved"), True, "Case simulation roi_preserved")

    require_equal(connectivity.get("schema_version"), 1, "Connectivity schema_version")
    require_equal(connectivity.get("status"), "PASS", "Connectivity status")
    require_equal(connectivity.get("z_percolating"), True, "Connectivity z_percolating")
    require_equal(connectivity.get("geometry_modified"), False, "Connectivity geometry_modified")

    require_equal(smoke.get("schema_version"), 1, "Smoke schema_version")
    require_equal(smoke.get("sop_version"), EXPECTED_SOP_VERSION, "Smoke sop_version")
    require_equal(smoke.get("status"), "PASS", "Smoke status")
    require_equal(smoke.get("numerical_sanity"), "PASS", "Smoke numerical_sanity")
    require_equal(raw_check.get("status"), "PASS", "RAW check status")

    source_file = Path(str(raw_check.get("source_file", ""))).resolve()
    if not source_file.is_file():
        raise ContractError(f"RAW source is unavailable for final immutability check: {source_file}")
    before = raw_check.get("sha256_before")
    after = sha256_file(source_file)
    require_equal(after, before, "Source RAW SHA256 after case preparation")
    require_equal(source_roi.get("sha256"), before, "Case source_roi SHA256")
    manifest_source = Path(str(source_roi.get("source_file", ""))).resolve()
    require_equal(manifest_source, source_file, "Case source_roi source_file")

    emit(
        {
            "schema_version": 1,
            "status": "PASS",
            "sop_version": EXPECTED_SOP_VERSION,
            "source_file": str(source_file),
            "source_sha256_before": before,
            "source_sha256_after": after,
            "source_immutable": True,
            "simulation_roi_preserved": True,
            "z_connectivity": "PASS",
            "smoke_test": "PASS",
        },
        args.output,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect-packages")
    inspect.add_argument("--installer-zip", required=True)
    inspect.add_argument("--sop-zip", required=True)
    inspect.add_argument("--expected-installer-sha256", required=True)
    inspect.add_argument("--expected-sop-sha256", required=True)
    inspect.add_argument("--output")
    inspect.set_defaults(handler=inspect_packages)

    stack = subparsers.add_parser("check-stack")
    stack.add_argument("--manifest", required=True)
    stack.add_argument("--package-identity", required=True)
    stack.add_argument(
        "--require-present",
        action="store_true",
        help="Fail if the stack manifest is absent (strict post-install mode).",
    )
    stack.add_argument("--output")
    stack.set_defaults(handler=check_stack)

    raw = subparsers.add_parser("check-raw")
    raw.add_argument("--raw", required=True)
    raw.add_argument("--expected-bytes", type=int, default=2_097_152)
    raw.add_argument("--expected-sha256", default="")
    raw.add_argument("--output")
    raw.set_defaults(handler=check_raw)

    acceptance = subparsers.add_parser("check-acceptance")
    acceptance.add_argument("--report", required=True)
    acceptance.add_argument("--output")
    acceptance.set_defaults(handler=check_acceptance)

    ready = subparsers.add_parser("check-ready")
    ready.add_argument("--ready", required=True)
    ready.add_argument("--case-manifest", required=True)
    ready.add_argument("--connectivity", required=True)
    ready.add_argument("--smoke-report", required=True)
    ready.add_argument("--raw-check", required=True)
    ready.add_argument("--output")
    ready.set_defaults(handler=check_ready)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        args.handler(args)
        return 0
    except (ContractError, KeyError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
