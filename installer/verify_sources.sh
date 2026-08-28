#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
S="$SCRIPT_DIR/sources"
P="$SCRIPT_DIR/patches"
MANIFEST="$S/BUNDLE_MANIFEST.txt"
BUILDER_VERSION="2.0.7"
LBPM_COMMIT="6d686d354e5b8140841d3601e4c8c0e4e4b77e48"
PATCH_FILE="0001-fix-OutletLayersPhase.patch"
PATCH_SHA="fbce8ac8f101c5f5ff3764c4e6e71f98d5a478e54609f3d63864dbc8e7d1c2b8"
files=("openmpi-4.1.8.tar.gz" "zlib-1.3.2.tar.gz" "hdf5-1.14.6.tar.gz" "LBPM-$LBPM_COMMIT.tar.gz")

manifest_value(){
  local key="$1"
  awk -v key="$key" '
    index($0, key "=") == 1 {
      value=substr($0, length(key)+2)
      sub(/\r$/, "", value)
      count++
    }
    END {
      if (count != 1) exit 1
      printf "%s", value
    }
  ' "$MANIFEST"
}

require_manifest_value(){
  local key="$1" expected="$2" actual
  actual="$(manifest_value "$key")" || { echo "ERROR: missing or duplicate manifest field: $key" >&2; exit 1; }
  [[ "$actual" == "$expected" ]] || { echo "ERROR: manifest field $key mismatch: expected=$expected actual=$actual" >&2; exit 1; }
}
[[ -f "$S/SHA256SUMS" ]] || { echo "ERROR: missing sources/SHA256SUMS" >&2; exit 1; }
for name in "${files[@]}"; do
  f="$S/$name"; [[ -s "$f" ]] || { echo "ERROR: missing $f" >&2; exit 1; }
  expected="$(awk -v n="$name" '{x=$2; sub(/\r$/, "", x); if (x==n || x=="*" n){print $1; exit}}' "$S/SHA256SUMS")"
  [[ -n "$expected" ]] || { echo "ERROR: no checksum for $name" >&2; exit 1; }
  actual="$(sha256sum "$f" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || { echo "ERROR: SHA256 mismatch for $name" >&2; exit 1; }
  echo "PASS  $name"
done
[[ -s "$P/$PATCH_FILE" ]] || { echo "ERROR: missing local patch" >&2; exit 1; }
actual="$(sha256sum "$P/$PATCH_FILE" | awk '{print $1}')"
[[ "$actual" == "$PATCH_SHA" ]] || { echo "ERROR: local patch checksum mismatch" >&2; exit 1; }
echo "PASS  patches/$PATCH_FILE"
[[ -f "$MANIFEST" ]] || { echo "ERROR: missing sources/BUNDLE_MANIFEST.txt" >&2; exit 1; }
require_manifest_value BUNDLE_FORMAT "2"
require_manifest_value BUILDER_VERSION "$BUILDER_VERSION"
require_manifest_value LBPM_REPO "OPM/LBPM"
require_manifest_value LBPM_COMMIT "$LBPM_COMMIT"
require_manifest_value LBPM_LOCAL_PATCHSET "outletlayersphase-fix-v1"
require_manifest_value LBPM_LOCAL_PATCH "$PATCH_FILE"
require_manifest_value LBPM_LOCAL_PATCH_SHA256 "$PATCH_SHA"
require_manifest_value OPENMPI_VERSION "4.1.8"
require_manifest_value ZLIB_VERSION "1.3.2"
require_manifest_value HDF5_VERSION "1.14.6"
created_at="$(manifest_value CREATED_AT)" || { echo "ERROR: missing or duplicate manifest field: CREATED_AT" >&2; exit 1; }
[[ -n "$created_at" ]] || { echo "ERROR: empty manifest field: CREATED_AT" >&2; exit 1; }
echo "All frozen sources and the audited patch verified."
