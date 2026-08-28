#!/usr/bin/env python3
"""Validate and prepare one immutable binary digital-rock ROI for LBPM.

Production input is fixed at 128 x 128 x 128 uint8 with 0=solid and 1=pore.
Connectivity is a 6-neighbor +Z validator. It never filters or relabels voxels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter, deque
from pathlib import Path

PRODUCTION_SHAPE_ZYX = (128, 128, 128)
SOP_VERSION = "1.3.2"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
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


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, payload: dict) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def connectivity_6(data: bytes, nx: int, ny: int, nz: int, pore_value: int) -> dict:
    """Return 6-neighbor +Z connectivity statistics without mutating *data*."""
    nvox = nx * ny * nz
    if len(data) != nvox:
        raise ValueError(f"connectivity input has {len(data)} bytes, expected {nvox}")
    plane = nx * ny
    visited = bytearray(nvox)
    component_count = 0
    spanning_component_count = 0
    pore_voxels = sum(value == pore_value for value in data)
    spanning_voxels = 0

    for start, value in enumerate(data):
        if value != pore_value or visited[start]:
            continue
        component_count += 1
        q = deque([start])
        visited[start] = 1
        component_voxels = 0
        touches_inlet = False
        touches_outlet = False

        while q:
            idx = q.popleft()
            component_voxels += 1
            z, rem = divmod(idx, plane)
            y, x = divmod(rem, nx)
            touches_inlet = touches_inlet or z == 0
            touches_outlet = touches_outlet or z == nz - 1

            if x > 0:
                nb = idx - 1
                if not visited[nb] and data[nb] == pore_value:
                    visited[nb] = 1
                    q.append(nb)
            if x + 1 < nx:
                nb = idx + 1
                if not visited[nb] and data[nb] == pore_value:
                    visited[nb] = 1
                    q.append(nb)
            if y > 0:
                nb = idx - nx
                if not visited[nb] and data[nb] == pore_value:
                    visited[nb] = 1
                    q.append(nb)
            if y + 1 < ny:
                nb = idx + nx
                if not visited[nb] and data[nb] == pore_value:
                    visited[nb] = 1
                    q.append(nb)
            if z > 0:
                nb = idx - plane
                if not visited[nb] and data[nb] == pore_value:
                    visited[nb] = 1
                    q.append(nb)
            if z + 1 < nz:
                nb = idx + plane
                if not visited[nb] and data[nb] == pore_value:
                    visited[nb] = 1
                    q.append(nb)

        if touches_inlet and touches_outlet:
            spanning_component_count += 1
            spanning_voxels += component_voxels

    return {
        "connected_component_count": component_count,
        "spanning_component_count": spanning_component_count,
        "pore_voxels": pore_voxels,
        "spanning_voxels": spanning_voxels,
        "z_percolating": spanning_component_count > 0,
    }


def assert_no_source_output_collision(source: Path, case_dir: Path) -> None:
    reserved_names = {
        "rock.raw",
        "rock_geometry.raw",
        "rock_waterdrive.raw",
        "input-decomp.db",
        "input-production.TEMPLATE.db",
        "case_manifest.json",
        "connectivity_report.json",
        "geometry-prep.log",
        "decomp.log",
        "CASE_PREPARED.json",
        "READY_FOR_PARAMETERIZATION.json",
        "READY_FOR_PARAMETERIZATION.txt",
    }
    candidates = {(case_dir / name).resolve() for name in reserved_names}
    if source in candidates or source.parent == case_dir or case_dir in source.parents:
        raise SystemExit(
            "SOURCE_OUTPUT_PATH_COLLISION: source RAW must be outside the case directory "
            "and must not resolve to any preparation output"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--nx", type=int, default=128)
    parser.add_argument("--ny", type=int, default=128)
    parser.add_argument("--nz", type=int, default=128)
    parser.add_argument("--solid-value", type=int, default=0)
    parser.add_argument("--pore-value", type=int, default=1)
    parser.add_argument("--reservoir-layers", type=int, default=3)
    parser.add_argument("--voxel-length-um", type=float, default=1.0)
    parser.add_argument(
        "--keep",
        choices=("all", "percolating"),
        default="all",
        help="Deprecated compatibility alias: all means validate/preserve; percolating fails",
    )
    parser.add_argument("--test-only-allow-non-128", action="store_true", help=argparse.SUPPRESS)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.keep == "percolating":
        raise SystemExit(
            "Geometry mutation is no longer supported by SOP v1.3.2. "
            "Perform connectivity filtering during upstream dataset preprocessing."
        )
    if args.voxel_length_um <= 0:
        raise SystemExit("voxel length must be > 0 microns")
    if args.reservoir_layers < 3:
        raise SystemExit("reservoir layers must be >= 3 to protect the source ROI")
    if min(args.nx, args.ny, args.nz) <= 0:
        raise SystemExit("RAW dimensions must be positive")
    if args.solid_value == args.pore_value:
        raise SystemExit("solid and pore labels must differ")
    if not all(0 <= value <= 255 for value in (args.solid_value, args.pore_value)):
        raise SystemExit("solid and pore labels must fit uint8")
    if (args.solid_value, args.pore_value) != (0, 1):
        raise SystemExit("INPUT_ROCK_LABEL_UNSUPPORTED: production labels must be 0=solid, 1=pore")

    shape_zyx = (args.nz, args.ny, args.nx)
    if shape_zyx != PRODUCTION_SHAPE_ZYX and not args.test_only_allow_non_128:
        raise SystemExit("INPUT_ROCK_SHAPE_UNSUPPORTED: production RAW must be exactly 128x128x128")

    src = args.input.resolve()
    case_dir = args.case_dir.resolve()
    if not src.is_file():
        raise SystemExit(f"Input RAW does not exist or is not a file: {src}")
    assert_no_source_output_collision(src, case_dir)
    if case_dir.exists() and any(case_dir.iterdir()):
        raise SystemExit(f"CASE_DIRECTORY_NOT_EMPTY: {case_dir}")

    source_sha256_before = sha256(src)
    data = src.read_bytes()
    nvox = args.nx * args.ny * args.nz
    if len(data) != nvox:
        raise SystemExit(f"RAW size mismatch: got {len(data)}, expected {nvox}")

    counts = Counter(data)
    unknown = sorted(set(counts) - {args.solid_value, args.pore_value})
    if unknown:
        raise SystemExit(
            f"INPUT_ROCK_LABEL_INVALID: unexpected uint8 values {unknown}; expected only 0 and 1"
        )

    connectivity = connectivity_6(data, args.nx, args.ny, args.nz, args.pore_value)
    pore_voxels = connectivity["pore_voxels"]
    solid_voxels = nvox - pore_voxels
    porosity = pore_voxels / nvox
    connectivity_report = {
        "schema_version": 1,
        "status": "PASS" if connectivity["z_percolating"] else "FAIL",
        "source_file": str(src),
        "source_sha256": source_sha256_before,
        "shape_zyx": list(shape_zyx),
        "dtype": "uint8",
        "labels": {"solid": args.solid_value, "pore": args.pore_value},
        "flow_axis": "+Z",
        "connectivity_definition": {
            "neighbors": 6,
            "inlet_plane": "z=0",
            "outlet_plane": "z=nz-1",
        },
        "total_voxels": nvox,
        "solid_voxels": solid_voxels,
        "pore_voxels": pore_voxels,
        "porosity": porosity,
        "z_percolating": connectivity["z_percolating"],
        "spanning_voxels": connectivity["spanning_voxels"],
        "connected_component_count": connectivity["connected_component_count"],
        "spanning_component_count": connectivity["spanning_component_count"],
        "geometry_modified": False,
    }

    case_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(case_dir / "connectivity_report.json", connectivity_report)
    if sha256(src) != source_sha256_before:
        raise SystemExit("SOURCE_ROCK_IMMUTABILITY_FAILED: source SHA256 changed during validation")
    if not connectivity["z_percolating"]:
        raise SystemExit(
            "INPUT_ROCK_CONNECTIVITY_FAILED: no +Z spanning pore component under 6-neighbor connectivity"
        )

    rock_copy = case_dir / "rock.raw"
    geometry_path = case_dir / "rock_geometry.raw"
    atomic_write_bytes(rock_copy, data)
    atomic_write_bytes(geometry_path, data)

    r = args.reservoir_layers
    plane = args.nx * args.ny
    ext_nz = args.nz + 2 * r
    ext = bytearray([1]) * (ext_nz * plane)
    ext[: r * plane] = bytes([2]) * (r * plane)
    roi_start = r * plane
    ext[roi_start : roi_start + nvox] = data
    ext_path = case_dir / "rock_waterdrive.raw"
    atomic_write_bytes(ext_path, bytes(ext))

    if bytes(ext[roi_start : roi_start + nvox]) != data:
        raise SystemExit("SIMULATION_ROI_PRESERVATION_FAILED: embedded ROI differs from source RAW")
    source_sha256_after = sha256(src)
    if source_sha256_after != source_sha256_before or sha256_bytes(data) != source_sha256_before:
        raise SystemExit("SOURCE_ROCK_IMMUTABILITY_FAILED: source SHA256 changed during case preparation")

    manifest = {
        "schema_version": 1,
        "sop_version": SOP_VERSION,
        "status": "CASE_GEOMETRY_PREPARED_NOT_PHYSICALLY_PARAMETERIZED",
        "source_roi": {
            "source_file": str(src),
            "shape_zyx": list(shape_zyx),
            "dtype": "uint8",
            "labels": {"solid": 0, "pore": 1},
            "byte_count": nvox,
            "sha256": source_sha256_before,
            "sha256_before": source_sha256_before,
            "sha256_after": source_sha256_after,
            "solid_voxels": solid_voxels,
            "pore_voxels": pore_voxels,
            "porosity": porosity,
            "geometry_modified": False,
        },
        "connectivity": {
            "status": "PASS",
            "report_file": "connectivity_report.json",
            "flow_axis": "+Z",
            "neighbors": 6,
            "z_percolating": True,
        },
        "simulation": {
            "roi_preserved": True,
            "simulation_roi": {
                "filename": "rock_geometry.raw",
                "shape_zyx": list(shape_zyx),
                "sha256": sha256(geometry_path),
                "byte_for_byte_equal_to_source": True,
            },
            "simulation_domain": {
                "filename": "rock_waterdrive.raw",
                "shape_zyx": [ext_nz, args.ny, args.nx],
                "sha256": sha256(ext_path),
                "byte_count": ext_nz * plane,
            },
            "augmentation": {
                "type": "z_reservoir_layers",
                "inlet_layers": r,
                "outlet_layers": r,
                "inlet_phase_label": 2,
                "outlet_phase_label": 1,
            },
            "roi_offset_zyx": [r, 0, 0],
            "roi_slice_z": [r, r + args.nz],
        },
        "saturation_contract": {
            "pore_space_basis": "source_128_cube_roi",
            "numerator_domain": "residual_gas_voxels_inside_source_roi",
            "denominator_pore_voxels": pore_voxels,
            "reservoirs_excluded": True,
        },
        "voxel_length_um": args.voxel_length_um,
        "expected_bytes": {
            "rock.raw": nvox,
            "rock_geometry.raw": nvox,
            "rock_waterdrive.raw": ext_nz * plane,
            "ID.00000": (args.nx + 2) * (args.ny + 2) * (ext_nz + 2),
        },
    }
    atomic_write_json(case_dir / "case_manifest.json", manifest)

    atomic_write_text(case_dir / "input-decomp.db", f'''Domain {{
    Filename = "rock_waterdrive.raw"
    nproc = 1, 1, 1
    n = {args.nx}, {args.ny}, {ext_nz}
    N = {args.nx}, {args.ny}, {ext_nz}
    voxel_length = {args.voxel_length_um}
    BC = 0
    ReadType = "8bit"
    ReadValues = 0, 1, 2
    WriteValues = 0, 1, 2
}}
Analysis {{
}}
Visualization {{
}}
''')

    atomic_write_text(case_dir / "input-production.TEMPLATE.db", f'''// TEMPLATE ONLY. Do not run until every __PLACEHOLDER__ is frozen.
Color {{
    protocol = "__PROTOCOL__"
    capillary_number = __CA_IF_USED__
    tauA = __TAU_GAS__
    tauB = __TAU_WATER__
    rhoA = __RHO_GAS__
    rhoB = __RHO_WATER__
    alpha = __ALPHA__
    beta = __BETA__
    F = __FX__, __FY__, __FZ__
    Restart = false
    din = __DIN__
    dout = __DOUT__
    timestepMax = __TIMESTEP_MAX__
    WettingConvention = "__WETTING_CONVENTION__"
    ComponentLabels = 0
    ComponentAffinity = __AFFINITY__
}}
Domain {{
    Filename = "rock_waterdrive.raw"
    nproc = 1, 1, 1
    n = {args.nx}, {args.ny}, {ext_nz}
    N = {args.nx}, {args.ny}, {ext_nz}
    voxel_length = {args.voxel_length_um}
    BC = __BC__
    InletLayers = 0, 0, {r}
    OutletLayers = 0, 0, {r}
    InletLayersPhase = 2
    OutletLayersPhase = 1
    ReadType = "8bit"
    ReadValues = 0, 1, 2
    WriteValues = 0, 1, 2
}}
Analysis {{
    analysis_interval = __ANALYSIS_INTERVAL__
    subphase_analysis_interval = __SUBPHASE_INTERVAL__
    restart_interval = __RESTART_INTERVAL__
    visualization_interval = __VIS_INTERVAL__
    restart_file = "Restart"
    N_threads = __ANALYSIS_THREADS__
    load_balance = "independent"
}}
Visualization {{
    write_silo = false
    save_8bit_raw = true
    save_phase_field = false
    save_pressure = false
    save_velocity = false
}}
FlowAdaptor {{
}}
''')

    if sha256(src) != source_sha256_before:
        raise SystemExit("SOURCE_ROCK_IMMUTABILITY_FAILED: source SHA256 changed after output writes")

    print(f"Case geometry prepared: {case_dir}")
    print(f"source_sha256_before={source_sha256_before}")
    print(f"source_sha256_after={source_sha256_after}")
    print(f"connected_components={connectivity['connected_component_count']}")
    print(f"spanning_components={connectivity['spanning_component_count']}")
    print(f"porosity={porosity:.12g}")
    print("geometry_modified=false")
    print("simulation_roi_preserved=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
