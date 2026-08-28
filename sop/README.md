# LBPM-postinstall-SOP-v1.3.2

This package is the post-install validation and single-case preparation companion for installers `2.0.5-offline`, `2.0.6-offline`, and `2.0.7-offline`. Builder v2.0.7 is recommended; the two earlier installer versions remain exact compatibility targets.

## Scientific responsibility boundary

> SOP assumes the input 128³ RAW has already completed all scientific geometry preprocessing.

> SOP validates the rock geometry but does not modify pore/solid topology.

The production data path is:

```text
Dataset preprocessing
    -> final immutable 128 x 128 x 128 RAW
    -> SOP v1.3.2 validation and case construction
    -> post-install / first-case numerical sanity
    -> production parameterization and Runner (a later project)
```

The production invariant is `INPUT_ROI == SIMULATION_ROI`. The SOP never deletes or adds pores, removes non-spanning components, relabels source voxels, or repairs a failed rock. Connectivity is a validator only. A failed rock returns `INPUT_ROCK_CONNECTIVITY_FAILED` and does not continue to simulation.

`--keep all` remains only as a deprecated alias for validate/preserve. `--keep percolating` fails with a migration message. Filtering belongs to upstream dataset preprocessing.

## Fixed production RAW contract

```text
shape          128 x 128 x 128 (z, y, x in manifests)
byte count     2,097,152
dtype          uint8
solid label    0
pore label     1
flow axis      +Z
connectivity   6-neighbor; inlet z=0; outlet z=127
```

Wrong dimensions, byte count, labels, equal solid/pore labels, or missing +Z spanning connectivity fail fast. Smaller shapes are available only through the hidden test-only Python flag used by unit fixtures; `prepare_case.sh` always passes 128 x 128 x 128.

The source RAW must be outside the target case directory. Before any output is written, resolved source and output paths are checked for collision. The source SHA256 is recorded before preparation and recalculated after preparation and again after serial decomposition.

## Installation prerequisite and directory layout

Install the generated `LBPM-portable-offline-installer.zip` first. The SOP requires:

```text
/root/LBPM-stack/LBPM_BUILD_MANIFEST.txt
```

Recommended layout:

```text
/root/LBPM-stack/                         installed software stack
/root/rivermind-data/
├── LBPM-offline/                        portable installer media
├── lbpm-validation/                     acceptance reports and smoke artifacts
├── lbpm-simulations/                    prepared digital-rock cases
└── LBPM-postinstall-SOP-v1.3.2/         this package
```

Do not move `/root/LBPM-stack` after installation because the stack may contain absolute runtime paths.

## 1. Post-install acceptance

```bash
cd /root/rivermind-data/LBPM-postinstall-SOP-v1.3.2
bash bin/post_install_acceptance.sh
```

The command validates installer/build identity, the frozen LBPM commit, the audited local patch, source semantics, dynamic linking, GPU architecture, CUDA, Open MPI, TestSetDevice, and an upstream-derived lightweight Piston smoke/sanity chain. It records GPU name, driver, compute capability, CUDA version, MPI identity/version/CUDA-aware status, LBPM commit, patch identity, build/source hashes, and executable paths/hashes. UCX is not assumed or required and is not reported without direct evidence that it was selected by the runtime.

`ldd` is fail-closed: either an `ldd` command error or a `not found` result fails acceptance.

All shell-to-shell calls use explicit `bash child.sh` invocation. The SOP does
not depend on POSIX executable bits surviving a Windows-generated ZIP; invoking
the documented top-level commands with `bash` remains valid when every packaged
`.sh` file is mode `0644` after Linux extraction.

Machine interface:

```json
{
  "schema_version": 1,
  "sop_version": "1.3.2",
  "status": "PASS",
  "checks": {
    "lbpm_identity": "PASS",
    "patch": "PASS",
    "dynamic_linking": "PASS",
    "gpu": "PASS",
    "cuda": "PASS",
    "mpi": "PASS",
    "testsetdevice": "PASS",
    "piston": "PASS"
  },
  "provenance": {}
}
```

The authoritative file is `lbpm-validation/acceptance_report.json`. `POSTINSTALL_PASS.txt` is a human-readable compatibility marker. Both are invalidated before every new acceptance run and published only after all current checks pass; failures leave a machine-readable `status: FAIL` report and no PASS marker.

Piston is an upstream-derived lightweight smoke/sanity test, not an official full physical benchmark. It requires exit code zero, GPU binding, `timelog.csv`, the upstream 12-column timelog schema, finite values, saturation within `[-epsilon, 1+epsilon]`, and `id_t200.raw` at the expected byte size.

## 2. Prepare one immutable 128³ rock

```bash
bash bin/prepare_case.sh \
  --input /data/final_rock.raw \
  --case-id rock-000001 \
  --voxel-length-um 1.0
```

A case ID must be a safe basename. Absolute paths, `..`, `/`, and `\` are rejected. An existing non-empty case directory is rejected without deleting its scientific outputs. A rerun first invalidates stale READY/PREPARED markers, then fails if other content remains.

Successful preparation produces `CASE_PREPARED.json`, not READY. It performs:

1. fixed shape/dtype/label validation;
2. source SHA256 capture;
3. non-mutating 6-neighbor +Z connectivity analysis;
4. exact source copies `rock.raw` and `rock_geometry.raw`;
5. optional simulation-domain reservoir augmentation in `rock_waterdrive.raw`;
6. byte-for-byte extraction and comparison of the embedded source ROI;
7. serial decomposition and `ID.00000` size validation;
8. post-decomposition source/ROI contract revalidation;
9. atomic publication of PREPARED state.

For three reservoir layers at each end:

```text
source ROI             128 x 128 x 128, 2,097,152 bytes
simulation domain      134 x 128 x 128, 2,195,456 bytes
ROI offset (z,y,x)     [3, 0, 0]
ROI slice              simulation_domain[3:131, :, :]
ID.00000 (one rank)    2,298,400 bytes
```

The inlet reservoir uses water label `2`; the outlet reservoir uses gas label `1`. Those layers are outside the scientific ROI. The 128³ ROI inside `rock_waterdrive.raw` is byte-for-byte identical to the source RAW.

## JSON case contracts

`connectivity_report.json` records a check, never a cleaning operation:

```json
{
  "schema_version": 1,
  "status": "PASS",
  "source_file": "/data/final_rock.raw",
  "source_sha256": "...",
  "shape_zyx": [128, 128, 128],
  "dtype": "uint8",
  "labels": {"solid": 0, "pore": 1},
  "flow_axis": "+Z",
  "connectivity_definition": {
    "neighbors": 6,
    "inlet_plane": "z=0",
    "outlet_plane": "z=nz-1"
  },
  "total_voxels": 2097152,
  "solid_voxels": 0,
  "pore_voxels": 2097152,
  "porosity": 1.0,
  "z_percolating": true,
  "spanning_voxels": 2097152,
  "connected_component_count": 1,
  "spanning_component_count": 1,
  "geometry_modified": false
}
```

`case_manifest.json` separates the three geometry concepts:

```json
{
  "schema_version": 1,
  "sop_version": "1.3.2",
  "source_roi": {
    "shape_zyx": [128, 128, 128],
    "dtype": "uint8",
    "sha256": "...",
    "sha256_before": "...",
    "sha256_after": "...",
    "geometry_modified": false
  },
  "simulation": {
    "roi_preserved": true,
    "simulation_roi": {
      "filename": "rock_geometry.raw",
      "byte_for_byte_equal_to_source": true
    },
    "simulation_domain": {
      "filename": "rock_waterdrive.raw",
      "shape_zyx": [134, 128, 128]
    },
    "augmentation": {
      "type": "z_reservoir_layers",
      "inlet_layers": 3,
      "outlet_layers": 3
    },
    "roi_offset_zyx": [3, 0, 0]
  },
  "saturation_contract": {
    "pore_space_basis": "source_128_cube_roi",
    "denominator_pore_voxels": 123456,
    "reservoirs_excluded": true
  }
}
```

The future S_rg contract is fixed as:

```text
residual gas voxels inside the original 128³ ROI
-------------------------------------------------
pore voxels inside the original 128³ ROI
```

This SOP does not implement the production S_rg extractor.

## 3. READY state and first-case smoke

Use the wrapper so READY is published only after the smoke state is known.

First server / first representative rock:

```bash
bash bin/run_to_parameterization.sh \
  --rock /data/final_rock.raw \
  --case-id rock-000001 \
  --first-case-smoke
```

Later cases on an already accepted server:

```bash
bash bin/run_to_parameterization.sh \
  --rock /data/final_rock_002.raw \
  --case-id rock-000002 \
  --skip-postinstall
```

The first-rock smoke is a 2000-step numerical sanity run, not production physical validation. It checks exit status, GPU binding, timelog schema and finite values, saturation tolerance, expected final timestep/RAW, source-ROI pore/solid invariants, LBPM media porosity, and source/embedded-ROI hashes.

`READY_FOR_PARAMETERIZATION.json` distinguishes:

```json
{
  "schema_version": 1,
  "status": "READY",
  "environment": "ACCEPTED",
  "case_preparation": "PASS",
  "smoke_test": "PASS",
  "final": "READY"
}
```

For later cases, `smoke_test` is `NOT_REQUIRED`. A failed required smoke never publishes READY.

## Deliberately outside v1.3.2

This SOP does not choose drive mode, BC, Ca, contact angle, affinity, alpha/beta, tau, flux, din/dout, production timestep/convergence, or official physical benchmarks. It does not implement Runner, scheduling, retries, databases, GUI/Web, batch orchestration, or production S_rg extraction.

Local Windows tests establish only `STATIC/LOCAL TEST PASS`. The package becomes `PRODUCTION VALIDATED` only after the documented Linux NVIDIA GPU server sequence succeeds.
