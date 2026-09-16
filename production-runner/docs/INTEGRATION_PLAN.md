# Runner 1.0.1 integration plan

Goal: repair F-01/F-02, integrate the external Runner with the existing pinned Installer/SOP, and publish reviewable source with a reproducible download path.

Base repository: Javis-101/lbpm-server-bootstrap @ 8acdb62a9768911250474003597f595b785ac266.
Original artifact: SHA256 4ca81be2706deb4f4db2e6aec175b97278df386e8f85d127557014a2fd706075.

Constraints: do not change Ca, R1, output labels, compression thresholds, solver physics, installer or old releases. Do not claim physical GPU validation from CPU tests. No credentials, RAW research data, private run identifiers or remote GPU operations in this change.

1. Reproduce both review regressions on the exact v1.0.0 package; retain failing evidence.
2. Centralize result eligibility: frozen input/protocol/attempt identity, outcome hash, required output hashes, completion-marker identity, MPS epoch timing. Use the same checks at normal commit, restart reconciliation, and export. Preserve rejected markers as evidence, never export known-bad results as valid.
3. Add direct commit/export/corrupt marker/unknown epoch regressions and reproduce failures before changes. Add subprocess resume regressions for both a pending outcome and an existing completion marker in a faulted epoch.
4. Exercise the actual repository SOP scripts via a private environment adapter, with only MPI/decomposition mocked on CPU; test immutable source, phase reservoirs, prepared reuse and unchanged installed SOP config. Check installer environment/manifest names and pinned patch contracts.
5. Preserve root Bootstrap entry points; add a production-runner subdirectory, documented handoff, reproducible packager, separate CI test/build workflow, and generic user-editable machine configuration.
6. Run all engineering tests, the two original review reproducers, package verification and extraction checks. Inspect data-deletion and MPS shutdown paths. State real GPU evidence as NOT_PERFORMED.
7. Publish source on runner-v1.0.1-integration, open a PR, read back GitHub content/commit and CI state. Never overwrite Bootstrap v1.0.3. Provide a pinned GitHub download path.
