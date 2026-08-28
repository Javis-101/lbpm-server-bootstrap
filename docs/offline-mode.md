# Offline Mode

The Portable Installer verifies four pinned source archives before build: OpenMPI 4.1.8, zlib 1.3.2, HDF5 1.14.6, and OPM/LBPM at commit `6d686d354e5b8140841d3601e4c8c0e4e4b77e48`. It also verifies the local patch hash.

The source checkout keeps `installer/sources/BUNDLE_MANIFEST.txt`, `installer/sources/SHA256SUMS`, download/assembly scripts, and the patch, but excludes the tarballs themselves. Operators building an offline payload must obtain the exact archives from their official upstream locations and verify every recorded SHA256 before packaging.

Network fallback is opt-in and is allowed only for the pinned URLs. It must not silently substitute a newer version or accept a filename without a matching checksum. Complete offline bundles belong in GitHub Release assets, never Git history.
