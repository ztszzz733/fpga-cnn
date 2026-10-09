# Control—Datapath 联调定向序列与期望控制信号

对应 Control v1.0 / CPU-CD-IF-C1，2026-09-14。以下序列来自现有 `tb/unit/tb_cpu_control.sv`，本次使用真实 Control + test-only Datapath stub 回归。接真实 Datapath 时保留指令和期望值，替换装载/提交观测适配；不能直接把 TB 的 stub 层级路径用于生产模块。

## 运行和采样约定

工程根目录运行：`python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot`。仅跑程序序列可用 `--test pipeline`。`tb/filelists/cpu_control.f` 包括 stub/TB；生产清单为 `rtl/filelists/cpu_control.f`。

除另说明，每个场景独立复位，RESET_PC=0、寄存器/测试内存清零，机器码按字节地址 0、4、8……装入。x0 恒零。周期指上升沿后的组合稳定区；真实同步 IMEM 的取指时间须按其返回协议适配，不能直接套用 stub 的总拍数。

编码：FWD_REG=00，FWD_WB=01，FWD_MEM=10；PC_NEXT=00，PC_TARGET=01，PC_JALR=10。门控字顺序固定为 `(pc_en, if_id_en, if_id_flush, id_ex_flush)`。

| 触发条件 | 门控字 | pc_sel | 其他期望 |
|---|---|---|---|
| rst_n=0（即使同时有重定向/暂停） | (0,0,1,1) | 00 | D 译码字、三路 fwd 全零；Datapath 下个上升沿同步清状态 |
| 有效 EX Branch taken / JAL | (1,1,1,1) | 01 | 更新 EX 目标；年轻指令清空，当前 E 自身继续进入 M |
| 有效 EX JALR | (1,1,1,1) | 10 | Datapath 目标为 (前递 rs1+imm)&~1 |
| D 消费者依赖 E Load 且无重定向 | (0,0,0,1) | 00 | 保持 PC/IF-ID，插入 E 气泡；M/W 继续 |
| 正常 / 分支不跳 | (1,1,0,0) | 00 | 正常推进 |

## 可装载的程序序列

| TB 场景 | 按地址顺序的 32 位机器码 | 关键控制信号和提交期望 |
|---|---|---|
| pipeline_load_use | `00002283 00228333`；预置 mem[0]=42、x2=7 | LW x5,0(x0) → ADD x6,x5,x2。一次暂停；消费者到 E 时 fwd_a=01、WB=42；x6=49。 |
| pipeline_load_store | `00002283 00502223`；mem[0]=91 | LW x5 → SW x5,4(x0)。一次暂停；SW 到 E 时 fwd_store=01、fwd_a=00；ALU B 仍选 IMM；mem[4]=91，仅一次 Store。 |
| pipeline_forward_store_and_WB_ID | `00900293 00b00293 00502223 00500333` | x5=9 → x5=11 → SW → ADD。SW 在 E 时 M/W 都写 x5，fwd_store=10，选较新的 11；后续 ADD 在 D 经 WB→ID 得到 11。mem[4]=11、x6=11，无暂停。 |
| pipeline_branch_flush | `00000663 06300393 00702223 00100413` | BEQ x0,x0,+12：E 级 pc_sel=01、双 flush；目标 PC=12，下一沿 D/E valid 清零；x7=0、Store=0、仅目标 x8=1 提交。 |
| pipeline_JAL_link | `00c002ef 06300393 00702223 00028313` | JAL x5,+12：D 级 jump=01、wb_sel=10、regwrite=1、uses=00；E pc_sel=01、双 flush；x5=4、目标消费者 x6=4，错误 Store=0。 |
| pipeline_ALU_branch_forward | `00100293 00528663 06300393 00702223 00100413` | ADDI x5,1 → BEQ x5,x5,+12。分支 E 时 fwd_a=fwd_b=10、pc_sel=01；目标地址 16、x8=1、Store=0。比较器必须使用前递值。 |
| pipeline_JALR_forward_mask | `01100293 00028367 06300393 00702223 00100413` | ADDI x5,17 → JALR x6,x5,0。JALR 在 E 时 fwd_a=10、pc_sel=10、双 flush；目标 16；x6=8、x8=1、x7=0、Store=0。 |
| pipeline_D1_safe_NOP | `00900293 0ff0000f 00000073 00100073 025282b3 00503223 00001067 00128313` | 合法 ADDI、FENCE、ECALL、EBREAK、非法 MUL/Store/JALR、合法 ADDI。六个安全 NOP 的 D 译码全零；x5=9、x6=10，合法寄存器提交仅 2 次，Store/重定向/暂停均为 0。 |
| stub_D1_RESET_PC_parameter | RESET_PC=0x40；0x00:`06300393`，0x40:`00000297`，0x44:`00128313` | 从 0x40 取 AUIPC，PC/指令配对，x5=0x40、x6=0x41、x7=0。两沿之间拉低 rst_n 后 PC 不立即改变，下个上升沿回到 0x40 并清全部 valid。 |

逐信号期望是对真实 Datapath 的验收要求；已有 TB 对程序结果和部分关键周期做断言，其余信号由单元定向测试和波形交叉核对，不表示每个表格单元都有独立程序级断言。

## LW→消费者边沿对照

| 上升沿后的区间 | D | E | M | W | 控制 / 数据 |
|---|---|---|---|---|---|
| E0→E1 | ADD | LW | 旧指令 | 旧指令 | pc_en=if_id_en=0，id_ex_flush=1，if_id_flush=0 |
| E1→E2 | ADD 保持 | 气泡 | LW | 旧指令 | 恢复推进；LW 数据须在 E2 前满足捕获条件 |
| E2→E3 | 后续 | ADD | 气泡 | LW | fwd_a=FWD_WB=01，wb_data=42 |

若在 E2 才向同步 SRAM 发请求，E2 捕获的不是新 Load 数据，不能照此宣布通过。真实 wrapper 须另给请求接受、返回有效、WB 捕获的边沿证据，见 [存储时序契约](memory_timing_contract.md)。

## 单元输入矩阵

| 测试源 | 输入场景 | 期望 |
|---|---|---|
| run_decode / decode_cases.csv | 37 条支持指令及非法/特殊编码 | 完整 28 位 D 控制字逐字段比对，包括两路 uses；valid_d=0 或 reset 时全零 |
| run_forward | E 两源同时匹配有效 M/W 写回 | M 非 Load 选 10；M 不匹配/无效时可选 W=01；E 无效、源未使用、源为 x0 时选 00 |
| run_forward 的 MEM Load 负条件 | E 消费仍在 M 的 Load，同时 W 有旧同名值 | fwd=00，不选 Load 地址或旧 WB；内部 operand_unready 被识别。这不是合法可执行状态，C1 没有对它自动补救的全局等待端口。 |
| run_load_use | Load→ALU/Store 地址/Store 数据/Branch/JALR | 真依赖暂停；ADDI 立即数字段、LUI/AUIPC/JAL 假源字段不暂停；rd_e=0、invalid D/E 不暂停 |
| run_branch / run_jump | 六类分支各 taken/not-taken，JAL/JALR，有符号与无符号比较不同 | pc_sel/双 flush 对应上表；D 分支不控制 E，valid_e=0 不重定向 |
| run_reset | rst_n、redirect、load_use 八种组合 | 仲裁器独立注入验证 reset > redirect > stall |
| stub_flush_over_enable / step_link | flush=1 且 enable=0，运行中复位、错误路径提交 | flush 优先；invalid M 无 Store，invalid W 无写回，x0 恒零 |

同步 IMEM 返回、LB/LH 等 LSU 数据行为、真实 MMIO 脉冲/只读 STATUS、CNN B 口 DMA 属于后续真实 Datapath/CNN 验收，本次 stub 不覆盖。
