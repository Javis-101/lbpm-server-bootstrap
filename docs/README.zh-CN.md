# LBPM Server Bootstrap 中文指南

[English README](../README.md) | 简体中文

LBPM Server Bootstrap 是一个面向 OPM/LBPM 数字岩心模拟的独立社区项目。它把离线优先的依赖安装、LBPM 身份核验、CUDA/GPU 运行时检查、安装后验收、真实岩心 RAW 契约和受控 ColorModel 冒烟运行串成一个可审计流程。

> [!IMPORTANT]
> **部署时请下载 [v1.0.3 GitHub Release](https://github.com/Javis-101/lbpm-server-bootstrap/releases/tag/v1.0.3)，不要克隆 `main` 作为冻结部署包。**
>
> - `v1.0.3`：已在真实 NVIDIA Tesla T4 服务器完成验证的不可变正式版本
> - `main`：包含后续路径安全加固的 `1.0.4-dev` 开发与审计源码

## 它解决什么问题

普通的“编译成功”不足以说明一台 GPU 服务器已经适合可复现研究。本项目继续检查编译器与 GNU Fortran 链接、CUDA 可见性、MPI/HDF5/LBPM 身份、本地补丁、RAW 几何契约、+Z 连通性、源数据不可变性、ROI 保持以及 GPU 数值冒烟证据。

它适合：

- 使用 OPM/LBPM 的数字岩心与多孔介质研究者；
- 租用短期 CUDA GPU 服务器的用户；
- 需要可复现 LBPM 环境和机器可读验收证据的团队；
- 从受控环境批量生成模拟数据的科研工作流。

## 下载与 Quick Start

验证制品：`LBPM-server-bootstrap-v1.0.3.zip`

SHA256：

```text
f1bf6e5649769aba5d246535d3f74f1cbc4032ebab78ee9bb54fa7a439360507
```

在兼容的 Ubuntu-like x86_64 GPU 服务器上执行：

```bash
curl -LO https://github.com/Javis-101/lbpm-server-bootstrap/releases/download/v1.0.3/LBPM-server-bootstrap-v1.0.3.zip
curl -LO https://github.com/Javis-101/lbpm-server-bootstrap/releases/download/v1.0.3/LBPM-server-bootstrap-v1.0.3.zip.sha256

sha256sum -c LBPM-server-bootstrap-v1.0.3.zip.sha256
unzip LBPM-server-bootstrap-v1.0.3.zip
cd LBPM-server-bootstrap-v1.0.3

sudo bash run_all.sh \
  --raw /absolute/path/to/your_rock.raw
```

宿主机需要预先具备 CUDA 与文档列出的编译工具链；Bootstrap 不修改 APT 源，也不自动安装缺失的操作系统软件包。租用或配置服务器前请阅读[兼容性说明](compatibility.md)。

## 发布包里有什么

v1.0.3 完整 ZIP 包含：

```text
LBPM Server Bootstrap v1.0.3
├── Portable Offline Installer v2.0.7
│   ├── OpenMPI 4.1.8
│   ├── zlib 1.3.2
│   ├── Parallel HDF5 1.14.6
│   └── OPM/LBPM v2026.04 + 已审计本地补丁
├── Post-install SOP v1.3.2
└── 环境检查、安装/复用、GPU 验收、RAW 契约、真实岩心冒烟与证据生成
```

仓库中的 [`installer/`](../installer/) 是 Installer 源码，[`sop/`](../sop/) 是 SOP 源码；完整的 Installer 与 SOP ZIP payload 只存在于 GitHub Release 制品中，不进入 Git 历史。

## 真实服务器验证

v1.0.3 已在 Ubuntu 24.04.x、NVIDIA Tesla T4、CUDA 12.8、OpenMPI 4.1.8、HDF5 1.14.6 和 OPM/LBPM v2026.04 环境完成真实服务器验证。

已通过：全新安装、精确兼容复用、LBPM 身份、CUDA/GPU 运行时、Piston 基础验收、真实岩心 RAW 契约、+Z 连通性、源数据不可变性、ROI 保持、GPU ColorModel 冒烟以及证据生成。详细记录见 [v1.0.3 validation](validation/v1.0.3.md)。

## 科学边界

通过 Bootstrap/SOP 表示基础设施、LBPM 构建、GPU 运行时、数据契约和冒烟模拟已经达到工程就绪状态。

它**不等于**生产级水驱气模拟、残余气饱和度、毛细数选择、润湿性模型或最终科学参数已经完成物理验证。`READY_FOR_PARAMETERIZATION` 是工程交接状态，不是物理模型认证。

## 获取帮助

- 安装问题与使用讨论：[GitHub Discussions](https://github.com/Javis-101/lbpm-server-bootstrap/discussions)
- 可复现缺陷：[GitHub Issues](https://github.com/Javis-101/lbpm-server-bootstrap/issues)
- 贡献规范：[CONTRIBUTING.md](../CONTRIBUTING.md)
- 完整英文说明：[README.md](../README.md)

LBPM Server Bootstrap 不是 OPM 官方项目。上游软件请参见 [OPM/LBPM](https://github.com/OPM/LBPM)。
