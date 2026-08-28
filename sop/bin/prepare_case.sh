#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

usage(){
cat <<'USAGE'
Usage:
  prepare_case.sh --input /path/to/final_128_cube.raw --case-id rock-000001 [options]
Options:
  --case-dir DIR          Override target case directory
  --keep all              Deprecated alias for validate/preserve (default)
  --keep percolating      Fails: geometry mutation was removed in v1.3.1
  --reservoir-layers N    Default: 3 (must be >=3)
  --voxel-length-um X     Default: 1.0 micron

Production RAW shape is fixed at 128 x 128 x 128 uint8, labels 0=solid and 1=pore.
USAGE
}

INPUT=""; CASE_ID=""; CASE_DIR=""; KEEP="all"
R=3; VOXEL_LENGTH_UM=1.0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --input) INPUT="$2"; shift 2;;
    --case-id) CASE_ID="$2"; shift 2;;
    --case-dir) CASE_DIR="$2"; shift 2;;
    --keep) KEEP="$2"; shift 2;;
    --reservoir-layers) R="$2"; shift 2;;
    --voxel-length-um) VOXEL_LENGTH_UM="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) usage; die "Unknown option: $1";;
  esac
done

[[ -n "$INPUT" ]] || { usage; die "--input is required"; }
if [[ "$KEEP" == "percolating" ]]; then
  die "Geometry mutation is no longer supported by SOP v1.3.2. Perform connectivity filtering during upstream dataset preprocessing."
fi
[[ "$KEEP" == "all" ]] || die "--keep only accepts deprecated alias 'all'; production behavior is validate/preserve"
if [[ -z "$CASE_DIR" ]]; then
  [[ -n "$CASE_ID" ]] || { usage; die "--case-id or --case-dir is required"; }
  CASE_DIR="$SIMULATION_DIR/$CASE_ID"
fi

require_acceptance_pass "$VALIDATION_DIR/acceptance_report.json"
source_lbpm_env
python3 "$SCRIPT_DIR/state_reports.py" case-start \
  --case-dir "$CASE_DIR" --case-id "$CASE_ID"

GEOMETRY_LOG="$(mktemp)"
if python3 "$SCRIPT_DIR/prepare_rock_case.py" \
  --input "$INPUT" --case-dir "$CASE_DIR" \
  --nx 128 --ny 128 --nz 128 --reservoir-layers "$R" \
  --voxel-length-um "$VOXEL_LENGTH_UM" --keep all 2>&1 | tee "$GEOMETRY_LOG"; then
  mv "$GEOMETRY_LOG" "$CASE_DIR/geometry-prep.log"
else
  rc=${PIPESTATUS[0]}
  mv "$GEOMETRY_LOG" "$CASE_DIR/geometry-prep.log"
  exit "$rc"
fi

cd "$CASE_DIR"
log "Running lbpm_serial_decomp"
mpi_run -np 1 lbpm_serial_decomp input-decomp.db 2>&1 | tee decomp.log
[[ -f ID.00000 ]] || die "ID.00000 not generated"
python3 - <<'PY'
import json
from pathlib import Path
manifest = json.loads(Path("case_manifest.json").read_text())
expected = int(manifest["expected_bytes"]["ID.00000"])
actual = Path("ID.00000").stat().st_size
print(f"ID.00000 actual={actual}, expected={expected}")
if actual != expected:
    raise SystemExit("ID.00000 size mismatch")
PY

python3 "$SCRIPT_DIR/verify_case_contract.py" --case-dir "$CASE_DIR" | tee case-contract-check.log
python3 "$SCRIPT_DIR/state_reports.py" case-prepared \
  --case-dir "$CASE_DIR" --acceptance-report "$VALIDATION_DIR/acceptance_report.json"
log "Case PREPARED; READY is published only by run_to_parameterization.sh after smoke state is known"
