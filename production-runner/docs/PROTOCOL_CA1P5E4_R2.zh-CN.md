# GW-Ca1p5e4-R2-v1 正式生产协议

本文件记录 RiverMind 1200 个 128³ 数字岩心的新一代正式生产协议。它是一个新的物理/数值协议身份，不覆盖也不替代历史的 `GW-Ca2e4-R1F125-v1`。

## 1. 冻结参数

物理与几何：

- `capillary_number = 1.5e-4`
- `rhoA = rhoB = 0.10`
- `tauA = 0.78`
- `tauB = 0.92`
- `alpha = 0.009`
- `beta = 0.90`
- `affinity = 0.2588190451`
- `WettingConvention = SCAL`
- 名义水接触角 75°
- ROI `128 x 128 x 128`
- 入口/出口各 3 层 reservoir
- `BC = 4`
- 流动方向 `+Z`
- 正式生产目标并发 `MPS-8`

停止规则：

```toml
[stopping]
check_pvi = 0.1
max_pvi = 3.6
window_points = 5

[stopping.standard]
start_pvi = 0.5
max_dsg = 0.0030
range_sg = 0.0060
max_flip = 0.0100
consecutive = 4

[stopping.accepted]
start_pvi = 3.0
max_dsg = 0.008
range_sg = 0.025
max_flip = 0.030
consecutive = 3
```

当前 Runner 公式对应：

- `CHECKPOINT_STEPS = 22124`
- `MAX_STEPS = 796464`
- 最大 checkpoint 数 = 36
- 若从 0.5 PVI 起每次 STANDARD 均通过，则最早在 0.8 PVI 达到连续 4 次确认。

## 2. 科研边界

`Ca=1.5e-4` 与历史 `Ca=2e-4` 不属于同一物理协议。旧生产根中的成功标签不得直接迁移到本协议的数据集。

`STANDARD`、`ACCEPTED` 和 `CAP_REACHED` 都是“协议定义终点”，不是无限时间渐近平衡的证明。

数值失败案例永远不产生有效标签。不得用失败前最后一个 checkpoint 冒充成功终点。

此前针对较宽 STANDARD 的离线扫描来自 `Ca=2e-4` 轨迹，只用于形成停止规则设计依据，不构成 `Ca=1.5e-4` 的科学验证证书。

## 3. 数值失败隔离策略

Runner 1.1.0 对 `NUMERICAL_FAILED` 采用“安全单任务隔离优先、整 epoch 恢复兜底”的策略：

1. 检测到数值失败时，优先使用 MPS v2 `terminate_client` 对当前、可唯一识别的 CUDA client 做定向终止。
2. 只有返回明确的 `safe_context_termination=true` 时，才允许仅把当前 case 记为 `NUMERICAL_FAILED`，而不发布共享 epoch fault；健康 peer 可以继续运行，调度器可补新任务。
3. 如果 client 已退出、身份不唯一、MPS 拒绝终止、响应不明确或其他安全条件不成立，则继续采用旧的 fail-safe 行为：发布 epoch fault，peer 进入隔离/恢复流程。
4. GPU/MPS 共享故障、基础设施错误和存在孤儿 CUDA producer 风险的异常，仍按保守路径处理。

此策略的目标是减少“一个可安全隔离的数值失败导致其他健康 MPS peer 重跑”的工程损耗，而不是把失败样本转成有效标签。

## 4. 生产目录边界

建议：

- Runner：`/root/rivermind-data/lbpm-runner-src-v1.1.0`
- protocol：`/root/rivermind-data/lbpm-production-protocols/GW-Ca1p5e4-R2-v1.toml`
- output root：`/root/rivermind-data/lbpm-production-data-ca1p5e4-r2-v1`

历史 `lbpm-runner-src-v1.0.1` 和 `lbpm-production-data-r1f125-v1` 保留，不覆盖、不删除。

## 5. 验证边界

GitHub Actions 仅验证 CPU 工程契约、协议计算、结果守卫、恢复逻辑、CPU MPS fixture 和可复现打包。真实 RTX 4090 D、NVIDIA MPS、LBPM 物理行为和正式 1200-case 生产仍需要目标服务器上的真实 GPU Canary 作为上线证据。
