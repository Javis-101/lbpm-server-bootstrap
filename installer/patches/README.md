# LBPM local patch set

This bundle keeps the upstream LBPM archive unchanged and applies one local compatibility patch at install time.

- Upstream repository: `OPM/LBPM`
- Frozen upstream commit: `6d686d354e5b8140841d3601e4c8c0e4e4b77e48` (Release 2026.04 merge point)
- Local patch: `0001-fix-OutletLayersPhase.patch`

The patch changes only the `OutletLayersPhase == 1` assignment in `models/ColorModel.cpp`:

```diff
- inletA = 1.0;
- inletB = 0.0;
+ outletA = 1.0;
+ outletB = 0.0;
```

It does **not** alter the LBM collision kernel, CUDA implementation, core-flooding flux formula, SubPhase analysis, or Domain decomposition.

The installer first inspects the source. If the upstream source is already fixed, it skips patching and only verifies the corrected state. If neither the known buggy nor corrected form is found, installation stops instead of guessing.
