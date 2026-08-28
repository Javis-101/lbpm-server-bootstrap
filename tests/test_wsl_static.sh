#!/usr/bin/env bash
set -Eeuo pipefail
export PYTHONDONTWRITEBYTECODE=1

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$TEST_DIR/.." && pwd -P)"
PORTABILITY_BIN="$(mktemp -d)"
trap 'rm -r -- "$PORTABILITY_BIN"' EXIT
printf '#!/usr/bin/env bash\nexit 1\n' > "$PORTABILITY_BIN/nvidia-smi"
chmod 0755 "$PORTABILITY_BIN/nvidia-smi"

cd "$ROOT"
while IFS= read -r -d '' script; do
  bash -n "$script"
done < <(find . -path './.git' -prune -o -type f -name '*.sh' -print0)

python3 -m unittest discover -s tests -p 'test_*.py' >/dev/null
python3 -m unittest discover -s sop/tests -p 'test_*.py' >/dev/null
python3 scripts/publication_gate.py . >/dev/null

bash tests/test_preflight.sh >/dev/null
bash tests/test_gfortran_preflight.sh >/dev/null
bash tests/test_stage_failure_propagation.sh >/dev/null
bash tests/test_installer_stage.sh >/dev/null
PATH="$PORTABILITY_BIN:$PATH" bash sop/tests/test_shell_portability_v132.sh >/dev/null
bash run_all.sh --help >/dev/null

printf 'SOURCE_PUBLICATION_STATIC_PASS\n'
