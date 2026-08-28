#!/usr/bin/env bash
# One-time first-rock numerical smoke/sanity only; parameters are not production physics.
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"
CASE_DIR="${1:-}"
[[ -n "$CASE_DIR" ]] || die "Usage: first_case_smoke_test.sh /path/to/case-dir"
CASE_DIR="$(cd "$CASE_DIR" && pwd -P)"
[[ -f "$CASE_DIR/CASE_PREPARED.json" ]] || die "Missing CASE_PREPARED.json"
[[ -f "$CASE_DIR/ID.00000" ]] || die "Missing ID.00000 decomposition/QC evidence"
[[ -f "$CASE_DIR/rock_waterdrive.raw" ]] || die "Missing rock_waterdrive.raw"
require_acceptance_pass "$VALIDATION_DIR/acceptance_report.json"
python3 "$SCRIPT_DIR/verify_case_contract.py" --case-dir "$CASE_DIR"
source_lbpm_env

read -r NX NY EXT_NZ R VOXEL_LENGTH_UM EXPECTED_BYTES <<<"$(python3 - "$CASE_DIR/case_manifest.json" <<'PY'
import json, sys
manifest = json.load(open(sys.argv[1]))
z, y, x = manifest["simulation"]["simulation_domain"]["shape_zyx"]
r = manifest["simulation"]["augmentation"]["inlet_layers"]
print(x, y, z, r, manifest["voxel_length_um"], manifest["expected_bytes"]["rock_waterdrive.raw"])
PY
)"
RUN_DIR="$CASE_DIR/engineering-smoke-2000"
[[ ! -e "$RUN_DIR" ]] || die "Engineering smoke directory already exists; refusing silent overwrite: $RUN_DIR"
mkdir "$RUN_DIR"
cp "$CASE_DIR/rock_waterdrive.raw" "$RUN_DIR/"
cd "$RUN_DIR"

cat > input-engineering-smoke.db <<EOF_DB
Color {
    tauA = 0.8
    tauB = 0.8
    rhoA = 1.0
    rhoB = 1.0
    alpha = 0.005
    beta = 0.95
    F = 0, 0, 0
    Restart = false
    din = 1.001
    dout = 0.999
    timestepMax = 2000
    ComponentLabels = 0
    ComponentAffinity = -1.0
}
Domain {
    Filename = "rock_waterdrive.raw"
    nproc = 1, 1, 1
    n = $NX, $NY, $EXT_NZ
    N = $NX, $NY, $EXT_NZ
    voxel_length = $VOXEL_LENGTH_UM
    BC = 3
    InletLayers = 0, 0, $R
    OutletLayers = 0, 0, $R
    InletLayersPhase = 2
    OutletLayersPhase = 1
    ReadType = "8bit"
    ReadValues = 0, 1, 2
    WriteValues = 0, 1, 2
}
Analysis {
    analysis_interval = 100
    blobid_interval = 500
    restart_interval = 1000
    visualization_interval = 500
    restart_file = "Restart"
    N_threads = 4
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

log "Running one-time first-rock numerical smoke/sanity test"
mpi_run -np 1 lbpm_color_simulator input-engineering-smoke.db 2>&1 | tee smoke.log
rc=${PIPESTATUS[0]}
[[ "$rc" -eq 0 ]] || die "Engineering smoke exited with $rc"
python3 "$SCRIPT_DIR/check_lbpm_porosity.py" \
  --manifest "$CASE_DIR/case_manifest.json" --log smoke.log | tee porosity-check.log
python3 "$SCRIPT_DIR/check_color_sanity.py" \
  --run-log smoke.log --timelog timelog.csv --output-dir "$RUN_DIR" \
  --expected-final-timestep 2000 --expected-raw-bytes "$EXPECTED_BYTES" \
  --tolerance 1e-9 | tee numerical-sanity-check.log
python3 "$SCRIPT_DIR/check_case_output.py" \
  --case-dir "$CASE_DIR" --output-dir "$RUN_DIR" \
  --expected-final-timestep 2000 --tolerance 1e-9 | tee output-check.log
python3 "$SCRIPT_DIR/verify_case_contract.py" --case-dir "$CASE_DIR"

python3 - "$SCRIPT_DIR" "$RUN_DIR" <<'PY'
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from state_reports import atomic_json, sha256
run_dir = Path(sys.argv[2]).resolve()
atomic_json(run_dir / "PASS.json", {
    "schema_version": 1,
    "sop_version": "1.3.2",
    "status": "PASS",
    "test_role": "first-rock numerical smoke/sanity test",
    "production_physical_validation": False,
    "numerical_sanity": "PASS",
    "completed_at": datetime.now(timezone.utc).isoformat(),
    "expected_final_timestep": 2000,
    "final_raw": {"file": "id_t2000.raw", "sha256": sha256(run_dir / "id_t2000.raw")},
})
PY
log "First-rock numerical smoke/sanity PASS"
