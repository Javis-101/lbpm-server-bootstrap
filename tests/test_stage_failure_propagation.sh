#!/usr/bin/env bash
set -Eeuo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$TEST_DIR/.." && pwd -P)"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -r -- "$TEMP_ROOT"' EXIT

if bash -Eeuo pipefail -c '
  source "$1"
  RUN_ID="stage-failure-fixture"
  RUN_ROOT="$2/run"
  LOG_DIR="$RUN_ROOT/logs"
  STATE_FILE="$RUN_ROOT/bootstrap-state.json"
  VERBOSE=0
  mkdir -p "$LOG_DIR"
  : > "$LOG_DIR/bootstrap.log"
  SENTINEL="$2/must-not-exist"
  stage_with_unhandled_failure() {
    printf "before failure\n"
    false
    : > "$SENTINEL"
  }
  run_stage 4 installer "Failure propagation fixture" \
    stage_with_unhandled_failure "$LOG_DIR/04-installer.log"
' _ "$ROOT/run_all.sh" "$TEMP_ROOT"; then
  stage_rc=0
else
  stage_rc=$?
fi

[[ "$stage_rc" -ne 0 ]]
[[ ! -e "$TEMP_ROOT/must-not-exist" ]]
python3 - "$TEMP_ROOT/run/bootstrap-state.json" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
installer = state["stages"]["installer"]
assert installer["status"] == "FAIL", installer
PY

printf 'STAGE_FAILURE_PROPAGATION_PASS\n'
