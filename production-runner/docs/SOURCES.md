# 实现依据与证据边界

本包没有复制LBPM求解器或SOP源代码；运行时调用用户已有安装，并为SOP配置建立私有副本。以下为制作时核查的主要一手依据。

1. OPM/LBPM，固定commit 6d686d354e5b8140841d3601e4c8c0e4e4b77e48：
   - https://github.com/OPM/LBPM/blob/6d686d354e5b8140841d3601e4c8c0e4e4b77e48/models/ColorModel.cpp
   - https://github.com/OPM/LBPM/blob/6d686d354e5b8140841d3601e4c8c0e4e4b77e48/analysis/runAnalysis.cpp
   - https://github.com/OPM/LBPM/blob/6d686d354e5b8140841d3601e4c8c0e4e4b77e48/docs/source/userGuide/models/color/protocols/coreFlooding.rst
   核查内容：core flooding通量/参数关系、AA偶数步输出、分析/可视化入口、native restart写出内容。

2. Javis-101/lbpm-server-bootstrap，v1.0.3 / SOP v1.3.2：
   - https://github.com/Javis-101/lbpm-server-bootstrap/blob/v1.0.3/sop/bin/prepare_case.sh
   - https://github.com/Javis-101/lbpm-server-bootstrap/blob/v1.0.3/sop/bin/common.sh
   - https://github.com/Javis-101/lbpm-server-bootstrap/blob/v1.0.3/sop/bin/state_reports.py
   核查内容：--input/--case-dir接口、环境配置优先级、accepted与prepared状态、已有patchset身份。

3. NVIDIA MPS文档（检索2026-09-15）：
   - https://docs.nvidia.com/deploy/mps/when-to-use-mps.html
   - https://docs.nvidia.com/deploy/mps/mpsv2-interface.html
   - https://docs.nvidia.com/deploy/mps/595/when-to-use-mps.html
   核查内容：ps输出、terminate_client的返回0、先结束CUDA上下文再发主机信号、PID命名空间、异常客户端退出的共享风险。本包采用Legacy v2，不把新版v3语法猜测用于用户已运行的旧服务。

本包的R1阈值、Ca选择、128³几何、输出/归档/恢复要求来自用户在本对话确认的研究合同。它们不是LBPM官方默认协议或官方收敛证明。先前18个成功样本的回放仅支持该子集上的停止规则比较；既不证明1200输入全部稳定，也不证明2.0e-4与2.5e-4结果完全相同。

本地验证日志是软件工程证据，不是GPU原生终止/物理模型验证证据。
