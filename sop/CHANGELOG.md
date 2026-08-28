# Changelog

## 1.3.2 — 2026-08-28

- Added exact compatibility with Portable Installer `2.0.7-offline` while retaining `2.0.5-offline` and `2.0.6-offline`.
- Made every SOP shell-to-shell invocation explicitly use `bash`, so Windows ZIP extraction with `0644` child scripts remains portable on Linux.
- Kept all v1.3.1 scientific RAW, connectivity, ROI-preservation, readiness, and numerical-sanity contracts unchanged.

Local release status: `CODE FREEZE CANDIDATE`; `REAL GPU RETEST NOT YET EXECUTED`.

## 1.3.1 — 2026-08-27

- Added exact compatibility with Builder/portable installer v2.0.6 while retaining the frozen v2.0.5 target; v2.0.6 is recommended.
- Made `manifest_get()` safe for both LF and CRLF build manifests by removing only a trailing carriage return before exact comparisons.
- Kept the v1.3.0 scientific RAW, connectivity, ROI-preservation, state-machine, and runtime-provenance contracts unchanged.
- Published this as a new controlled SOP tree; `LBPM-postinstall-SOP-v1.3.0` remains the historical v2.0.5 companion.

## 1.3.0 — 2026-08-27

- Fixed the production RAW contract at 128 x 128 x 128 uint8 with labels 0=solid and 1=pore.
- Changed connectivity from geometry preprocessing to a non-mutating 6-neighbor +Z validator.
- Removed production support for percolating-only/spanning-only geometry mutation; deprecated `--keep all` now means validate/preserve and `--keep percolating` fails.
- Added resolved-path collision checks and source SHA256 before/after enforcement.
- Preserved the source ROI byte-for-byte in `rock.raw`, `rock_geometry.raw`, and the embedded region of any augmented simulation domain.
- Added `connectivity_report.json`, restructured `case_manifest.json`, and fixed the future S_rg pore-space basis to the original 128³ ROI.
- Added `acceptance_report.json`, software/runtime provenance JSON, atomic state writes, and fail-closed `ldd` command handling.
- Invalidated stale PASS/READY state before each run and separated PREPARED, smoke PASS/NOT_REQUIRED, and READY.
- Added safe case-ID validation and fail-closed handling of non-empty case directories without recursive deletion.
- Strengthened Piston and first-case numerical sanity checks for GPU binding, timelog schema, finite values, saturation tolerance, expected timestep, and final RAW.
- Documented Piston as an upstream-derived lightweight smoke/sanity test, not an official full benchmark.

## 1.2.0 — 2026-08-15

- Audited Builder v2.0.5 / SOP v1.1.0 against OPM/LBPM Release 2026.04 (`6d686d354e5b8140841d3601e4c8c0e4e4b77e48`).
- Kept the external 3+core+3 geometry to protect the original rock ROI from external-boundary reservoir treatment.
- Changed the production handoff from `ID.00000` / `Domain::ReadIDs()` to `rock_waterdrive.raw` / `Domain.Filename` / `Domain::Decomp()`.
- Kept `ID.00000` as decomposition/QC evidence only.
- Added explicit `InletLayers`, `OutletLayers`, `InletLayersPhase=2`, and `OutletLayersPhase=1` to the production template.
- Made the artificial inlet reservoir water label `2` and outlet reservoir gas label `1`.
- Added explicit `voxel_length_um` input/manifest/template handling; default remains 1.0 micron.
- Added `phi_selected` to the case manifest and a fail-closed LBPM-log porosity consistency checker.
- Updated the first-rock engineering smoke to use the production `Filename` read path and require the porosity consistency gate.
- Removed the misleading production `endpoint_threshold` placeholder; convergence/early-stop policy remains outside this SOP.

## 1.1.0 — 2026-08-12

- Changed responsibility boundary: post-install SOP is now **validation-only** for LBPM source/build.
- Removed all automatic source patching and LBPM rebuild behavior from the SOP.
- Requires and verifies `LBPM_BUILD_MANIFEST.txt` produced by offline installer v2.0.5.
- Pins expected LBPM upstream commit and the single audited OutletLayersPhase patch SHA256.
- Fails closed if `OutletLayersPhase` is still buggy or source layout is unknown.
- Independently re-runs `TestSetDevice` and the complete Piston chain without modifying LBPM.
- Retains digital-rock QC, Z-percolation, 3+128+3 reservoir construction, serial decomposition, case manifest, and first-rock engineering smoke.
- Adds `UPSTREAM-AUDIT.md` documenting which historical LBPM issues are already fixed upstream.
