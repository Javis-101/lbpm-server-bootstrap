# 输出合同

## 顶层

```text
production_manifest.json    生产ID、Runner版本、协议/输入哈希和初始环境证据
protocol.snapshot.json      冻结科研协议
machine.snapshot.json       当前明确绑定的机器配置
inputs.json / inputs.tsv    1200输入身份与固定顺序
state.sqlite3               单写入者任务索引
sessions/                   每次start/resume的执行环境记录
epochs/                     MPS共享服务代际及异常隔离证据
status.json                 实时面板快照（不应误当作最终数据索引）
events.jsonl / master.log   调度、归档、恢复事件
archive_status.json         空间与当前归档状态
tasks_status.tsv            全输入状态表
dataset_index.csv           所有输入的标签索引，valid区分有效/失败
cases/                      所有样本与尝试
```

## 单样本

```text
cases/41_123/
  complete.json
  attempts/attempt_0001/
    job.json / process.json / worker_spawn.json / live.json
    input.db / run.log / prepare.log / worker.log
    rock.raw / rock_waterdrive.raw / ID.00000
    CASE_PREPARED.json / case_manifest.json / connectivity_report.json
    id_t16592.raw ...                   所有已经产生的检查点
    metrics.jsonl / metrics.csv
    stop_intent.json / mps_termination.json
    endpoint.raw
    outcome.json
    result/
      phase_final_roi.npy
      phase_final_full.raw
      result.json
    checkpoints.tar.zst                达到空间条件后生成
    archive_manifest.json
```

不存在的可选日志不补造。被中断/失败的旧attempt保留；后一次attempt不覆盖它。

## 最终标签

- phase_final_roi.npy：shape=(128,128,128)，轴序(Z,Y,X)，uint8，C-order/X最快；0固体、1气A、2水B。可在任意支持NumPy的平台读取，allow_pickle=False。
- phase_final_full.raw：shape=(134,128,128)的无头uint8数据，前后各3层缓冲；不要把其全域相占比当作ROI饱和度。
- endpoint.raw与result/phase_final_full.raw是同文件系统中同一不可变终点的两个硬链接名称，避免额外复制；不要直接编辑任何一个。
- result.json的sg_endpoint由该npy对应同一时刻、同一ROI的气体素/原始孔隙体素计算。不是从另一个检查时刻抄一个标量。

当前输出是离散相态，不包含连续phi、速度、压力场。日志中的数值检查也不等于逐体素全部物理量已输出并验证。

## PVI

生产判据使用整数检查点编号对应名义PVI，避免1.2与浮点数比较差异。当前格子步间隔16592，40周期663680；实际公式PVI略有舍入差异。

metrics/result中另记录 `timestep * logged_target_flux / original_ROI_pore_voxels`。这是按启动日志目标注入通量换算，日志本身有打印舍入；不是逐步测得的实际注入体积积分。

## 额外检查点

外部监控和安全终止存在延迟，可能在决策后产生额外检查点。这些文件也保留并归档；正式标签仍然指向事先持久化的选定终点。metrics停止于所选决策，不把额外文件当作另一次R1终点。

## 训练用索引

只使用dataset_index.csv里valid=True的行。CAP_REACHED是可用的协议终点标签但停止原因必须保留；数值失败Sg为空而不是0。结果记录协议哈希与attempt相对路径，便于母岩分组、失败统计与迁移。

完整路径=生产数据根 + phase_roi_relative。无须解压检查点即可读取最终标签。将来读取中间轨迹时，按STORAGE说明恢复该attempt的全部检查点。
