# OPM/LBPM upstream and v1.3.2 boundary audit

Frozen upstream for the companion installer:

- Repository: `OPM/LBPM`
- Commit: `6d686d354e5b8140841d3601e4c8c0e4e4b77e48` (Release 2026.04 merge)
- Installer-owned patch: `0001-fix-OutletLayersPhase.patch`
- Patchset: `outletlayersphase-fix-v1`
- Patch SHA256: `fbce8ac8f101c5f5ff3764c4e6e71f98d5a478e54609f3d63864dbc8e7d1c2b8`

The patch corrects `models/ColorModel.cpp` so `OutletLayersPhase == 1` writes `outletA/outletB`, not `inletA/inletB`. SOP v1.3.2 verifies this source state and build provenance. It never patches, rebuilds, or edits LBPM. The v1.3.2 verifier accepts exactly `2.0.5-offline`, `2.0.6-offline`, and `2.0.7-offline`; v2.0.7 is recommended, while earlier SOP releases remain historical companions.

## Upstream issues that do not require new local patches

- Issue #81, volumetric core-flood flux, was fixed in commit `7394e7ff331c36b86ab1c1cd7677b8a05b82e7f2`; the frozen release contains that correction.
- Issue #85, SubPhase flow magnitude, was fixed by merged PR #92.
- Issue #86, pressure-drop parenthesis, was included in PR #92. External reservoir layers keep boundary-domain handling outside the scientific ROI.

No v1.3.0 change is made to `analysis/SubPhase.cpp`, `common/Domain.cpp`, CUDA collision kernels, Ca-to-flux code, convergence, or FlowAdaptor. A future source change requires its own audit, regression test, patch hash, and installer version.

## v1.3.0 frozen-rock audit decision

The v1.2.0 preparation path used the same audited 6-neighbor +Z connectivity definition but could convert non-spanning pore components to solid under the default `percolating` policy. It could also overwrite the source when a source path resolved to a preparation output.

v1.3.0 removes both behaviors from the production path:

```text
v1.2.0: connectivity analysis -> selected/percolating mask -> geometry mutation
v1.3.0: connectivity analysis -> report -> PASS or INPUT_ROCK_CONNECTIVITY_FAILED
```

The algorithmic definition remains unchanged: six face-sharing neighbors, inlet plane `z=0`, outlet plane `z=nz-1`. This is a responsibility change, not a new scientific connectivity definition.

The production input is fixed at 128³ uint8 with labels 0/1. Non-128 production input is rejected. The 256³ memory concern from the v1.2.0 audit is out of scope because 128³ is the formal support boundary.

## Domain-read path and ROI preservation

The production template continues to use `Domain.Filename = "rock_waterdrive.raw"` / `Domain::Decomp()`. `ID.00000` remains decomposition/QC evidence. Three inlet and three outlet reservoir layers may be added outside the source ROI, while the embedded 128³ byte range is automatically extracted and compared against the source RAW.

Artificial reservoir augmentation is simulation-domain construction, not scientific rock preprocessing. `case_manifest.json` therefore records `source_roi`, `simulation_roi`, `simulation_domain`, augmentation, and ROI offset separately.

## Local validation boundary

Windows tests can prove Python behavior, JSON/state contracts, file hashes, packaging, and Shell syntax. They cannot execute CUDA, NVIDIA GPU binding, Open MPI, TestSetDevice, or ColorModel. Local completion is therefore a code-freeze candidate only; production validation requires the real Linux NVIDIA GPU server sequence.
