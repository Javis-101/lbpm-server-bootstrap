# Changelog

All notable changes to repository source are documented here. Frozen archives keep their own embedded changelogs and identities.

## 1.0.4-dev - Unreleased

- Created a source-only publication candidate with no third-party tarballs, nested ZIPs, research RAW, or raw server evidence in Git.
- Added a fail-closed installer `--prefix` guard for empty, root, relative, and dot-segment paths before directory creation or recursive removal.
- Added publication metadata, third-party notices, sanitized validation status, security/contribution policies, and lightweight static CI.
- Corrected the v1.0.3 evidence model: final external Tesla T4 run evidence takes precedence over build-time metadata embedded before execution.
- Marked repository HEAD as development code because the path-safety change is not byte-identical to the frozen v1.0.3 artifact and has not completed a new real GPU validation cycle.

## 1.0.3 - Frozen local artifact

- Artifact SHA256: `f1bf6e5649769aba5d246535d3f74f1cbc4032ebab78ee9bb54fa7a439360507`.
- Preserved Portable Installer 2.0.7-offline, SOP 1.3.2, and the pinned LBPM/dependency stack.
- Added GNU Fortran host-preflight coverage after the v1.0.2 Tesla T4 prerequisite failure.
- Completed real Tesla T4 fresh-install run `20260828T073123Z-8EUS31` and compatible-reuse run `20260828T074416Z-lQFk4b`; both passed the complete engineering acceptance workflow.

Historical v1.0.0-v1.0.2 details remain in the immutable artifact history. Build-time `validation pending` text inside v1.0.3 records the pre-execution state and is superseded by the later external runtime evidence.
