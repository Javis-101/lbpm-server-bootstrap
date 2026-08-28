#!/usr/bin/env bash
# SOP v1.3.2 validates an installed stack; it never patches or rebuilds LBPM.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"
mkdir -p "$VALIDATION_DIR" "$SIMULATION_DIR"

python3 "$SCRIPT_DIR/state_reports.py" acceptance-start --validation-dir "$VALIDATION_DIR"
CURRENT_CHECK="initialization"
on_failure(){
  local rc=$?
  trap - ERR
  python3 "$SCRIPT_DIR/state_reports.py" acceptance-fail \
    --validation-dir "$VALIDATION_DIR" --failed-check "$CURRENT_CHECK" --exit-code "$rc" || true
  exit "$rc"
}
trap on_failure ERR

log "LBPM post-install acceptance v1.3.2"
CURRENT_CHECK="software_verification"
bash "$SCRIPT_DIR/verify_lbpm_install.sh"
CURRENT_CHECK="testsetdevice"
bash "$SCRIPT_DIR/testsetdevice_recheck.sh"
CURRENT_CHECK="piston"
bash "$SCRIPT_DIR/piston_acceptance.sh"
CURRENT_CHECK="acceptance_report"
python3 "$SCRIPT_DIR/state_reports.py" acceptance-pass \
  --validation-dir "$VALIDATION_DIR" \
  --software-report "$VALIDATION_DIR/software-verification.json" \
  --testsetdevice-report "$VALIDATION_DIR/TestSetDevice.PASS.json" \
  --piston-report "$VALIDATION_DIR/piston_result.json"
trap - ERR
log "All post-install acceptance checks PASS"
