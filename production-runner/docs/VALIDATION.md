# Runner 1.0.1 工程验证边界

本版本修复原交付 ZIP 的 F-01、F-02，新增统一结果信任检查及回归。测试报告记录在 `validation.json`，完整本地日志见 `local-test-results.txt`；远端完整结果以本次 GitHub Actions 执行日志为准。

## 测试分层

1. 原 41 项 Runner 工程测试：路径/协议、真实文件/SQLite/inotify、CPU 模拟的动态队列、在线停止、异常与压缩恢复。
2. 原审查两项故障注入：在原 1.0.0 上重现失败；修复后重新执行。
3. 三项子进程恢复回归：损坏结果不导出有效；已故障 epoch 的待提交 outcome 和已有 complete marker 均被隔离。
4. 十三项快速信任边界回归：缓存失效、结果/源身份、完成标记、缺文件、已知失败状态、故障时间、已有空故障记录及提交路径。
5. 两项真实 SOP 源码接口检查：核对五个脚本的 Git blob 身份，调用实际 prepare_case/common/prepare_rock_case/state_reports/verify_case_contract。只有 MPI 分解被 CPU 模拟。
6. 可复现打包：连续两次字节相同，ZIP 及每个成员 SHA256 验证。

独立 ZIP 自检若找不到原仓库 SOP，会明确 skip 第5层。源码 checkout 的 CI 包含 SOP；也可通过 `LBPM_BOOTSTRAP_SOURCE` 指向它。

## 不包含的验证

没有执行真实 NVIDIA GPU/MPS/CUDA、真实 LBPM 碰撞推进或 1200 个研究输入；没有重编译 Installer 依赖。没有验证研究数据的压缩比或科学稳定性。不得把 CPU 工程测试、原 Bootstrap v1.0.3 的验证记录，或本次 `READY_FOR_PRODUCTION` 转述为新 Runner 的真实 GPU 认证。

首台机器的 prepare 必须读取实际软件身份/验收报告。首次原生运行必须检查 MPS 安全终止证据、同行推进和结果提交。未知 MPS 接口不使用盲目 kill 替代。

## 故障与存储范围

数据校验失败时完成标记进入 quarantine 并从有效索引排除，原文件保留。MPS epoch 时序检查在所有提交/复用入口一致。文件哈希缓存仅在同一进程且 inode、大小、mtime、ctime 未变时复用；它依赖可信文件系统元数据，不是对恶意存储的证明。跨进程 resume 重新哈希。

任务级恢复不等于分布函数续算。归档保留全部已产生检查点；压缩包经逐文件无损哈希校验后才释放冗余 RAW；同盘归档不是异地备份。

## 重复运行观察（未隐藏的失败记录）

最终源码完整套件为 60/60，通过。另一次在并行负载下执行的较早打包快照（59项）有1项恢复测试进入保护性 PAUSED，而测试期望 COMPLETE；该次原始 fixture 清理了临时目录，准确暂停原因没有留存。随后对同一恢复用例连续重复4次均通过，尚未重现。日志 `concurrent-old-package-repeat.txt` 与 `repeated-recovery-tests.txt` 一并保留。不能因此声称“所有重复测试均通过”，也不能把未重现推断成真实 GPU 没有问题。部署仍是候选；完整仓库 CI 和首机 MPS 证据仍未取得。
