# LBPM Production Runner 1.0.1

External production controller for the pinned LBPM Installer/SOP stack. This is an **engineering candidate, not real-GPU validated**. It does not modify the LBPM solver, install CUDA/MPI, or certify the chosen physical protocol.

**Publication status:** local integration candidate only. The source upload was blocked by the connector safety check; the remote branch has no Runner source commit yet.

**中文：** 这是与现有 Builder/Installer、SOP 衔接的外部生产控制器。代码和 CPU 工程测试不能替代真实 GPU 验收；当前版本不声称已经在 RiverMind 跑通完整生产。

- [中文使用说明](README.zh-CN.md)
- [仓库集成与下载](docs/BOOTSTRAP_INTEGRATION.zh-CN.md)
- [恢复边界](docs/RECOVERY.zh-CN.md)
- [修复和验证范围](docs/VALIDATION.md)
- [变更记录](CHANGELOG.md)

The root repository's Bootstrap `v1.0.3` release is unchanged. Runner versioning is independent.

```bash
# Run from this directory; edit/select a machine config before preparing.
bash run.sh verify-package
bash run.sh prepare --config config/rivermind.toml
# Only after prepare reports READY_FOR_PRODUCTION:
bash run.sh start --config config/rivermind.toml
bash run.sh status --watch --config config/rivermind.toml
```

For another machine use `config/machine.example.toml` or CLI path overrides. `--prepare-case` can point at a previously installed SOP, or at this repository's `sop/bin/prepare_case.sh` together with an explicit `--acceptance-report` from an already accepted stack. No path-specific source edits are required.

The 1200-source preset fixes Ca=2e-4, R1_FAST, all generated checkpoints retained, lossless compression below 10 GiB toward 15 GiB, and at most eight independent single-rank MPS clients. This schedules inputs; it does **not** guarantee 1200 valid numerical results. Interrupted attempts restart from the immutable initial geometry, not from 8-bit phase fields.

```bash
# CPU tests; no LBPM GPU execution.
bash run.sh selftest
# Deterministic ZIP + SHA256 outside the source tree.
python3 tools/package.py --out /tmp/lbpm-runner-release
```

Download a pinned source commit rather than mixing files from different Runner versions. Standalone ZIPs reuse an existing SOP; source-checkout CI also exercises the real sibling SOP scripts with mock decomposition.
