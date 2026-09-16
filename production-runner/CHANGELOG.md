# Runner changelog

## 1.1.0 — 2026-09-16

- Add the new `GW-Ca1p5e4-R2-v1` production protocol preset: `Ca=1.5e-4`, aggressive STANDARD (`start=0.5 PVI`, `max_dsg=0.0030`, `range_sg=0.0060`, `max_flip=0.0100`, 4 confirmations), unchanged ACCEPTED, and `max_pvi=3.6`.
- The new protocol produces `CHECKPOINT_STEPS=22124` and `MAX_STEPS=796464` under the frozen Runner time-grid formula. It is a new protocol identity; `Ca=2e-4` results are historical evidence and must not be migrated into the new formal dataset.
- Add fail-safe numerical-failure isolation. When a numerical failure is detected while its MPS client is still uniquely identifiable, Runner attempts targeted MPS v2 termination. A case is isolated without poisoning its epoch only after explicit `safe_context_termination=true`.
- Preserve the old conservative epoch-fault/quarantine path whenever targeted containment cannot be confirmed. Numerical failures remain invalid scientific labels and cannot publish a completion marker.
- Add CPU integration coverage for both safely isolated numerical failures and the conservative fallback path. Real NVIDIA MPS and LBPM physics still require target-GPU Canary validation.

Validation boundary: engineering code candidate; NOT a real-GPU or scientific validation certificate.

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
