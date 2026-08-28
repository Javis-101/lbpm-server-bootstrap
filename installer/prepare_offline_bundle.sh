#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCES="$SCRIPT_DIR/sources"
PATCHES="$SCRIPT_DIR/patches"
OUT="${OUTPUT_ZIP:-$(cd "$SCRIPT_DIR/.." && pwd -P)/LBPM-portable-offline-installer.zip}"
NO_DOWNLOAD=0
[[ "${1:-}" == "--no-download" ]] && { NO_DOWNLOAD=1; shift; }
[[ $# -eq 0 ]] || { echo "Usage: $0 [--no-download]" >&2; exit 2; }
mkdir -p "$SOURCES"

OMPI=openmpi-4.1.8.tar.gz
ZLIB=zlib-1.3.2.tar.gz
HDF5=hdf5-1.14.6.tar.gz
COMMIT=6d686d354e5b8140841d3601e4c8c0e4e4b77e48
LBPM="LBPM-$COMMIT.tar.gz"
PATCH=0001-fix-OutletLayersPhase.patch
OMPI_SHA=fb41086bbed9300baa2f3d7572491facfe5257412fa524ec5a396aa9101d5c62
ZLIB_SHA=bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16
HDF5_SHA=e4defbac30f50d64e1556374aa49e574417c9e72c6b1de7a4ff88c4b1bea6e9b
PATCH_SHA='fbce8ac8f101c5f5ff3764c4e6e71f98d5a478e54609f3d63864dbc8e7d1c2b8'

sha(){ sha256sum "$1" | awk '{print $1}'; }
download(){
  local dest="$1"; shift
  [[ "$NO_DOWNLOAD" -eq 0 ]] || { echo "ERROR: missing $(basename "$dest") with --no-download" >&2; exit 1; }
  local u
  for u in "$@"; do
    echo "Downloading $(basename "$dest") from $u"
    if command -v curl >/dev/null 2>&1; then curl -fL --retry 5 --connect-timeout 20 -o "$dest.part" "$u" && { mv "$dest.part" "$dest"; return; } || rm -f "$dest.part"
    elif command -v wget >/dev/null 2>&1; then wget --tries=5 --timeout=20 -O "$dest.part" "$u" && { mv "$dest.part" "$dest"; return; } || rm -f "$dest.part"
    else echo "ERROR: curl or wget is required" >&2; exit 1; fi
  done
  echo "ERROR: download failed for $(basename "$dest")" >&2; exit 1
}
ensure(){ local name="$1" expected="$2"; shift 2; local f="$SOURCES/$name"; [[ -s "$f" ]] || download "$f" "$@"; local a; a="$(sha "$f")"; [[ -z "$expected" || "$a" == "$expected" ]] || { echo "ERROR: SHA mismatch for $name" >&2; exit 1; }; echo "SHA256 OK: $name = $a"; }

[[ "$(sha "$PATCHES/$PATCH")" == "$PATCH_SHA" ]] || { echo "ERROR: patch checksum mismatch" >&2; exit 1; }
ensure "$OMPI" "$OMPI_SHA" "https://download.open-mpi.org/release/open-mpi/v4.1/$OMPI"
ensure "$ZLIB" "$ZLIB_SHA" "https://www.zlib.net/$ZLIB" "https://www.zlib.net/fossils/$ZLIB"
ensure "$HDF5" "$HDF5_SHA" "https://support.hdfgroup.org/releases/hdf5/v1_14/v1_14_6/downloads/$HDF5" "https://github.com/HDFGroup/hdf5/releases/download/hdf5_1.14.6/$HDF5"
ensure "$LBPM" "" "https://github.com/OPM/LBPM/archive/$COMMIT.tar.gz" "https://codeload.github.com/OPM/LBPM/tar.gz/$COMMIT"
{
  for x in "$OMPI" "$ZLIB" "$HDF5" "$LBPM"; do printf '%s  %s\n' "$(sha "$SOURCES/$x")" "$x"; done
} > "$SOURCES/SHA256SUMS"
printf '%s  %s\n' "$PATCH_SHA" "$PATCH" > "$PATCHES/SHA256SUMS"
cat > "$SOURCES/BUNDLE_MANIFEST.txt" <<EOF_M
BUNDLE_FORMAT=2
BUILDER_VERSION=2.0.7
LBPM_REPO=OPM/LBPM
LBPM_COMMIT=$COMMIT
LBPM_LOCAL_PATCHSET=outletlayersphase-fix-v1
LBPM_LOCAL_PATCH=$PATCH
LBPM_LOCAL_PATCH_SHA256=$PATCH_SHA
OPENMPI_VERSION=4.1.8
ZLIB_VERSION=1.3.2
HDF5_VERSION=1.14.6
CREATED_AT=$(date -Iseconds)
EOF_M
rm -f "$OUT"
if command -v zip >/dev/null 2>&1; then (cd "$SCRIPT_DIR/.." && zip -qr "$OUT" "$(basename "$SCRIPT_DIR")")
elif command -v python3 >/dev/null 2>&1; then python3 - "$SCRIPT_DIR" "$OUT" <<'PY'
from pathlib import Path
import sys, zipfile
root=Path(sys.argv[1]); out=Path(sys.argv[2])
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p in root.rglob('*'):
        if p.is_file(): z.write(p, Path(root.name)/p.relative_to(root))
PY
else echo "ERROR: zip or python3 required to create ZIP" >&2; exit 1; fi
echo "[OK] $OUT"
