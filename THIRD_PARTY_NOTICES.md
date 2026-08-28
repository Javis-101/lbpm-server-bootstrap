# Third-Party Notices

LBPM Server Bootstrap is an independent community project. It is not an official OPM project, and the upstream projects listed below do not endorse this repository.

Large upstream source archives are intentionally excluded from Git. When an offline release asset redistributes them, their original license and notice files must remain present in the archives.

## OPM/LBPM

- **Project:** OPM/LBPM
- **Version:** v2026.04 release line, commit `6d686d354e5b8140841d3601e4c8c0e4e4b77e48`
- **Upstream:** https://github.com/OPM/LBPM
- **License:** GNU General Public License version 3 (the pinned archive contains the GPL v3 license text)
- **Attribution:** Copyright remains with the OPM/LBPM authors and contributors; see the upstream source headers and history.
- **Role:** GPU lattice-Boltzmann simulation engine built and validated by this workflow.
- **Modifications:** This repository includes patch `installer/patches/0001-fix-OutletLayersPhase.patch`, targeting the pinned commit and correcting the `OutletLayersPhase == 1` assignments in `models/ColorModel.cpp`.
- **Redistribution:** Preserve upstream copyright and license notices, provide the corresponding source as required by GPL v3, and mark modified source versions.

OPM/LBPM is an upstream third-party project. LBPM Server Bootstrap is an independent community project. This repository is not an official OPM project.

## Open MPI

- **Project:** Open MPI
- **Version:** 4.1.8
- **Upstream:** https://www.open-mpi.org/ and https://github.com/open-mpi/ompi
- **License:** Open MPI BSD-style license; bundled subcomponents may carry additional compatible notices.
- **Attribution:** Copyright belongs to the universities, laboratories, companies, and contributors listed in Open MPI's `LICENSE` and source files.
- **Role:** MPI runtime built with CUDA support for the pinned stack.
- **Redistribution:** Retain the copyright notice, conditions, disclaimer, and bundled subcomponent notices.

## zlib

- **Project:** zlib
- **Version:** 1.3.2
- **Upstream:** https://zlib.net/ and https://github.com/madler/zlib
- **License:** zlib License
- **Attribution:** Copyright (C) 1995-2026 Jean-loup Gailly and Mark Adler, as stated in the pinned archive.
- **Role:** Compression dependency used when building parallel HDF5.
- **Redistribution:** Do not misrepresent origin, plainly mark altered source versions, and retain the zlib notice.

## HDF5

- **Project:** HDF5
- **Version:** 1.14.6
- **Upstream:** https://www.hdfgroup.org/solutions/hdf5/ and https://github.com/HDFGroup/hdf5
- **License:** HDF5 license (BSD-style terms plus component-specific notices)
- **Attribution:** Copyright 2006 by The HDF Group and copyright 1998-2006 by the Board of Trustees of the University of Illinois, with additional contributors and component notices listed in the pinned archive.
- **Role:** Parallel HDF5 dependency for the LBPM build.
- **Redistribution:** Retain `COPYING`, `COPYING_LBNL_HDF5`, disclaimers, and all applicable bundled component notices.

## CUDA and host toolchain

NVIDIA CUDA, system compilers, CMake, Make, Perl, and other host tools are prerequisites and are not redistributed by this repository. Their installation and licensing remain the operator's responsibility.
