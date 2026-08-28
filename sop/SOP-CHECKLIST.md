# LBPM post-install SOP v1.3.2 checklist

## A. Frozen installer prerequisite

- [ ] Installer version is 2.0.5-offline, 2.0.6-offline, or 2.0.7-offline (2.0.7 recommended; exact allowlist)
- [ ] `/root/LBPM-stack/LBPM_BUILD_MANIFEST.txt` exists
- [ ] LBPM commit is `6d686d354e5b8140841d3601e4c8c0e4e4b77e48`
- [ ] patchset is `outletlayersphase-fix-v1`
- [ ] SOP did not edit installer, Builder, LBPM source, or build output
- [ ] Linux extraction may yield `0644`; documented top-level scripts are invoked with `bash`

## B. Software acceptance

- [ ] stale `POSTINSTALL_PASS.txt` and acceptance report invalidated before checks
- [ ] installer/commit/patch identities PASS
- [ ] OutletLayersPhase semantic check PASS
- [ ] each `ldd` command exits zero and reports no `not found`
- [ ] GPU name, driver, compute capability and CUDA recorded
- [ ] MPI implementation/version/CUDA-aware status recorded
- [ ] LBPM executable paths and SHA256 recorded
- [ ] TestSetDevice report PASS
- [ ] Piston exit/GPU binding/timelog/numerical range/final RAW PASS
- [ ] `acceptance_report.json` has `schema_version=1`, `status=PASS`
- [ ] `POSTINSTALL_PASS.txt` published only after all checks PASS

## C. Immutable source RAW

- [ ] input is the final upstream-preprocessed scientific rock
- [ ] shape is exactly 128 x 128 x 128
- [ ] byte count is 2,097,152
- [ ] dtype is uint8 and labels are only 0=solid, 1=pore
- [ ] solid and pore labels differ
- [ ] source is outside the case directory
- [ ] resolved source does not collide with any preparation output
- [ ] source SHA256 before equals source SHA256 after preparation/decomposition
- [ ] case directory was empty; no prior scientific output was overwritten

## D. Connectivity and simulation domain

- [ ] 6-neighbor, +Z, z=0 to z=127 connectivity PASS
- [ ] connectivity is validation-only; no component was removed
- [ ] `connectivity_report.json:geometry_modified` is false
- [ ] `rock.raw` equals source RAW byte-for-byte
- [ ] `rock_geometry.raw` equals source RAW byte-for-byte
- [ ] inlet/outlet reservoirs exist only outside the 128³ ROI
- [ ] embedded simulation ROI equals source RAW byte-for-byte
- [ ] `case_manifest.json:simulation.roi_preserved` is true
- [ ] S_rg pore-space basis is `source_128_cube_roi`
- [ ] serial decomposition and ID.00000 byte-size check PASS
- [ ] `CASE_PREPARED.json` status is PREPARED

## E. READY state

- [ ] stale READY markers invalidated before preparation
- [ ] first representative rock uses `--first-case-smoke`
- [ ] first-case numerical smoke PASS, or later case explicitly records NOT_REQUIRED
- [ ] smoke checks timelog schema, finite values, tolerance and final `id_t2000.raw`
- [ ] source pore/solid invariants and media porosity PASS
- [ ] `READY_FOR_PARAMETERIZATION.json` has environment ACCEPTED
- [ ] case preparation is PASS
- [ ] smoke test is PASS or NOT_REQUIRED
- [ ] final status is READY

## F. Not frozen by this SOP

- [ ] production drive protocol / BC
- [ ] Ca, contact angle and affinity
- [ ] tauA/tauB, rhoA/rhoB, alpha/beta
- [ ] flux, din/dout and timestepMax
- [ ] production output/convergence criteria
- [ ] Runner, batch scheduling, retry or GPU scheduling
- [ ] production S_rg extractor
