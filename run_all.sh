#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
BOOTSTRAP_VERSION="1.0.3"
INSTALLER_ZIP_SHA256="6994dacf5674f02acf1c1a40e234f38135cc8eb70cf685ff19e655559d4de2a1"
SOP_ZIP_SHA256="946e25ef9747e1aca5eeea410d46612fbb7cc5a45090a1f6af54ae4de206fd58"

STACK_DIR="/root/rivermind-data/LBPM-stack-v207"
DATA_MOUNT="/root/rivermind-data"
BOOTSTRAP_RUN_ROOT="/root/rivermind-data/lbpm-bootstrap-runs"
MPI_RANKS="1"
VOXEL_LENGTH_UM="1.0"
EXPECTED_RAW_NX="128"
EXPECTED_RAW_NY="128"
EXPECTED_RAW_NZ="128"
FIRST_CASE_ID="41_001"
EXPECTED_FIRST_RAW_SHA256=""

RAW_PATH=""
CONFIG_PATH=""
CLI_EXPECTED_RAW_SHA256=""
VERBOSE=0
RUN_ROOT=""
RUN_ID=""
STATE_FILE=""
WORK_DIR=""
LOG_DIR=""
INSTALLER_ROOT=""
SOP_ROOT=""
CASE_DIR=""
INSTALL_ACTION=""
FAILED_STAGE=""
FAIL_REASON=""
FAILED_LOG=""
FINALIZED=0

usage() {
  cat <<'USAGE'
Usage:
  bash run_all.sh --raw /absolute/path/to/41_001.raw [options]

Options:
  --raw PATH                     Required immutable 128x128x128 uint8 RAW.
  --config PATH                  Bootstrap environment file.
  --expected-raw-sha256 HASH     Override EXPECTED_FIRST_RAW_SHA256.
  --verbose                      Stream full stage logs to the terminal.
  -h, --help                     Show this help.
USAGE
}

die_usage() {
  printf 'ERROR: %s\n' "$*" >&2
  usage >&2
  exit 2
}

load_config() {
  local path="$1" line key value
  [[ -f "$path" ]] || die_usage "Config file is missing: $path"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line//[[:space:]]/}" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" == *=* ]] || die_usage "Invalid config line (expected KEY=VALUE): $line"
    key="${line%%=*}"
    value="${line#*=}"
    key="${key//[[:space:]]/}"
    value="${value#\"}"; value="${value%\"}"
    value="${value#\'}"; value="${value%\'}"
    case "$key" in
      STACK_DIR) STACK_DIR="$value" ;;
      DATA_MOUNT) DATA_MOUNT="$value" ;;
      BOOTSTRAP_RUN_ROOT) BOOTSTRAP_RUN_ROOT="$value" ;;
      MPI_RANKS) MPI_RANKS="$value" ;;
      VOXEL_LENGTH_UM) VOXEL_LENGTH_UM="$value" ;;
      EXPECTED_RAW_NX) EXPECTED_RAW_NX="$value" ;;
      EXPECTED_RAW_NY) EXPECTED_RAW_NY="$value" ;;
      EXPECTED_RAW_NZ) EXPECTED_RAW_NZ="$value" ;;
      FIRST_CASE_ID) FIRST_CASE_ID="$value" ;;
      EXPECTED_FIRST_RAW_SHA256) EXPECTED_FIRST_RAW_SHA256="$value" ;;
      *) die_usage "Unknown config key: $key" ;;
    esac
  done < "$path"
}

parse_cli() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --raw) [[ $# -ge 2 ]] || die_usage "--raw requires PATH"; RAW_PATH="$2"; shift 2 ;;
      --config) [[ $# -ge 2 ]] || die_usage "--config requires PATH"; CONFIG_PATH="$2"; shift 2 ;;
      --expected-raw-sha256)
        [[ $# -ge 2 ]] || die_usage "--expected-raw-sha256 requires HASH"
        CLI_EXPECTED_RAW_SHA256="$2"; shift 2 ;;
      --verbose) VERBOSE=1; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die_usage "Unknown option: $1" ;;
    esac
  done
  [[ -n "$RAW_PATH" ]] || die_usage "--raw is required"
  [[ "$RAW_PATH" = /* ]] || die_usage "--raw must be an absolute Linux path"
}

validate_config() {
  [[ "$STACK_DIR" = /* ]] || die_usage "STACK_DIR must be absolute"
  [[ "$DATA_MOUNT" = /* ]] || die_usage "DATA_MOUNT must be absolute"
  [[ "$BOOTSTRAP_RUN_ROOT" = /* ]] || die_usage "BOOTSTRAP_RUN_ROOT must be absolute"
  [[ "$MPI_RANKS" == "1" ]] || die_usage "v1.0.3 requires MPI_RANKS=1"
  [[ "$EXPECTED_RAW_NX" == "128" && "$EXPECTED_RAW_NY" == "128" && "$EXPECTED_RAW_NZ" == "128" ]] \
    || die_usage "v1.0.3 requires EXPECTED_RAW_NX/NY/NZ=128"
  [[ "$VOXEL_LENGTH_UM" == "1.0" ]] || die_usage "v1.0.3 requires VOXEL_LENGTH_UM=1.0"
  [[ "$FIRST_CASE_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
    || die_usage "FIRST_CASE_ID must be a safe basename"
  if [[ -n "$EXPECTED_FIRST_RAW_SHA256" && ! "$EXPECTED_FIRST_RAW_SHA256" =~ ^[0-9A-Fa-f]{64}$ ]]; then
    die_usage "EXPECTED_FIRST_RAW_SHA256 must be empty or 64 hexadecimal characters"
  fi
}

create_run_root() {
  local stamp
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$BOOTSTRAP_RUN_ROOT" 2>/dev/null \
    || die_usage "Unable to create configured BOOTSTRAP_RUN_ROOT: $BOOTSTRAP_RUN_ROOT"
  RUN_ROOT="$(mktemp -d "$BOOTSTRAP_RUN_ROOT/${stamp}-XXXXXX" 2>/dev/null)" \
    || die_usage "Unable to create run directory under BOOTSTRAP_RUN_ROOT: $BOOTSTRAP_RUN_ROOT"
  RUN_ID="$(basename "$RUN_ROOT")"
  WORK_DIR="$RUN_ROOT/work"
  LOG_DIR="$RUN_ROOT/logs"
  STATE_FILE="$RUN_ROOT/bootstrap-state.json"
  INSTALLER_ROOT="$WORK_DIR/LBPM-portable-offline-installer"
  SOP_ROOT="$WORK_DIR/LBPM-postinstall-SOP-v1.3.2"
  CASE_DIR="$RUN_ROOT/simulations/$FIRST_CASE_ID"
  mkdir -p "$WORK_DIR" "$LOG_DIR" "$RUN_ROOT/validation" "$RUN_ROOT/simulations" \
    "$RUN_ROOT/evidence" "$RUN_ROOT/host" "$RUN_ROOT/state"
  : > "$LOG_DIR/bootstrap.log"
}

record_stage() {
  local stage="$1" status="$2" detail="${3:-}" log="${4:-}"
  local arguments=(record --state "$STATE_FILE" --run-id "$RUN_ID" --stage "$stage" --status "$status")
  [[ -z "$detail" ]] || arguments+=(--detail "$detail")
  [[ -z "$log" ]] || arguments+=(--log "$log")
  python3 "$SCRIPT_DIR/bin/write_summary.py" "${arguments[@]}" >>"$LOG_DIR/bootstrap.log" 2>&1
}

capture_command() (
  set -Eeuo pipefail
  local log="$1"; shift
  if [[ "$VERBOSE" -eq 1 ]]; then
    "$@" 2>&1 | tee "$log"
    return "${PIPESTATUS[0]}"
  fi
  "$@" >"$log" 2>&1
)

run_stage() {
  local number="$1" stage="$2" label="$3" function_name="$4" log="$5" reason rc
  printf '[%s/9] %-30s ' "$number" "$label"
  set +e
  capture_command "$log" "$function_name"
  rc=$?
  set -e
  if [[ "$rc" -eq 0 ]]; then
    record_stage "$stage" "PASS" "" "$log"
    printf 'PASS\n'
    return 0
  else
    reason="$(tail -n 1 "$log" 2>/dev/null || true)"
    [[ -n "$reason" ]] || reason="stage command exited with code $rc"
    FAILED_STAGE="$stage"
    FAIL_REASON="$reason"
    FAILED_LOG="$log"
    record_stage "$stage" "FAIL" "$reason" "$log" || true
    printf 'FAIL\n'
    return "$rc"
  fi
}

stage_package_integrity() {
  command -v sha256sum >/dev/null
  command -v unzip >/dev/null
  command -v python3 >/dev/null
  (cd "$SCRIPT_DIR" && sha256sum -c SHA256SUMS)
  unzip -t "$SCRIPT_DIR/packages/LBPM-portable-offline-installer.zip"
  unzip -t "$SCRIPT_DIR/packages/LBPM-postinstall-SOP-v1.3.2.zip"
  python3 "$SCRIPT_DIR/bin/bootstrap_contract.py" inspect-packages \
    --installer-zip "$SCRIPT_DIR/packages/LBPM-portable-offline-installer.zip" \
    --sop-zip "$SCRIPT_DIR/packages/LBPM-postinstall-SOP-v1.3.2.zip" \
    --expected-installer-sha256 "$INSTALLER_ZIP_SHA256" \
    --expected-sop-sha256 "$SOP_ZIP_SHA256" \
    --output "$RUN_ROOT/state/package-identity.json"
  unzip -q "$SCRIPT_DIR/packages/LBPM-portable-offline-installer.zip" -d "$WORK_DIR"
  unzip -q "$SCRIPT_DIR/packages/LBPM-postinstall-SOP-v1.3.2.zip" -d "$WORK_DIR"
  [[ -d "$INSTALLER_ROOT" && -d "$SOP_ROOT" ]]
  (cd "$SOP_ROOT" && sha256sum -c SHA256SUMS)
}

effective_uid(){ id -u; }
kernel_name(){ uname -s; }
machine_arch(){ uname -m; }
ubuntu_like_os(){
  local os_id os_like
  [[ -r /etc/os-release ]] || return 1
  os_id="$(. /etc/os-release; printf '%s' "${ID:-}")"
  os_like="$(. /etc/os-release; printf '%s' "${ID_LIKE:-}")"
  [[ "$os_id" == "ubuntu" || " $os_like " == *" debian "* || " $os_like " == *" ubuntu "* ]]
}
data_mount_writable(){ [[ -d "$DATA_MOUNT" && -w "$DATA_MOUNT" ]]; }
tool_available(){ command -v "$1" >/dev/null 2>&1; }
active_python_environment(){
  [[ -n "${CONDA_PREFIX:-}" || -n "${CONDA_DEFAULT_ENV:-}" || -n "${VIRTUAL_ENV:-}" ]]
}
gfortran_executable(){ command -v gfortran; }
gfortran_version_line(){ gfortran --version | sed -n '1p'; }
gfortran_link_probe(){
  local probe_dir probe_bin link_rc cleanup_rc=0
  probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/lbpm-gfortran-link.XXXXXX")" || return 1
  probe_bin="$probe_dir/probe"
  if printf 'int main(){return 0;}\n' | g++ -x c++ - -lgfortran -o "$probe_bin"; then
    link_rc=0
  else
    link_rc=$?
  fi
  rm -f -- "$probe_bin" || cleanup_rc=$?
  rmdir -- "$probe_dir" || cleanup_rc=$?
  [[ "$link_rc" -eq 0 ]] || return "$link_rc"
  return "$cleanup_rc"
}
write_gfortran_evidence(){
  local path="$1" version="$2" link_test="$3"
  mkdir -p "$RUN_ROOT/host"
  python3 - "$RUN_ROOT/host/prerequisites.json" "$path" "$version" "$link_test" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

destination = Path(sys.argv[1])
payload = {
    "schema_version": 1,
    "gfortran": {
        "path": sys.argv[2],
        "version": sys.argv[3],
        "link_test": sys.argv[4],
    },
}
fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)
except Exception:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
PY
}
visible_gpu_count(){
  nvidia-smi --query-gpu=name --format=csv,noheader | awk 'NF {count++} END {print count+0}'
}
capture_host_evidence(){
  {
    id
    uname -a
    printf '\n/etc/os-release:\n'
    cat /etc/os-release
  } > "$RUN_ROOT/host/host-info.txt"
  nvidia-smi > "$RUN_ROOT/host/gpu-info.txt"
  { nvcc --version; printf '\nGPU query:\n'; nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader; } \
    > "$RUN_ROOT/host/cuda-info.txt"
  { gcc --version; g++ --version; gfortran --version; cmake --version; make --version; } \
    > "$RUN_ROOT/host/compiler-info.txt"
  df -h "$DATA_MOUNT" "$BOOTSTRAP_RUN_ROOT" > "$RUN_ROOT/host/disk-info.txt"
}

stage_host_preflight() {
  local tool gpu_count gfortran_path gfortran_version
  [[ "$(effective_uid)" == "0" ]] || { printf 'Bootstrap v1.0.3 requires root\n' >&2; return 1; }
  [[ "$(kernel_name)" == "Linux" ]] || { printf 'Bootstrap v1.0.3 requires Linux\n' >&2; return 1; }
  [[ "$(machine_arch)" == "x86_64" ]] || { printf 'Bootstrap v1.0.3 requires x86_64\n' >&2; return 1; }
  ubuntu_like_os || { printf 'Ubuntu-like distribution required\n' >&2; return 1; }
  active_python_environment && {
    printf 'Active Python environment detected. Deactivate Conda/venv and rerun Bootstrap.\n' >&2
    return 1
  }
  data_mount_writable \
    || { printf 'Configured data mount is missing or not writable: %s\n' "$DATA_MOUNT" >&2; return 1; }
  for tool in nvidia-smi nvcc gcc g++ cmake make tar unzip sha256sum python3 df ldd; do
    tool_available "$tool" || { printf 'Required command not found: %s\n' "$tool" >&2; return 1; }
  done
  if ! tool_available gfortran; then
    write_gfortran_evidence "NOT_FOUND" "NOT_AVAILABLE" "NOT_RUN"
    printf '%s\n' \
      'GNU Fortran compiler not found.' \
      'LBPM requires libgfortran when built with GCC on Linux.' \
      '' \
      'Ubuntu/Debian host prerequisite:' \
      '  apt-get update' \
      '  apt-get install -y gfortran' \
      'GNU Fortran / libgfortran link support is unavailable: gfortran command not found.' >&2
    return 1
  fi
  gfortran_path="$(gfortran_executable)"
  [[ -n "$gfortran_path" ]] || {
    write_gfortran_evidence "NOT_FOUND" "NOT_AVAILABLE" "NOT_RUN"
    printf 'GNU Fortran / libgfortran link support is unavailable: gfortran command not found.\n' >&2
    return 1
  }
  if ! gfortran_version="$(gfortran_version_line)" || [[ -z "$gfortran_version" ]]; then
    write_gfortran_evidence "$gfortran_path" "NOT_AVAILABLE" "NOT_RUN"
    printf 'GNU Fortran compiler exists but its version could not be determined.\n' >&2
    return 1
  fi
  if ! gfortran_link_probe; then
    write_gfortran_evidence "$gfortran_path" "$gfortran_version" "FAIL"
    printf 'GNU Fortran / libgfortran link support is unavailable. Real link probe with -lgfortran failed.\n' >&2
    return 1
  fi
  write_gfortran_evidence "$gfortran_path" "$gfortran_version" "PASS"
  gpu_count="$(visible_gpu_count)"
  [[ "$gpu_count" == "1" ]] || { printf 'Exactly one visible NVIDIA GPU is required; found %s\n' "$gpu_count" >&2; return 1; }
  capture_host_evidence
}

stage_source_verification() {
  [[ -n "$INSTALLER_ROOT" && -r "$INSTALLER_ROOT/verify_sources.sh" ]]
  (cd "$INSTALLER_ROOT" && bash "$INSTALLER_ROOT/verify_sources.sh")
}

stage_installer() {
  local decision action installer_rc action_file action_tmp
  decision="$RUN_ROOT/state/stack-decision.json"
  action_file="$RUN_ROOT/state/install-action.txt"
  action_tmp="$action_file.tmp"
  python3 "$SCRIPT_DIR/bin/bootstrap_contract.py" check-stack \
    --manifest "$STACK_DIR/LBPM_BUILD_MANIFEST.txt" \
    --package-identity "$RUN_ROOT/state/package-identity.json" --output "$decision"
  action="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["install_action"])' "$decision")"
  if [[ "$action" == "INSTALL" ]]; then
    printf 'INSTALLING\n' > "$action_tmp"
    mv "$action_tmp" "$action_file"
    if (cd "$INSTALLER_ROOT" && bash setup.sh --prefix "$STACK_DIR"); then
      :
    else
      installer_rc=$?
      printf 'Portable Installer failed with exit code %s\n' "$installer_rc" >&2
      return "$installer_rc"
    fi
    python3 "$SCRIPT_DIR/bin/bootstrap_contract.py" check-stack \
      --manifest "$STACK_DIR/LBPM_BUILD_MANIFEST.txt" \
      --package-identity "$RUN_ROOT/state/package-identity.json" \
      --require-present \
      --output "$RUN_ROOT/state/stack-after-install.json"
    [[ -f "$STACK_DIR/lbpm_env.sh" ]] \
      || { printf 'POST_INSTALL_ENV_MISSING: %s/lbpm_env.sh\n' "$STACK_DIR" >&2; return 1; }
    printf 'INSTALLED\n' > "$action_tmp"
    mv "$action_tmp" "$action_file"
  elif [[ "$action" == "SKIP_EXISTING_COMPATIBLE" ]]; then
    python3 "$SCRIPT_DIR/bin/bootstrap_contract.py" check-stack \
      --manifest "$STACK_DIR/LBPM_BUILD_MANIFEST.txt" \
      --package-identity "$RUN_ROOT/state/package-identity.json" \
      --require-present \
      --output "$RUN_ROOT/state/stack-after-install.json"
    [[ -f "$STACK_DIR/lbpm_env.sh" ]] \
      || { printf 'POST_INSTALL_ENV_MISSING: %s/lbpm_env.sh\n' "$STACK_DIR" >&2; return 1; }
    printf 'SKIPPED\n' > "$action_tmp"
    mv "$action_tmp" "$action_file"
  else
    printf 'Unexpected install action: %s\n' "$action" >&2
    return 1
  fi
}

stage_environment_identity() {
  [[ -f "$STACK_DIR/lbpm_env.sh" ]] || { printf 'Missing LBPM environment: %s/lbpm_env.sh\n' "$STACK_DIR" >&2; return 1; }
  # shellcheck disable=SC1090
  source "$STACK_DIR/lbpm_env.sh"
  local color serial mpi binary ldd_output
  color="$(command -v lbpm_color_simulator)"
  serial="$(command -v lbpm_serial_decomp)"
  mpi="$(command -v mpirun)"
  {
    printf 'lbpm_color_simulator=%s\n' "$color"
    printf 'lbpm_serial_decomp=%s\n' "$serial"
    printf 'mpirun=%s\n' "$mpi"
    "$mpi" --version
    for binary in "$color" "$serial"; do
      printf '\nldd %s\n' "$binary"
      if ! ldd_output="$(ldd "$binary" 2>&1)"; then
        printf '%s\n' "$ldd_output"
        printf 'ldd command failed for %s\n' "$binary" >&2
        return 1
      fi
      printf '%s\n' "$ldd_output"
      if grep -F 'not found' <<< "$ldd_output"; then
        printf 'Unresolved dynamic library in %s\n' "$binary" >&2
        return 1
      fi
    done
  } > "$RUN_ROOT/host/lbpm-runtime-identity.txt"
}

stage_sop_deployment() {
  local temporary_config="$SOP_ROOT/.config.env.bootstrap.tmp"
  [[ "$(tr -d '\r\n' < "$SOP_ROOT/VERSION")" == "1.3.2" ]]
  (cd "$SOP_ROOT" && sha256sum -c SHA256SUMS)
  {
    printf 'STACK_DIR=%s\n' "$STACK_DIR"
    printf 'DATA_DIR=%s\n' "$RUN_ROOT"
    printf 'VALIDATION_DIR=%s\n' "$RUN_ROOT/validation"
    printf 'SIMULATION_DIR=%s\n' "$RUN_ROOT/simulations"
    printf 'MPI_RANKS=%s\n' "$MPI_RANKS"
  } > "$temporary_config"
  mv "$temporary_config" "$SOP_ROOT/config.env"
}

stage_sop_acceptance() {
  (cd "$SOP_ROOT" && bash bin/post_install_acceptance.sh)
  python3 "$SCRIPT_DIR/bin/bootstrap_contract.py" check-acceptance \
    --report "$RUN_ROOT/validation/acceptance_report.json" \
    --output "$RUN_ROOT/state/acceptance-check.json"
}

stage_raw_and_first_rock() {
  local raw_args=(check-raw --raw "$RAW_PATH" --expected-bytes 2097152 --output "$RUN_ROOT/state/raw-check.json")
  if [[ -n "$EXPECTED_FIRST_RAW_SHA256" ]]; then
    raw_args+=(--expected-sha256 "$EXPECTED_FIRST_RAW_SHA256")
  fi
  python3 "$SCRIPT_DIR/bin/bootstrap_contract.py" "${raw_args[@]}"
  (cd "$SOP_ROOT" && bash bin/run_to_parameterization.sh \
    --rock "$RAW_PATH" --case-id "$FIRST_CASE_ID" --skip-postinstall \
    --first-case-smoke --voxel-length-um "$VOXEL_LENGTH_UM")
  python3 "$SCRIPT_DIR/bin/bootstrap_contract.py" check-ready \
    --ready "$CASE_DIR/READY_FOR_PARAMETERIZATION.json" \
    --case-manifest "$CASE_DIR/case_manifest.json" \
    --connectivity "$CASE_DIR/connectivity_report.json" \
    --smoke-report "$CASE_DIR/engineering-smoke-2000/PASS.json" \
    --raw-check "$RUN_ROOT/state/raw-check.json" \
    --output "$RUN_ROOT/state/ready-check.json"
}

finalize_run() {
  local incoming_rc="$1" overall archive_result archive archive_sha sidecar evidence_log planned_archive
  local final_rc="$incoming_rc"
  FINALIZED=1
  trap - EXIT
  [[ -n "$RUN_ROOT" ]] || exit "$final_rc"
  if [[ -f "$RUN_ROOT/state/install-action.txt" ]]; then
    INSTALL_ACTION="$(tr -d '\r\n' < "$RUN_ROOT/state/install-action.txt")"
  fi
  if [[ "$incoming_rc" -eq 0 ]]; then overall="PASS"; else overall="FAIL"; fi
  evidence_log="$LOG_DIR/09-evidence.log"
  planned_archive="$RUN_ROOT/artifacts/LBPM-validation-evidence-$RUN_ID.tar.gz"
  record_stage "evidence" "PASS" "bounded snapshot requested" "$evidence_log" || true
  python3 "$SCRIPT_DIR/bin/write_summary.py" render \
    --state "$STATE_FILE" --run-root "$RUN_ROOT" --status "$overall" \
    --failed-stage "$FAILED_STAGE" --fail-reason "$FAIL_REASON" --install-action "$INSTALL_ACTION" \
    --archive "$planned_archive" --archive-sha256 "SIDECAR_SHA256" > /dev/null 2>>"$evidence_log" || true
  if archive_result="$(python3 "$SCRIPT_DIR/bin/collect_evidence.py" \
      --run-root "$RUN_ROOT" --installer-root "$INSTALLER_ROOT" \
      --stack-manifest "$STACK_DIR/LBPM_BUILD_MANIFEST.txt" --case-dir "$CASE_DIR" 2>>"$evidence_log")"; then
    printf '%s\n' "$archive_result" > "$RUN_ROOT/state/evidence-result.json"
    archive="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["archive"])' "$archive_result")"
    archive_sha="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["archive_sha256"])' "$archive_result")"
    sidecar="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["sidecar"])' "$archive_result")"
  else
    record_stage "evidence" "FAIL" "evidence collection failed" "$evidence_log" || true
    archive="NOT_PRODUCED"; archive_sha="NOT_PRODUCED"; sidecar="NOT_PRODUCED"
    if [[ "$overall" == "PASS" ]]; then
      overall="FAIL"; final_rc=1; FAILED_STAGE="evidence"; FAIL_REASON="evidence collection failed"; FAILED_LOG="$evidence_log"
    fi
  fi
  python3 "$SCRIPT_DIR/bin/write_summary.py" render \
    --state "$STATE_FILE" --run-root "$RUN_ROOT" --status "$overall" \
    --failed-stage "$FAILED_STAGE" --fail-reason "$FAIL_REASON" --install-action "$INSTALL_ACTION" \
    --archive "$archive" --archive-sha256 "$archive_sha"
  printf '\nEvidence archive:\n%s\n\nSHA256:\n%s\nSidecar:\n%s\n' "$archive" "$archive_sha" "$sidecar"
  if [[ "$overall" == "FAIL" && -n "$FAILED_LOG" ]]; then
    printf '\nLast useful lines from failed stage (%s):\n' "$FAILED_LOG" >&2
    tail -n 80 "$FAILED_LOG" >&2 || true
  fi
  exit "$final_rc"
}

on_exit() {
  local rc="$1"
  [[ "$FINALIZED" -eq 1 ]] && return
  if [[ "$rc" -ne 0 && -z "$FAILED_STAGE" ]]; then
    FAILED_STAGE="unexpected_error"
    FAIL_REASON="unexpected orchestration error (exit $rc)"
    FAILED_LOG="$LOG_DIR/bootstrap.log"
    record_stage "$FAILED_STAGE" "FAIL" "$FAIL_REASON" "$FAILED_LOG" || true
  fi
  finalize_run "$rc"
}

main() {
  parse_cli "$@"
  if [[ -n "$CONFIG_PATH" ]]; then
    load_config "$CONFIG_PATH"
  elif [[ -f "$SCRIPT_DIR/bootstrap.env" ]]; then
    load_config "$SCRIPT_DIR/bootstrap.env"
  else
    load_config "$SCRIPT_DIR/bootstrap.env.example"
  fi
  if [[ -n "$CLI_EXPECTED_RAW_SHA256" ]]; then EXPECTED_FIRST_RAW_SHA256="$CLI_EXPECTED_RAW_SHA256"; fi
  validate_config
  create_run_root
  trap 'on_exit $?' EXIT

  run_stage 1 package_integrity "Package integrity" stage_package_integrity "$LOG_DIR/01-package-integrity.log"
  run_stage 2 host_preflight "Host preflight" stage_host_preflight "$LOG_DIR/02-host-preflight.log"
  run_stage 3 source_verification "Installer source verification" stage_source_verification "$LOG_DIR/03-source-verification.log"
  run_stage 4 installer "LBPM installation/reuse" stage_installer "$LOG_DIR/04-installer.log"
  INSTALL_ACTION="$(tr -d '\r\n' < "$RUN_ROOT/state/install-action.txt")"
  run_stage 5 environment_identity "LBPM environment identity" stage_environment_identity "$LOG_DIR/05-environment-identity.log"
  run_stage 6 sop_deployment "SOP deployment" stage_sop_deployment "$LOG_DIR/06-sop-deployment.log"
  run_stage 7 sop_acceptance "SOP acceptance" stage_sop_acceptance "$LOG_DIR/07-sop-acceptance.log"
  run_stage 8 raw_and_first_rock "RAW + first-rock smoke" stage_raw_and_first_rock "$LOG_DIR/08-first-rock.log"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
