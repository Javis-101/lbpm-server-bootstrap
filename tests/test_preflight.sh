#!/usr/bin/env bash
set -Eeuo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$TEST_DIR/.." && pwd -P)"

# shellcheck disable=SC1091
source "$ROOT/run_all.sh"
unset CONDA_PREFIX CONDA_DEFAULT_ENV VIRTUAL_ENV

TEMP_ROOT="$(mktemp -d)"
trap 'rm -r -- "$TEMP_ROOT"' EXIT
RUN_ROOT="$TEMP_ROOT/run"
DATA_MOUNT="$TEMP_ROOT/data"
BOOTSTRAP_RUN_ROOT="$TEMP_ROOT/runs"
mkdir -p "$RUN_ROOT/host" "$DATA_MOUNT" "$BOOTSTRAP_RUN_ROOT"

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
gfortran_link_probe(){ return 0; }

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

(
  effective_uid(){ printf '1000\n'; }
  expect_fail "requires root" stage_host_preflight
)

(
  tool_available(){ [[ "$1" != "nvidia-smi" ]]; }
  expect_fail "nvidia-smi" stage_host_preflight
)

(
  tool_available(){ [[ "$1" != "nvcc" ]]; }
  expect_fail "nvcc" stage_host_preflight
)

(
  data_mount_writable(){ return 1; }
  expect_fail "not writable" stage_host_preflight
)

(
  export CONDA_PREFIX="$TEMP_ROOT/conda"
  expect_fail "Active Python environment detected" stage_host_preflight
)

(
  export VIRTUAL_ENV="$TEMP_ROOT/venv"
  expect_fail "Active Python environment detected" stage_host_preflight
)

(
  export CONDA_DEFAULT_ENV="py312"
  expect_fail "Active Python environment detected" stage_host_preflight
)

stage_host_preflight

INSTALLER_ROOT="$TEMP_ROOT/installer"
mkdir -p "$INSTALLER_ROOT"
cat > "$INSTALLER_ROOT/verify_sources.sh" <<SH
#!/usr/bin/env bash
set -Eeuo pipefail
: > "$TEMP_ROOT/stage3-verified"
SH
chmod 0644 "$INSTALLER_ROOT/verify_sources.sh"
stage_source_verification
[[ -f "$TEMP_ROOT/stage3-verified" ]]

RUN_ROOT=""
BLOCKER="$TEMP_ROOT/not-a-directory"
: > "$BLOCKER"
(
  BOOTSTRAP_RUN_ROOT="$BLOCKER/child"
  expect_fail "Unable to create configured BOOTSTRAP_RUN_ROOT" create_run_root
)
[[ -z "$RUN_ROOT" ]]

printf 'PREFLIGHT_TESTS_PASS\n'
