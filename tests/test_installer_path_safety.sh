#!/usr/bin/env bash
set -Eeuo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$TEST_DIR/.." && pwd -P)"
GUARD="$ROOT/installer/lib/path_safety.sh"

# Regression contract: every value below could redirect recursive removals
# outside the intended installation tree and must fail before layout creation.
source "$GUARD"

for invalid in "" "/" "." "relative/path"; do
  if validate_install_root "$invalid" >/dev/null 2>&1; then
    printf 'Unsafe install root was accepted: <%s>\n' "$invalid" >&2
    exit 1
  fi
done

validate_install_root "/opt/lbpm-stack"
validate_install_root "/data/lbpm/LBPM-stack"

TEMP_ROOT="$(mktemp -d)"
trap 'rm -r -- "$TEMP_ROOT"' EXIT
cd "$TEMP_ROOT"

if bash "$ROOT/installer/install_lbpm_offline.sh" --prefix relative/path \
    >stdout.log 2>stderr.log; then
  printf 'Installer unexpectedly accepted a relative --prefix\n' >&2
  exit 1
fi

grep -F 'Install root must be an absolute path' stderr.log >/dev/null
[[ ! -e "$TEMP_ROOT/relative" ]]

printf 'INSTALLER_PATH_SAFETY_PASS\n'
