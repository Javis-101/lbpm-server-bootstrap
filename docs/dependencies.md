# Dependency Inventory

This source-level inventory is the current SBOM substitute. It does not claim to enumerate the host operating system or CUDA installation.

| Component | Version or identity | Role | Source integrity |
| --- | --- | --- | --- |
| LBPM Server Bootstrap | 1.0.3 validated release representation | orchestration and evidence | Git tag plus immutable Release asset SHA256 |
| OPM/LBPM | `6d686d354e5b8140841d3601e4c8c0e4e4b77e48` (v2026.04 line) | simulation engine | archive SHA256 recorded in `installer/sources/SHA256SUMS` |
| Local LBPM patch | `outletlayersphase-fix-v1` | `OutletLayersPhase` correction | `fbce8ac8f101c5f5ff3764c4e6e71f98d5a478e54609f3d63864dbc8e7d1c2b8` |
| Open MPI | 4.1.8 | CUDA-aware MPI | fixed SHA256 manifest |
| zlib | 1.3.2 | HDF5 compression dependency | fixed SHA256 manifest |
| HDF5 | 1.14.6 | parallel data I/O | fixed SHA256 manifest |
| Post-install SOP | 1.3.2 source snapshot | acceptance and real-rock smoke | source ledger in `sop/SHA256SUMS` |

License and attribution details are in `THIRD_PARTY_NOTICES.md`.
