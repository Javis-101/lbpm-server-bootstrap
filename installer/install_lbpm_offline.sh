#!/usr/bin/env bash
# LBPM portable offline-first installer.
# v2.0.7: v2.0.6 frozen stack plus a mode-bit-independent setup entry point.
set -Eeuo pipefail
IFS=$'\n\t'

INSTALLER_VERSION="2.0.7-offline"
OPENMPI_VERSION="4.1.8"
ZLIB_VERSION="1.3.2"
HDF5_VERSION="1.14.6"
LBPM_REPO="https://github.com/OPM/LBPM"
LBPM_COMMIT="6d686d354e5b8140841d3601e4c8c0e4e4b77e48"
PATCHSET_ID="outletlayersphase-fix-v1"
PATCH_FILE_NAME="0001-fix-OutletLayersPhase.patch"
PATCH_SHA256="fbce8ac8f101c5f5ff3764c4e6e71f98d5a478e54609f3d63864dbc8e7d1c2b8"

OPENMPI_SHA256="fb41086bbed9300baa2f3d7572491facfe5257412fa524ec5a396aa9101d5c62"
ZLIB_SHA256="bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16"
HDF5_SHA256="e4defbac30f50d64e1556374aa49e574417c9e72c6b1de7a4ff88c4b1bea6e9b"

OPENMPI_ARCHIVE="openmpi-${OPENMPI_VERSION}.tar.gz"
ZLIB_ARCHIVE="zlib-${ZLIB_VERSION}.tar.gz"
HDF5_ARCHIVE="hdf5-${HDF5_VERSION}.tar.gz"
LBPM_ARCHIVE="LBPM-${LBPM_COMMIT}.tar.gz"

OPENMPI_URL="https://download.open-mpi.org/release/open-mpi/v4.1/${OPENMPI_ARCHIVE}"
ZLIB_URL="https://www.zlib.net/${ZLIB_ARCHIVE}"
ZLIB_FALLBACK_URL="https://www.zlib.net/fossils/${ZLIB_ARCHIVE}"
HDF5_URL="https://support.hdfgroup.org/releases/hdf5/v1_14/v1_14_6/downloads/${HDF5_ARCHIVE}"
HDF5_FALLBACK_URL="https://github.com/HDFGroup/hdf5/releases/download/hdf5_${HDF5_VERSION}/${HDF5_ARCHIVE}"
LBPM_URL="https://github.com/OPM/LBPM/archive/${LBPM_COMMIT}.tar.gz"
LBPM_FALLBACK_URL="https://codeload.github.com/OPM/LBPM/tar.gz/${LBPM_COMMIT}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$SCRIPT_DIR/lib/path_safety.sh"
BUNDLE_SOURCES="$SCRIPT_DIR/sources"
BUNDLE_PATCHES="$SCRIPT_DIR/patches"
ALLOW_NETWORK=0
SKIP_TESTS=0
REBUILD_LBPM=0
INSTALL_ROOT="${HOME:-/tmp}/LBPM-stack"
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 4)"

SRC_ROOT="" DEPS_ROOT="" BUILD_ROOT="" INSTALLS_ROOT="" RUN_ROOT="" LOG_DIR=""
MPI_DIR="" ZLIB_DIR="" HDF5_DIR="" LBPM_SRC="" LBPM_BUILD="" LBPM_INSTALL=""
ENV_FILE="" MANIFEST_FILE="" BUILD_MANIFEST_FILE="" LOG_FILE=""
CUDA_HOME="" CUDA_VERSION="" CUDA_ARCH="" GPU_NAME="" GPU_CC="" CUDA_LIBDIR=""
PATCH_STATUS="NOT_CHECKED" TESTSETDEVICE_STATUS="NOT_RUN" PISTON_STATUS="NOT_RUN"
START_TIME="$(date +%s)"

usage() {
cat <<'USAGE'
LBPM Offline-First Portable Installer v2.0.7

Usage:
  ./install_lbpm_offline.sh [options]

Options:
  --prefix PATH        Install root (default: $HOME/LBPM-stack)
  --jobs N             Parallel build jobs
  --skip-tests         Skip TestSetDevice and Piston smoke test (debug only)
  --rebuild-lbpm       Force a clean LBPM rebuild; keep dependencies
  --allow-network      Allow HTTPS fallback only if a bundled source is missing
  -h, --help           Show help

Default behavior is OFFLINE when all files under ./sources are present.
The frozen upstream LBPM source archive is kept unchanged; the audited local
OutletLayersPhase patch is applied to the extracted working tree before build.

Required host baseline:
  Linux x86_64, NVIDIA driver, CUDA Devel toolkit (nvcc), gcc/g++, make,
  cmake>=3.24, ctest, tar, perl, m4, patch, sha256sum.
USAGE
}

log(){ printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn(){ printf '[%s] WARNING: %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }
die(){ printf '[%s] ERROR: %s\n' "$(date '+%H:%M:%S')" "$*" >&2; exit 1; }
trap 'rc=$?; printf "\n[ERROR] installer stopped (exit=%s, line=%s)\n" "$rc" "${BASH_LINENO[0]:-?}" >&2; [[ -n "${LOG_FILE:-}" ]] && printf "Log: %s\n" "$LOG_FILE" >&2; exit "$rc"' ERR

parse_args(){
  while (($#)); do
    case "$1" in
      --prefix) [[ $# -ge 2 ]] || die "--prefix requires PATH"; INSTALL_ROOT="$2"; shift 2;;
      --jobs) [[ $# -ge 2 && "$2" =~ ^[1-9][0-9]*$ ]] || die "--jobs requires a positive integer"; JOBS="$2"; shift 2;;
      --skip-tests) SKIP_TESTS=1; shift;;
      --rebuild-lbpm) REBUILD_LBPM=1; shift;;
      --allow-network) ALLOW_NETWORK=1; shift;;
      -h|--help) usage; exit 0;;
      *) die "unknown option: $1";;
    esac
  done
}

layout(){
  SRC_ROOT="$INSTALL_ROOT/src"; DEPS_ROOT="$INSTALL_ROOT/deps"; BUILD_ROOT="$INSTALL_ROOT/build"
  INSTALLS_ROOT="$INSTALL_ROOT/install"; RUN_ROOT="$INSTALL_ROOT/run"; LOG_DIR="$INSTALL_ROOT/logs"
  MPI_DIR="$DEPS_ROOT/openmpi"; ZLIB_DIR="$DEPS_ROOT/zlib"; HDF5_DIR="$DEPS_ROOT/hdf5"
  LBPM_SRC="$SRC_ROOT/LBPM"; LBPM_BUILD="$BUILD_ROOT/LBPM"; LBPM_INSTALL="$INSTALLS_ROOT/LBPM"
  ENV_FILE="$INSTALL_ROOT/lbpm_env.sh"; MANIFEST_FILE="$INSTALL_ROOT/install-manifest.txt"
  BUILD_MANIFEST_FILE="$INSTALL_ROOT/LBPM_BUILD_MANIFEST.txt"
  mkdir -p "$SRC_ROOT" "$DEPS_ROOT" "$BUILD_ROOT" "$INSTALLS_ROOT" "$RUN_ROOT" "$LOG_DIR"
  LOG_FILE="$LOG_DIR/install-$(date '+%Y%m%d-%H%M%S').log"
  exec > >(tee -a "$LOG_FILE") 2>&1
}

require_cmd(){ command -v "$1" >/dev/null 2>&1 || die "Missing host tool: $1. Use a CUDA Devel image with basic build tools installed."; }
version_ge(){ [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" == "$2" ]]; }

check_host_tools(){
  [[ "$(uname -s)" == Linux ]] || die "Linux is required"
  [[ "$(uname -m)" == x86_64 ]] || die "This bundle targets Linux x86_64"
  local c
  for c in nvidia-smi nvcc gcc g++ make cmake ctest tar perl m4 patch sha256sum awk sed grep sort head tee stat; do require_cmd "$c"; done
  local cv; cv="$(cmake --version | awk 'NR==1{print $3}')"
  version_ge "$cv" "3.24" || die "CMake >= 3.24 required; found $cv"
}

detect_cuda(){
  nvidia-smi >/dev/null || die "nvidia-smi cannot communicate with the NVIDIA driver"
  local nvcc_path rows first unique
  nvcc_path="$(readlink -f "$(command -v nvcc)")"
  CUDA_HOME="$(cd "$(dirname "$nvcc_path")/.." && pwd -P)"
  CUDA_VERSION="$($CUDA_HOME/bin/nvcc --version | sed -n 's/.*release \([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' | head -n1)"
  [[ -n "$CUDA_VERSION" ]] || die "Cannot parse CUDA version"
  rows="$(nvidia-smi --query-gpu=name,compute_cap --format=csv,noheader 2>/dev/null || true)"
  if [[ -n "$rows" ]]; then
    first="$(printf '%s\n' "$rows" | head -n1)"; GPU_NAME="${first%,*}"; GPU_CC="${first##*, }"
    unique="$(printf '%s\n' "$rows" | awk -F',' '{gsub(/ /,"",$2);print $2}' | sort -u | wc -l | tr -d ' ')"
    [[ "$unique" -eq 1 ]] || die "Mixed GPU compute capabilities detected; expose a homogeneous GPU set"
  else
    GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n1)"
    local tdcc="$INSTALL_ROOT/.cc-probe"; rm -rf "$tdcc"; mkdir -p "$tdcc"
    cat > "$tdcc/cc.cu" <<'CUCC'
#include <cstdio>
#include <cuda_runtime.h>
int main(){ cudaDeviceProp p{}; if(cudaGetDeviceProperties(&p,0)!=cudaSuccess) return 2; std::printf("%d.%d\n",p.major,p.minor); }
CUCC
    "$CUDA_HOME/bin/nvcc" "$tdcc/cc.cu" -o "$tdcc/cc" >/dev/null 2>&1 || die "Cannot build CUDA capability probe"
    GPU_CC="$("$tdcc/cc")"; rm -rf "$tdcc"
  fi
  CUDA_ARCH="${GPU_CC/./}"
  [[ "$CUDA_ARCH" =~ ^[0-9]+$ ]] || die "Invalid compute capability: $GPU_CC"
  local td="$INSTALL_ROOT/.nvcc-probe"; rm -rf "$td"; mkdir -p "$td"; printf '__global__ void k(){}\n' > "$td/p.cu"
  "$CUDA_HOME/bin/nvcc" -arch="sm_${CUDA_ARCH}" -c "$td/p.cu" -o "$td/p.o" >/dev/null 2>&1 || die "CUDA $CUDA_VERSION cannot compile sm_${CUDA_ARCH}; choose a newer CUDA Devel image"
  rm -rf "$td"
}

known_hash_for(){
  case "$1" in
    "$OPENMPI_ARCHIVE") printf '%s\n' "$OPENMPI_SHA256";;
    "$ZLIB_ARCHIVE") printf '%s\n' "$ZLIB_SHA256";;
    "$HDF5_ARCHIVE") printf '%s\n' "$HDF5_SHA256";;
    *) return 1;;
  esac
}

verify_archive(){
  local f="$1" expected actual base; base="$(basename "$f")"
  [[ -s "$f" ]] || die "Source archive missing/empty: $f"
  expected="$(known_hash_for "$base" 2>/dev/null || true)"
  if [[ -z "$expected" && -f "$BUNDLE_SOURCES/SHA256SUMS" ]]; then
    expected="$(awk -v n="$base" '{name=$2; sub(/\r$/, "", name); if (name==n || name=="*" n) {print $1; exit}}' "$BUNDLE_SOURCES/SHA256SUMS")"
  fi
  [[ -n "$expected" ]] || die "No checksum recorded for $base. Rebuild the offline bundle with prepare_offline_bundle.*"
  actual="$(sha256sum "$f" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || die "SHA256 mismatch for $base: expected=$expected actual=$actual"
  log "Checksum PASS: $base"
}

verify_patch_bundle(){
  local f="$BUNDLE_PATCHES/$PATCH_FILE_NAME" actual recorded
  [[ -s "$f" ]] || die "Missing local patch: $f"
  actual="$(sha256sum "$f" | awk '{print $1}')"
  [[ "$actual" == "$PATCH_SHA256" ]] || die "Bundled patch SHA256 mismatch: expected=$PATCH_SHA256 actual=$actual"
  if [[ -f "$BUNDLE_PATCHES/SHA256SUMS" ]]; then
    recorded="$(awk -v n="$PATCH_FILE_NAME" '{name=$2; sub(/\r$/, "", name); if (name==n || name=="*" n) {print $1; exit}}' "$BUNDLE_PATCHES/SHA256SUMS")"
    [[ "$recorded" == "$PATCH_SHA256" ]] || die "patches/SHA256SUMS does not match installer-pinned patch SHA"
  fi
  log "Checksum PASS: local patch $PATCH_FILE_NAME"
}

download_file(){
  local dest="$1"; shift; local url
  [[ "$ALLOW_NETWORK" -eq 1 ]] || die "Bundled source missing: $(basename "$dest"). Network fallback disabled."
  if command -v curl >/dev/null 2>&1; then
    for url in "$@"; do log "Network fallback: $url"; curl -fL --retry 5 --connect-timeout 20 -o "$dest.part" "$url" && { mv "$dest.part" "$dest"; return; } || rm -f "$dest.part"; done
  elif command -v wget >/dev/null 2>&1; then
    for url in "$@"; do log "Network fallback: $url"; wget --tries=5 --timeout=20 -O "$dest.part" "$url" && { mv "$dest.part" "$dest"; return; } || rm -f "$dest.part"; done
  else die "--allow-network requested but curl/wget is unavailable"; fi
  die "Failed to download $(basename "$dest")"
}

source_file(){
  local name="$1"; shift; local f="$BUNDLE_SOURCES/$name"
  [[ -s "$f" ]] || download_file "$f" "$@"
  verify_archive "$f"
  printf '%s\n' "$f"
}

preflight_sources(){
  log "Preflight: validating frozen source archives and local patch"
  source_file "$OPENMPI_ARCHIVE" "$OPENMPI_URL" >/dev/null
  source_file "$ZLIB_ARCHIVE" "$ZLIB_URL" "$ZLIB_FALLBACK_URL" >/dev/null
  source_file "$HDF5_ARCHIVE" "$HDF5_URL" "$HDF5_FALLBACK_URL" >/dev/null
  source_file "$LBPM_ARCHIVE" "$LBPM_URL" "$LBPM_FALLBACK_URL" >/dev/null
  verify_patch_bundle
  log "All frozen inputs are checksum-verified"
}

extract_clean(){ local a="$1" parent="$2" dirname="$3"; rm -rf "$parent/$dirname"; tar -xzf "$a" -C "$parent"; [[ -d "$parent/$dirname" ]] || die "Expected extracted directory not found: $dirname"; }

find_cuda_libdir(){
  local p linkdir d
  [[ -e "$CUDA_HOME/lib64/stubs/libcuda.so" ]] && { printf '%s\n' "$CUDA_HOME/lib64/stubs"; return; }
  for d in /usr/lib/x86_64-linux-gnu /usr/lib64 /usr/lib/wsl/lib; do [[ -e "$d/libcuda.so" ]] && { printf '%s\n' "$d"; return; }; done
  p="$(ldconfig -p 2>/dev/null | awk '/libcuda\.so\.1 /{print $NF;exit}' || true)"
  if [[ -n "$p" && -e "$p" ]]; then linkdir="$DEPS_ROOT/cuda-driver-link"; mkdir -p "$linkdir"; ln -sfn "$p" "$linkdir/libcuda.so"; printf '%s\n' "$linkdir"; return; fi
  return 1
}

openmpi_ok(){ [[ -x "$MPI_DIR/bin/mpirun" ]] && "$MPI_DIR/bin/mpirun" --version 2>/dev/null | head -n1 | grep -q "$OPENMPI_VERSION" && "$MPI_DIR/bin/ompi_info" --parsable --all 2>/dev/null | grep -Eq '(mpi|opal)_built_with_cuda_support:value:true'; }
build_openmpi(){
  openmpi_ok && { log "Reuse OpenMPI $OPENMPI_VERSION"; return; }
  rm -rf "$MPI_DIR"; local a src cfg; source_file "$OPENMPI_ARCHIVE" "$OPENMPI_URL" >/dev/null; a="$BUNDLE_SOURCES/$OPENMPI_ARCHIVE"; extract_clean "$a" "$SRC_ROOT" "openmpi-$OPENMPI_VERSION"; src="$SRC_ROOT/openmpi-$OPENMPI_VERSION"
  cfg=("$src/configure" "--prefix=$MPI_DIR" "--with-cuda=$CUDA_HOME" "--disable-mpi-fortran")
  CUDA_LIBDIR="$(find_cuda_libdir || true)"; [[ -n "$CUDA_LIBDIR" ]] && cfg+=("--with-cuda-libdir=$CUDA_LIBDIR")
  (cd "$src" && "${cfg[@]}" && make -j"$JOBS" && make install)
  openmpi_ok || die "OpenMPI CUDA-aware verification failed"
}

zlib_ok(){ [[ -f "$ZLIB_DIR/include/zlib.h" ]] && grep -Eq '#define[[:space:]]+ZLIB_VERSION[[:space:]]+"1\.3\.2"' "$ZLIB_DIR/include/zlib.h"; }
build_zlib(){
  zlib_ok && { log "Reuse zlib $ZLIB_VERSION"; return; }
  rm -rf "$ZLIB_DIR"; local a src; source_file "$ZLIB_ARCHIVE" "$ZLIB_URL" "$ZLIB_FALLBACK_URL" >/dev/null; a="$BUNDLE_SOURCES/$ZLIB_ARCHIVE"; extract_clean "$a" "$SRC_ROOT" "zlib-$ZLIB_VERSION"; src="$SRC_ROOT/zlib-$ZLIB_VERSION"
  (cd "$src" && ./configure --prefix="$ZLIB_DIR" && make -j"$JOBS" && make install); zlib_ok || die "zlib verification failed"
}

hdf5_ok(){ [[ -x "$HDF5_DIR/bin/h5pcc" ]] && "$HDF5_DIR/bin/h5pcc" -showconfig 2>/dev/null | grep -q "HDF5 Version: *$HDF5_VERSION" && "$HDF5_DIR/bin/h5pcc" -showconfig 2>/dev/null | grep -Eq 'Parallel HDF5:[[:space:]]*yes'; }
build_hdf5(){
  hdf5_ok && { log "Reuse Parallel HDF5 $HDF5_VERSION"; return; }
  rm -rf "$HDF5_DIR"; local a src; source_file "$HDF5_ARCHIVE" "$HDF5_URL" "$HDF5_FALLBACK_URL" >/dev/null; a="$BUNDLE_SOURCES/$HDF5_ARCHIVE"; extract_clean "$a" "$SRC_ROOT" "hdf5-$HDF5_VERSION"; src="$SRC_ROOT/hdf5-$HDF5_VERSION"
  (cd "$src" && CC="$MPI_DIR/bin/mpicc" CXX="$MPI_DIR/bin/mpicxx" CFLAGS='-fPIC -O3' CXXFLAGS='-fPIC -O3 -std=c++14' ./configure --prefix="$HDF5_DIR" --enable-parallel --enable-shared --disable-fortran --with-zlib="$ZLIB_DIR" && make -j"$JOBS" && make install)
  hdf5_ok || die "Parallel HDF5 verification failed"
}

extract_lbpm_archive(){
  local archive="$1" dest="$2"
  rm -rf "$dest"; mkdir -p "$dest"
  tar -xzf "$archive" -C "$dest" --strip-components=1
  [[ -f "$dest/CMakeLists.txt" ]] || die "LBPM archive extraction failed: CMakeLists.txt not found in $dest"
}

prepare_lbpm_source(){
  if [[ -f "$LBPM_SRC/.lbpm_bundle_commit" ]] && grep -qx "$LBPM_COMMIT" "$LBPM_SRC/.lbpm_bundle_commit"; then
    log "Reuse extracted LBPM source $LBPM_COMMIT at $LBPM_SRC"
    return
  fi
  local a
  source_file "$LBPM_ARCHIVE" "$LBPM_URL" "$LBPM_FALLBACK_URL" >/dev/null
  a="$BUNDLE_SOURCES/$LBPM_ARCHIVE"
  extract_lbpm_archive "$a" "$LBPM_SRC"
  printf '%s\n' "$LBPM_COMMIT" > "$LBPM_SRC/.lbpm_bundle_commit"
  rm -f "$LBPM_SRC/.lbpm_local_patchset"
  log "LBPM upstream source normalized to canonical path: $LBPM_SRC"
}

outlet_patch_state(){
  local src="$LBPM_SRC/models/ColorModel.cpp"
  [[ -f "$src" ]] || { printf 'missing\n'; return; }
  perl -0777 -ne '
    if (/if\s*\(domain_db->keyExists\("OutletLayersPhase"\)\).*?if\s*\(outlet_layers_phase\s*==\s*1\)\s*\{(.*?)\n\s*\}/s) {
      my $b=$1;
      if ($b =~ /outletA\s*=\s*1\.0\s*;/ && $b =~ /outletB\s*=\s*0\.0\s*;/) { print "fixed\n"; }
      elsif ($b =~ /inletA\s*=\s*1\.0\s*;/ && $b =~ /inletB\s*=\s*0\.0\s*;/) { print "buggy\n"; }
      else { print "unknown\n"; }
    } else { print "unknown\n"; }
  ' "$src"
}

apply_lbpm_patchset(){
  local p="$BUNDLE_PATCHES/$PATCH_FILE_NAME" state
  verify_patch_bundle
  state="$(outlet_patch_state)"
  case "$state" in
    fixed)
      PATCH_STATUS="ALREADY_FIXED"
      log "OutletLayersPhase source is already corrected; patch application skipped"
      ;;
    buggy)
      log "Applying audited local patch: $PATCH_FILE_NAME"
      (cd "$LBPM_SRC" && patch --batch --forward -p1 < "$p")
      [[ "$(outlet_patch_state)" == fixed ]] || die "OutletLayersPhase patch verification failed after patch application"
      PATCH_STATUS="APPLIED"
      ;;
    *)
      die "Unexpected OutletLayersPhase source layout. Refusing to modify an unrecognized LBPM tree."
      ;;
  esac
  printf '%s\n' "$PATCHSET_ID" > "$LBPM_SRC/.lbpm_local_patchset"
  log "Patchset verification PASS: $PATCHSET_ID ($PATCH_STATUS)"
}

manifest_value(){ [[ -f "$MANIFEST_FILE" ]] || return 1; sed -n "s/^$1=//p" "$MANIFEST_FILE" | head -n1; }
lbpm_reusable(){
  [[ "$REBUILD_LBPM" -eq 0 && -x "$LBPM_INSTALL/bin/lbpm_color_simulator" ]] \
    && [[ "$(manifest_value LBPM_COMMIT || true)" == "$LBPM_COMMIT" ]] \
    && [[ "$(manifest_value PATCHSET_ID || true)" == "$PATCHSET_ID" ]] \
    && [[ "$(manifest_value PATCH_SHA256 || true)" == "$PATCH_SHA256" ]] \
    && [[ "$(manifest_value CUDA_ARCH || true)" == "sm_$CUDA_ARCH" ]] \
    && [[ "$(manifest_value CUDA_VERSION || true)" == "$CUDA_VERSION" ]];
}

build_lbpm(){
  lbpm_reusable && { log "Reuse patched LBPM build for sm_$CUDA_ARCH"; return; }
  rm -rf "$LBPM_BUILD" "$LBPM_INSTALL"; mkdir -p "$LBPM_BUILD" "$LBPM_INSTALL"
  cmake -S "$LBPM_SRC" -B "$LBPM_BUILD" \
    -D CMAKE_BUILD_TYPE=Release \
    -D CMAKE_C_COMPILER="$MPI_DIR/bin/mpicc" -D CMAKE_CXX_COMPILER="$MPI_DIR/bin/mpicxx" \
    -D MPI_CXX_COMPILER="$MPI_DIR/bin/mpicxx" -D MPIEXEC="$MPI_DIR/bin/mpirun" \
    -D CMAKE_C_FLAGS='-fPIC' -D CMAKE_CXX_FLAGS='-fPIC' -D CMAKE_CXX_STANDARD=14 \
    -D USE_MPI=1 -D USE_EXT_MPI_FOR_SERIAL_TESTS:BOOL=TRUE \
    -D USE_CUDA=1 -D CMAKE_CUDA_FLAGS="-arch=sm_$CUDA_ARCH" -D CMAKE_CUDA_HOST_COMPILER="$(command -v gcc)" \
    -D USE_HDF5=1 -D HDF5_DIRECTORY="$HDF5_DIR" \
    -D USE_SILO=0 -D USE_NETCDF=0 -D USE_TIMER=0 -D USE_DOXYGEN=0 -D USE_LATEX=0 \
    -D TEST_MAX_PROCS=1 -D DISABLE_LTO=ON -D DISABLE_GOLD=ON -D LBPM_INSTALL_DIR="$LBPM_INSTALL"
  cmake --build "$LBPM_BUILD" --target install -j"$JOBS"
  [[ -x "$LBPM_INSTALL/bin/lbpm_color_simulator" ]] || die "lbpm_color_simulator not installed"
  [[ -x "$LBPM_INSTALL/bin/lbpm_serial_decomp" ]] || die "lbpm_serial_decomp not installed"
}

write_env(){ cat > "$ENV_FILE" <<EOF_ENV
# Generated by LBPM offline installer $INSTALLER_VERSION
export LBPM_ROOT="$INSTALL_ROOT"
export LBPM_SRC="$LBPM_SRC"
export LBPM_BUILD="$LBPM_BUILD"
export LBPM_INSTALL="$LBPM_INSTALL"
export MPI_DIR="$MPI_DIR"
export ZLIB_DIR="$ZLIB_DIR"
export HDF5_DIR="$HDF5_DIR"
export CUDA_HOME="$CUDA_HOME"
export LBPM_CUDA_ARCH="sm_$CUDA_ARCH"
export PATH="$MPI_DIR/bin:$HDF5_DIR/bin:$LBPM_INSTALL/bin:\$PATH"
export LD_LIBRARY_PATH="$MPI_DIR/lib:$MPI_DIR/lib64:$HDF5_DIR/lib:$HDF5_DIR/lib64:$ZLIB_DIR/lib:$CUDA_HOME/lib64:\${LD_LIBRARY_PATH:-}"
if [[ \${EUID:-\$(id -u)} -eq 0 ]]; then export OMPI_ALLOW_RUN_AS_ROOT=1; export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1; fi
EOF_ENV
}

write_manifest(){
  local created; created="$(date -Iseconds)"
  cat > "$MANIFEST_FILE" <<EOF_M
INSTALLER_VERSION=$INSTALLER_VERSION
INSTALLED_AT=$created
GPU_NAME=$GPU_NAME
GPU_CC=$GPU_CC
CUDA_ARCH=sm_$CUDA_ARCH
CUDA_VERSION=$CUDA_VERSION
OPENMPI_VERSION=$OPENMPI_VERSION
ZLIB_VERSION=$ZLIB_VERSION
HDF5_VERSION=$HDF5_VERSION
LBPM_REPO=$LBPM_REPO
LBPM_COMMIT=$LBPM_COMMIT
PATCHSET_ID=$PATCHSET_ID
PATCH_FILE=$PATCH_FILE_NAME
PATCH_SHA256=$PATCH_SHA256
PATCH_STATUS=$PATCH_STATUS
TESTSETDEVICE_STATUS=$TESTSETDEVICE_STATUS
PISTON_SMOKE_STATUS=$PISTON_STATUS
BUNDLE_SOURCE_DIR=$BUNDLE_SOURCES
EOF_M
  cp "$MANIFEST_FILE" "$BUILD_MANIFEST_FILE"
}

mpi_run(){ if [[ ${EUID:-$(id -u)} -eq 0 ]]; then OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 "$MPI_DIR/bin/mpirun" --allow-run-as-root "$@"; else "$MPI_DIR/bin/mpirun" "$@"; fi; }

generate_piston_raw(){
  local out="$1"
  perl -e '
    use strict; use warnings;
    my ($nx,$ny,$nz,$r)=(96,24,24,8);
    open(my $fh, ">:raw", $ARGV[0]) or die $!;
    for my $x (0..$nx-1) {
      for my $y (0..$ny-1) {
        for my $z (0..$nz-1) {
          my $Y=$y-$ny/2; my $Z=$z-$nz/2;
          my $v = ($Y*$Y+$Z*$Z > $r*$r) ? 0 : (($x < 12) ? 1 : 2);
          print $fh pack("C",$v);
        }
      }
    }
    close($fh);
  ' "$out"
}

run_piston_smoke(){
  local d="$RUN_ROOT/smoke-test-piston"
  rm -rf "$d"; mkdir -p "$d"; cd "$d"
  generate_piston_raw "Piston.raw"
  [[ "$(stat -c '%s' Piston.raw)" == "55296" ]] || die "Piston.raw size mismatch"
  cat > input.db <<'EOF_PISTON'
Color {
    tauA = 0.7
    tauB = 0.7
    rhoA = 1.0
    rhoB = 1.0
    alpha = 1e-3
    beta = 0.95
    F = 0, 0, 0
    Restart = false
    timestepMax = 200
    flux = 2.0
    ComponentLabels = 0
    ComponentAffinity = -1.0
}
Domain {
    Filename = "Piston.raw"
    nproc = 1, 1, 1
    n = 24, 24, 96
    N = 24, 24, 96
    L = 1, 1, 1
    BC = 4
    ReadType = "8bit"
    ReadValues = 0, 1, 2
    WriteValues = 0, 1, 2
}
Analysis {
    blobid_interval = 200
    analysis_interval = 100
    restart_interval = 200
    visualization_interval = 200
    restart_file = "Restart"
    N_threads = 1
    load_balance = "independent"
}
Visualization {
    write_silo = false
    save_8bit_raw = false
    save_phase_field = false
    save_pressure = false
    save_velocity = false
}
FlowAdaptor {
}
EOF_PISTON
  log "Piston smoke: serial decomposition"
  mpi_run -np 1 "$LBPM_INSTALL/bin/lbpm_serial_decomp" input.db 2>&1 | tee decomp.log
  [[ -f ID.00000 ]] || die "Piston smoke did not generate ID.00000"
  [[ "$(stat -c '%s' ID.00000)" == "66248" ]] || die "Piston ID.00000 size mismatch"
  log "Piston smoke: ColorModel on GPU"
  set -o pipefail
  mpi_run -np 1 "$LBPM_INSTALL/bin/lbpm_color_simulator" input.db 2>&1 | tee color.log
  local rc=${PIPESTATUS[0]}
  [[ "$rc" -eq 0 ]] || die "Piston ColorModel exited with $rc"
  grep -q 'MPI rank=0 will use GPU ID' color.log || die "Piston smoke did not report GPU binding"
  PISTON_STATUS="PASS"
  log "Piston smoke PASS: Piston.raw=55296, ID.00000=66248, ColorModel exit=0"
}

run_tests(){
  log "Running TestSetDevice"
  ctest --test-dir "$LBPM_BUILD" -N | grep -q TestSetDevice || die "Expected TestSetDevice is missing from frozen LBPM build"
  OMPI_ALLOW_RUN_AS_ROOT=1 OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1 ctest --test-dir "$LBPM_BUILD" -R '^TestSetDevice$' --output-on-failure
  TESTSETDEVICE_STATUS="PASS"
  run_piston_smoke
}

main(){
  parse_args "$@"
  validate_install_root "$INSTALL_ROOT" || exit 2
  layout
  log "LBPM Offline Installer $INSTALLER_VERSION"
  log "Frozen upstream: $LBPM_REPO @ $LBPM_COMMIT"
  log "Local patchset: $PATCHSET_ID"
  log "Bundle sources: $BUNDLE_SOURCES"
  log "Network fallback: $ALLOW_NETWORK"
  check_host_tools; detect_cuda
  log "GPU: $GPU_NAME | CC $GPU_CC | sm_$CUDA_ARCH | CUDA $CUDA_VERSION"
  mkdir -p "$BUNDLE_SOURCES"
  preflight_sources
  build_openmpi; export PATH="$MPI_DIR/bin:$PATH"; export LD_LIBRARY_PATH="$MPI_DIR/lib:$MPI_DIR/lib64:${LD_LIBRARY_PATH:-}"
  build_zlib; build_hdf5; export LD_LIBRARY_PATH="$HDF5_DIR/lib:$HDF5_DIR/lib64:$ZLIB_DIR/lib:$LD_LIBRARY_PATH"
  prepare_lbpm_source; apply_lbpm_patchset; build_lbpm; write_env
  if [[ "$SKIP_TESTS" -eq 1 ]]; then TESTSETDEVICE_STATUS="SKIPPED"; PISTON_STATUS="SKIPPED"; else run_tests; fi
  write_manifest
  local elapsed=$(( $(date +%s)-START_TIME ))
  cat <<EOF_DONE

============================================================
LBPM offline installation finished
Installer     : $INSTALLER_VERSION
GPU           : $GPU_NAME
CUDA          : $CUDA_VERSION / sm_$CUDA_ARCH
OpenMPI       : $OPENMPI_VERSION (CUDA-aware)
zlib          : $ZLIB_VERSION
Parallel HDF5 : $HDF5_VERSION
LBPM upstream : $LBPM_COMMIT
Local patch   : $PATCH_FILE_NAME ($PATCH_STATUS)
TestSetDevice : $TESTSETDEVICE_STATUS
Piston smoke  : $PISTON_STATUS
Executable    : $LBPM_INSTALL/bin/lbpm_color_simulator
Activate      : source "$ENV_FILE"
Build manifest: $BUILD_MANIFEST_FILE
Log           : $LOG_FILE
Elapsed       : ${elapsed}s
============================================================
EOF_DONE
}
main "$@"
