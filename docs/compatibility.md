# Compatibility

## Frozen v1.0.3 profile

- Ubuntu-like Linux, x86_64, root execution;
- one visible NVIDIA GPU and installed CUDA toolkit with `nvcc`;
- GCC/G++, GNU Fortran, and a successful real `-lgfortran` link probe;
- CMake 3.24 or newer, Make, tar, unzip, patch, Perl, Python 3, and SHA256 tools;
- OpenMPI 4.1.8, zlib 1.3.2, parallel HDF5 1.14.6;
- OPM/LBPM commit `6d686d354e5b8140841d3601e4c8c0e4e4b77e48` plus patchset `outletlayersphase-fix-v1`;
- `MPI_RANKS=1`;
- one 128 x 128 x 128 uint8 RAW with `0=solid`, `1=pore`, +Z flow axis, and 1.0 micrometre voxels.

This is a bounded profile, not a promise that every Ubuntu, compiler, driver, CUDA, or GPU combination works.

## Repository source candidate

Repository HEAD is `1.0.4-dev` because it includes an installer path-safety change. It has static regression evidence only and is not a production-validated replacement for the frozen artifact.
