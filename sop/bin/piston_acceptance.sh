#!/usr/bin/env bash
# Upstream-derived lightweight smoke/sanity test; not an official full benchmark.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"
source_lbpm_env
require_cmd mktemp
require_cmd perl
require_cmd stat
RUN_DIR="$(mktemp -d "$VALIDATION_DIR/piston-recheck.XXXXXX")"
cd "$RUN_DIR"

perl -e '
  use strict; use warnings;
  my ($nx,$ny,$nz,$r)=(96,24,24,8);
  open(my $fh, ">:raw", "Piston.raw") or die $!;
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
'
[[ "$(stat -c '%s' Piston.raw)" == "55296" ]] || die "Piston.raw size mismatch"

cat > input.db <<'EOF_DB'
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
    save_8bit_raw = true
    save_phase_field = false
    save_pressure = false
    save_velocity = false
}
FlowAdaptor {
}
EOF_DB

log "Piston sanity: serial decomposition"
mpi_run -np 1 lbpm_serial_decomp input.db 2>&1 | tee decomp.log
[[ -f ID.00000 ]] || die "Piston sanity did not generate ID.00000"
[[ "$(stat -c '%s' ID.00000)" == "66248" ]] || die "Piston ID.00000 size mismatch"

log "Piston sanity: ColorModel GPU run"
mpi_run -np 1 lbpm_color_simulator input.db 2>&1 | tee color.log
rc=${PIPESTATUS[0]}
[[ "$rc" -eq 0 ]] || die "Piston ColorModel exited with $rc"
python3 "$SCRIPT_DIR/check_color_sanity.py" \
  --run-log color.log --timelog timelog.csv --output-dir "$RUN_DIR" \
  --expected-final-timestep 200 --expected-raw-bytes 55296 --tolerance 1e-9 | tee sanity-check.log

python3 - "$SCRIPT_DIR" "$RUN_DIR" "$VALIDATION_DIR/piston_result.json" <<'PY'
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from state_reports import atomic_json, sha256
run_dir = Path(sys.argv[2]).resolve()
payload = {
    "schema_version": 1,
    "sop_version": "1.3.2",
    "status": "PASS",
    "test_role": "upstream-derived lightweight smoke/sanity test",
    "official_full_benchmark": False,
    "numerical_sanity": "PASS",
    "completed_at": datetime.now(timezone.utc).isoformat(),
    "run_directory": str(run_dir),
    "expected_final_timestep": 200,
    "final_raw": {"file": "id_t200.raw", "sha256": sha256(run_dir / "id_t200.raw")},
}
atomic_json(run_dir / "PASS.json", payload)
atomic_json(Path(sys.argv[3]), payload)
PY
log "Piston lightweight smoke/sanity PASS"
