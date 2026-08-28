#!/usr/bin/env bash
# Validation only. This script MUST NOT patch, rebuild, or edit LBPM source.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"

source_lbpm_env
mkdir -p "$VALIDATION_DIR"
require_cmd ldd
require_cmd nvidia-smi
require_cmd perl
require_cmd python3
MANIFEST="$STACK_DIR/LBPM_BUILD_MANIFEST.txt"
SRC="$STACK_DIR/src/LBPM/models/ColorModel.cpp"
PATCHSET_MARKER="$STACK_DIR/src/LBPM/.lbpm_local_patchset"

[[ -f "$MANIFEST" ]] || die "Missing $MANIFEST. SOP v1.3.2 requires installer v2.0.5, v2.0.6, or v2.0.7 build manifest."
[[ -f "$SRC" ]] || die "Missing LBPM source: $SRC"

expect_manifest(){
  local key="$1" expected="$2" actual
  actual="$(manifest_get "$key" "$MANIFEST" || true)"
  [[ "$actual" == "$expected" ]] || die "Manifest mismatch: $key expected='$expected' actual='$actual'"
  printf '%-24s %s\n' "$key" "$actual"
}

expect_installer_version(){
  local actual
  actual="$(manifest_get INSTALLER_VERSION "$MANIFEST" || true)"
  installer_version_supported "$actual" || die "Manifest mismatch: INSTALLER_VERSION expected='$EXPECTED_INSTALLER_VERSIONS' actual='$actual'"
  printf '%-24s %s\n' INSTALLER_VERSION "$actual"
}

log "Validating LBPM v2.0.5/v2.0.6/v2.0.7 build manifest"
expect_installer_version
expect_manifest LBPM_REPO "$EXPECTED_LBPM_REPO"
expect_manifest LBPM_COMMIT "$EXPECTED_LBPM_COMMIT"
expect_manifest OPENMPI_VERSION "$EXPECTED_OPENMPI_VERSION"
expect_manifest ZLIB_VERSION "$EXPECTED_ZLIB_VERSION"
expect_manifest HDF5_VERSION "$EXPECTED_HDF5_VERSION"
expect_manifest PATCHSET_ID "$EXPECTED_PATCHSET_ID"
expect_manifest PATCH_FILE "$EXPECTED_PATCH_FILE"
expect_manifest PATCH_SHA256 "$EXPECTED_PATCH_SHA256"

PATCH_STATUS="$(manifest_get PATCH_STATUS "$MANIFEST" || true)"
case "$PATCH_STATUS" in
  APPLIED|ALREADY_FIXED) printf '%-24s %s\n' PATCH_STATUS "$PATCH_STATUS";;
  *) die "Unexpected PATCH_STATUS='$PATCH_STATUS'. Reinstall with v2.0.5, v2.0.6, or v2.0.7; SOP will not repair it.";;
esac

[[ -f "$PATCHSET_MARKER" ]] || die "Missing patchset marker: $PATCHSET_MARKER"
[[ "$(tr -d '\r\n' < "$PATCHSET_MARKER")" == "$EXPECTED_PATCHSET_ID" ]] || die "Patchset marker mismatch"

STATE="$(perl -0777 -ne '
  if (/if\s*\(domain_db->keyExists\("OutletLayersPhase"\)\).*?if\s*\(outlet_layers_phase\s*==\s*1\)\s*\{(.*?)\n\s*\}/s) {
    my $b=$1;
    if ($b =~ /outletA\s*=\s*1\.0\s*;/ && $b =~ /outletB\s*=\s*0\.0\s*;/ &&
        $b !~ /inletA\s*=\s*1\.0\s*;/ && $b !~ /inletB\s*=\s*0\.0\s*;/) { print "fixed\n"; }
    elsif ($b =~ /inletA\s*=\s*1\.0\s*;/ && $b =~ /inletB\s*=\s*0\.0\s*;/) { print "buggy\n"; }
    else { print "unknown\n"; }
  } else { print "unknown\n"; }
' "$SRC")"
[[ "$STATE" == "fixed" ]] || die "OutletLayersPhase source verification is '$STATE'. SOP refuses to modify source."
log "OutletLayersPhase semantic check PASS"

declare -A EXE_PATHS
for exe in lbpm_color_simulator lbpm_permeability_simulator lbpm_serial_decomp; do
  path="$(command -v "$exe" || true)"
  [[ -n "$path" && -x "$path" ]] || die "$exe not found after sourcing lbpm_env.sh"
  if ! ldd_output="$(ldd "$path" 2>&1)"; then
    printf '%s\n' "$ldd_output" >&2
    die "ldd command failed for $exe"
  fi
  if grep -q 'not found' <<<"$ldd_output"; then
    printf '%s\n' "$ldd_output" >&2
    die "$exe has unresolved shared libraries"
  fi
  EXE_PATHS["$exe"]="$path"
  log "$exe -> $path"
done

GPU_NAMES="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null)"
DRIVER_VERSIONS="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | sort -u)"
CURRENT_CC="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | tr -d ' ' | sort -u)"
[[ -n "$GPU_NAMES" && -n "$DRIVER_VERSIONS" && -n "$CURRENT_CC" ]] || die "Could not determine GPU provenance"
[[ "$(printf '%s\n' "$CURRENT_CC" | wc -l | tr -d ' ')" == "1" ]] || die "Mixed GPU compute capabilities are visible"
EXPECTED_ARCH="$(manifest_get CUDA_ARCH "$MANIFEST" || true)"
CURRENT_ARCH="sm_${CURRENT_CC/./}"
[[ "$CURRENT_ARCH" == "$EXPECTED_ARCH" ]] || die "GPU architecture mismatch: build=$EXPECTED_ARCH current=$CURRENT_ARCH"

NVCC_BIN="${CUDA_HOME:-}/bin/nvcc"
if [[ ! -x "$NVCC_BIN" ]]; then NVCC_BIN="$(command -v nvcc || true)"; fi
[[ -n "$NVCC_BIN" && -x "$NVCC_BIN" ]] || die "nvcc not found after sourcing lbpm_env.sh"
CUDA_VERSION="$("$NVCC_BIN" --version | sed -n 's/.*release \([0-9][0-9.]*\).*/\1/p' | tail -n1)"
[[ -n "$CUDA_VERSION" ]] || die "Could not determine CUDA toolkit version"

MPIRUN_BIN="${MPI_DIR:-}/bin/mpirun"
OMPI_INFO_BIN="${MPI_DIR:-}/bin/ompi_info"
[[ -x "$MPIRUN_BIN" && -x "$OMPI_INFO_BIN" ]] || die "Open MPI runtime tools are missing"
MPI_VERSION="$($MPIRUN_BIN --version | head -n1)"
[[ "$MPI_VERSION" == *"Open MPI"* ]] || die "Unexpected MPI implementation: $MPI_VERSION"
if "$OMPI_INFO_BIN" --parsable --all 2>/dev/null | grep -Eq 'mpi_built_with_cuda_support:value:true|opal_built_with_cuda_support:value:true'; then
  CUDA_AWARE_MPI_STATUS="SUPPORTED"
else
  CUDA_AWARE_MPI_STATUS="NOT_REPORTED_BY_OMPI_INFO"
fi

python3 "$SCRIPT_DIR/write_software_report.py" \
  --output "$VALIDATION_DIR/software-verification.json" \
  --manifest "$MANIFEST" --source "$SRC" \
  --gpu-name "$GPU_NAMES" --driver-version "$DRIVER_VERSIONS" \
  --compute-capability "$CURRENT_CC" --cuda-version "$CUDA_VERSION" \
  --mpi-implementation "Open MPI" --mpi-version "$MPI_VERSION" \
  --cuda-aware-mpi-status "$CUDA_AWARE_MPI_STATUS" --patch-status "$PATCH_STATUS" \
  --executable "lbpm_color_simulator=${EXE_PATHS[lbpm_color_simulator]}" \
  --executable "lbpm_permeability_simulator=${EXE_PATHS[lbpm_permeability_simulator]}" \
  --executable "lbpm_serial_decomp=${EXE_PATHS[lbpm_serial_decomp]}"
log "Software verification PASS"
