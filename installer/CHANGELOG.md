# Changelog

## 2.0.7

- Make `bash setup.sh` independent of the extracted executable bit on
  `install_lbpm_offline.sh` by invoking the child explicitly through Bash.
- Preserve the v2.0.6 deterministic-LF producer and LF/CRLF consumer contract.
- Keep all frozen upstream, dependency, and local-patch identities unchanged.

## 2.0.6

- Fix Windows-generated `BUNDLE_MANIFEST.txt` using CRLF line endings.
- Write the manifest deterministically as ASCII with LF line endings.
- Accept both LF and CRLF manifests on Linux by stripping only a trailing carriage return.
- Keep semantic verification strict for every required manifest field.

## 2.0.5

- Keep upstream OPM/LBPM commit `6d686d354e5b8140841d3601e4c8c0e4e4b77e48` unchanged.
- Add audited local `OutletLayersPhase` patch and SHA256 tracking.
- Add strict patch state detection: buggy / already fixed / unknown.
- Include patchset in LBPM binary reuse criteria.
- Replace direct Bubble simulator smoke with a full Piston decomposition + ColorModel GPU smoke test.
- Generate Piston.raw without NumPy dependency.
- Add `LBPM_BUILD_MANIFEST.txt` and test provenance.
- Keep v2.0.4 CRLF-safe `SHA256SUMS` parsing.

## 2.0.4

- Canonicalize extracted LBPM source to `src/LBPM`.
- Fix Windows-generated CRLF checksum parsing.
- Improve portable offline bundle behavior.
