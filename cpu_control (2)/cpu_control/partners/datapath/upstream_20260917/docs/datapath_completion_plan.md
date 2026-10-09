# CPU Datapath 实施前审查与补全计划

审查日期：2026-09-15  
审查阶段：只读实施前审查；未编译、未仿真、未修改既有工程文件。  
证据标记：`[DP]` 为 Datapath 主工程，`[C1]` 为 M 方正式 C1/生产 RTL，`[Z2]` 为 Z 方正式回复，`[CNN]` 为 `fpga-cnn-main.zip` 内 `mobilefacenet/` 新版工程，`[SPEC]` 为系统规格。

## 1. 审查范围

本次递归检查 `D:\FPGA\CPU`，只读核对 Datapath、M 方 Control、Z 方 CNN、接口回复、README、filelist、测试脚本、SystemVerilog 生产文件、存储器时序和 MMIO/SRAM 说明；仅执行 Verilator `--version`。未运行编译、仿真、格式化、综合或 Git 变更命令。

审查重点是判断现有基础模块能否复用、C1 的真实边界、固定一周期同步 IMEM/Data SRAM 的可实现时序，以及 CNN CPU 侧 MMIO 与 CNN SRAM Master 边界。[证据：用户任务说明；下列实际文件]

## 2. 实际找到的工程和文档路径

| 类别 | 实际路径 | 判定 |
|---|---|---|
| Datapath 主工程 | `D:\FPGA\CPU\face_recognition_soc` | 唯一符合预期且含当前基础 RTL/TB/脚本的主工程 `[DP]` |
| Datapath RTL | `face_recognition_soc\rtl\common`、`face_recognition_soc\rtl\cpu_datapath` | 9 个生产源文件 `[DP]` |
| Datapath TB/脚本 | `face_recognition_soc\tb\unit\tb_base_modules.sv`、`scripts\run_base_tests.sh` | 当前唯一基础验证入口 `[DP]` |
| M 方 Control 工程 | `D:\FPGA\CPU\incoming\cpu_control` | 生产 filelist 明确列出 7 个文件；排除 `build/backups`、`说明文档/原版` `[C1]` |
| C1 生产顶层 | `incoming\cpu_control\rtl\cpu_control\cpu_control.sv` | 48 端口组合 Control `[C1]` |
| C1 正式接口说明 | `incoming\cpu_control\docs\cpu_control_interface.md` | v1.0，M 方冻结 `[C1]` |
| D1 / M 回复 | `incoming\cpu_control\docs\inputs\CPU-DP-IF-D1.md`、`control_reply_to_D1.md`、`control_reply_to_P1.md` | D1 原文及 M 方正式接受记录 `[C1]` |
| 存储时序说明 | `incoming\cpu_control\docs\memory_timing_contract.md` | C1 固定时延约束 `[C1]` |
| Z 方正式回复 | `incoming\reply\发给CPU负责人_Z方对DZ1的正式回复_Z2.md` | 2026-09-15 / Z2 `[Z2]` |
| Z 方接口说明 | `incoming\reply\五级流水线CPU与MobileFaceNet加速器对接说明_v0.1.md`、`doc\发给Z负责人_CPU_Datapath对Z1接口提案的正式回复_DZ1.md` | Z1/DZ1 协商材料 |
| CNN 工程包 | `D:\FPGA\CPU\incoming\fpga-cnn-main.zip` | 包内 README 明确 `mobilefacenet/` 是新版；根 `rtl/` 是旧版，不能混编 `[CNN]` |
| CNN 新版生产目录（ZIP 内） | `fpga-cnn-main/mobilefacenet/rtl/` | 顶层 `mobilefacenet_accelerator_top.sv`，唯一 filelist `rtl/files.f` `[CNN]` |
| 系统规格 | `D:\FPGA\CPU\doc\face_recognition_soc_spec_v0.1.md` | 早期 v0.1 建议；冲突时低于正式 C1/Z2/生产 RTL `[SPEC]` |

仅用 `tar -tf` 和 `tar -xOf` 读取 ZIP，没有解压，也没有建立临时审查目录。Z2 文中所称交付包名 `MobileFaceNet_CPU_Z2_20260915.zip` 与现场文件名不同，但现场 ZIP 时间为 2026-09-15 19:45，Z2 为 19:46，且 ZIP 内新版顶层、九寄存器映射、基址和握手均与 Z2 一致；因此可用于本轮接口审查，但正式交付清单/哈希仍应由 Z 方补充确认。[证据：Z2 §6；ZIP README、顶层与 `accelerator_regs.sv`]

## 3. AGENTS.md 约束

找到的有效约束为 `D:\FPGA\CPU\incoming\cpu_control\AGENTS.md`；`说明文档\原版\AGENTS.md` 只约束其历史材料，`build\backups` 内副本不作为当前约束。

影响如下：M 方 C1 v1.0 已冻结本方端口/编码/控制规则；Control 必须保持组合逻辑；跨级状态由 Datapath 持有；真实 Datapath/CNN 未联调时不得宣称联调通过；不得修改生产 Datapath/CNN；网络代理约束与本次离线只读审查无实际动作关系。[证据：`incoming/cpu_control/AGENTS.md`]

## 4. 当前 Datapath 文件清单

| 路径 | 类型/作用 |
|---|---|
| `rtl/common/cpu_control_pkg.sv` | 当前 Datapath 控制编码 package |
| `rtl/cpu_datapath/alu.sv` | 组合 ALU |
| `rtl/cpu_datapath/imm_gen.sv` | I/S/B/U/J 立即数生成 |
| `rtl/cpu_datapath/pc.sv` | 参数化 PC 寄存器 |
| `rtl/cpu_datapath/regfile.sv` | 32×32 双读单写寄存器堆及 WB→ID 旁路 |
| `rtl/cpu_datapath/if_id_reg.sv` | IF/ID 流水寄存器 |
| `rtl/cpu_datapath/id_ex_reg.sv` | ID/EX 数据与控制流水寄存器 |
| `rtl/cpu_datapath/ex_mem_reg.sv` | EX/MEM 数据与控制流水寄存器 |
| `rtl/cpu_datapath/mem_wb_reg.sv` | MEM/WB 数据与控制流水寄存器 |
| `tb/unit/tb_base_modules.sv` | 上述模块联合单元 TB |
| `scripts/run_base_tests.sh` | Verilator 基础测试脚本 |
| `README.md` | 当前范围和未完成项说明 |

没有 Datapath filelist，也没有完整顶层、LSU、存储器/MMIO 模型或完整流水测试。[证据：`rg --files D:\FPGA\CPU`；`[DP] README`]

## 5. 已完成模块和测试状态

| 模块 | 状态 | 现有自动测试 | 明确缺口 | 复用结论 |
|---|---|---|---|---|
| `cpu_control_pkg` | 已有 | 通过使用各编码间接覆盖 | 未与 M 方同一物理文件编译；无保留码测试 | 数值可复用，文件须统一 |
| `alu` | 已有 | 10 种操作、零标志、溢出回绕、符号/无符号边界、移位 | default/未知控制、更多移位量掩码组合 | 可直接复用 |
| `imm_gen` | 已有 | I/S/B/U/J 正负和对齐、NONE | 各类型极值/随机指令位拼接 | 可直接复用 |
| `pc` | 已有 | reset、enable、hold、reset 优先 | 参数非零 RESET_PC | 可直接复用 |
| `regfile` | 已有 | 双读、写、禁写、x0、两读口同周期 WB 旁路 | 全地址/随机、多次 reset | 可直接复用 |
| `if_id_reg` | 已有 | reset、advance、hold、flush、flush>enable | redirect 延迟响应属于取指封装而非本模块 | 可直接复用 |
| `id_ex_reg` | 已有 | reset、flush、连续传递全部字段 | 无 enable（符合 C1）；valid=0 但非 flush 时字段仍可非零，顶层须以 valid 门控 | 可直接复用 |
| `ex_mem_reg` | 已有 | reset、边沿/连续传递全部字段 | 无 flush/enable；错误路径副作用需顶层验证 | 可直接复用（C1 不要求冻结 M/W） |
| `mem_wb_reg` | 已有 | reset、边沿/连续传递全部字段 | 未携带 `load_type`/地址低位；必须在 M 级先完成 load 抽取再传 `read_data_m` | 可直接复用，按此约束设计 LSU |

这里只确认 TB 源码确实包含上述检查；本轮禁止运行完整编译或仿真，因此不把 README 所述或历史声称升级为本机本轮 PASS。[证据：`tb_base_modules.sv`、`run_base_tests.sh`、`README.md`]

## 6. 现有模块端口及行为摘要

| 模块/参数 | 输入 | 输出 | reset / enable / flush / valid / 字段 |
|---|---|---|---|
| `alu` | `a[31:0], b[31:0], alu_ctrl[3:0]` | `result[31:0], zero` | 纯组合；default=0 |
| `imm_gen` | `instr[31:0], imm_type[2:0]` | `imm_ext[31:0]` | 纯组合；default=0 |
| `pc #(RESET_PC=0)` | `clk,rst_n,pc_en,next_pc[31:0]` | `pc_q[31:0]` | 上升沿同步低有效 reset；reset > enable > hold |
| `regfile` | `clk,rst_n,rs1/rs2[4:0],we,waddr[4:0],wdata[31:0]` | `rd1/rd2[31:0]` | 同步清 32 寄存器；写 x0 禁止；组合读；同周期同址旁路 |
| `if_id_reg` | `clk,rst_n,en,flush,valid_i,instr_i,pc_i,pc4_i` | 对应 `_o` | reset/flush 清全部；优先级 reset(与 flush 同分支) > flush > en > hold |
| `id_ex_reg` | `clk,rst_n,flush`；D 级 valid、PC/PC4、rd1/rd2/imm、rs1/rs2/rd、uses、ALU/源选、写回/访存/load/store/wb/branch/jump | 对应 E 级字段 | reset/flush 清全部；无 enable；否则每拍更新 |
| `ex_mem_reg` | `clk,rst_n`；E 级 valid、ALU、store data、PC4、rd、写回/访存/load/store/wb | 对应 M 级字段 | reset 清全部；无 flush/enable；每拍推进 |
| `mem_wb_reg` | `clk,rst_n`；M 级 valid、已处理 read data、ALU、PC4、rd、regwrite、wb | 对应 W 级字段 | reset 清全部；无 flush/enable；每拍推进 |

四组寄存器接口确实不统一：只有 IF/ID 有 enable+flush，ID/EX 只有 flush，EX/MEM 与 MEM/WB 都没有二者。这与 C1 “load-use 只保持 PC/IF-ID、冲刷 ID/EX，M/W 继续推进”一致，不应为风格统一而改写。[证据：四个 RTL；C1 `pipeline_control.sv`]

## 7. Control C1 接口完整映射表

方向均相对建议的 `cpu_datapath`。`clk/rst_n` 是双方公共输入。reset 时 Datapath 必须将反馈 valid/副作用/编号/指令清零或保证无效；stall 时仅保持 PC/IF-ID并冲刷 ID/EX；redirect 时清 IF/ID、ID/EX且旧 EX 继续进入 M。[证据：`cpu_control.sv`、`cpu_control_interface.md`、`pipeline_control.sv`]

| 信号 | DP 方向 | 宽度 | 级 | 含义及 Datapath 来源/使用 |
|---|---|---:|---|---|
| `clk` | input | 1 | 公共 | 流水时钟；Control 仅预留 |
| `rst_n` | input | 1 | 公共 | CPU 流水同步低有效复位；Control 组合安全限定 |
| `instr_d` | output | 32 | D | IF/ID 指令 |
| `rs1_d` | output | 5 | D | `instr_d[19:15]` |
| `rs2_d` | output | 5 | D | `instr_d[24:20]` |
| `rd_e` | output | 5 | E | ID/EX rd |
| `rd_m` | output | 5 | M | EX/MEM rd |
| `rd_w` | output | 5 | W | MEM/WB rd |
| `regwrite_m` | output | 1 | M | EX/MEM regwrite 元数据；副作用仍由 valid 限定 |
| `regwrite_w` | output | 1 | W | MEM/WB regwrite 元数据；真实 RF we=`valid_w&&regwrite_w&&rd_w!=0` |
| `memread_e` | output | 1 | E | ID/EX load 标记 |
| `cmp_eq_e` | output | 1 | E | 前递后 rs1==rs2 |
| `cmp_lt_e` | output | 1 | E | 前递后有符号小于 |
| `cmp_ltu_e` | output | 1 | E | 前递后无符号小于 |
| `mul_busy` | output | 1 | 公共 | RV32I 首版固定 0；不是隐藏 memory ready |
| `valid_d` | output | 1 | D | IF/ID valid |
| `valid_e` | output | 1 | E | ID/EX valid |
| `valid_m` | output | 1 | M | EX/MEM valid |
| `valid_w` | output | 1 | W | MEM/WB valid |
| `rs1_e` | output | 5 | E | ID/EX rs1 |
| `rs2_e` | output | 5 | E | ID/EX rs2 |
| `uses_rs1_e` | output | 1 | E | ID/EX use1 |
| `uses_rs2_e` | output | 1 | E | ID/EX use2 |
| `branch_type_e` | output | 3 | E | ID/EX branch type |
| `jump_e` | output | 2 | E | ID/EX jump type |
| `memread_m` | output | 1 | M | EX/MEM load 标记，防止把 load 地址作为 MEM 前递值 |
| `pc_sel` | input | 2 | E/IF | next-PC 选择；00 顺序、01 PC_e+imm、10 JALR |
| `pc_en` | input | 1 | IF | PC 写使能；load-use/reset 时 0 |
| `if_id_en` | input | 1 | IF/D | IF/ID 写使能；load-use/reset 时 0 |
| `if_id_flush` | input | 1 | IF/D | reset/redirect 清错误路径；优先于 enable |
| `id_ex_flush` | input | 1 | D/E | reset/redirect/load-use 插气泡 |
| `alu_ctrl` | input | 4 | D→E | D 级译码，必须先入 ID/EX |
| `alu_src_a_sel` | input | 2 | D→E | D 级 A 源选择，先入 ID/EX |
| `alu_src_b_sel` | input | 2 | D→E | D 级 B 源选择，先入 ID/EX |
| `fwd_a` | input | 2 | E | 当前 EX rs1 即时前递选择 |
| `fwd_b` | input | 2 | E | 当前 EX rs2 即时前递选择 |
| `fwd_store` | input | 2 | E | Store 数据即时选择，结果写入 EX/MEM `write_data` |
| `regwrite_d` | input | 1 | D→W | 随指令流水，最终控制写回 |
| `memread_d` | input | 1 | D→M | 随指令流水，M 级读 |
| `memwrite_d` | input | 1 | D→M | 随指令流水，M 级 store |
| `load_type_d` | input | 3 | D→M | LB/LH/LW/LBU/LHU |
| `store_type_d` | input | 2 | D→M | SB/SH/SW |
| `wb_sel_d` | input | 2 | D→W | ALU/load/PC+4 |
| `branch_type_d` | input | 3 | D→E | 分支类型，进入 ID/EX 后反馈 |
| `jump_d` | input | 2 | D→E | JAL/JALR，进入 ID/EX 后反馈 |
| `imm_type_d` | input | 3 | D | 驱动 ID 立即数生成，结果进入 ID/EX |
| `uses_rs1_d` | input | 1 | D→E | hazard 元数据 |
| `uses_rs2_d` | input | 1 | D→E | hazard 元数据 |

分类结论：前 48 项正好覆盖 2 个公共端口、24 个 Control 输入（DP 输出）及 22 个 Control 输出（DP 输入）。`redirect_target`、`branch_taken`、`jump_taken` 不是 C1 端口：目标由 Datapath 内部形成，是否重定向由 Control 内部 `branch_control` 产生并编码为 `pc_sel`。`load_use`、`redirect`、`operand_unready`、合法性信号是 Control 内部信号，不要求 Datapath 产生。IMEM/DMEM/MMIO、load 抽取、store strobe 和 fetch kill 是 Datapath 内部/外部存储边界，不应暴露给 Control。

## 8. Datapath 与 Control package 差异表

两份 SHA-256：Control `FC0F6CF...D0A3C`；Datapath `60EF561C...FE4C`，文件不相同。[证据：本轮 `Get-FileHash`]

| 类别 | Datapath 名称 | Control 名称 | 数值/宽度 | 结论 |
|---|---|---|---|---|
| PC 顺序 | `PC_SEQ` | `PC_NEXT` | 0 / 2 | 同值不同名 |
| ALU A | `ALUA_RS1/PC/ZERO` | `A_REG/PC/ZERO` | 0/1/2 / 2 | 同值不同名 |
| ALU B | `ALUB_RS2/IMM` | `B_REG/IMM` | 0/1 / 2 | 同值不同名 |
| Branch | `BR_BEQ/BNE/BLT/BGE/BLTU/BGEU` | `BR_EQ/NE/LT/GE/LTU/GEU` | 1..6 / 3 | 同值不同名；`BR_NONE=0` 同名同值 |
| Jump | `JUMP_NONE/JAL/JALR` | `J_NONE/J_JAL/J_JALR` | 0/1/2 / 2 | 同值不同名 |
| Forward | `FWD_REG/WB/MEM` | 同名 | 0/1/2 / 2 | 同名同值 |
| WB | `WB_ALU/LOAD/PC4` | 同名 | 0/1/2 / 2 | 同名同值 |
| Immediate | `IMM_NONE/I/S/B/U/J` | 同名 | 0..5 / 3 | 同名同值 |
| ALU | 10 个 `ALU_*` | 同名 | 0..9 / 4 | 同名同值 |
| Load | `LOAD_LB/LH/LW/LBU/LHU` | 无命名常量；decoder 直接传 `funct3` | 0/1/2/4/5 / 3 | 数值一致，符号集合不同 |
| Store | `STORE_SB/SH/SW` | 无命名常量；decoder 取 `instr[13:12]` | 0/1/2 / 2 | 数值一致，符号集合不同 |
| 结构体 | 无 | `decode_t` | packed 28 位（字段合计） | Control 独有内部类型 |

未发现“同名不同值”或位宽冲突；数值编码全部兼容。建议后续采用 M 方生产 package 为唯一物理源，在不改变任何已确认数值的前提下补入 Datapath 需要的兼容别名和 LOAD/STORE 名称，或统一重命名 Datapath 引用；`decode_t` 可保留为 Control 内部共享类型。最终文件须双方共同确认并只编译一次，不能继续维护两个哈希不同的同名 package。该建议依据 C1/P1 明确要求唯一 package，以及现场数值无冲突。

## 9. CNN MMIO CPU 侧接口要求

- CPU 侧端口：`mmio_addr[31:0]`、`mmio_wdata[31:0]`、`mmio_we`、`mmio_re`、`mmio_rdata[31:0]`、`mmio_ready`。
- 窗口为 `0x4000_0000..0x4000_0FFF`；只将对齐 LW/SW 且偏移为 `00,04,08,0C,10,14,18,1C,20` 的请求转发 CNN。
- SRAM 与 MMIO 译码互斥。非法/未对齐/不支持宽度或窗口内未实现偏移：不发 CNN 请求，load 返回 0，store 无副作用并在本地完成，不能等待 `mmio_ready`。
- `valid_m=0`、reset 或被冲刷指令不得产生 `mmio_we/re`；一条 M 级 SW 只提交一次。
- 新版 CNN 对合法请求组合 `ready=1`，不因 BUSY 等待。因此 C1 没有全流水 memory stall 仍可用于首版；建议把首版外部契约限定为合法 MMIO 零等待/同周期应答。若未来 `ready` 可拉低，必须共同升级停顿接口，不能局部冻结 M 级。
- `mem_addr/mem_wdata/mem_read/mem_write/mem_rdata/mem_ready` 是 CNN 访问共享 SRAM 的 Master/B 口协议，明确不属于本次 Datapath CPU 侧 MMIO 顶层接口。

[证据：Z2 §§2、5、8；ZIP `mobilefacenet/README.md`、`accelerator_regs.sv`、`mobilefacenet_accelerator_top.sv`]

## 10. 当前 Datapath 缺失功能清单

| 项目 | 状态 | 证据/备注 |
|---|---|---|
| `cpu_datapath` 顶层 | 尚未完成 | 无文件；README 明示 |
| PC next MUX | 尚未完成 | 仅有 PC 寄存器 |
| IF 请求 PC/返回 PC 配对 | 尚未完成 | 无 fetch wrapper |
| 同步 IMEM response valid | 尚未完成 | 无模型/状态 |
| redirect 后错路响应丢弃 | 尚未完成 | 无 kill 状态 |
| 寄存器堆完整连接 | 部分完成 | regfile 已有，顶层未接 |
| WB 数据 MUX | 尚未完成 | 无模块/顶层 |
| ALU 操作数 MUX | 尚未完成 | ALU 已有，MUX 未接 |
| EX forward MUX | 尚未完成 | Control 有选择，DP 无 MUX |
| branch comparator | 尚未完成 | 无比较器连接 |
| Branch/JAL target | 尚未完成 | 无 `pc_e+imm_e` 通路 |
| JALR target及 bit0 清零 | 尚未完成 | 无相关逻辑 |
| load 抽取/扩展 | 尚未完成 | 无 LSU |
| store 移位/byte enable | 尚未完成 | 无 LSU |
| SRAM 范围译码 | 尚未完成 | 无地址路由 |
| CNN MMIO 范围译码 | 尚未完成 | 无地址路由 |
| 未映射/非对齐策略 | 尚未完成 | 文档已有规则，RTL 无 |
| EX/MEM/WB 完整连接 | 部分完成 | 寄存器已有，顶层/存储数据配对无 |
| 五级 valid 传播 | 部分完成 | 四级寄存器有 valid，fetch valid 无 |
| stall/flush 优先级连接 | 部分完成 | 寄存器能力与 C1 匹配，顶层无 |
| Control 反馈 | 部分完成 | 字段存在，比较/顶层无 |
| IMEM/DMEM/MMIO 外部端口 | 尚未完成 | 无顶层 |
| Control stub | 尚未完成 | M 方 stub 不得复制为本工程正式 stub |
| IMEM/DMEM 模型 | 尚未完成 | 无文件 |
| CNN MMIO stub | 尚未完成 | 无文件 |
| 完整 Datapath TB/脚本 | 尚未完成 | 仅基础 TB/脚本 |
| CNN B 口适配器/双口 SRAM | 不属于本阶段 | 用户边界与 Z2 §5 |

## 11. 建议新增模块及文件路径

后续实现阶段（本轮未创建）建议新增：

| 路径 | 职责 |
|---|---|
| `rtl/cpu_datapath/cpu_datapath.sv` | 顶层、五级连接、C1/存储/MMIO 边界 |
| `rtl/cpu_datapath/lsu.sv` | load 抽取扩展、store 对齐/strobe、合法性 |
| `rtl/cpu_datapath/address_decoder.sv` | SRAM/MMIO/未映射互斥译码 |
| `rtl/cpu_datapath/fetch_adapter.sv` | 同步 IMEM 请求 PC/valid、缓冲、kill |
| `tb/models/control_stub.sv` | 仅按 C1 行为驱动，不实例化 M 方真实 Control |
| `tb/models/imem_model.sv` | 64 KiB 固定一周期同步读 |
| `tb/models/dmem_model.sv` | 256 KiB、小端、4-bit strobe、固定一周期读 |
| `tb/models/cnn_mmio_stub.sv` | 九寄存器、组合 ready、状态规则的可替换简化模型 |
| `tb/integration/tb_cpu_datapath.sv` | 独立系统级 scoreboard/assertion TB |
| `scripts/run_datapath_tests.sh` | Verilator 自动测试入口 |
| `docs/cpu_datapath_interface.md` | 完成后的端口与精确时序说明 |

简单 MUX、比较器和目标加法建议直接放在顶层组合逻辑，避免产生过碎模块；是否拆分不影响接口。

## 12. cpu_datapath 顶层建议端口表

### 12.1 基础、IMEM、Data SRAM、CNN MMIO

| 端口 | 方向 | 宽度 | 说明 |
|---|---|---:|---|
| `clk`,`rst_n` | input | 1 | 公共时钟/低有效同步 CPU 复位 |
| `imem_addr` | output | 32 | 字节地址，请求 PC |
| `imem_re` | output | 1 | 请求有效；固定一周期，不增外部 ready |
| `imem_rdata` | input | 32 | 请求后一个周期返回 |
| `dmem_addr` | output | 32 | 字节地址（可按 wrapper 要求对齐低两位） |
| `dmem_wdata` | output | 32 | 已移位 store 数据 |
| `dmem_wstrb` | output | 4 | 字节写使能 |
| `dmem_re`,`dmem_we` | output | 1 | 仅有效、合法 SRAM M 级访问 |
| `dmem_rdata` | input | 32 | 固定一周期同步读返回 |
| `mmio_addr`,`mmio_wdata` | output | 32 | CPU 侧完整字节地址/写数据 |
| `mmio_we`,`mmio_re` | output | 1 | 仅合法、有效、对齐 LW/SW |
| `mmio_rdata` | input | 32 | 合法寄存器读数据 |
| `mmio_ready` | input | 1 | 首版合法请求须及时为 1；不得用作 C1 未定义的全局 stall |

外部 IMEM response valid 不需要新增：固定一周期契约下由 `fetch_adapter` 内部请求 valid 延迟生成；若存储器未来可能无响应或变延迟，需升级接口而不是继续沿用此表。

### 12.2 Control Path

严格加入第 7 节全部 46 个非公共同名端口，方向按第 7 节；`clk/rst_n` 不重复。建议显式命名连接，禁止 `.*` 掩盖漏接。`mul_busy` 首版组合常量 0 是 C1 明确的 RV32I 行为。

## 13. 五级流水线数据流连接方案

1. IF：PC 输出请求地址；fetch adapter 保存请求 PC/PC+4/valid，固定一周期返回后送 IF/ID。
2. ID：IF/ID 指令导出 C1 反馈、读 regfile、生成 immediate；Control D 级控制与数据一起进入 ID/EX。
3. EX：先按 `fwd_a/b/store` 得到最新 rs1/rs2/store data；再按 ID/EX 源选控制形成 ALU 输入；同时做比较和三个目标地址；结果及副作用元数据进入 EX/MEM。
4. MEM：以 `valid_m` 门控地址译码；SRAM load 发同步请求、store 在该级一次提交；MMIO 仅合法 LW/SW。load 读字在 M 周期完成抽取/扩展并在 M→W 沿进入 `read_data_m` 路径。
5. WB：`wb_sel_w` 选择 ALU、load 或 PC+4；`valid_w&&regwrite_w&&rd_w!=0` 写 regfile，并作为 FWD_WB 与 WB→ID 旁路值。

[证据：现有四级寄存器字段；C1 §6/§8]

## 14. forwarding 方案

先前递寄存器源，再做 ALU source 选择。FWD_MEM 数据必须是 M 级“非 Load 最终待写回值”：普通 ALU 为 `alu_result_m`，JAL/JALR 为 `pc4_m`；绝不能前递 load 地址。FWD_WB 始终为最终 `wb_data`。优先级由 Control 保证 M 非 load > W > reg；M load 同名时遮挡 W 旧值。分支比较使用前递后的两个寄存器值；JALR 使用前递后 rs1；store data 用独立 `fwd_store` 后写入 EX/MEM。[证据：`hazard_unit.sv`、C1 §6]

## 15. stall 和 flush 方案

统一优先级：reset > EX redirect > load-use > normal。load-use：`pc_en=0`、`if_id_en=0`、`id_ex_flush=1`，EX load 继续到 M，M/W 继续推进。redirect：目标 PC 在该沿装入，IF/ID 与 ID/EX 清空，当前跳转/分支仍进 EX/MEM。所有真实副作用额外与对应级 `valid` 相与。

同步取指还有内部状态：IF/ID 停止时，已经返回但不能写入的数据必须进入一项 response buffer，或请求门控必须证明不会丢失；redirect 时清 buffer、清 pending valid，并丢弃旧路径延迟返回。该状态属于 Datapath，不修改 C1。[证据：C1 `pipeline_control.sv`、D1 回复第 9 项]

## 16. branch、JAL 和 JALR 方案

- `cmp_eq_e=(src1_fwd==src2_fwd)`；`cmp_lt_e=$signed(src1_fwd)<$signed(src2_fwd)`；`cmp_ltu_e=src1_fwd<src2_fwd`。
- Branch/JAL target=`pc_e+imm_e`；JALR target=`(src1_fwd+imm_e)&32'hFFFF_FFFE`。
- `pc_sel=PC_TARGET` 选前者，`PC_JALR` 选后者，顺序选当前取指流的 PC+4。
- JAL/JALR 自身 `pc4_e` 随流水到 WB，不能被 redirect flush 清掉；只清更年轻的 IF/ID、ID/EX。

[证据：C1 `branch_control.sv`、接口文档 §6.1/§7]

## 17. 同步 IMEM 时序方案

设请求地址在周期 N 稳定，并由 IMEM 在 N→N+1 上升沿采样；`imem_rdata` 在该沿后于周期 N+1 稳定。Datapath 同时把该请求的 PC、PC+4、request-valid 延迟一拍；IF/ID 在下一个可写沿捕获配对的 `{rdata,pc,pc4,valid}`。reset 释放后：第一个有效请求在首个允许沿被采样，返回在该沿后有效，并在再下一个上升沿进入 IF/ID（按寄存边界命名可称请求后一完整周期）；报告/波形必须以实际模型沿为准。

load-use 期间 PC/IF-ID 保持：禁止重复接受同一 PC 为新指令，并用一项 pending/response 缓冲保存已返回响应，解除暂停时只消费一次。redirect 沿取消旧 pending/response；可令 `imem_re=0` 避免该沿再采样旧 PC，目标 PC 装载后下一允许沿发目标请求。需要内部 `fetch_req_valid`、延迟 `fetch_rsp_valid`、`fetch_kill`/epoch 和一项缓冲；不需要将它们加到 C1。

## 18. 同步 Data SRAM 时序方案

load 地址在 EX 组合产生并进入 EX/MEM。进入 M 后地址整个周期稳定；SRAM 在 M 周期末上升沿采样地址，并在该沿后输出读字。下一 M→W 沿由 `mem_wb_reg` 捕获处理后的 load 数据，同时捕获的 `rd/regwrite/wb_sel` 来自同一条仍在 EX/MEM 的 load 元数据。这样消费者在 load-use 气泡后一拍进入 EX 时，可从 WB 最终数据前递。

实现时必须用时钟级 TB 证明没有 NBA“同沿采地址又同沿抓新数据”的错误假设。若实体 SRAM 定义为采样后再多一沿才可供 M→W 捕获，则 C1 的一气泡方案不成立，必须升级 memory stall/ready；本轮没有证据显示必须如此，因此当前是可实现但待模型验证，不构成阻塞。

store 在 M 级提交：`dmem_we=valid_m&&memwrite_m&&sram_hit&&aligned`，每条指令只在推进的一个 M 周期写一次；无效/错路/非法访问 strobe 为 0。[证据：C1 memory timing contract；Z2 §2]

## 19. load/store 处理方案

- SRAM 32 位读字按 `addr[1:0]` 右移 0/8/16/24；LB/LBU 取 8 位符号/零扩展，LH/LHU 按 bit1 取半字并扩展，LW 原字。
- 对齐：byte 任意，half 要 `addr[0]=0`，word 要 `addr[1:0]=0`。非法 load 返回 0，非法 store 无副作用；无 trap 是当前接口限制。
- SB：`wstrb=0001<<addr[1:0]`，数据低字节复制或左移至目标 lane；SH：`0011<<{addr[1],1'b0}`，数据低半字对齐；SW：`1111`。
- MMIO 只允许对齐 LW/SW，不允许 LB/LH/SB/SH。load type 在 M 级完成抽取，正好适配当前 MEM/WB 不保存 `load_type` 的结构。

## 20. SRAM 与 MMIO 地址译码方案

优先做互斥区域命中：SRAM=`0x0000_0000..0x0003_FFFF`；CNN window=`0x4000_0000..0x4000_0FFF`。窗口内再判断九个有效对齐寄存器偏移。只有有效且合法的 M 指令产生一个目标请求；不得同时置 dmem 与 mmio 请求。

未映射读/非法 MMIO 读在本地选择 0 并完成；未映射写无副作用。CNN 合法地址的 `mmio_ready` 依据现有 RTL组合及时响应。SRAM 256 KiB 是 Z2 当前确定性测试网络的建议且与任务基线一致，但实体双口 SRAM 和 B 口适配仍未冻结；当前 Datapath CPU A 口可按该范围实现参数化译码。[证据：Z2 §§2、4、5]

## 21. 仿真 stub 规划

- `control_stub.sv`：独立、test-only，按 48 端口 C1 做足够的 RV32I 译码/冒险选择以驱动 Datapath；不复制、包含或实例化 M 方生产 Control；真实 Control 联调另测。
- `imem_model.sv`：64 KiB、字节地址、小端、固定一周期同步读；断言对齐/越界，支持程序加载。
- `dmem_model.sv`：256 KiB、固定一周期读、四 byte enable、小端；记录写事务用于副作用检查。
- `cnn_mmio_stub.sv`：九个合法地址、合法请求及时 ready、状态粘滞及可配置完成延迟；不实现 CNN SRAM Master，不冒充真实计算。
- `tb_cpu_datapath.sv`：指令驱动+寄存器/内存 scoreboard、逐沿断言、超时非零退出；检查请求次数和错误路径零副作用。
- `run_datapath_tests.sh`：新建独立 build 子目录，显式 filelist，失败返回非零；基础回归与完整回归都运行。

## 22. 详细测试清单

| ID | 测试 | 必须检查 |
|---|---|---|
| DP-01 | 顺序执行 | PC/指令配对、每条只退休一次 |
| DP-02 | R 型算术逻辑 | 10 种 ALU 及边界 |
| DP-03 | I 型 | 9 种 immediate 运算/移位量 |
| DP-04 | LUI/AUIPC | zero/PC 源和 U immediate |
| DP-05 | JAL | 目标、PC+4 写回、flush |
| DP-06 | JALR | 前递 rs1、bit0 清零、PC+4 |
| DP-07 | 六分支 | taken/not-taken、有符号/无符号 |
| DP-08 | EX/MEM 前递 | 非 load 及 JAL PC+4 |
| DP-09 | MEM/WB 前递 | ALU/load/PC+4 最终值 |
| DP-10 | 双源前递 | A/B 来自不同级、M 优先 W |
| DP-11 | load-use | 恰一气泡、WB 数据正确 |
| DP-12 | WB→ID | 同周期同址读新值、x0 排除 |
| DP-13 | pipeline flush | IF/ID、ID/EX 清空，旧 EX 保留 |
| DP-14 | valid | D/E/M/W 传播与副作用门控 |
| DP-15 | LB/LH/LW/LBU/LHU | 四 lane、符号/零扩展、对齐 |
| DP-16 | SB/SH/SW | 数据移位、所有 strobe、对齐 |
| DP-17 | SRAM | 边界地址、固定一周期配对 |
| DP-18 | CNN MMIO | 九寄存器对齐 LW/SW、ready |
| DP-19 | 非法/未映射 | 读 0、写无效、无永久等待 |
| DP-20 | reset 优先 | PC/valid/副作用/pending 清除 |
| DP-21 | stall vs flush | redirect 优先于 load-use |
| DP-22 | IMEM 延迟响应 kill | redirect 后旧响应不入 IF/ID |
| DP-23 | 错路 RF | 不写寄存器 |
| DP-24 | 错路 SRAM | `dmem_we/wstrb=0` |
| DP-25 | 错路 MMIO | `mmio_we=0`、START 不触发 |
| DP-26 | fetch stall | 不丢、不重、不跳过指令 |
| DP-27 | 连续 stores | 每条恰一次，不重复提交 |
| DP-28 | M-load 遮挡 W | 不前递较老 WB 同名值 |
| DP-29 | 保留/非法指令 | 安全 NOP、无副作用 |
| DP-30 | 复位释放首指令 | 精确记录首次请求/响应/IF-ID 沿 |

## 23. 建议实现顺序

1. 共同确定唯一兼容 package 文件，保持全部数值不变。
2. 实现并单测 `lsu.sv` 与 `address_decoder.sv`。
3. 实现并逐沿单测 `fetch_adapter.sv` 和同步 IMEM 模型。
4. 搭建 `cpu_datapath.sv`：WB→ID、D→E 控制、forward、比较/目标、M/W。
5. 加入 C1 形状的独立 Control stub，完成无存储流水测试。
6. 加入同步 dmem/MMIO stub，验证 load-use、store 和地址路由。
7. 完成 30 项回归与文档；之后才进行真实 Control 结构联调。
8. CNN 真实 MMIO、B 口 SRAM、SoC 顶层和 FPGA 工作保持在后续独立阶段。

## 24. 已确认事项

- Datapath 主工程唯一定位为 `face_recognition_soc`；9 个基础生产文件存在。
- C1 为 48 个端口，M 方 v1.0 已冻结其本方端口/编码/控制规则；Control 是组合逻辑。
- 两份 package 数值无冲突，差异是命名、LOAD/STORE 符号和 `decode_t`。
- 现有流水寄存器能力与 C1 load-use/redirect 推进方式兼容。
- Z2 确认 MMIO 基址、4 KiB window、九个地址、对齐 LW/SW、非法访问本地完成和合法请求及时 ready。
- ZIP 内 `mobilefacenet/` 是新版生产工程；其顶层为 12 个外部接口信号加 clk/rst_n（MMIO 六信号、RAM Master 六信号），与 Z2 描述一致。
- Data SRAM 当前首轮建议/基线是 256 KiB、`0..0x3FFFF`；CPU A 口固定一周期读。

## 25. 待确认事项

- 将哪一份经双方确认的 package 作为唯一物理文件，以及是否用兼容别名还是统一改引用。
- 现场 CNN ZIP 文件名/内容清单与 Z2 所称正式包名不一致，需 Z 方给出正式 SHA-256 或确认现场 ZIP 即交付版本。
- IMEM/实体 Data SRAM 的确切模块端口、采样沿、输出寄存器配置；须用计划部署模型验证本文第 17/18 节。
- 256 KiB 地址图、CPU 4 KiB 数据/栈候选区、双口同址冲突与全局复位分发仍需系统级归档。
- `mmio_ready` 未来是否永远维持现有及时响应契约；若可等待，C1 必须升级全流水停顿机制。
- 完整 Datapath 对 C1 的正式回签尚未在生产 RTL 顶层上完成；本报告只证明可映射。

## 26. 是否存在实现阻塞

结论：**不存在阻止进入“固定一周期存储器 + 及时响应 MMIO + test-only stubs”的 Datapath 补全阶段的硬阻塞；可以不等待 M、Z 进一步回复开始实现。** C1 已足够明确，Z2/MMIO 与生产 RTL一致，package 数值无冲突，现有寄存器结构可支持一拍 load-use。

但以下是进入真实三方集成前必须解决的阻塞：唯一 package 物理文件冻结；实体 IMEM/SRAM 边沿验证；CNN 正式包哈希确认；双口 SRAM/B 口适配器与全局复位/同址冲突冻结。若实际 SRAM 不能在 load 的 M 周期末提供可由 M→W 正确捕获的数据，或 MMIO 改为可变等待，则必须停止并升级 C1，不能靠当前 Datapath 局部补丁解决。

## 27. 明确排除的集成工作

本计划不合入或修改 M 方真实 Control、Z 方真实 CNN；不建完整 SoC 顶层；不实现 CNN B 口适配器或真实双口 SRAM；不做三方联调、FPGA 综合、布局布线、约束、上板、真实模型精度或网络后处理验证。M/Z RTL 仅作为接口证据。

## 28. Verilator 版本检查结果

| 项目 | 结果 |
|---|---|
| 可执行文件 | `C:\msys64\ucrt64\bin\verilator_bin.exe`，存在且可直接调用 |
| 命令 | `& 'C:\msys64\ucrt64\bin\verilator_bin.exe' --version` |
| 输出 | `Verilator 5.050 2026-07-01 rev vUNKNOWN-built20260702` |
| 退出码 | 0 |
| 环境警告 | 无；`rev vUNKNOWN` 是版本字符串内容，未伴随警告或失败 |

未调用 Bash，未编译任何 RTL。

## 29. 本步骤执行过的命令

以下为语义等价记录（PowerShell 输出编码显式设为 UTF-8）：

1. `Get-Content -Raw -Encoding UTF8 <用户附件>`
2. `rg --files -g 'AGENTS.md' D:\FPGA\CPU`
3. `Get-Content -Raw` 读取适用 `AGENTS.md`
4. `rg --files D:\FPGA\CPU` 并筛选 README/filelist/脚本/Markdown/SV/ZIP
5. `Get-Content -Raw` 读取 Datapath 9 个 RTL、TB、脚本和 README
6. `Get-Content -Raw` 读取 M 方生产 RTL、C1/D1/P1/时序说明
7. `tar -tf D:\FPGA\CPU\incoming\fpga-cnn-main.zip`
8. `tar -xOf <zip> <entry>` 只读查看新版 README、顶层、寄存器、memory master、filelist
9. `Get-Content -Raw` 读取 Z1/DZ1/Z2 与系统规格
10. `Get-Item` 查看关键文件时间/大小
11. `Get-FileHash -Algorithm SHA256` 比较两份 package
12. `& 'C:\msys64\ucrt64\bin\verilator_bin.exe' --version`
13. `Test-Path` 检查目标 docs/报告是否存在
14. `New-Item -ItemType Directory D:\FPGA\CPU\face_recognition_soc\docs`
15. 使用补丁工具新建本报告

没有执行 Git、下载、安装、解压、编译、仿真、格式化、删除、移动或重命名命令。

## 30. 文件变更记录

本步骤只新建：

- 目录：`D:\FPGA\CPU\face_recognition_soc\docs`
- 文件：`D:\FPGA\CPU\face_recognition_soc\docs\datapath_completion_plan.md`

本步骤未修改任何原有 RTL、testbench、脚本或接口文件。
