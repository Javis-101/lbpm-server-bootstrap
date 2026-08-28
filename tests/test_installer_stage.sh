#!/usr/bin/env bash
set -Eeuo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$TEST_DIR/.." && pwd -P)"
TEMP_ROOT="$(mktemp -d)"
trap 'rm -r -- "$TEMP_ROOT"' EXIT

INSTALLER_FIXTURE="$TEMP_ROOT/installer"
mkdir -p "$INSTALLER_FIXTURE"
cat > "$INSTALLER_FIXTURE/setup.sh" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail
[[ "${1:-}" == "--prefix" && -n "${2:-}" ]]
prefix="$2"
mkdir -p "$prefix"

write_manifest() {
  cat > "$prefix/LBPM_BUILD_MANIFEST.txt" <<'MANIFEST'
INSTALLER_VERSION=2.0.7-offline
LBPM_REPO=https://github.com/OPM/LBPM
LBPM_COMMIT=6d686d354e5b8140841d3601e4c8c0e4e4b77e48
PATCHSET_ID=outletlayersphase-fix-v1
PATCH_SHA256=fbce8ac8f101c5f5ff3764c4e6e71f98d5a478e54609f3d63864dbc8e7d1c2b8
OPENMPI_VERSION=4.1.8
ZLIB_VERSION=1.3.2
HDF5_VERSION=1.14.6
MANIFEST
}

case "${FIXTURE_MODE:?}" in
  exit126) exit 126 ;;
  exit1) exit 1 ;;
  no_manifest) exit 0 ;;
  wrong_manifest)
    write_manifest
    printf 'INSTALLER_VERSION=wrong\n' > "$prefix/LBPM_BUILD_MANIFEST.txt"
    ;;
  missing_env)
    write_manifest
    ;;
  pass)
    write_manifest
    : > "$prefix/lbpm_env.sh"
    ;;
  *) printf 'unknown fixture mode: %s\n' "$FIXTURE_MODE" >&2; exit 2 ;;
esac
SH
chmod +x "$INSTALLER_FIXTURE/setup.sh"

make_identity() {
  local path="$1"
  mkdir -p "$(dirname "$path")"
  cat > "$path" <<'JSON'
{
  "status": "PASS",
  "installer_version": "2.0.7-offline",
  "lbpm_repo": "https://github.com/OPM/LBPM",
  "lbpm_commit": "6d686d354e5b8140841d3601e4c8c0e4e4b77e48",
  "patchset_id": "outletlayersphase-fix-v1",
  "patch_sha256": "fbce8ac8f101c5f5ff3764c4e6e71f98d5a478e54609f3d63864dbc8e7d1c2b8",
  "openmpi_version": "4.1.8",
  "zlib_version": "1.3.2",
  "hdf5_version": "1.14.6"
}
JSON
}

run_fixture() {
  local name="$1" mode="$2" evidence="${3:-0}"
  local case_root="$TEMP_ROOT/$name"
  mkdir -p "$case_root/run/logs" "$case_root/run/state" "$case_root/run/evidence" \
    "$case_root/run/host" "$case_root/run/validation" "$case_root/run/simulations" \
    "$case_root/run/artifacts" "$case_root/stack"
  : > "$case_root/run/logs/bootstrap.log"
  make_identity "$case_root/run/state/package-identity.json"

  if bash -Eeuo pipefail -c '
    source "$1"
    RUN_ROOT="$2/run"
    RUN_ID="$(basename "$RUN_ROOT")"
    LOG_DIR="$RUN_ROOT/logs"
    STATE_FILE="$RUN_ROOT/bootstrap-state.json"
    INSTALLER_ROOT="$3"
    STACK_DIR="$2/stack"
    WORK_DIR="$RUN_ROOT/work"
    SOP_ROOT="$WORK_DIR/LBPM-postinstall-SOP-v1.3.2"
    CASE_DIR="$RUN_ROOT/simulations/41_001"
    VERBOSE=0
    FIXTURE_MODE="$4"
    export FIXTURE_MODE
    if [[ "$5" == "1" ]]; then trap '\''on_exit $?'\'' EXIT; fi
    run_stage 4 installer "LBPM installation/reuse" stage_installer "$LOG_DIR/04-installer.log"
    : > "$2/stage5-sentinel"
  ' _ "$ROOT/run_all.sh" "$case_root" "$INSTALLER_FIXTURE" "$mode" "$evidence"; then
    FIXTURE_RC=0
  else
    FIXTURE_RC=$?
  fi
}

assert_failed() {
  local name="$1" mode="$2" expected_rc="$3" expected_text="$4" evidence="${5:-0}"
  run_fixture "$name" "$mode" "$evidence"
  [[ "$FIXTURE_RC" -eq "$expected_rc" ]]
  [[ ! -e "$TEMP_ROOT/$name/stage5-sentinel" ]]
  grep -F "$expected_text" "$TEMP_ROOT/$name/run/logs/04-installer.log" >/dev/null
  python3 - "$TEMP_ROOT/$name/run/bootstrap-state.json" <<'PY'
import json, sys
from pathlib import Path
state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert state["stages"]["installer"]["status"] == "FAIL", state
PY
}

assert_failed exit126 exit126 126 'Portable Installer failed with exit code 126' 1
python3 - "$TEMP_ROOT/exit126/run/summary.json" <<'PY'
import json, sys
from pathlib import Path
summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert summary["status"] == "FAIL", summary
assert summary["failed_stage"] == "installer", summary
archive = Path(summary["evidence"]["archive"])
assert archive.is_file(), archive
assert Path(str(archive) + ".sha256").is_file(), archive
PY

assert_failed exit1 exit1 1 'Portable Installer failed with exit code 1'
assert_failed no_manifest no_manifest 1 'POST_INSTALL_STACK_MISSING'
assert_failed wrong_manifest wrong_manifest 1 'FAIL_EXISTING_STACK_MISMATCH'
assert_failed missing_env missing_env 1 'POST_INSTALL_ENV_MISSING'

run_fixture pass pass
[[ "$FIXTURE_RC" -eq 0 ]]
[[ -f "$TEMP_ROOT/pass/stage5-sentinel" ]]
[[ "$(tr -d '\r\n' < "$TEMP_ROOT/pass/run/state/install-action.txt")" == "INSTALLED" ]]
python3 - "$TEMP_ROOT/pass/run/bootstrap-state.json" <<'PY'
import json, sys
from pathlib import Path
state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert state["stages"]["installer"]["status"] == "PASS", state
PY
python3 - "$TEMP_ROOT/pass/run/state/stack-after-install.json" <<'PY'
import json, sys
from pathlib import Path
stack = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert stack["status"] == "PASS", stack
assert stack["manifest_present"] is True, stack
assert stack["compatible"] is True, stack
PY

# A second run over the exact compatible stack must skip installation and pass.
SECOND="$TEMP_ROOT/second"
mkdir -p "$SECOND/run/logs" "$SECOND/run/state"
: > "$SECOND/run/logs/bootstrap.log"
make_identity "$SECOND/run/state/package-identity.json"
cp "$TEMP_ROOT/pass/stack/LBPM_BUILD_MANIFEST.txt" "$SECOND/stack-manifest.txt"
mkdir -p "$SECOND/stack"
cp "$SECOND/stack-manifest.txt" "$SECOND/stack/LBPM_BUILD_MANIFEST.txt"
: > "$SECOND/stack/lbpm_env.sh"
if bash -Eeuo pipefail -c '
  source "$1"
  RUN_ROOT="$2/run"; RUN_ID="run"; LOG_DIR="$RUN_ROOT/logs"
  STATE_FILE="$RUN_ROOT/bootstrap-state.json"; INSTALLER_ROOT="$3"
  STACK_DIR="$2/stack"; VERBOSE=0
  run_stage 4 installer "LBPM installation/reuse" stage_installer "$LOG_DIR/04-installer.log"
' _ "$ROOT/run_all.sh" "$SECOND" "$INSTALLER_FIXTURE"; then
  :
else
  printf 'Compatible second-run fixture unexpectedly failed\n' >&2
  exit 1
fi
[[ "$(tr -d '\r\n' < "$SECOND/run/state/install-action.txt")" == "SKIPPED" ]]

printf 'INSTALLER_STAGE_CONTRACT_PASS\n'
