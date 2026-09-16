# Runner changelog

## 1.0.1 — 2026-09-15

- F-01: central result validation at commit, startup recovery and export. A corrupt or missing endpoint is not marked valid; completion markers are moved to a quarantine evidence directory, not erased.
- F-02: apply the same MPS epoch trust gate to pending outcomes, existing completion markers, ordinary runtime completion and exported results. Outcomes at/after a recorded peer fault are quarantined and requeued as interruptions.
- Validate frozen input/protocol/case/attempt identity and outcome/commit hashes together. Cache verified file hashes only while filesystem identity and timestamps are unchanged; resume starts with a fresh cache.
- Add regression coverage for fault/corruption recovery and integration using this repository's actual SOP 1.3.2 scripts. MPI decomposition/GPU work remain CPU mocks in tests.
- Add deterministic source-only packaging and GitHub CI. Remove private historical bootstrap-run identifiers from the editable RiverMind preset.
- No changes to Ca, R1, solver source, geometry, archive policy, Installer or previous Bootstrap releases.

Validation boundary: engineering code candidate; NOT a real-GPU or scientific validation certificate.

## 1.0.0 — superseded

The previously supplied private ZIP had two reproducible result-recovery defects. Do not start new production with it. Keep it only for historical reproduction; use 1.0.1 for the repaired integration.
