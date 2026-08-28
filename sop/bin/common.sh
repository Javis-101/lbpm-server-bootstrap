#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PKG_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"

if [[ -f "$PKG_DIR/config.env" ]]; then
  # shellcheck disable=SC1091
  source "$PKG_DIR/config.env"
fi

STACK_DIR="${STACK_DIR:-/root/LBPM-stack}"
DATA_DIR="${DATA_DIR:-/root/rivermind-data}"
VALIDATION_DIR="${VALIDATION_DIR:-$DATA_DIR/lbpm-validation}"
SIMULATION_DIR="${SIMULATION_DIR:-$DATA_DIR/lbpm-simulations}"
MPI_RANKS="${MPI_RANKS:-1}"

EXPECTED_INSTALLER_VERSION="2.0.7-offline"
EXPECTED_INSTALLER_VERSIONS="2.0.5-offline, 2.0.6-offline, or 2.0.7-offline"
EXPECTED_LBPM_REPO="https://github.com/OPM/LBPM"
EXPECTED_LBPM_COMMIT="6d686d354e5b8140841d3601e4c8c0e4e4b77e48"
EXPECTED_OPENMPI_VERSION="4.1.8"
EXPECTED_ZLIB_VERSION="1.3.2"
EXPECTED_HDF5_VERSION="1.14.6"
EXPECTED_PATCHSET_ID="outletlayersphase-fix-v1"
EXPECTED_PATCH_FILE="0001-fix-OutletLayersPhase.patch"
EXPECTED_PATCH_SHA256="fbce8ac8f101c5f5ff3764c4e6e71f98d5a478e54609f3d63864dbc8e7d1c2b8"
SOP_VERSION="1.3.2"

log(){ printf '[%(%H:%M:%S)T] %s\n' -1 "$*"; }
warn(){ printf '[WARN] %s\n' "$*" >&2; }
die(){ printf '[ERROR] %s\n' "$*" >&2; exit 1; }

require_cmd(){ command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"; }

require_acceptance_pass(){
  local report="${1:-$VALIDATION_DIR/acceptance_report.json}"
  python3 - "$report" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(f"acceptance report is missing: {path}")
report = json.loads(path.read_text())
if report.get("schema_version") != 1 or report.get("status") != "PASS":
    raise SystemExit(f"acceptance report is not a schema_version=1 PASS: {path}")
PY
}

source_lbpm_env(){
  [[ -f "$STACK_DIR/lbpm_env.sh" ]] || die "Missing $STACK_DIR/lbpm_env.sh. Install with LBPM offline installer v2.0.5, v2.0.6, or v2.0.7 first."
  # shellcheck disable=SC1090
  source "$STACK_DIR/lbpm_env.sh"
}

manifest_get(){
  local key="$1" manifest="${2:-$STACK_DIR/LBPM_BUILD_MANIFEST.txt}"
  [[ -f "$manifest" ]] || return 1
  awk -v key="$key" '
    index($0, key "=") == 1 {
      value=substr($0, length(key)+2)
      sub(/\r$/, "", value)
      print value
      exit
    }
  ' "$manifest"
}

installer_version_supported(){
  case "$1" in
    2.0.5-offline|2.0.6-offline|2.0.7-offline) return 0;;
    *) return 1;;
  esac
}

mpi_run(){
  local mpirun_bin="${MPI_DIR:-}/bin/mpirun"
  if [[ ! -x "$mpirun_bin" ]]; then
    mpirun_bin="$(command -v mpirun || true)"
  fi
  [[ -n "$mpirun_bin" && -x "$mpirun_bin" ]] || die "mpirun not found"
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 \
      "$mpirun_bin" --allow-run-as-root "$@"
  else
    "$mpirun_bin" "$@"
  fi
}
