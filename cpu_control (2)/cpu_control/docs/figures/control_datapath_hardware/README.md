# Control + Datapath 完整硬件连线图

绘图日期：2026-09-18。

- [完整高清图 PNG](control_datapath_all_hardware.png)
- [完整矢量图 SVG（推荐放大查线）](control_datapath_all_hardware.svg)
- [主通路概览 PNG](control_datapath_overview.png)
- [逐端口、逐网核对数据](hardware_audit.json)

完整图是**一张连续图**，包含主通路、全部实例端子、全部顶层组合逻辑、每根顶层网络的驱动和扇出，以及模块内部硬件节点的数据依赖和选择条件。所有信号标注位宽。同一 N 编号表示同一根网络，端子在图中分布显示。D 是 Datapath、C 是 Control、T 是仿真边界；G 表示跨顶层接口网络。

覆盖 150 根顶层网络、18 个生产子模块实例、49 组顶层组合逻辑。454 项端口和内部节点声明已与实际 mixed VCD 逐项核对，其中 435 项属于生产 Control/Datapath 层级，19 项是存储器/CNN MMIO 模型端口。生产层级唯一排除的非参数波形声明是寄存器堆复位循环的 integer `i`，它是仿真循环变量。寄存器堆的 `regs[0:31]` 没被 XSim 导出为数组波形，但其 32×32 bit 硬件及写回旁路已列入图中。

硬件画到 RTL 模块、状态寄存器、运算器、比较器和 MUX 层级，不是综合后的门级网表。模块内具体位操作和译码真值表以对应 RTL 为准。

来源：实际文件 `D:/QQ/face_recognition_soc_datapath_complete.zip`，压缩包 SHA-256 为 `7dcad4fb247b2b12a172009b63fd2f8c5506dbd57f4107793c95a4eb77ecd91c`。已逐文件确认本次使用的解压 Datapath 生产源码与压缩包原件一致。本方 Control 取自 `rtl/cpu_control`。

波形证据为 `build/runs/20260917_212107_968626_real_datapath_review/mixed/waves/real_control_datapath.vcd`。本次绘图**没有重新运行仿真**，没有修改双方生产 RTL。图中同步指令存储器模型、同步数据存储器模型与 CNN MMIO stub 标为橙色边界，不能据此宣称实体 SRAM、CNN 核心、DMA 或 FPGA 已实现/通过验证。

重新生成：

```powershell
python scripts/draw_control_datapath_hardware.py
```
