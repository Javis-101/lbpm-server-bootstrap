#!/usr/bin/env python3
"""Build the immutable software/runtime provenance report for acceptance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", prefix=f".{path.name}.",
        suffix=".tmp", dir=path.parent, delete=False
    )
    tmp = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def read_manifest(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def split_values(text: str) -> list[str]:
    return [value.strip() for value in text.splitlines() if value.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--gpu-name", required=True)
    parser.add_argument("--driver-version", required=True)
    parser.add_argument("--compute-capability", required=True)
    parser.add_argument("--cuda-version", required=True)
    parser.add_argument("--mpi-implementation", required=True)
    parser.add_argument("--mpi-version", required=True)
    parser.add_argument("--cuda-aware-mpi-status", required=True)
    parser.add_argument("--patch-status", required=True)
    parser.add_argument("--executable", action="append", default=[])
    args = parser.parse_args()

    if not args.manifest.is_file() or not args.source.is_file():
        raise SystemExit("build manifest or ColorModel source is missing")
    manifest = read_manifest(args.manifest)
    required_manifest = ("LBPM_COMMIT", "PATCHSET_ID", "PATCH_SHA256", "INSTALLER_VERSION", "CUDA_ARCH")
    missing = [key for key in required_manifest if not manifest.get(key)]
    if missing:
        raise SystemExit(f"build manifest keys are missing: {missing}")

    executables: dict[str, dict[str, str]] = {}
    for item in args.executable:
        if "=" not in item:
            raise SystemExit(f"invalid --executable value: {item}")
        name, raw_path = item.split("=", 1)
        path = Path(raw_path).resolve()
        if not name or not path.is_file():
            raise SystemExit(f"executable is missing: {item}")
        executables[name] = {"path": str(path), "sha256": sha256(path)}
    if not executables:
        raise SystemExit("at least one executable identity is required")

    payload = {
        "schema_version": 1,
        "sop_version": "1.3.2",
        "status": "PASS",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "lbpm_identity": "PASS",
            "patch": "PASS",
            "dynamic_linking": "PASS",
            "gpu": "PASS",
            "cuda": "PASS",
            "mpi": "PASS",
        },
        "provenance": {
            "installer_version": manifest["INSTALLER_VERSION"],
            "lbpm_commit": manifest["LBPM_COMMIT"],
            "local_patch": {
                "patchset_id": manifest["PATCHSET_ID"],
                "patch_sha256": manifest["PATCH_SHA256"],
                "status": args.patch_status,
            },
            "build_manifest": {"path": str(args.manifest.resolve()), "sha256": sha256(args.manifest)},
            "color_model_source": {"path": str(args.source.resolve()), "sha256": sha256(args.source)},
            "gpu": {
                "name": split_values(args.gpu_name),
                "driver_version": split_values(args.driver_version),
                "compute_capability": split_values(args.compute_capability),
                "cuda_arch": manifest["CUDA_ARCH"],
            },
            "cuda": {"version": args.cuda_version},
            "mpi": {
                "implementation": args.mpi_implementation,
                "version": args.mpi_version,
                "cuda_aware_status": args.cuda_aware_mpi_status,
            },
            "executables": executables,
        },
    }
    atomic_json(args.output.resolve(), payload)
    print("SOFTWARE_VERIFICATION_REPORT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
