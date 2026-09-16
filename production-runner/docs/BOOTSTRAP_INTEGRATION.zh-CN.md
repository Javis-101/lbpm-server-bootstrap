# Builder / SOP / Runner 集成与下载

**本次交付状态：本地集成候选已完成，GitHub 只创建了分支，源码写入被工具安全检查拦截；尚无 Runner 源码提交、PR、CI 运行或 Release。下文 GitHub 下载步骤仅在实际提交并通过 CI 后适用，不表示现在已经可下载。**

## 对应关系与版本

- 仓库基线：`Javis-101/lbpm-server-bootstrap` 的 `8acdb62a9768911250474003597f595b785ac266`。
- 已有安装层：Portable Offline Installer 2.0.7；SOP 1.3.2 接口也声明接受既有 2.0.5/2.0.6 构建。Runner 检查实际 commit/patch/环境，不因安装包名字相似就跳过身份检查。
- 固定 LBPM：`6d686d354e5b8140841d3601e4c8c0e4e4b77e48`，`outletlayersphase-fix-v1`。
- Runner：1.0.1，外部控制器，独立版本，不改变根目录 Bootstrap VERSION、原 v1.0.3 Release 或求解器源码。
- 本次不编译 CUDA/MPI/LBPM，也不运行真实 GPU；真实 SOP 接口测试的 MPI 分解是明确的 CPU 模拟。

## 已有服务器：不重装，只接入

1. 下载 GitHub 上本次集成的固定 commit 源码（或 CI 生成的 Runner ZIP + SHA256），不要混用不同版本的零散 Python 文件。
2. 源码版进入 `production-runner/`；独立 ZIP 进入 `LBPM-Production-Runner-v1.0.1/`。
3. 把 `config/rivermind.toml` 复制到包外作为个人机器配置，例如 `$HOME/lbpm-machine.toml`，保留可迁移性。
4. 当前预设提供 `/root/rivermind-data/LBPM-stack-v207` 等普通目录。SOP 不包含私有历史运行 ID，只在该工作区查找唯一候选；多个候选必须由 `--prepare-case` 明确指定。
5. 若使用已经安装的 SOP，其 `config.env` 可提供原 `VALIDATION_DIR`，但 Runner 不修改该文件。也可以显式传入 `--acceptance-report`。

```bash
cp config/rivermind.toml "$HOME/lbpm-machine.toml"
bash run.sh verify-package
bash run.sh show-config --config "$HOME/lbpm-machine.toml"
bash run.sh prepare --config "$HOME/lbpm-machine.toml"
# 只有上一条 READY_FOR_PRODUCTION 后才启动：
bash run.sh start --config "$HOME/lbpm-machine.toml"
bash run.sh status --watch --config "$HOME/lbpm-machine.toml"
```

`READY_FOR_PRODUCTION` 表示环境/输入清单就绪，不是物理稳定性认证。没有授权自动重新安装或执行平台关机。

## 直接使用本仓库 SOP 源码

从仓库的 `production-runner/` 目录执行时，可以用 CLI 选择兄弟目录 SOP：

```bash
bash run.sh prepare --config "$HOME/lbpm-machine.toml" \
  --prepare-case "$PWD/../sop/bin/prepare_case.sh" \
  --acceptance-report /actual/validated/acceptance_report.json
```

上例的 `/actual/validated/acceptance_report.json` 必须替换成实际验收报告路径，不是一个提供的文件。把相同路径写进自己的机器配置，再执行 start/resume；CLI 覆盖不会自动回写用户的 TOML。没有真实 PASS 报告时，按原 Bootstrap/SOP 流程完成验收，不能制造报告绕过检查。

## 接口合同

| 上游接口 | Runner 对接 |
|---|---|
| `write_env` 的 `lbpm_env.sh`、MPI_DIR、PATH、LD_LIBRARY_PATH | source 用户选择的可信环境，并在私有 SOP 副本桥接明确的 MPI/LBPM 路径 |
| `LBPM_BUILD_MANIFEST.txt` 的 LBPM_COMMIT、PATCHSET_ID | prepare 校验声明并记录二进制和实际 ColorModel 源码哈希，不冒充重新验证编译产物来源 |
| `prepare_case.sh --input --case-id --case-dir --voxel-length-um` | 用 bash 调用，参数数组传入，标准输入 /dev/null，不要求脚本执行位 |
| SOP `config.env` | 创建 output/sop-runtime 私有配置副本，不修改源 SOP |
| CASE_PREPARED / case_manifest / connectivity_report | 验证固定 ROI、源 RAW 哈希、缓冲相位、ID 大小与准备产物哈希后复用 |
| `input-production.TEMPLATE.db` | 不直接运行占位符模板；Runner 从冻结协议生成完整 input.db |
| READY_FOR_PARAMETERIZATION | 上游工程状态，不能当作 R1 终点或有效训练标签 |
| 生产 complete.json | 统一核对冻结身份、outcome、终点哈希与 MPS epoch，才可导出 valid=true |

`tests/test_bootstrap_bridge.py` 调用本仓库真实的五个 SOP 脚本，验证路径含空格、无执行位、私有配置、原始数据不变及 prepared 复用；分解输出仅模拟文件合同，未验证真实数值分解。

## 下载与可复现构建

- 从本次 PR/commit 的 **Code → Download ZIP** 获取仓库源码；归档中的根目录安装器仍不是原 Release 的完整离线依赖 payload。
- GitHub Actions 的 `production-runner-engineering` 成功后，artifact `LBPM-Production-Runner-v1.0.1` 包含独立 Runner ZIP 和校验文件。下载 artifact 外层 ZIP 后先解开，里面才是 Runner 发布包。
- 本地可执行 `python3 tools/package.py --out /tmp/lbpm-runner-release`。构建拒绝不匹配的程序哈希，固定 ZIP 顺序/时间戳，并生成包内 SHA256SUMS 与 ZIP 外部 SHA256。
- GitHub 自动生成的整个仓库 ZIP 与独立 Runner ZIP 不是同一文件；不可混用它们的校验值。

## 两处审查缺陷的修复

F-01：发现终点损坏后隔离 complete.json 并标为 OUTPUT_FAILED。普通导出与显式导出都核查相同证据，SQLite 已拒绝的结果不再被完成标记反向覆盖成 valid=true。

F-02：正常提交、已有完成标记、重启发现的成功 outcome、导出都调用相同 epoch 检查。结果结束时间不早于已记录 MPS 故障时即拒绝，并保留旧结果/检查点，按中断重建尝试。缺少 epoch 或故障时间不完整时不猜测安全。

新版本没有自动变更 Ca、R1、归档阈值或失败补样规则。因 MPS 共享故障隔离，同行任务可能重算；历史离线加速率不是墙钟承诺。
