# LBPM Production Runner v1.0.1

**版本化、离线优先、可迁移的 1200 输入正式生产工具。**

本包是 LBPM 外部任务控制器，不是新的 LBM 求解器，也不是重新安装 LBPM 的 Builder。它复用已安装的 LBPM / OpenMPI 与 SOP v1.3.2，不修改 LBPM 源码，不自动换物理参数，不自动关机。

## 交付状态

- 已包含可运行源码、外部配置、中文操作说明、工程测试和完整性清单。
- 本地测试使用真实文件/进程/SQLite/libzstd，以及**明确标记的 CPU 模拟 MPI/MPS 进程**。
- **本交付环境没有执行你的真实 NVIDIA GPU、真实 LBPM 或 1200 个岩心；不能把本地工程测试报告当作服务器 GPU 验收、物理有效性证明或数值稳定性保证。**
- 第一批真实运行就是正式生产：有效输出可进入数据集，不另开参数筛选。首次原生在线早停需看到 `mps_termination.json` 的成功记录及同 GPU 其他任务持续正常推进。

## 当前预填协议

Ca=2.0e-4；rhoA/B=.10/.10；tauA/B=.78/.92；alpha=.009；beta=.90；SCAL affinity=+0.2588190451；名义水接触角75°；BC4；全气孔隙初态、+Z水驱气。

原始ROI为128³ uint8（二值0固体/1孔隙）。计算域128×128×134，入口/出口各3层。输出相标签0固体/1气A/2水B。所有饱和度仅在原始128³孔隙上计算。

R1_FAST每名义0.1PVI判定，最大4PVI；采用最近偶数 `checkpoint_steps=16592`，最大 `663680` 步（40个周期）。保留名义PVI和按启动日志目标通量换算的PVI，不将其冒充实际测量注入体积。STANDARD最早1.5PVI；ACCEPTED最早3.2PVI。完整规则在 `config/protocol.toml`。

R1的早期研究依据来自Ca=2.5e-4的18个成功轨迹离线回放，不是当前Ca=2.0e-4全体输入的独立验证。结果称为**协议终点气相饱和度**，CAP_REACHED不等于物理收敛；NaN不当作标签，不填成0。

## 快速开始（RiverMind）

把 ZIP 上传到 `/root/rivermind-data`，然后：

```bash
cd /root/rivermind-data
unzip LBPM-Production-Runner-v1.0.1.zip
cd LBPM-Production-Runner-v1.0.1
bash run.sh prepare --config config/rivermind.toml
bash run.sh start --config config/rivermind.toml
bash run.sh status --watch --config config/rivermind.toml
```

`prepare`登记输入/冻结协议/检查依赖，不启动LBPM模拟。遇到阻断会打印具体原因，不会自动安装或改旧环境。通过后即可直接 `start`，不必等待聊天确认。

包内 Shell 文件可用 `bash run.sh` 运行，不依赖ZIP是否保留执行位。需要另一个已有Python时：

```bash
export LBPM_RUNNER_PYTHON=/absolute/path/to/python3
```

更多操作见 [QUICKSTART](docs/QUICKSTART.zh-CN.md)。代码/配置分离与迁移见 [CONFIG](docs/CONFIG.zh-CN.md)。

## 运行依赖与兼容边界

- Linux、Python >=3.9，所选Python已有NumPy；Python<3.11时使用包内MIT tomli 2.2.1。
- 系统 `libzstd >=1.4`（常见名称libzstd.so.1），由ctypes调用；**不需要zstd命令行，也不需要pip安装zstandard**。
- 已就绪的 CUDA LBPM + OpenMPI；当前适配固定commit `6d686d354e5b8140841d3601e4c8c0e4e4b77e48` 及 `outletlayersphase-fix-v1`。记录二进制、源码与已有构建证明的哈希；不是重新认证编译过程。
- SOP v1.3.2及其已有schema1/PASS acceptance_report.json。Runner建立独立SOP运行副本与环境桥接，不改原SOP配置。
- NVIDIA Legacy MPS v2 `ps` / `terminate_client`，GPU和控制器在同一可见PID命名空间。不能识别客户端时拒绝盲目发信号。v3、跨宿主机PID转换、任意CUDA/硬件平台不在本版已验证范围。
- 存储应提供可靠的POSIX锁、同文件系统原子重命名及fsync语义；本版不承诺不可靠NFS/FUSE上的数据库掉电安全。
- 不包含CUDA/MPI/LBPM/NumPy的跨平台二进制重装包；**现有RiverMind环境已经具备NumPy，实际libzstd和其他依赖由prepare检测**。运行时不会联网下载。

## 主要操作

```bash
bash run.sh show-config --config config/rivermind.toml
bash run.sh prepare --config config/rivermind.toml
bash run.sh start --config config/rivermind.toml
bash run.sh status --watch --config config/rivermind.toml
bash run.sh pause --drain --config config/rivermind.toml
bash run.sh resume --config config/rivermind.toml
bash run.sh export --config config/rivermind.toml
bash run.sh diagnose --config config/rivermind.toml
```

所有命令接受 `--output-root` 等路径覆盖。`status`只读，不要求GPU仍在线。

## 中断、异常和存储

- 断网/关闭查看面板：后台生产不依赖SSH标准输入；重新连接再看status。
- 调度器退出而工作进程还活着：resume先识别并接管，不重复提交。
- 服务器关机：已提交结果保留。没有完整可认证终点的在途任务从初态建立新attempt；**不是从RAW继续LBPM微观状态，不启用native Restart**。
- 数值NaN：标记NUMERICAL_FAILED，不自动换Ca、不重复试同一数值失败。
- 非正常MPS客户端退出存在共享服务风险。本版采取保守策略：隔离该MPS epoch，安全终止并重新排队可能受影响的同行任务，重建空闲的本工具MPS服务。数据留在旧attempt。反复基础设施中断有次数上限，不能把它们算成岩心数值失败。**此策略可能降低吞吐；42%不是本Runner工期保证。**
- 保留所有已产生检查点，包括失败/中断尝试与监控延迟产生的额外场。低于10GiB逐attempt无损归档，至15GiB停止回收；仅在完整清单/大小/解压哈希验证后释放冗余RAW。不处理运行目录、不删除历史实验。
- 低于5GiB或动态安全预留量暂停新任务；极低空间请求安全中断。压缩不是备份，不保证磁盘一定装得下所有数据。

## 结果

`dataset_index.csv`含全部1200输入的状态，只有 `valid=True` 行可作为标签。最终相态为 `phase_final_roi.npy`（Z,Y,X，uint8，128³），标量来自同一终点；其他数据见 [OUTPUTS](docs/OUTPUTS.zh-CN.md)。

处理1200输入 ≠ 保证1200个有效样本；不重复岩心补数，不隐瞒失败或同母岩选择偏差。

## 完整性与测试

```bash
bash run.sh verify-package
bash run.sh selftest
```

`verify-package`校验程序和vendored代码，允许正常编辑外部配置。`selftest`为CPU工程测试，使用临时模拟数据，不启动真实LBPM/CUDA，不是压缩率或物理参数试验。完整日志与范围见 `docs/VALIDATION.md`。
