# Architecture

The bootstrap is an orchestration layer over two separately bounded components: the Portable Installer builds or exactly reuses the pinned dependency/LBPM stack, and the SOP verifies the installed runtime and prepares one immutable real-rock case.

The outer stages are package integrity, host preflight, source verification, install/reuse, environment identity, SOP deployment, SOP acceptance, RAW/first-rock smoke, and evidence finalization. A failed stage stops dependent work but still attempts a bounded failure summary and evidence archive.

Repository source and release payload have different roles. Git stores scripts, manifests, hashes, patches, tests, policies, and sanitized documentation. Large third-party source archives and complete offline bundles are release assets only. The frozen v1.0.3 artifact is outside Git and remains immutable.

The evidence boundary excludes source/final RAW, intermediate simulation RAW, Restart/HDF5/build trees, credentials, and unredacted host identity. `READY_FOR_PARAMETERIZATION` is an engineering state, not a physical-model certification.
