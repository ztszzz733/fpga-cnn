# CPU_CONTROL C1 接口逐端口契约

## 2026-10-08 六模块实际实现更新

当前板级顶层为 `rtl/soc/face_soc_top.sv`：六个平级大模块 `cpu_core / cnn / datasram / IEM / image_bridge / clock_unit`。CNN 的原生 mem_* 直接接 datasram，**不经过 CPU**；B 口仲裁和读写完成时序已写进 datasram 内部，不再实例化旧 CPU 存储子系统、独立适配器或系统 B 仲裁器。CPU A 口保留固定一拍，Control C1 和原 Datapath 计算模块不变。

UART 图像桥和时钟复位模块本次已有实际 RTL。图像桥为 IMIO 分块读写 + CRC32；时钟直通、复位三拍同步释放。封装 7 根数字 I/O，busy 灯是图像桥忙，不是 CNN busy。CNN 自带 MMIO：QUEUE_BASE=+0x08、TASK_COUNT=+0x18、START=0x3D；图像桥 error 保留，CNN 存储错误锁存 cnn_mem_fault，恢复需系统复位。

当前接线以 [顶层三组线小白说明](../SoC顶层连线与总体IO说明_小白版.md) 为准；另见 [六模块图](../docs/SoC芯片封装与内部IO层级连接图.md)、[修改说明](../docs/CNN实际代码整合修改说明_小白版.md)、[UART 协议](../docs/uart_image_bridge_protocol.md)、[本次验证](../docs/soc_six_module_verification_20261008.md)。编译清单 `rtl/filelists/system_cnn.f`；测试 `python scripts/run_cnn_integration.py`。

**下面保留原章节作为注明日期的历史记录。** 其中“CPU 存储子系统”“外置 sram_b_arbiter”“image_io_bridge / clock_reset_unit 待实现”、旧 IMG0 协议草案、旧 stub 和旧逐层 MMIO 不再是当前板级接线依据。CPU C1 基本规则仍适用；历史仿真不代表本次板级上板通过。

## C1 选择编码

| 信号 | 完整有效编码（其他保留） |
|---|---|
| pc_sel | 00=PC+4，01=EX PC+立即数（Branch/JAL），10=EX JALR 目标 |
| fwd_a/b/store | 00=ID/EX 原寄存器值，01=WB 最终值，10=MEM 非 Load 最终待写回值 |
| alu_src_a_sel | 00=前递 rs1，01=PC_e，10=0 |
| alu_src_b_sel | 00=前递 rs2，01=ImmExt_e |
| wb_sel_d | 00=ALU，01=Load，10=PC+4 |
| imm_type_d | 000=NONE，001=I，010=S，011=B，100=U，101=J |
| branch_type_d/e | 000=NONE，001=BEQ，010=BNE，011=BLT，100=BGE，101=BLTU，110=BGEU |
| jump_d/e | 00=NONE，01=JAL，10=JALR |
| load_type_d | 000=LB，001=LH，010=LW，100=LBU，101=LHU |
| store_type_d | 00=SB，01=SH，10=SW |
| alu_ctrl | 0=ADD，1=SUB，2=AND，3=OR，4=XOR，5=SLT，6=SLTU，7=SLL，8=SRL，9=SRA |

类型在对应使能为 0 时没有操作意义，但仍输出确定 0。PC 目标数值、寄存器最终数据、地址对齐错误均由 Datapath 实现，Control 没有这些数据输入。

## D1 对齐补充

- PC由Datapath持有；B1开发值固定为`RESET_PC=32'h0000_0000`，stub和显式接线样例已支持参数化。它不是新增Control端口；D/Z回签和最终系统归档仍待完成。stub的参数地址须位于其1 KiB IMEM内且4字节对齐。
- WB→ID 使用显式旁路：`valid_w && regwrite_w && rd_w!=0` 且源编号匹配时，ID 读取最终 WB 数据；x0 始终为零。真实 Datapath 待实现验证，stub 已有此行为。
- 实际寄存器写入以`valid_w && regwrite_w && rd_w!=0`限定。当前生产Datapath的Data SRAM请求在EX→MEM沿由E级valid、类型、地址命中和对齐条件门控；CNN MMIO写在MEM级由对应M级valid和写控制门控。两条路径不得统一套用同一个`valid_m && memwrite_m`表达式。重定向清除年轻指令，当前EX的Branch/JAL/JALR仍进入后级。
- 第一版非法指令、FENCE、ECALL、EBREAK 输出安全零控制，不触发访存、寄存器写入或重定向；不实现 trap。37 条 RV32I 指令范围见 [译码表](decode_table.csv)，不支持 M/Zmmul、CSR、特权、压缩和原子扩展，`mul_busy=0`。
- LB/LBU/SB 可访问任意字节地址；LH/LHU/SH 要求 2 字节对齐；LW/SW 要求 4 字节对齐；CNN 张量基地址要求 4 字节对齐。第一版不支持未对齐半字/字访问，没有异常反馈，软件和执行测试必须遵守。Control 仅译码类型，不能检查地址。
- 固定1周期同步IMEM/Data SRAM是B1开发契约；实体wrapper仍须按[存储时序契约](memory_timing_contract.md)完成边沿验收。MMIO第一版无额外等待。
- CNN九个32位端口位于Datapath/CNN边界。Datapath负责CPU SRAM A口、MMIO路由、CONTROL.start/soft_reset单周期脉冲及只读STATUS；CNN和图像桥各自通过70位请求、35位返回连接`sram_b_arbiter`，再访问SRAM B口。MMIO偏移为`0x00～0x20`，B1基址为`0x4000_0000`、窗口为`0x1000`。Control不增加CNN端口。

逐项处理结果及待确认内容见 [Control 对 D1 的项目对齐记录](control_reply_to_D1.md)。
