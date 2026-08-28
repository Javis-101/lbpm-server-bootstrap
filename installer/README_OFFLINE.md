# LBPM portable offline installer v2.0.7

## Frozen software line

- OPM/LBPM upstream commit: `6d686d354e5b8140841d3601e4c8c0e4e4b77e48` (Release 2026.04 merge point)
- OpenMPI: `4.1.8`
- zlib: `1.3.2`
- HDF5: `1.14.6` (built as Parallel HDF5)
- One audited local LBPM patch: `patches/0001-fix-OutletLayersPhase.patch`

The upstream LBPM tarball remains byte-for-byte unchanged. The patch is applied only to the extracted working tree immediately before compiling LBPM.

## v2.0.7 changes

1. `bash setup.sh` invokes `install_lbpm_offline.sh` through Bash rather than
   depending on a POSIX executable bit that a Windows-generated ZIP may omit.
2. No upstream, dependency, patch, build, or smoke-test identity changed.

## v2.0.6 changes

1. Windows bundle generation writes `BUNDLE_MANIFEST.txt` with deterministic LF line endings.
2. Linux source verification accepts both LF and CRLF manifests without relaxing field values.
3. Every required manifest field is checked exactly; missing, duplicate, or incorrect fields fail closed.

## v2.0.5 changes

1. Fixes the confirmed `OutletLayersPhase` assignment bug via a recorded two-line patch.
2. Refuses to patch if the expected buggy/fixed code layout cannot be identified.
3. Makes LBPM build reuse depend on the patchset SHA, preventing an old unpatched v2.0.4 binary from being silently reused.
4. Replaces the broken Bubble smoke test with a complete Piston chain:
   `Piston.raw -> lbpm_serial_decomp -> ID.00000 -> lbpm_color_simulator`.
5. The Piston generator uses Perl and therefore does not add a NumPy dependency to the server baseline.
6. Writes `LBPM_BUILD_MANIFEST.txt` with GPU/CUDA/dependency/upstream/patch/test provenance.

## Build the portable ZIP on Windows

From the builder root, double-click/run `prepare_offline_bundle.bat`, or:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\prepare_offline_bundle.ps1
```

The output is:

```text
LBPM-portable-offline-installer.zip
```

## Install on a clean GPU server

```bash
unzip LBPM-portable-offline-installer.zip
cd LBPM-portable-offline-installer
bash verify_sources.sh
bash setup.sh
```

For root, the default install path is `/root/LBPM-stack`; otherwise it is `$HOME/LBPM-stack`.

Normal production setup should **not** use `--skip-tests`. The v2.0.5 smoke-test fix remains unchanged in v2.0.7.

## Expected post-install evidence

- `TestSetDevice`: PASS
- Piston.raw: `55296` bytes
- Piston `ID.00000`: `66248` bytes
- `lbpm_color_simulator`: exit 0 and reports GPU binding
- `/root/LBPM-stack/LBPM_BUILD_MANIFEST.txt` (for root installs)

## Scope of the local patch

Only `models/ColorModel.cpp` is locally changed, and only these two assignments:

```diff
- inletA = 1.0;
- inletB = 0.0;
+ outletA = 1.0;
+ outletB = 0.0;
```

No local changes are made to `SubPhase.cpp`, `Domain.cpp`, core-flooding flux computation, CUDA kernels, or the underlying color-gradient LBM numerical model.
