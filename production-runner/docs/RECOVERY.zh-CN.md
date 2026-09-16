# 恢复、状态和异常处理

## 三个不同层级

**会话断开**：工作进程已后台独立运行，stdin与SSH/任务表隔离。关闭浏览器或Ctrl+C退出status不停止计算。

**任务级恢复**：已提交结果核验后跳过；未启动继续排队；被中断且无可认证终点的岩心新建attempt，从相同原始初态重跑。旧attempt全部保留。

**LBPM微观状态续算**：本版不提供，也不启用native Restart。离散相标签RAW不含全部分布函数；此前项目的Restart对照也不是连续运行的等价替代。绝不拿id_t*.raw冒充完整恢复文件。

## 结果提交

工作进程在完整CLOSE_WRITE/MOVED_TO事件后读取检查场，校验尺寸、0/1/2标签、ROI几何和孔隙相计数。R1决策写入stop_intent；endpoint.raw完成持久化后才结束对应CUDA工作。结果文件及result.json写完后，主管进程才发布case/complete.json并更新索引。

MPS安全终止成功返回0之前，不能给客户端发终止信号。识别不到同PID命名空间、同token、同工作目录、同求解器二进制的唯一客户端时，暂停新提交，不猜PID。

如果崩溃发生在endpoint.raw和stop_intent均已持久化之后，恢复时重验二者、输入和协议；没有已知NaN或MPS epoch污染，可只补结果提交。若证据不足则从初态新建attempt，不从半个RAW继续。

## 终态

- SUCCEEDED_STANDARD / SUCCEEDED_ACCEPTED：对应分支达标，数据提交完成。
- CAP_REACHED：到最大4PVI有合法有限时间终点；不是收敛证明。
- NUMERICAL_FAILED：已知NaN/数值断言。不自动重跑，不换Ca。
- CONFIG_FAILED：源数据、prepared合同或配置错误，不生产标签。
- OUTPUT_FAILED：输出或控制器异常后无法认证终点。记录证据，不混入训练集。
- INTERRUPTED / INFRA_FAILED：非科学失败，可自动建立新attempt；达到默认3次attempt上限后进入RETRY_LIMIT并留待处理。
- STOP_CONTROL_BLOCKED / ORPHAN_REQUIRES_RECOVERY：不安全发信号；暂停新增任务，需要诊断。原进程可能仍在运行。

worker的outcome不等于训练集提交。训练入口只接受complete.json对应结果和dataset_index中的valid=True。

## MPS共享故障隔离

原生MPS客户端异常退出可能影响同GPU其他客户端，因此不将“还能继续跑”直接等同于可信。

NaN源任务记录NUMERICAL_FAILED；本版暂停该epoch派发，将可能受影响的同行attempt标记中断/隔离，先通过terminate_client安全清理其CUDA上下文，再结束主机进程。已在异常之前提交的成果保持；异常之后同epoch成果不会静默混入训练集。所有检查点保留。服务空闲后只重建本工具拥有的MPS，同行任务重新排队。

这比不理会abort更保守，可能增加重算和耗时；不能用历史离线42%直接承诺生产墙钟节省。重试次数有界，不进行无限自动重算。无法安全清理时明确进入RECOVERY_REQUIRED，而不是全局pkill。

## 计划关机

pause --drain停止派发，活跃任务照常达到R1或上限并提交。SAFE_TO_STOP只在受管工作与本工具MPS完成收尾后出现。工具不调用shutdown、reboot或平台停机API。

## 不要做的操作

不要在运行中编辑input.db、改协议快照、重新跑旧实验启动脚本、删除SQLite/complete/归档清单，或对共享MPS使用全局kill。

需要释放云实例前，应另行备份生产数据和原始输入。压缩同一块数据盘上的文件不能防止该数据盘被释放、丢失或损坏。

SQLite使用DELETE journal与FULL同步，只有主管进程写入；每样本结果是可恢复依据。可靠性依赖文件系统/平台确实实现所需持久化语义。数据库物理损坏、数据盘丢失不等价于普通断网；先保留现场，导出diagnose，不自行清空索引。

## 几何准备期间掉电

Runner在独立所有权记录中登记自己启动的SOP准备。如果重启后该case只有半成品且没有CASE_PREPARED标记，只有所有权与原始哈希相同时才把半成品重命名保留为 `.interrupted-prep-*`，重新从原始输入准备。未知来源的既有半成品、已完成的prepared目录不自动覆盖。
