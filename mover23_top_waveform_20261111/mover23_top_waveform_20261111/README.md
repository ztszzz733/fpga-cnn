# CPU＋CNN＋新存储顶层原始波形

解压 GitHub 波形 ZIP 后双击 `open_top_waveform.cmd`，优先用包内 `runtime/gtkwave64` 的便携版 GTKWave 打开 `mover23_top_raw.vcd` 和 `top_interconnect.gtkw`；在本机原工程目录则可回退使用工程内 GTKWave。视图只选取生产顶层模块之间的接口信号：时钟复位、CPU→IMEM、CPU→本地 RAM、CPU/图像桥/CNN MMIO、23 路 CNN→新存储、存储维护 CSR、PS GP0 与 MOVER→HP0/DDR。`top_milestones.tcl` 在原始时间轴上设置 A～H 导航标记。波形文件是 Verilator 在真实四帧六类算子系统仿真中直接记录的 VCD，`.gtkw` 与 Tcl 只决定显示和导航，没有构造波形数据。

- 仿真入口：`simulation/scripts/run_mover23_top_waveform.py`；生产顶层：`rtl/soc/ees331/face_soc_ees331_mover_top.sv`。
- 测试使用真实 CPU、23 客户端 CNN、新 tile RAM 和 DATA MOVER RTL；PS GP0/HP0 及 DDR 为测试模型。所有 23 路均已连接，但本次四帧图实际启动 15 路；全部 23 路的分组动态覆盖见另一次 `coverage23.json`，不在这份 VCD 中冒充已发生。
- 结果：PASS，44 任务、28,812 字节中间输出核对、342,441 周期；最终输出 SHA-256 为 `d961e0eb6f303e1f4e49a9792e92778ba2d4f5b4ee6600976d3417ee6f9d08f0`。
- 原始 VCD：660,940,287 字节，SHA-256 `8f5efcad718e2fe746934b0a73bc7e09427d648d0345ebe4954fab3a4cc14a27`。`result.json` 记录源码与输入样例哈希；`simulation.log` 保存原始 PASS 文本。

VCD 较大，GTKWave 首次打开需要等待读取。此包没有将历史 UART/旧缓存顶层的 VCD 当成本轮结果，也没有声称真实 PS7/板外 DDR 上板验证完成。
