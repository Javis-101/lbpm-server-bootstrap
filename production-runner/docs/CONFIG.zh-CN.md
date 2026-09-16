# 配置、路径和迁移

## 配置优先级

环境项采用：**CLI > LBPM_RUNNER_前缀环境变量 > TOML > 有界唯一发现**。

示例：

```bash
bash run.sh prepare --config config/machine.example.toml \
  --lbpm-root /home/me/LBPM-stack \
  --raw-root /home/me/rocks \
  --output-root /home/me/production
```

TOML中相对路径始终相对于该TOML文件所在目录；支持 `~`、`${HOME}` 等显式变量。变量未定义会报错，不会把它当作错误的字面路径继续运行。未知键会阻断，防止把max_jobs拼成max_job后悄悄用默认值。

常用环境变量：

```text
LBPM_RUNNER_LBPM_ROOT / LBPM_RUNNER_LBPM_BINARY / LBPM_RUNNER_MPIRUN
LBPM_RUNNER_ENV_SCRIPT / LBPM_RUNNER_PREPARE_CASE
LBPM_RUNNER_RAW_ROOT / LBPM_RUNNER_CASE_ROOT / LBPM_RUNNER_OUTPUT_ROOT
LBPM_RUNNER_ACCEPTANCE_REPORT / LBPM_RUNNER_BUILD_MANIFEST / LBPM_RUNNER_SOURCE_ROOT
LBPM_RUNNER_MPS_CONTROL / LBPM_RUNNER_NVIDIA_SMI / LBPM_RUNNER_LIBZSTD
LBPM_RUNNER_GPU / LBPM_RUNNER_MAX_JOBS / LBPM_RUNNER_MPS_BASE
LBPM_RUNNER_COMPRESS_BELOW_GIB / LBPM_RUNNER_COMPRESS_UNTIL_GIB
LBPM_RUNNER_PYTHON（仅启动入口选择已有解释器）
```

CLI支持prepare/start/resume等命令后传 `--config`、`--protocol`、`--output-root`、`--raw-root`、`--case-root`、`--lbpm-root`、`--lbpm-binary`、`--mpirun`、`--env-script`、`--prepare-case`、`--acceptance-report`、`--gpu`、`--max-jobs`。

## 自动发现边界

仅从明确的lbpm_root派生标准安装路径，或在PATH中查找工具。SOP只在该stack相邻的bootstrap工作区有界搜索；多个候选即报错。原始数据目录/正式输出目录不盲猜。不递归扫描整台机器，也不自动采用“最新master”。

## SOP路径可迁移，不再被旧config.env覆盖

prepare_case必须可读，但不要求可执行位，调用方式为bash + 参数列表。

Runner把选定SOP的bin复制到生产根的sop-runtime。独立config.env指向新的prepared目录；stack-env/lbpm_env.sh先source用户指定的现有env_script，再把MPI_DIR和求解器/PATH入口绑定到显式选择的mpirun与LBPM目录；已有PASS acceptance report复制为独立快照。原SOP、原config.env、旧bootstrap目录都不修改。此镜像是适配部署路径，不是重写几何或分解算法。

## 协议冻结

protocol.toml首次prepare后形成protocol.snapshot.json和SHA256。start/resume核对相同协议。修改Ca、tau、ROI、R1阈值等后必须换一个生产输出根，不能续写旧生产。

机器配置允许显式迁移，输入清单只记raw_root下的相对名称；attempt/result路径相对于生产根。原始RAW、最终场和归档都保留哈希。路径变化不自动改变科学协议。

## 从RiverMind迁移到另一台机器

1. 原机器先pause --drain并看到SAFE_TO_STOP。
2. 复制**整个生产数据根**，包括SQLite及其日志、inputs/protocol快照、所有cases/attempts、归档与清单；不要只复制最终RAW。另复制原始输入与需要复用的prepared cases，保持相对命名。
3. 新机器具有兼容的LBPM/SOP/GPU环境后，修改machine TOML的路径。
4. 对复制来的生产根运行resume，不对它重新prepare。
5. 二进制/源码/MPI/SOP身份发生变化时会阻断；明确审核后才能使用 `--accept-runtime-change`。会记录新的执行环境，但不宣称跨GPU或重新编译后的位级一致性。

```bash
bash run.sh resume --config config/new-machine.toml
# 只有确实理解并接受执行环境差异时：
bash run.sh resume --config config/new-machine.toml --accept-runtime-change
```

如果旧任务还活着，禁止一边运行一边换路径/并发配置。仅更换服务器配置不能让GPU内存状态迁移。

## 升级工具

先排空当前任务，再部署新版本，旧数据根不动。不能在线覆盖正在运行的runner模块。初版不自动跨schema升级，不下载更新，不调用sudo/apt，不修改GPU全局compute mode。
