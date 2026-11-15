# 图与文件对应

| 架构图位置 | 文件/实例 | 本次边界 |
|---|---|---|
| Main Decoder | rtl/cpu_control/main_decoder.sv / u_main_decoder | D 控制字、源使用、合法性 |
| ALU Decoder | rtl/cpu_control/alu_decoder.sv / u_alu_decoder | D ALU 操作及完整 funct 合法性 |
| Hazard / Forward | rtl/cpu_control/hazard_unit.sv / u_hazard_unit | load-use、EX A/B/Store 前递 |
| PC / Branch Control | rtl/cpu_control/branch_control.sv / u_branch_control | EX 比较与 redirect |
| Control Output / Pipeline Gating Matrix | rtl/cpu_control/pipeline_control.sv / u_pipeline_control | reset/redirect/stall 仲裁 |
| CPU CONTROL 框 | rtl/cpu_control/cpu_control.sv | 显式连接及复位/valid 安全限定 |
| CNN Driver Control | sw/drivers/cnn_driver_example.c | 普通 LW/SW 访问，无额外 Control 端口 |
| Datapath 框 | tb/models/control_datapath_stub.sv | 仅验证模型，不是负责人的生产 RTL |
| CNN 寄存器、DMA、CNN 框 | 未实现 | 属于 Datapath/CNN 负责人 |

共享编码：rtl/common/cpu_control_pkg.sv。没有已有 soc_pkg 可合并；未来并入团队包前逐项比对数字，避免维护冲突的枚举。

完整黄金表有 37 条基线指令，以及项目 NOP 与非法样例。`expected` 是 28 位打包控制字，字段从高到低为 alu[4]、src_a[2]、src_b[2]、regwrite、memread、memwrite、load_type[3]、store_type[2]、wb[2]、branch[3]、jump[2]、imm[3]、use1、use2。表内单列字段便于审核，不需要手算十六进制。

golden CSV 独立于 RTL，run_tests.py 只根据 mask 固定合法编码位、随机填写剩余指令位，不调用 DUT 生成期望。主 TB 逐字段比较并用手工机器码运行 stub 序列。内部 decode_t 用于整洁连线，不改变外部 logic ABI。

这是指定 RV32I 子集和项目简化行为，不是带完整异常/特权功能的 ISA 合规实现。ECALL/EBREAK 不触发 trap；普通 FENCE 仅在当前固定有序无未完成访存模型按 NOP，不能代表通用内存屏障。

ISA 语义依据：[RISC-V 官方 RV32I 规范](https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html)。C1 端口、枚举和安全 NOP/复位均为项目选择。
