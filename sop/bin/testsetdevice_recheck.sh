#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"
source_lbpm_env
BUILD_DIR="$STACK_DIR/build/LBPM"
[[ -d "$BUILD_DIR" ]] || die "Missing LBPM build directory: $BUILD_DIR"
require_cmd ctest
ctest --test-dir "$BUILD_DIR" -N | grep -q 'TestSetDevice' || die "TestSetDevice is missing"
log "Re-running TestSetDevice (validation only)"
OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 \
  ctest --test-dir "$BUILD_DIR" -R '^TestSetDevice$' --output-on-failure
python3 - "$SCRIPT_DIR" "$VALIDATION_DIR/TestSetDevice.PASS.json" <<'PY'
import sys
from datetime import datetime, timezone
sys.path.insert(0, sys.argv[1])
from state_reports import atomic_json
atomic_json(__import__('pathlib').Path(sys.argv[2]), {
    "schema_version": 1,
    "sop_version": "1.3.2",
    "status": "PASS",
    "check": "TestSetDevice",
    "completed_at": datetime.now(timezone.utc).isoformat(),
})
PY
