#!/usr/bin/env python3
"""Revalidate source immutability and embedded-ROI preservation for one case."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"CASE_CONTRACT_VERIFICATION_FAILED: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", required=True, type=Path)
    args = parser.parse_args()
    case = args.case_dir.resolve()
    manifest_path = case / "case_manifest.json"
    report_path = case / "connectivity_report.json"
    if not manifest_path.is_file() or not report_path.is_file():
        fail("case_manifest.json or connectivity_report.json is missing")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or report.get("schema_version") != 1:
        fail("unsupported JSON schema_version")
    source_roi = manifest.get("source_roi", {})
    source = Path(source_roi.get("source_file", ""))
    expected_sha = source_roi.get("sha256")
    if not source.is_file() or sha256(source) != expected_sha:
        fail("source RAW is missing or its SHA256 changed")
    source_bytes = source.read_bytes()

    if source_roi.get("geometry_modified") is not False:
        fail("source_roi.geometry_modified must be false")
    if report.get("geometry_modified") is not False or report.get("status") != "PASS":
        fail("connectivity report is not a non-mutating PASS")

    for name in ("rock.raw", "rock_geometry.raw"):
        path = case / name
        if not path.is_file() or path.read_bytes() != source_bytes:
            fail(f"{name} is not byte-for-byte equal to source RAW")

    simulation = manifest.get("simulation", {})
    domain_info = simulation.get("simulation_domain", {})
    domain_path = case / domain_info.get("filename", "")
    if not domain_path.is_file() or sha256(domain_path) != domain_info.get("sha256"):
        fail("simulation domain is missing or its SHA256 differs from the manifest")
    shape = source_roi.get("shape_zyx", [])
    if len(shape) != 3:
        fail("source ROI shape is invalid")
    nz, ny, nx = map(int, shape)
    offset = simulation.get("roi_offset_zyx", [])
    if len(offset) != 3 or offset[1:] != [0, 0]:
        fail("unsupported ROI offset")
    start = int(offset[0]) * ny * nx
    embedded = domain_path.read_bytes()[start : start + nz * ny * nx]
    if embedded != source_bytes:
        fail("embedded simulation ROI differs from source RAW")
    if simulation.get("roi_preserved") is not True:
        fail("simulation.roi_preserved must be true")
    if manifest.get("saturation_contract", {}).get("pore_space_basis") != "source_128_cube_roi":
        fail("S_rg pore-space basis is not the source 128 cube ROI")

    print(f"source_sha256={expected_sha}")
    print("source_immutable=true")
    print("simulation_roi_preserved=true")
    print("CASE_CONTRACT_VERIFICATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
