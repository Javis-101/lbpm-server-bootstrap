# 首次部署与日常操作

## 1. 上传、解压

ZIP上传到数据盘。SHA256文件也上传后，可先在同目录运行：

```bash
sha256sum -c LBPM-Production-Runner-v1.0.1.zip.sha256
unzip LBPM-Production-Runner-v1.0.1.zip
cd LBPM-Production-Runner-v1.0.1
```

不要把生产数据存进工具版本目录。默认正式数据目录是 `/root/rivermind-data/lbpm-production-data`，与此前实验完全分离。

## 2. 准备并启动

```bash
bash run.sh prepare --config config/rivermind.toml
bash run.sh start --config config/rivermind.toml
bash run.sh status --watch --config config/rivermind.toml
```

prepare会扫描1200个输入、核对哈希、输出时间步网格，登记输入而非一次prepare全部岩心。实际运行中，每个工作进程按需调用SOP，或者严格验证后复用prepared case。

期望准备摘要：

```text
INPUTS=1200  INVALID_OR_DUPLICATE=0
CHECKPOINT_STEPS=16592  MAX_STEPS=663680
READY_FOR_PRODUCTION (not a scientific stability certificate)
```

若 `INVALID_OR_DUPLICATE` 非0，记录中会说明对应输入被拒绝，不能静默拿它们当有效数据。

start内部已处理后台化、标准输入隔离和单实例锁。**不用自己启动MPS，不用另拼nohup命令，不重复点击多个start。** ALREADY_RUNNING表示已有控制器，不表示又启动了一套队列。

## 3. 首次真实生产需要看的证据

面板出现活跃任务后，最近完整PVI会随输出增长。每5秒刷新面板不意味着每5秒有新相场。没有足够真实吞吐数据时，ETA暂不显示。

首个STANDARD/ACCEPTED任务，attempt目录会出现：
- stop_intent.json：所选时刻及哈希；
- mps_termination.json：MPS成功返回0后才允许发主机信号；
- result/result.json：终点标量、场、时间及停止原因；
- case目录的complete.json：该任务成果正式提交。

这是服务器上的首次原生早停证据，**不是包内CPU模拟MPS测试可以代替的东西**。若MPS控制不能安全确认，程序会暂停新任务、保留现有进程与数据，不冒险kill。需要诊断时使用diagnose。

## 4. 断网后

重新登录，进入工具目录，再运行status。不需要重新prepare，也不需要重新模拟已完成的数据。

## 5. 计划关机

```bash
bash run.sh pause --drain --config config/rivermind.toml
bash run.sh status --watch --config config/rivermind.toml
```

确认 `SAFE_TO_STOP` 后由你自己到平台关机。工具没有自动关机功能。没有SAFE_TO_STOP时，不把一个暂时不更新的监控页面当作计算已结束。

## 6. 意外关机后

服务器及同一数据盘恢复后：

```bash
bash run.sh resume --config config/rivermind.toml
bash run.sh status --watch --config config/rivermind.toml
```

恢复的基本单位是单个attempt，而不是64个整批。旧attempt检查点保留。更多边界见RECOVERY。

## 7. 完成与取数

```bash
bash run.sh export --config config/rivermind.toml
bash run.sh status --config config/rivermind.toml
```

export重验最终结果哈希并重建dataset_index.csv。只有valid=True的行用于训练。状态COMPLETE表示输入全部有终态记录，不代表全部成功。

## 8. 出错时只导出一个诊断包

```bash
bash run.sh diagnose --config config/rivermind.toml
```

命令打印诊断包路径。默认不收集RAW、私钥或整份环境变量；日志可能有用户名、绝对路径，分享前检查即可。不要自行删除state.sqlite3、complete.json或归档清单来“重新启动”。
