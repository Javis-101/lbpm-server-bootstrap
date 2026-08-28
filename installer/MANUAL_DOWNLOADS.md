# Manual source download list — v2.0.7

Place these four files in `sources/` without renaming them, then run the builder with `-NoDownload` (PowerShell) or `--no-download` (Linux/macOS):

1. `openmpi-4.1.8.tar.gz`
2. `zlib-1.3.2.tar.gz`
3. `hdf5-1.14.6.tar.gz`
4. `LBPM-6d686d354e5b8140841d3601e4c8c0e4e4b77e48.tar.gz`

The builder verifies fixed SHA256 values for OpenMPI/zlib/HDF5, records the actual SHA256 of the frozen LBPM commit archive, and always verifies the bundled local patch before packaging.

The local patch is already included under `patches/`; do not download or edit it manually.
