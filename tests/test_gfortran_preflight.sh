#!/usr/bin/env bash
set -Eeuo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$TEST_DIR/.." && pwd -P)"
# shellcheck disable=SC1091
source "$ROOT/run_all.sh"
unset CONDA_PREFIX CONDA_DEFAULT_ENV VIRTUAL_ENV

TEMP_ROOT="$(mktemp -d)"
trap 'rm -r -- "$TEMP_ROOT"' EXIT
RUN_ROOT="$TEMP_ROOT/direct-run"
DATA_MOUNT="$TEMP_ROOT/data"
BOOTSTRAP_RUN_ROOT="$TEMP_ROOT/runs"
mkdir -p "$RUN_ROOT/host" "$DATA_MOUNT" "$BOOTSTRAP_RUN_ROOT"

effective_uid(){ printf '0\n'; }
kernel_name(){ printf 'Linux\n'; }
machine_arch(){ printf 'x86_64\n'; }
ubuntu_like_os(){ return 0; }
data_mount_writable(){ return 0; }
visible_gpu_count(){ printf '1\n'; }
capture_host_evidence(){ return 0; }
TEST_ONLY="${GFORTRAN_TEST_ONLY:-ALL}"

expect_fail(){
  local expected="$1"; shift
  local output
  if output="$("$@" 2>&1)"; then
    printf 'Expected failure but command passed: %s\n' "$expected" >&2
    exit 1
  fi
  [[ "$output" == *"$expected"* ]] || {
    printf 'Failure did not contain %s: %s\n' "$expected" "$output" >&2
    exit 1
  }
}

# G1: the executable itself is a required host prerequisite.
if [[ "$TEST_ONLY" == "ALL" || "$TEST_ONLY" == "G1" ]]; then
(
  tool_available(){ [[ "$1" != "gfortran" ]]; }
  expect_fail "GNU Fortran compiler not found" stage_host_preflight
)
fi

# G2: finding gfortran is insufficient; the real -lgfortran probe is authoritative.
if [[ "$TEST_ONLY" == "ALL" || "$TEST_ONLY" == "G2" ]]; then
(
  tool_available(){ return 0; }
  gfortran_executable(){ printf '/fixture/bin/gfortran\n'; }
  gfortran_version_line(){ printf 'GNU Fortran fixture 13.3.0\n'; }
  gfortran_link_probe(){ return 9; }
  expect_fail "Real link probe with -lgfortran failed" stage_host_preflight
)
fi

# G3: a successful executable/version/link contract records machine-readable evidence.
if [[ "$TEST_ONLY" == "ALL" || "$TEST_ONLY" == "G3" ]]; then
(
  tool_available(){ return 0; }
  gfortran_executable(){ printf '/fixture/bin/gfortran\n'; }
  gfortran_version_line(){ printf 'GNU Fortran fixture 13.3.0\n'; }
  gfortran_link_probe(){ return 0; }
  stage_host_preflight
  python3 - "$RUN_ROOT/host/prerequisites.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["schema_version"] == 1, payload
assert payload["gfortran"]["path"] == "/fixture/bin/gfortran", payload
assert payload["gfortran"]["version"] == "GNU Fortran fixture 13.3.0", payload
assert payload["gfortran"]["link_test"] == "PASS", payload
PY
)
fi

# G4: a Stage 2 link failure must stop Stage 3/4 and still produce FAIL evidence.
if [[ "$TEST_ONLY" == "ALL" || "$TEST_ONLY" == "G4" ]]; then
PROPAGATION_RUN="$TEMP_ROOT/propagation-run"
set +e
(
  set -Eeuo pipefail
  RUN_ROOT="$PROPAGATION_RUN"
  RUN_ID="gfortran-propagation"
  LOG_DIR="$RUN_ROOT/logs"
  STATE_FILE="$RUN_ROOT/bootstrap-state.json"
  STACK_DIR="$TEMP_ROOT/stack"
  INSTALLER_ROOT=""
  CASE_DIR="$RUN_ROOT/simulations/41_001"
  VERBOSE=0
  FINALIZED=0
  mkdir -p "$LOG_DIR" "$RUN_ROOT/host" "$RUN_ROOT/state" "$RUN_ROOT/evidence"
  : > "$LOG_DIR/bootstrap.log"
  effective_uid(){ printf '0\n'; }
  kernel_name(){ printf 'Linux\n'; }
  machine_arch(){ printf 'x86_64\n'; }
  ubuntu_like_os(){ return 0; }
  data_mount_writable(){ return 0; }
  tool_available(){ return 0; }
  visible_gpu_count(){ printf '1\n'; }
  capture_host_evidence(){ return 0; }
  gfortran_executable(){ printf '/fixture/bin/gfortran\n'; }
  gfortran_version_line(){ printf 'GNU Fortran fixture 13.3.0\n'; }
  gfortran_link_probe(){ return 9; }
  trap 'finalize_run $?' EXIT
  run_stage 2 host_preflight "Host preflight" stage_host_preflight "$LOG_DIR/02-host-preflight.log"
  : > "$TEMP_ROOT/stage3-must-not-run"
  : > "$TEMP_ROOT/stage4-must-not-run"
)
propagation_rc=$?
set -e
[[ "$propagation_rc" -ne 0 ]]
[[ ! -e "$TEMP_ROOT/stage3-must-not-run" ]]
[[ ! -e "$TEMP_ROOT/stage4-must-not-run" ]]
python3 - "$PROPAGATION_RUN/summary.json" <<'PY'
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert summary["status"] == "FAIL", summary
assert summary["failed_stage"] == "host_preflight", summary
assert "-lgfortran" in summary["fail_reason"], summary
archive = Path(summary["evidence"]["archive"])
assert archive.is_file(), archive
assert Path(str(archive) + ".sha256").is_file(), archive
PY
fi

# G5: the real probe must remove its temporary directory after PASS and FAIL.
if [[ "$TEST_ONLY" == "ALL" || "$TEST_ONLY" == "G5" ]]; then
FAKE_BIN="$TEMP_ROOT/fake-bin"
PROBE_TMP="$TEMP_ROOT/probe-tmp"
mkdir -p "$FAKE_BIN" "$PROBE_TMP"
cat > "$FAKE_BIN/g++" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail
output=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-o" ]]; then output="$2"; shift 2; else shift; fi
done
if [[ "${FAKE_GFORTRAN_LINK_RESULT:-FAIL}" == "PASS" ]]; then
  : > "$output"
  exit 0
fi
exit 9
SH
chmod 0755 "$FAKE_BIN/g++"

PATH="$FAKE_BIN:$PATH" TMPDIR="$PROBE_TMP" FAKE_GFORTRAN_LINK_RESULT=PASS gfortran_link_probe
[[ -z "$(find "$PROBE_TMP" -mindepth 1 -print -quit)" ]]
set +e
PATH="$FAKE_BIN:$PATH" TMPDIR="$PROBE_TMP" FAKE_GFORTRAN_LINK_RESULT=FAIL gfortran_link_probe
probe_rc=$?
set -e
[[ "$probe_rc" -ne 0 ]]
[[ -z "$(find "$PROBE_TMP" -mindepth 1 -print -quit)" ]]
fi

printf 'GFORTRAN_PREFLIGHT_G1_G5_PASS\n'
