# Production Runner / 正式生产控制器

> 集成补丁说明：在本次对话的最终检查时，GitHub 只有空的功能分支，源码写入被工具侧安全检查拦截；本文件与代码是待提交内容。以下 Actions 与下载流程在源码真正提交后才可使用。

新增的 [production-runner/](production-runner/) 是现有 Builder/Installer 和 SOP 之后的生产管理层，不是替代求解器或重新安装器。

**Runner 1.0.1 是修复后的工程候选版本，尚未完成真实 NVIDIA GPU 验收。** 原 Bootstrap v1.0.3 的发布物、安装入口、版本与验证记录不变。

| 层 | 已有/新增位置 | 职责 |
|---|---|---|
| 离线环境构建安装 | `installer/`、原 Bootstrap Release | 固定 LBPM、MPI、HDF5 和补丁，建立环境与构建清单 |
| 几何准备/工程验收 | `sop/` | 原始 128³ 二值 RAW 不变，准备缓冲层、分解和状态报告 |
| 正式生产 | `production-runner/` | 外部参数、队列、R1 在线停止、完整输出、空间触发无损压缩、任务级恢复 |

先阅读 [集成与下载说明](production-runner/docs/BOOTSTRAP_INTEGRATION.zh-CN.md)。已有接受过验收的 LBPM 环境不需要重装。

```bash
cd production-runner
bash run.sh verify-package
bash run.sh show-config --config config/rivermind.toml
bash run.sh prepare --config config/rivermind.toml
# prepare 成功后再执行：
bash run.sh start --config config/rivermind.toml
bash run.sh status --watch --config config/rivermind.toml
```

路径通过配置、环境变量或 CLI 注入。跨机器改机器配置，不改求解协议，不改源代码。发现多个旧 SOP 时要求明确指定，不自动选择“最新”目录。

[工程 CI](.github/workflows/production-runner.yml) 在源码 checkout 上测试 Runner 与真实 SOP 脚本的接口，但用 CPU 模拟 MPI 分解与 MPS/GPU 过程。CI 成功后生成独立 Runner ZIP 和 SHA256 artifact；也可从固定 Git commit 下载仓库源码，直接运行上述目录。

**边界：** 1200 个输入不保证 1200 个数值有效标签；压缩不是独立备份；断电后仅恢复任务队列，没有承诺从相标签 RAW 无损恢复 LBM 分布函数。不要使用旧 Runner 1.0.0 新开生产。
