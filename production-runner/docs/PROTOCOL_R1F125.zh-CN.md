# GW-Ca2e4-R1F125-v1 protocol note

This document records the production protocol preset selected on 2026-09-16 for the RiverMind OPM/LBPM dataset workflow.

## Scope

The new preset is:

```text
GW-Ca2e4-R1F125-v1
```

It is derived from `GW-Ca2e4-R1-v1` and changes only the STANDARD field-flip tolerance:

```text
max_flip = 0.0010   ->   0.00125
             0.100% ->   0.125%
```

All physical parameters and all other stopping-rule parameters remain unchanged.

## Frozen scientific parameters

```text
Ca = 2.0e-4
rhoA = 0.10
rhoB = 0.10
tauA = 0.78
tauB = 0.92
alpha = 0.009
beta = 0.90
SCAL affinity = +0.2588190451
nominal water contact angle = 75 deg
BC = 4
flow = +Z
voxel length = 1 um
reservoir = 3 inlet + 3 outlet
```

Stopping grid:

```text
checkpoint = 0.1 PVI
window_points = 5
MAX_PVI = 4.0
```

STANDARD:

```text
start_pvi   = 1.2
max_dsg     = 0.0005
range_sg    = 0.0010
max_flip    = 0.00125
consecutive = 4
```

ACCEPTED remains unchanged:

```text
start_pvi   = 3.0
max_dsg     = 0.008
range_sg    = 0.025
max_flip    = 0.030
consecutive = 3
```

## Offline evidence used for the change

### Current production-matched Canary: 41_199, Ca=2.0e-4

The first formal RiverMind case (`41_199`) completed under the previous R1 rule at 3.2 PVI with:

```text
stop reason = ACCEPTED
Sg endpoint = 20.7612624724%
```

Offline replay of its retained checkpoints with `max_flip=0.00125` gives:

```text
hypothetical stop = STANDARD @ 2.9 PVI
actual wall-time saving relative to the recorded 3.2 PVI endpoint = 9.38%
|Delta Sg| vs 3.2 PVI = 0.027633 percentage points
pore-space field disagreement vs 3.2 PVI = 0.101571%
gas Jaccard vs 3.2 PVI = 0.995123
```

The 41_199 trajectory also showed that `0.125%` produces the same 2.9 PVI endpoint as `0.103%`, `0.105%`, `0.110%`, and `0.150%`; therefore 0.125% was selected as the next evidence-supported breakpoint while avoiding unnecessary relaxation beyond that level.

### Historical blind24 stress set: Ca=2.5e-4

These trajectories use a different capillary number and are therefore stress-test evidence only, not direct validation of the current Ca=2.0e-4 production protocol.

For the 18 complete PASS trajectories:

```text
STANDARD max_flip     0.100%      0.125%
mean stop PVI         2.894       2.750
STD / ACCEPTED stops  6 / 12      8 / 10
mean |Delta Sg|       0.4490 pp   0.4830 pp
mean field difference 0.991%      1.047%
max |Delta Sg|        1.5497 pp   1.5497 pp
max field difference  4.379%      4.379%
mean gas Jaccard      0.9460      0.9423
```

For the 6 historical numerical-failure trajectories, the relaxed rule did not add any new case that would stop before the known failure. The only such trajectory remained `49_016`, which reached the unchanged ACCEPTED rule at 3.2 PVI under both the old and new STANDARD thresholds.

## Interpretation boundary

The endpoint is a protocol-defined endpoint. It is not a claim of infinite-time or thermodynamic equilibrium.

The purpose of the relaxed STANDARD threshold is to reduce unnecessary late-stage computation while preserving a single, reproducible endpoint definition for dataset generation.

## Production identity and output-root rule

Do not mutate an already prepared production root to use this protocol.

The Runner intentionally rejects a protocol mismatch against an existing frozen manifest. Use a new output root and explicitly select this preset, for example:

```bash
bash run.sh prepare \
  --config config/rivermind.toml \
  --protocol config/protocol-r1f125.toml \
  --output-root /root/rivermind-data/lbpm-production-data-r1f125-v1
```

Then perform a single-case real GPU Canary before switching the same new production identity to MPS-8.

The previous `GW-Ca2e4-R1-v1` production root and its `41_199` result must remain untouched as historical evidence.
