#!/usr/bin/env python3
"""Validate ColorModel RAW outputs inside the immutable source ROI."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-final-timestep", type=int, default=2000)
    parser.add_argument("--tolerance", type=float, default=1.0e-9)
    args = parser.parse_args()

    case = args.case_dir.resolve()
    output = args.output_dir.resolve()
    manifest = json.loads((case / "case_manifest.json").read_text(encoding="utf-8"))
    source_roi = manifest["source_roi"]
    nz, ny, nx = map(int, source_roi["shape_zyx"])
    ext_nz, ext_ny, ext_nx = map(
        int, manifest["simulation"]["simulation_domain"]["shape_zyx"]
    )
    if (ext_ny, ext_nx) != (ny, nx):
        raise SystemExit("simulation domain XY shape differs from source ROI")
    offset_z = int(manifest["simulation"]["roi_offset_zyx"][0])
    plane = nx * ny
    expected_pores = int(source_roi["pore_voxels"])
    if expected_pores <= 0:
        raise SystemExit("source ROI pore voxel count must be positive")
    source = (case / "rock_geometry.raw").read_bytes()

    files: list[tuple[int, Path]] = []
    for path in output.glob("id_t*.raw"):
        match = re.fullmatch(r"id_t(\d+)\.raw", path.name)
        if match:
            files.append((int(match.group(1)), path))
    files.sort()
    if not files:
        raise SystemExit("No id_t*.raw files found")
    timesteps = {timestep for timestep, _ in files}
    if args.expected_final_timestep not in timesteps:
        raise SystemExit(f"expected id_t{args.expected_final_timestep}.raw is missing")

    print("timestep source_pores water gas Sw_source_roi Sg_source_roi solid_changed")
    for timestep, path in files:
        data = path.read_bytes()
        expected_size = ext_nz * plane
        if len(data) != expected_size:
            raise SystemExit(f"{path}: bad size {len(data)}, expected {expected_size}")
        core = data[offset_z * plane : (offset_z + nz) * plane]
        gas = water = fluid = solid_changed = invalid_phase = 0
        for source_label, phase_label in zip(source, core):
            if source_label == 1:
                if phase_label == 1:
                    gas += 1
                elif phase_label == 2:
                    water += 1
                else:
                    invalid_phase += 1
                if phase_label in (1, 2):
                    fluid += 1
            elif phase_label != 0:
                solid_changed += 1
        if invalid_phase:
            raise SystemExit(f"t={timestep}: pore voxels with invalid phase labels={invalid_phase}")
        if fluid != expected_pores:
            raise SystemExit(f"t={timestep}: fluid={fluid}, expected source pores={expected_pores}")
        if solid_changed:
            raise SystemExit(f"t={timestep}: source solid voxels changed={solid_changed}")
        sw = water / expected_pores
        sg = gas / expected_pores
        if not math.isfinite(sw) or not math.isfinite(sg):
            raise SystemExit(f"t={timestep}: non-finite saturation")
        if not (-args.tolerance <= sw <= 1 + args.tolerance):
            raise SystemExit(f"t={timestep}: Sw outside numerical tolerance: {sw}")
        if not (-args.tolerance <= sg <= 1 + args.tolerance):
            raise SystemExit(f"t={timestep}: Sg outside numerical tolerance: {sg}")
        print(
            f"{timestep:8d} {fluid:12d} {water:6d} {gas:6d} "
            f"{sw:.6f} {sg:.6f} {solid_changed}"
        )
    print("CASE_OUTPUT_CHECK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
