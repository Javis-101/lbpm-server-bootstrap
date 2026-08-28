#!/usr/bin/env python3
"""Numerical smoke/sanity checks for an LBPM ColorModel run."""
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

REQUIRED_COLUMNS = (
    "sw",
    "krw",
    "krn",
    "krwf",
    "krnf",
    "vw",
    "vn",
    "force",
    "pw",
    "pn",
    "wet",
    "peff",
)
NONFINITE_TOKEN = re.compile(r"(?<![A-Za-z0-9_])(?:nan|[+-]?inf(?:inity)?)(?![A-Za-z0-9_])", re.I)


def split_fields(line: str) -> list[str]:
    return [field for field in re.split(r"[\s,]+", line.strip()) if field]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-log", required=True, type=Path)
    parser.add_argument("--timelog", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-final-timestep", required=True, type=int)
    parser.add_argument("--expected-raw-bytes", required=True, type=int)
    parser.add_argument("--tolerance", type=float, default=1.0e-9)
    args = parser.parse_args()

    if args.tolerance < 0:
        raise SystemExit("tolerance must be non-negative")
    if not args.run_log.is_file():
        raise SystemExit(f"run log is missing: {args.run_log}")
    log_text = args.run_log.read_text(encoding="utf-8", errors="replace")
    if "MPI rank=0 will use GPU ID" not in log_text:
        raise SystemExit("GPU binding line is missing from ColorModel log")
    if NONFINITE_TOKEN.search(log_text):
        raise SystemExit("ColorModel log contains a non-finite numeric token")

    if not args.timelog.is_file():
        raise SystemExit(f"timelog is missing: {args.timelog}")
    lines = [line for line in args.timelog.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    if len(lines) < 2:
        raise SystemExit("timelog has no data rows")
    header = split_fields(lines[0])
    missing = [name for name in REQUIRED_COLUMNS if name not in header]
    if missing:
        raise SystemExit(f"timelog required columns are missing: {missing}")
    sw_index = header.index("sw")
    rows = 0
    sw_min = math.inf
    sw_max = -math.inf
    for line_number, line in enumerate(lines[1:], start=2):
        fields = split_fields(line)
        if len(fields) != len(header):
            raise SystemExit(
                f"timelog row {line_number} has {len(fields)} values, expected {len(header)}"
            )
        try:
            values = [float(value) for value in fields]
        except ValueError as exc:
            raise SystemExit(f"timelog row {line_number} contains a non-numeric value: {exc}")
        if not all(math.isfinite(value) for value in values):
            raise SystemExit(f"timelog row {line_number} contains a non-finite value")
        saturation = values[sw_index]
        if saturation < -args.tolerance or saturation > 1.0 + args.tolerance:
            raise SystemExit(
                f"saturation out of numerical range at row {line_number}: {saturation}"
            )
        sw_min = min(sw_min, saturation)
        sw_max = max(sw_max, saturation)
        rows += 1

    final_raw = args.output_dir / f"id_t{args.expected_final_timestep}.raw"
    if not final_raw.is_file():
        raise SystemExit(f"expected final RAW is missing: {final_raw.name}")
    actual_bytes = final_raw.stat().st_size
    if actual_bytes != args.expected_raw_bytes:
        raise SystemExit(
            f"{final_raw.name} size mismatch: got {actual_bytes}, expected {args.expected_raw_bytes}"
        )

    print(f"timelog_rows={rows}")
    print(f"sw_min={sw_min:.12g}")
    print(f"sw_max={sw_max:.12g}")
    print(f"final_raw={final_raw.name}")
    print("COLOR_NUMERICAL_SANITY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
