# R2 Production Protocol and Numerical-Failure Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the frozen `GW-Ca1p5e4-R2-v1` protocol and upgrade the Runner so a confirmed, safely contained case-local numerical failure does not automatically quarantine healthy MPS peers.

**Architecture:** Preserve the existing fail-safe epoch recovery as the fallback. Change only the worker numerical-failure path: attempt targeted `MPS.terminate()` for the failed client; when that returns `safe_context_termination=true`, classify only that attempt as `NUMERICAL_FAILED` and avoid publishing the shared epoch fault. If containment is unavailable or unconfirmed, publish the existing epoch fault and retain peer quarantine. Add the new protocol as a separate immutable preset and bump the Runner to 1.1.0.

**Tech Stack:** Python 3.9/3.12, `unittest`, TOML protocol presets, NVIDIA MPS v2 control contract, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-16-r2-production-protocol-and-numerical-isolation-design.md`

## Global Constraints

- Protocol name is exactly `GW-Ca1p5e4-R2-v1`.
- `Ca=0.00015`; rho/tau/alpha/beta/affinity/BC/domain remain frozen as specified in the design.
- STANDARD is `start=0.5`, `max_dsg=0.0030`, `range_sg=0.0060`, `max_flip=0.0100`, `consecutive=4`.
- ACCEPTED remains `start=3.0`, `0.008`, `0.025`, `0.030`, `consecutive=3`.
- `check_pvi=0.1`, `window_points=5`, `max_pvi=3.6`.
- MPS production target remains 8 concurrent jobs.
- A numerical failure never becomes a valid scientific label.
- Safe single-case isolation is used only after positively confirmed `safe_context_termination=true`; otherwise retain epoch-wide fail-safe quarantine.
- Existing protocol presets and old production roots are not modified in place.

---

### Task 1: Add R2 protocol contract with failing tests first

**Files:**
- Create: `production-runner/config/protocol-ca1p5e4-r2.toml`
- Create: `production-runner/tests/test_r2_protocol.py`

**Interfaces:**
- Consumes: `runner.config.load_protocol(path)`, `runner.protocol.time_grid(p)`, `runner.protocol.replay(rows,p)`.
- Produces: a protocol preset whose time grid is `checkpoint_steps=22124`, `max_steps=796464`, and whose earliest all-stable STANDARD decision is index 8 / 0.8 PVI.

- [ ] **Step 1: Write failing tests** asserting exact frozen physics/stopping values, time-grid values, earliest STANDARD at checkpoint 8, unchanged ACCEPTED values, and CAP at checkpoint 36 for deliberately nonconvergent rows.
- [ ] **Step 2: Push tests only and verify GitHub Actions fails because `config/protocol-ca1p5e4-r2.toml` is missing.**
- [ ] **Step 3: Add the exact TOML preset.**
- [ ] **Step 4: Verify protocol tests pass.**

### Task 2: Implement safe numerical-failure isolation with TDD

**Files:**
- Modify: `production-runner/tests/test_integration.py`
- Modify: `production-runner/tests/fixtures/mock_tools.py`
- Modify: `production-runner/runner/worker.py`

**Interfaces:**
- Consumes: `MPS.terminate(token, run_dir, binary) -> dict` with `safe_context_termination` on confirmed targeted termination; existing `first_fault(epoch/fault.json, ...)` fallback.
- Produces: safely-contained case-local `NUMERICAL_FAILED` without epoch fault; unsafe/unconfirmed numerical failure retains epoch fault and peer recovery.

- [ ] **Step 1: Extend the CPU MPS fixture so a numerical case can remain registered long enough for targeted `terminate_client`, and so the fixture records targeted termination calls.**
- [ ] **Step 2: Add an integration test with one `nan` case and stable peers. Assert one `NUMERICAL_FAILED`, three valid peers, no peer `INTERRUPTED`, no epoch `fault.json`, and at least one `terminate_client` call.**
- [ ] **Step 3: Add an integration test where the fixture rejects targeted termination. Assert the original conservative recovery behavior remains active and no failed case is committed as a valid label.**
- [ ] **Step 4: Push tests/fixture only and verify the new safe-isolation test fails against old worker behavior.**
- [ ] **Step 5: Modify `worker.py` minimally: on detecting `NUMERIC`, attempt targeted termination before setting the epoch fault; only suppress the epoch fault when the returned record explicitly confirms safe context termination. On containment failure, set the epoch fault exactly as the old code did.**
- [ ] **Step 6: Verify both new tests and all existing integration tests pass.**

### Task 3: Version, package identity, docs, and CI

**Files:**
- Modify: `production-runner/VERSION`
- Modify: `production-runner/runner/__init__.py`
- Modify: `production-runner/PACKAGE_FILES.json`
- Modify: `.github/workflows/production-runner.yml`
- Create: `production-runner/docs/PROTOCOL_CA1P5E4_R2.zh-CN.md`
- Modify: `production-runner/CHANGELOG.md`

**Interfaces:**
- Produces: Runner version `1.1.0`, deterministic package verification for all changed code, artifact name `LBPM-Production-Runner-v1.1.0`, and an operator-facing protocol/failure-isolation note.

- [ ] **Step 1: Bump `VERSION` and `runner.__version__` to `1.1.0`; update artifact label in the workflow.**
- [ ] **Step 2: Add protocol documentation covering scientific identity, new time grid, old-root non-migration, MPS-8 target, and safe/fallback numerical-failure semantics.**
- [ ] **Step 3: Add changelog entry.**
- [ ] **Step 4: Recompute `PACKAGE_FILES.json` hashes for every inventoried file changed by this release.**
- [ ] **Step 5: Run/observe GitHub Actions on Python 3.9 and 3.12; require all Runner tests, package verification, ZIP build, extracted ZIP verification, and static publication gates to be green.**
- [ ] **Step 6: Open/update the integration PR only after CI is green; do not merge automatically.**

## Verification checklist

- [ ] New branch is isolated from the old `runner-v1.0.1-integration` branch.
- [ ] Old `protocol.toml` and `protocol-r1f125.toml` remain byte-identical.
- [ ] R2 protocol time grid equals 22124 / 796464.
- [ ] STANDARD earliest decision is 0.8 PVI.
- [ ] Safe numerical failure does not publish shared epoch fault.
- [ ] Rejected/unsafe targeted termination retains shared epoch fault/recovery.
- [ ] Failed case has no `complete.json` and no valid export label.
- [ ] Full test matrix green on Python 3.9/3.12.
- [ ] Package verification and extracted ZIP verification green.
