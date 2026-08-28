# Evidence Contract

## Purpose

The evidence snapshot records enough identity, decision, machine-report, and bounded log information to audit one Bootstrap execution. It is generated on both PASS and FAIL. Missing upstream outputs are marked `NOT_PRODUCED`; they are never fabricated.

## Included when available

```text
evidence/
├── summary.json
├── summary.txt
├── summary.md
├── evidence_inventory.json
├── EVIDENCE_SHA256SUMS
├── host/
│   ├── host-info.txt
│   ├── gpu-info.txt
│   ├── cuda-info.txt
│   ├── compiler-info.txt
│   ├── prerequisites.json
│   ├── disk-info.txt
│   └── lbpm-runtime-identity.txt
├── installer/
│   ├── BUNDLE_MANIFEST.txt
│   ├── LBPM_BUILD_MANIFEST.txt
│   └── verify-sources.log
├── acceptance/
│   ├── acceptance_report.json
│   ├── software-verification.json
│   ├── TestSetDevice.PASS.json
│   └── piston_result.json
├── first-rock/
│   ├── raw.sha256.json
│   ├── raw.sha256
│   ├── READY_FOR_PARAMETERIZATION.json
│   ├── connectivity_report.json
│   ├── case_manifest.json
│   ├── smoke.PASS.json
│   └── final-raw-metadata.json
└── logs/
    └── bounded stage logs
```

`host/prerequisites.json` records the resolved gfortran path, the first
`gfortran --version` line, and the authoritative real `-lgfortran` link-probe
status. Failed preflight runs retain the available prerequisite evidence; no
successful link status is inferred from package metadata or `ldconfig`.

`final-raw-metadata.json` contains only filename, byte size, and SHA256. The final smoke RAW itself is not copied.

## Explicit exclusions

The snapshot never recursively copies:

- the source RAW;
- the installed stack or build tree;
- `Restart.*` files;
- HDF5 output;
- intermediate or final `id_t*.raw` data;
- the full simulation directory;
- source caches or duplicate dependency archives beyond the small identity manifest.

## Integrity and archive

`EVIDENCE_SHA256SUMS` covers every evidence file except itself. The final archive is written to:

```text
<run-root>/artifacts/LBPM-validation-evidence-<run-id>.tar.gz
```

Its external sidecar `<archive>.sha256` is authoritative. An archive cannot contain its own final hash without creating a circular dependency, so the summary inside the archive records the sidecar contract; the final summaries retained in the run root and terminal print the actual archive SHA256.

## Interpretation boundary

A PASS means the pinned infrastructure, SOP acceptance, RAW data contract, and first-rock numerical sanity completed for that run. It does not mean production physical validation, production parameter selection, batch Runner validation, or S_rg production validation.
