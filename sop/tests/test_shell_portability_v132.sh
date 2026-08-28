#!/usr/bin/env bash
set -Eeuo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$TEST_DIR/.." && pwd -P)"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -r -- "$TEMP_ROOT"' EXIT

cp -R "$ROOT/." "$TEMP_ROOT/sop"
find "$TEMP_ROOT/sop" -type f -name '*.sh' -exec chmod 0644 {} +

STACK_DIR="$TEMP_ROOT/stack"
DATA_DIR="$TEMP_ROOT/data"
VALIDATION_DIR="$DATA_DIR/validation"
SIMULATION_DIR="$DATA_DIR/simulations"
mkdir -p "$STACK_DIR" "$VALIDATION_DIR" "$SIMULATION_DIR"
: > "$STACK_DIR/lbpm_env.sh"

set +e
acceptance_output="$(STACK_DIR="$STACK_DIR" DATA_DIR="$DATA_DIR" \
  VALIDATION_DIR="$VALIDATION_DIR" SIMULATION_DIR="$SIMULATION_DIR" \
  bash "$TEMP_ROOT/sop/bin/post_install_acceptance.sh" 2>&1)"
acceptance_rc=$?
set -e
[[ "$acceptance_rc" -ne 0 ]]
[[ "$acceptance_output" != *"Permission denied"* ]]
[[ "$acceptance_output" == *"Missing required command:"* || \
   "$acceptance_output" == *"Missing $STACK_DIR/LBPM_BUILD_MANIFEST.txt"* ]]

printf '{"schema_version":1,"status":"PASS"}\n' > "$VALIDATION_DIR/acceptance_report.json"
python3 -c 'from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(bytes([1]) * (128 ** 3))' \
  "$TEMP_ROOT/rock.raw"
set +e
case_output="$(STACK_DIR="$STACK_DIR" DATA_DIR="$DATA_DIR" \
  VALIDATION_DIR="$VALIDATION_DIR" SIMULATION_DIR="$SIMULATION_DIR" \
  bash "$TEMP_ROOT/sop/bin/run_to_parameterization.sh" \
    --rock "$TEMP_ROOT/rock.raw" --case-id portability --skip-postinstall 2>&1)"
case_rc=$?
set -e
[[ "$case_rc" -ne 0 ]]
[[ "$case_output" != *"Permission denied"* ]]
[[ -f "$SIMULATION_DIR/portability/case_manifest.json" ]]
[[ "$case_output" == *"[ERROR]"* ]]

printf 'SOP_0644_CHILD_SHELL_PASS\n'
