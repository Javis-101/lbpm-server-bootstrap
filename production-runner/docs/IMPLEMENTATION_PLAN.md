# LBPM Production Runner — Implementation Plan

Goal: deliver a relocatable offline-first Linux production controller for the approved 1200-input LBPM protocol, without modifying or rebuilding LBPM.

Architecture: one SQLite-writing supervisor, detached per-attempt workers, immutable input/protocol manifests, relative run paths, recoverable result commits, and an independent verified lossless archiver. Workers never read a shared queue through stdin. A dedicated same-namespace Legacy MPS v2 service provides safe early termination; unsupported capabilities block dispatch, not silently downgrade.

Tech stack: Python >=3.9, NumPy supplied by the established LBPM/SOP environment, vendored MIT tomli 2.2.1 for Python <3.11, system libzstd via ctypes, Bash, OpenMPI, NVIDIA MPS. No network installation or LBPM source modifications.

## Approved constraints
- Ca=2e-4, rhoA/B=.1/.1, tauA/B=.78/.92, alpha=.009, beta=.90, SCAL affinity +0.2588190451, BC4, 128³ ROI with 3+3 z reservoirs.
- R1 five-checkpoint windows: STANDARD start1.2, adjacent .0005/range .001/flip .001, count4; ACCEPTED start3, adjacent .008/range .025/flip .03, count3. Nominal check .1, cap4. Integer-even time grid is recorded.
- Every generated checkpoint is retained, including post-decision overshoot and interrupted/failed attempts. Archive only after writers exit and inventory is frozen. SHA256 verification precedes release of identical raw copies. Raw inputs and historical experiments are never deleted.
- Paths: CLI > prefixed environment > TOML > unique scoped discovery. Scientific protocol is independently frozen; path migration is explicit and audited.
- Interruption recovery is task-level, not native LBPM restart. No promise of 1200 successful labels or GPU-verified reliability before server evidence.

## Work packages / verification
1. Configuration, identity, and protocol: unit tests for precedence, unknown keys, relative paths, immutable protocol, nearest-even .1PVI=16592 and 40 outputs=663680. Generate deterministic family-interleaved queue with file hashes.
2. Atomic storage and outcome states: test transactional index, process identity including boot/start ticks, duplicate lock refusal, restart replay and no overwrite of submitted result.
3. Frame reader and R1: test label/ROI validation, missing and partial output rejection, exact window logic, minimum STANDARD1.5 and ACCEPTED3.2, cap classification and constant-label correlation edge cases.
4. Lossless archive: actual libzstd round-trip, tar inventory and hash comparison, truncated/corrupt stream refusal, no deletion on failed verification, interrupted cleanup recovery, safe restore names, watermarks and reserve handling.
5. MPS and worker: fixture control daemon protocol, PID/cwd/token match, command-response0 required before any signal, timeout refusal, close-write events, source geometry preserved, intentional stop versus NaN outcomes.
6. Supervisor/CLI: mocked LBPM subprocess integration exercises full lifecycle, dynamic replenishment, crash/recovery, pause drain, earlystop and final postprocess, reports and diagnostics. Real GPU behavior explicitly remains unvalidated.
7. Packaging: run all tests, compile all modules, bash syntax check, ZIP extraction selftest, checksums, Chinese quickstart/config/recovery/output docs. No source/experimental RAW or private logs shipped.
