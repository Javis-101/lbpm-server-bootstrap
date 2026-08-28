#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

usage(){
cat <<'USAGE'
Usage:
  run_to_parameterization.sh --rock /path/final_128_cube.raw --case-id rock-000001 [options]
Options:
  --skip-postinstall
  --first-case-smoke
  --keep all|percolating   'all' is a deprecated preserve alias; percolating fails
  --voxel-length-um X      Default: 1.0 micron
USAGE
}
ROCK=""; CASE_ID=""; SKIP=0; SMOKE=0; KEEP="all"; VOXEL_LENGTH_UM=1.0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rock) ROCK="$2"; shift 2;;
    --case-id) CASE_ID="$2"; shift 2;;
    --skip-postinstall) SKIP=1; shift;;
    --first-case-smoke) SMOKE=1; shift;;
    --keep) KEEP="$2"; shift 2;;
    --voxel-length-um) VOXEL_LENGTH_UM="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) usage; die "Unknown option: $1";;
  esac
done
[[ -n "$ROCK" && -n "$CASE_ID" ]] || { usage; exit 2; }

if [[ "$SKIP" -eq 0 ]]; then
  bash "$SCRIPT_DIR/post_install_acceptance.sh"
else
  require_acceptance_pass "$VALIDATION_DIR/acceptance_report.json"
fi

bash "$SCRIPT_DIR/prepare_case.sh" --input "$ROCK" --case-id "$CASE_ID" \
  --keep "$KEEP" --voxel-length-um "$VOXEL_LENGTH_UM"
SMOKE_STATUS="NOT_REQUIRED"
if [[ "$SMOKE" -eq 1 ]]; then
  bash "$SCRIPT_DIR/first_case_smoke_test.sh" "$SIMULATION_DIR/$CASE_ID"
  SMOKE_STATUS="PASS"
fi
python3 "$SCRIPT_DIR/state_reports.py" case-ready \
  --case-dir "$SIMULATION_DIR/$CASE_ID" \
  --acceptance-report "$VALIDATION_DIR/acceptance_report.json" \
  --smoke-status "$SMOKE_STATUS"
log "Case READY_FOR_PARAMETERIZATION with smoke_test=$SMOKE_STATUS"
