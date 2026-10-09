# CPU_CONTROL C1 接口逐端口契约

文档编号：CPU-CD-IF-C1。2026-09-14 已收到 [CPU-DP-IF-D1](inputs/CPU-DP-IF-D1.md)：Datapath 原则接受 C1，Control 项目按 D1 对齐；存储器时序及公共地址仍待三方冻结，真实直连未验证。本次不改变 C1 端口、编码、流水级或采样契约，沿用 C1 接口版本。

顶层共 48 个普通 logic 端口：26 个输入（含公共 clk/rst_n）、22 个输出。Datapath 对应信号方向相反，clk/rst_n 仍为双方公共输入；其 IMEM、Data SRAM 和 CNN 端口不计入此表。
clk 无内部时序用途；rst_n 低时组合输出立即取安全值，不表示 Control 内有异步复位寄存器。Datapath/stub 流水状态在上升沿同步检查低有效复位，优先级为复位 > flush > enable > 保持；系统复位方式仍待三方统一。

| 端口 | 方向（相对 Control） | 位宽 | 阶段 | 产生位置 | 采样/使用位置 | 复位或无效约定 | 来源 |
|---|---|---:|---|---|---|---|---|
| `clk` | input | 1 | 公共 | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `rst_n` | input | 1 | N | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `instr_d` | input | 32 | D | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `rs1_d` | input | 5 | D | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `rs2_d` | input | 5 | D | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `rd_e` | input | 5 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `rd_m` | input | 5 | M | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `rd_w` | input | 5 | W | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `regwrite_m` | input | 1 | M | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `regwrite_w` | input | 1 | W | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `memread_e` | input | 1 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `cmp_eq_e` | input | 1 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `cmp_lt_e` | input | 1 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `cmp_ltu_e` | input | 1 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `mul_busy` | input | 1 | 公共 | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | 原规格 |
| `valid_d` | input | 1 | D | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | C1 补充 |
| `valid_e` | input | 1 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | C1 补充 |
| `valid_m` | input | 1 | M | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | C1 补充 |
| `valid_w` | input | 1 | W | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | C1 补充 |
| `rs1_e` | input | 5 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | C1 补充 |
| `rs2_e` | input | 5 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | C1 补充 |
| `uses_rs1_e` | input | 1 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | C1 补充 |
| `uses_rs2_e` | input | 1 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | C1 补充 |
| `branch_type_e` | input | 3 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | C1 补充 |
| `jump_e` | input | 2 | E | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | C1 补充 |
| `memread_m` | input | 1 | M | Datapath 对应流水级（clk/rst_n 为公共输入） | 组合 Control | valid/副作用/编号清 0；rst_n=0；instr 清 0；mul_busy 固定 0 | C1 补充 |
| `pc_sel` | output | 2 | E 决策/前级更新 | Pipeline Control | PC/IF-ID/ID-EX | flush=1；enable=0；pc_sel=00 | 原规格 |
| `pc_en` | output | 1 | E 决策/前级更新 | Pipeline Control | PC/IF-ID/ID-EX | flush=1；enable=0；pc_sel=00 | 原规格 |
| `if_id_en` | output | 1 | E 决策/前级更新 | Pipeline Control | PC/IF-ID/ID-EX | flush=1；enable=0；pc_sel=00 | 原规格 |
| `if_id_flush` | output | 1 | E 决策/前级更新 | Pipeline Control | PC/IF-ID/ID-EX | flush=1；enable=0；pc_sel=00 | 原规格 |
| `id_ex_flush` | output | 1 | E 决策/前级更新 | Pipeline Control | PC/IF-ID/ID-EX | flush=1；enable=0；pc_sel=00 | 原规格 |
| `alu_ctrl` | output | 4 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | 原规格 |
| `alu_src_a_sel` | output | 2 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | 原规格 |
| `alu_src_b_sel` | output | 2 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | 原规格 |
| `fwd_a` | output | 2 | E 即时 | Hazard | EX 前递 MUX | 00 | 原规格 |
| `fwd_b` | output | 2 | E 即时 | Hazard | EX 前递 MUX | 00 | 原规格 |
| `fwd_store` | output | 2 | E 即时 | Hazard | EX 前递 MUX | 00 | 原规格 |
| `regwrite_d` | output | 1 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | 原规格 |
| `memread_d` | output | 1 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | 原规格 |
| `memwrite_d` | output | 1 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | 原规格 |
| `load_type_d` | output | 3 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | 原规格 |
| `store_type_d` | output | 2 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | 原规格 |
| `wb_sel_d` | output | 2 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | 原规格 |
| `branch_type_d` | output | 3 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | 原规格 |
| `jump_d` | output | 2 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | 原规格 |
| `imm_type_d` | output | 3 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | C1 补充 |
| `uses_rs1_d` | output | 1 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | C1 补充 |
| `uses_rs2_d` | output | 1 | D | 译码器 | ID/EX（imm_type 驱动 D 级 ImmGen） | 0 | C1 补充 |

有效 D 指令必须有 rs1_d=instr_d[19:15]、rs2_d=instr_d[24:20]。验证检查这两个等式。
E 的 rs/uses/branch/jump 必须来自同一 ID/EX 指令；M/W 控制与对应 rd 和 valid 同步。
所有 D 控制须先进入 ID/EX；M/W 所需字段继续随指令前进。禁止隐藏影子流水寄存器。
编码唯一来源为 `rtl/common/cpu_control_pkg.sv`，双方编译同一文件且只编译一次；decode_table.csv 是检查用表格。D1 已原则接受 C1 编码，pc_sel 与原表一致；交付归属及共享版本仍需双方记录。
前递先选择 rs1/rs2，再用 ALUSrc 选择 ALU 输入；分支比较和 Store 数据使用前递寄存器值。
fwd_store 是 EX 级 Store rs2 的选择，随 WriteData 进入 EX/MEM，不是 MEM 旁路。
rst_n=0 或 valid_d=0 时完整译码字为 0；其余级 valid=0 时不产生前递/重定向。
非法指令内部 illegal_d=1，控制字为 0；未增加 trap 端口。mul_busy 非零不在支持域。

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

- PC 由 Datapath 持有，采用参数 `RESET_PC`、默认 `32'h0000_0000` 作为开发建议；stub 和显式接线样例已支持该参数。它不是新增 Control 端口，最终复位地址待三方确认。stub 的参数地址须位于其 1 KiB IMEM 内且 4 字节对齐。
- WB→ID 使用显式旁路：`valid_w && regwrite_w && rd_w!=0` 且源编号匹配时，ID 读取最终 WB 数据；x0 始终为零。真实 Datapath 待实现验证，stub 已有此行为。
- 实际寄存器写入以 `valid_w && regwrite_w && rd_w!=0` 限定；SRAM/MMIO 写入以 `valid_m && memwrite_m` 限定。重定向清除年轻指令，当前 EX 的 Branch/JAL/JALR 仍进入后级。
- 第一版非法指令、FENCE、ECALL、EBREAK 输出安全零控制，不触发访存、寄存器写入或重定向；不实现 trap。37 条 RV32I 指令范围见 [译码表](decode_table.csv)，不支持 M/Zmmul、CSR、特权、压缩和原子扩展，`mul_busy=0`。
- LB/LBU/SB 可访问任意字节地址；LH/LHU/SH 要求 2 字节对齐；LW/SW 要求 4 字节对齐；CNN 张量基地址要求 4 字节对齐。第一版不支持未对齐半字/字访问，没有异常反馈，软件和执行测试必须遵守。Control 仅译码类型，不能检查地址。
- 固定 1 周期同步 IMEM/Data SRAM 和 MMIO 无额外等待是 D1 建议，尚未构成真实 wrapper 验收；具体边沿和请求/返回配对见 [存储时序契约](memory_timing_contract.md)。
- CNN 九个 32 位端口位于 Datapath/CNN 边界。Datapath 负责 CPU SRAM A 口、MMIO 路由、CONTROL.start/soft_reset 单周期脉冲及只读 STATUS；CNN DMA 使用 SRAM B 口。MMIO 偏移为 0x00～0x20，`CNN_MMIO_BASE` 未冻结，Control 不增加 CNN 端口。

逐项处理结果及待确认内容见 [Control 对 D1 的项目对齐记录](control_reply_to_D1.md)。
