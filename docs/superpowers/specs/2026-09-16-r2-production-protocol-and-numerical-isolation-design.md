# R2 Production Protocol and Numerical-Failure Isolation Design

## Goal

Create the next LBPM production protocol for the 1200-case RiverMind dataset and update the Production Runner so an isolated numerical failure does not automatically quarantine every healthy MPS peer when the failed CUDA client can be safely contained.

## Frozen protocol identity

Protocol name: `GW-Ca1p5e4-R2-v1`.

Physics and domain:

- `capillary_number = 0.00015`
- `rhoA = rhoB = 0.10`
- `tauA = 0.78`
- `tauB = 0.92`
- `alpha = 0.009`
- `beta = 0.90`
- `affinity = 0.2588190451`
- `wetting_convention = "SCAL"`
- nominal water contact angle = 75 deg
- `128 x 128 x 128` ROI, 3 inlet + 3 outlet reservoir layers
- `BC = 4`, flow along +Z
- MPS production concurrency remains 8

Stopping grid:

- `check_pvi = 0.1`
- `window_points = 5`
- `max_pvi = 3.6`

STANDARD:

- `start_pvi = 0.5`
- `max_dsg = 0.0030`
- `range_sg = 0.0060`
- `max_flip = 0.0100`
- `consecutive = 4`

ACCEPTED remains unchanged:

- `start_pvi = 3.0`
- `max_dsg = 0.008`
- `range_sg = 0.025`
- `max_flip = 0.030`
- `consecutive = 3`

Expected time grid from the current Runner formula is `CHECKPOINT_STEPS=22124`, `MAX_STEPS=796464`.

## Scientific boundary

Changing Ca from `2e-4` to `1.5e-4` creates a new physical protocol identity. Results from the previous `GW-Ca2e4-R1F125-v1` production root must not be migrated into the new dataset. The previous root remains historical evidence only.

`STANDARD`, `ACCEPTED`, and `CAP_REACHED` are protocol-defined endpoints. They are not assertions of infinite-time equilibrium.

A numerical failure is never a valid scientific label. No last-good checkpoint from a failed case may be promoted to a successful endpoint merely to salvage the case.

## Numerical-failure isolation

The existing Runner treats a detected `NUMERICAL_FAILED` as an epoch-wide fault immediately. That behavior produced peer `MPS_PEER_ABORT_QUARANTINE` interruptions even when the original failure was case-local.

The new policy is fail-safe isolation:

1. A worker detecting an LBPM numerical failure first attempts a targeted MPS termination of its own positively identified client token.
2. If targeted termination succeeds and reports `safe_context_termination=true`, the worker records `NUMERICAL_FAILED` for that case only. It does **not** create the shared epoch `fault.json` marker. Healthy MPS peers continue and the supervisor may refill the free slot.
3. If safe targeted termination cannot be established, the worker preserves the existing epoch-wide fault path. Peers drain/quarantine exactly as before.
4. Infrastructure failures, worker exceptions with ambiguous live CUDA state, and MPS/GPU shared failures continue to use the existing conservative epoch recovery path.
5. `NUMERICAL_FAILED` remains terminal and invalid for export.

The implementation must not weaken the existing protection against duplicate CUDA clients or unsafe host-side signals.

## Runner versioning and compatibility

This behavior changes failure-handling semantics, so the Production Runner version advances from `1.0.1` to `1.1.0`.

Existing protocol files and old output roots remain immutable and reproducible. The new protocol is added as a new preset rather than replacing `protocol.toml` or `protocol-r1f125.toml`.

## Deployment

The server deployment uses a new source directory and a new output root. Recommended paths:

- Runner source: `/root/rivermind-data/lbpm-runner-src-v1.1.0`
- Protocol: `/root/rivermind-data/lbpm-production-protocols/GW-Ca1p5e4-R2-v1.toml`
- Production root: `/root/rivermind-data/lbpm-production-data-ca1p5e4-r2-v1`

The old `lbpm-runner-src-v1.0.1` and `lbpm-production-data-r1f125-v1` remain untouched.

## Acceptance criteria

- Protocol validation produces `CHECKPOINT_STEPS=22124` and `MAX_STEPS=796464`.
- Earliest possible STANDARD stop is 0.8 PVI (four consecutive passes beginning at 0.5 PVI).
- ACCEPTED logic is unchanged.
- A safely isolated numerical failure does not create an epoch-wide fault and does not interrupt healthy peers.
- An unsafe/unconfirmed numerical failure still creates an epoch-wide fault and preserves peer quarantine behavior.
- A numerical failure can never produce `result.json`, `complete.json`, or a valid export row.
- Existing Runner engineering tests remain green on Python 3.9 and 3.12.
- Package verification and reproducible ZIP verification remain green.
