# Troubleshooting

## GNU Fortran or `-lgfortran` failure

The v1.0.2 Tesla T4 record failed at link time because the host lacked a usable GNU Fortran development/runtime link target. Install or repair the host toolchain manually, then confirm both `gfortran --version` and a real `g++ ... -lgfortran` link probe. The bootstrap does not modify APT sources or install packages.

## Invalid installer prefix

Repository HEAD rejects empty, `/`, relative, and dot-segment prefixes before creating the install layout. Use a dedicated absolute directory such as `/opt/lbpm-stack` or `/data/lbpm/LBPM-stack`.

## Package or source identity failure

Do not rename or replace an archive to satisfy a filename check. Compare the actual SHA256 with the recorded manifest and reacquire the exact pinned source when it differs.

## Existing stack mismatch

The workflow reuses only an exact compatible manifest. Preserve a mismatched stack for investigation and choose a fresh dedicated install root; do not overwrite or delete it automatically.

## RAW contract failure

Verify dimensions, byte count, uint8 labels, flow-axis convention, and source provenance. Connectivity failure is a rejection, not permission to alter the rock. Do not crop, relabel, filter, or repair the input inside this workflow.

## GPU or CUDA failure

Check `nvidia-smi`, `nvcc --version`, visible device count, compute capability, and CUDA compiler support for the target architecture. GitHub-hosted CI cannot diagnose real GPU binding.
