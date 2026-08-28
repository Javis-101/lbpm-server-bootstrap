# LBPM Server Bootstrap

From a clean CUDA/Linux server to an auditable OPM/LBPM GPU stack with a reproducible, offline-first bootstrap and acceptance workflow.

> **Release line:** this branch is the source publication representation for the immutable, real-server-validated v1.0.3 artifact. Repository `main` is the hardened `1.0.4-dev` development line.

LBPM Server Bootstrap is an independent community project built around [OPM/LBPM](https://github.com/OPM/LBPM). It is not an official OPM project.

## Overview

This project coordinates a pinned LBPM dependency stack, post-install acceptance, an immutable real-rock data contract, a bounded GPU ColorModel smoke run, and a sanitized evidence trail. Its purpose is to turn infrastructure readiness into a reproducible engineering decision rather than treating a successful compile as the finish line.

The frozen local artifact is `LBPM-server-bootstrap-v1.0.3.zip` with SHA256:

```text
f1bf6e5649769aba5d246535d3f74f1cbc4032ebab78ee9bb54fa7a439360507
```

That artifact remains byte-for-byte unchanged and is not stored in Git. It passed a Tesla T4 fresh installation and an exact compatible-reuse run. This branch preserves the v1.0.3 runtime logic and adds only publication metadata around a source-only representation; the GitHub Release ZIP remains the authoritative deployable artifact.

## Why this project exists

An LBPM build can succeed while the server is still unsuitable for reproducible research. Compiler linkage, CUDA visibility, MPI identity, patched-source provenance, RAW geometry, Z-connectivity, ROI preservation, and bounded simulation evidence must agree. This project makes those checks explicit and fail-closed.

## What it validates

- package and source SHA256 identity;
- host, CUDA, compiler, GNU Fortran, MPI, HDF5, and LBPM prerequisites;
- fresh installation versus exact compatible reuse;
- LBPM commit and local patch identity;
- GPU binding and lightweight Piston/runtime acceptance;
- a 128 x 128 x 128 uint8 RAW envelope;
- labels, +Z connectivity, source immutability, and ROI preservation through the SOP;
- a bounded GPU ColorModel numerical smoke run;
- machine-readable summaries and evidence inventory.

## What it does not validate

Passing Bootstrap/SOP validation means the infrastructure, LBPM build, GPU runtime, data contract, and smoke simulation are engineering-ready.

It does **not** constitute physical validation of a production water-displacing-gas simulation, residual gas saturation, capillary-number selection, wettability model, or final scientific parameterization. It also does not select production parameters, develop a batch Runner, modify APT sources, install missing OS packages, or certify arbitrary CUDA/Linux combinations.

## Architecture and workflow

```text
Host preflight
  -> pinned source and patch verification
  -> install or exact compatible reuse
  -> LBPM/MPI/CUDA runtime identity
  -> post-install SOP acceptance
  -> immutable RAW and +Z connectivity contract
  -> GPU ColorModel smoke
  -> bounded evidence archive
  -> READY_FOR_PARAMETERIZATION (engineering state only)
```

See [architecture](docs/architecture.md) and the [evidence contract](docs/EVIDENCE-CONTRACT.md).

## Supported environment

The frozen profile targets Ubuntu-like x86_64 Linux as root, one visible NVIDIA GPU, an already installed CUDA toolkit, GCC/G++, GNU Fortran with working `-lgfortran` linkage, CMake 3.24 or newer, OpenMPI 4.1.8, zlib 1.3.2, parallel HDF5 1.14.6, and OPM/LBPM commit `6d686d354e5b8140841d3601e4c8c0e4e4b77e48`.

The data contract is one upstream-preprocessed 128 x 128 x 128 uint8 RAW, `0=solid`, `1=pore`, flow axis `+Z`, voxel length 1.0 micrometre, and `MPI_RANKS=1`. See [compatibility](docs/compatibility.md).

## Quick start

This source checkout intentionally does not contain the large offline archives required by `run_all.sh`. For the validated workflow, download `LBPM-server-bootstrap-v1.0.3.zip` from the v1.0.3 GitHub Release and verify its published SHA256 before use. Do not reconstruct, modify, or redistribute a different archive under the v1.0.3 name.

You can run the source-only static gates:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/publication_gate.py .
```

The v1.0.3 installer was validated with its default stack path. Do not pass an arbitrary root or system directory as a custom installer prefix. The additional fail-closed path guard exists only on `main` for the future v1.0.4 line and requires its own real-server validation before release.

## Online versus offline mode

The installer is offline-first: fixed source archives are verified locally. An explicit network fallback can acquire only the pinned sources when an archive is absent. Git never tracks those tarballs; a complete offline bundle belongs in a release asset. See [offline mode](docs/offline-mode.md).

## Configuration

Copy `bootstrap.env.example` to the ignored `bootstrap.env` and use neutral absolute Linux paths. Never commit server-specific paths, credentials, SSH information, or research-data locations.

## Validation gates

The repository gate covers shell/Python syntax, version and metadata consistency, forbidden secret-like content, forbidden research data and archives, required notices, and installer prefix safety. GitHub-hosted CI is static only; it does not emulate an NVIDIA GPU or establish production validation.

The confirmed runtime evidence disposition and sanitized run identifiers are documented in [v1.0.3 validation](docs/validation/v1.0.3.md).

## Real-rock smoke workflow

The SOP validates the RAW envelope, label semantics, six-neighbour +Z spanning connectivity, immutable source copies, reservoir layers outside the scientific ROI, decomposition evidence, and a bounded ColorModel smoke run. A failed rock is rejected; the workflow does not repair, filter, relabel, or silently crop it.

## Output and evidence

Each run has a unique directory with a state file, per-stage logs, host/runtime identity, validation reports, a bounded evidence archive, and a sidecar SHA256. Source/final RAW, Restart/HDF5/build trees, intermediate RAW, credentials, and private host identifiers are excluded from public evidence.

## Repository layout

```text
bin/                 bootstrap contracts and evidence helpers
installer/           offline installer source, patch, and source manifests
sop/                 post-install acceptance and real-rock workflow source
packages/            policy only; no archives tracked
docs/                architecture, compatibility, validation, and operations
scripts/             publication gates
tests/               bootstrap and publication regression tests
.github/workflows/   lightweight static CI
```

## Compatibility and troubleshooting

Read [compatibility](docs/compatibility.md) before selecting a host. For missing GNU Fortran linkage, CUDA visibility, archive identity, existing-stack mismatch, or RAW-contract failures, see [troubleshooting](docs/troubleshooting.md).

## Upstream LBPM

The pinned upstream is [OPM/LBPM](https://github.com/OPM/LBPM) release line v2026.04 at commit `6d686d354e5b8140841d3601e4c8c0e4e4b77e48`. The local patch targets `models/ColorModel.cpp` and corrects the `OutletLayersPhase == 1` assignment. Full attribution and redistribution notes are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License and citation

Repository-authored material is licensed under `GPL-3.0-only`; third-party components retain their own licenses. See [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and [CITATION.cff](CITATION.cff).

## Acknowledgements

This work relies on OPM/LBPM, Open MPI, zlib, HDF5, CUDA-capable systems, and the maintainers and contributors of those projects. Their inclusion here does not imply endorsement or official affiliation.
