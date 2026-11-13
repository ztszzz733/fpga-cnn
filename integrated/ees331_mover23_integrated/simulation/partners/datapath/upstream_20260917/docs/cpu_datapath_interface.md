# 完整 RV32I CPU Datapath 接口与验证

日期：2026-09-15。状态：Datapath 主体与 test-only 集成验证完成；尚未连接 M 方真实 Control 或 Z 方真实 CNN。

## 1. 参数与外部端口

`cpu_datapath` 参数：`RESET_PC=0x00000000`、`SRAM_BASE=0x00000000`、`SRAM_SIZE=0x00040000`、`CNN_MMIO_BASE=0x40000000`、`CNN_MMIO_SIZE=0x1000`。

基础端口为 `clk/rst_n`。IMEM 为 `imem_addr/imem_re/imem_rdata`；Data SRAM 为 `dmem_addr/dmem_wdata/dmem_wstrb/dmem_re/dmem_we/dmem_rdata`；CNN CPU侧为 `mmio_addr/mmio_wdata/mmio_re/mmio_we/mmio_rdata/mmio_ready`。IMEM和Data SRAM无 ready，MMIO首版要求合法请求零等待。

## 2. C1 48端口核对

已逐项对照 M 方生产 `cpu_control.sv`：总数48，包括公共输入 `clk/rst_n`、24个 Datapath→Control和22个 Control→Datapath端口，名称、方向和位宽均一致。

| 方向 | 逐项映射 |
|---|---|
| DP→Control，D | `instr_d[31:0]`, `rs1_d[4:0]`, `rs2_d[4:0]`, `valid_d` |
| DP→Control，E | `rd_e[4:0]`, `memread_e`, `cmp_eq_e`, `cmp_lt_e`, `cmp_ltu_e`, `valid_e`, `rs1_e[4:0]`, `rs2_e[4:0]`, `uses_rs1_e`, `uses_rs2_e`, `branch_type_e[2:0]`, `jump_e[1:0]` |
| DP→Control，M/W | `rd_m`, `rd_w`, `regwrite_m`, `regwrite_w`, `valid_m`, `valid_w`, `memread_m`；编号均5位 |
| DP→Control，公共 | `mul_busy=0` |
| Control→DP，流水 | `pc_sel[1:0]`, `pc_en`, `if_id_en`, `if_id_flush`, `id_ex_flush` |
| Control→DP，D译码 | `alu_ctrl[3:0]`, `alu_src_a_sel[1:0]`, `alu_src_b_sel[1:0]`, `regwrite_d`, `memread_d`, `memwrite_d`, `load_type_d[2:0]`, `store_type_d[1:0]`, `wb_sel_d[1:0]`, `branch_type_d[2:0]`, `jump_d[1:0]`, `imm_type_d[2:0]`, `uses_rs1_d`, `uses_rs2_d` |
| Control→DP，EX即时 | `fwd_a[1:0]`, `fwd_b[1:0]`, `fwd_store[1:0]` |

真实连接时，实例化 M 方 `cpu_control` 并按同名端口显式连接；双方只编译 Datapath 工程的唯一 `cpu_control_pkg.sv`。本次测试没有复制、include或实例化 M RTL。

## 3. 五级流水与PC

IF由参数化 `pc`、`fetch_adapter` 和 `if_id_reg`组成。顺序目标为 `pc_q+4`，branch/JAL目标为 `pc_e+imm_e`，JALR目标为 `(src1_fwd_e+imm_e)&0xFFFFFFFE`。非法 `pc_sel`确定输出0。fetch adapter保存同步IMEM请求PC/PC+4；IF/ID在 `if_id_en=1` 时即使 `fetch_valid=0` 也写入 bubble。reset/flush沿用现有模块优先级。

ID直接输出指令及rs编号，`regfile`组合读，`imm_gen`按C1类型扩展；D级数据和全部控制进入 `id_ex_reg`，`id_ex_flush`插入bubble。E结果进入既有 `ex_mem_reg`，M结果进入既有 `mem_wb_reg`。valid元数据不被顶层提前清零，但寄存器、SRAM和MMIO副作用分别由对应级valid门控。

WB选择为 ALU结果、已处理load数据或PC+4，非法选择为0。RF写使能严格为 `valid_w && regwrite_w && rd_w!=0`；同一 `wb_data_w`供写回、WB前递和既有WB→ID旁路。

## 4. 前递、比较与跳转

E级独立形成 `src1_fwd_e/src2_fwd_e/store_data_fwd_e`。`FWD_REG`取ID/EX值，`FWD_WB`取最终WB值，`FWD_MEM`取M级非load的最终值。M级候选只对 `WB_ALU`和`WB_PC4`有效；load或非法选择确定为0，杜绝把load地址作为结果。

ALU A选择寄存器/PC/0，B选择寄存器/立即数，非法值为0。分支比较使用前递后的两个寄存器源，分别产生相等、有符号小于和无符号小于。JAL/JALR通过 `WB_PC4`写链接寄存器；机器码测试检查两者PC+4，并断言JALR目标bit0为0。

## 5. Data SRAM时序和LSU

所有SRAM请求在E级产生，地址为ALU结果。E级 `address_decoder` 和 `lsu`生成命中、类型/对齐、移位写数据和strobe：

`dmem_re = rst_n && valid_e && memread_e && sram_hit_e && load_type_valid_e && load_aligned_e`

`dmem_we = rst_n && valid_e && memwrite_e && sram_hit_e && store_type_valid_e && store_aligned_e`

`dmem_wstrb`仅在写请求有效时输出实际strobe，否则为0。store数据先通过独立 `fwd_store`。请求在EX→M沿由同步模型采样/提交。

load的地址、低位、type、rd、regwrite和wb选择由EX/MEM配对；同步 `dmem_rdata` 在M周期稳定，M级第二个 `address_decoder/lsu`完成LB/LH/LW/LBU/LHU抽取扩展，再于M→W沿保存。LB/LBU任意lane，LH/LHU要求2字节对齐，LW要求4字节对齐；SB任意lane、SH要求2字节、SW要求4字节。非法、非对齐或越界读返回0且不请求，store无副作用。

## 6. MMIO

MMIO在M级使用第二次地址译码。仅九个偏移 `0x00..0x20` 的对齐LW/SW有效。合法LW产生 `mmio_re`，ready为1时选择 `mmio_rdata`；合法SW产生 `mmio_we`和EX/MEM保存的未移位完整store数据。LB/LH/LBU/LHU、SB/SH、非对齐、窗口内未实现及窗口外访问均返回0/无副作用且不等待。

合法请求若 `mmio_ready=0`，因C1没有memory stall，顶层不隐藏停顿：load确定取0，simulation assertion报告外部零等待契约违规。M级MMIO可与下一条E级SRAM请求并行，因为是两个独立外部接口；集成测试实际观察到该组合。

与真实CNN连接时只把上述六个CPU侧MMIO信号连接Z方寄存器从接口，并要求合法请求及时ready。本顶层不实现CNN SRAM Master、B口适配器、双口共享SRAM或MobileFaceNet计算。

## 7. reset、stall、flush和副作用

C1优先级为 reset > redirect > load-use > normal。reset关闭PC/IF-ID并冲刷前两级；redirect更新目标并冲刷年轻IF/D指令；load-use只保持PC/IF-ID并冲刷ID/EX，M/W不停顿。当前E指令比同周期被redirect清除的D/IF指令更老，因此合法E级SRAM store继续提交。

顶层断言读写互斥、写strobe非零、reset无写、MMIO ready契约。集成TB另断言 invalid E/M无请求、SRAM/MMIO互斥、控制无X和x0恒零，并以错误路径store/MMIO/register指令验证flush后零副作用。

## 8. test-only组件

- `control_stub.sv`：独立组合实现测试所需RV32I译码、前递、load-use、branch/jump和C1优先级；端口同C1，但不是M实现也不替代它。
- `imem_model.sv`：64 KiB小端字节数组、固定一周期同步读取；非对齐/越界返回 `0x00000013`。
- `dmem_model.sv`：第五步已验证的256 KiB固定一周期模型。
- `cnn_mmio_stub.sv`：九寄存器、组合ready、读回和写事务计数；不是Z RTL，无CNN计算或SRAM Master。

## 9. 完整测试覆盖

`tb_cpu_datapath.sv`只向IMEM写入真实RV32I机器码并运行CPU，没有强制内部控制。它包含500周期超时、寄存器和SRAM签名scoreboard、SRAM/MMIO事务计数、PC目标/link/redirect检查、load stall计数及逐周期断言。

覆盖40类要求：顺序ADD/ADDI；10种R型；主要I型；LUI/AUIPC；MEM/WB和EX/MEM前递、双源不同级及WB→ID；LW立即使用且恰一气泡；LB/LBU四lane；LH/LHU两lane；SB四lane；SH两lane；SW；连续load/store及store→load；M-MMIO/E-SRAM并行；BEQ/BNE taken/not、BLT/BGE、BLTU/BGEU；JAL/JALR/link/bit0；三类redirect错误副作用；合法MMIO LW/SW；未实现、非对齐和窄MMIO拒绝；SRAM非对齐/越界；x0、reset、bubble、非法指令；以及包含上述相邻依赖和控制流的混合压力程序。全部检查通过。

## 10. 构建、警告和限制

入口为 `./scripts/run_datapath_tests.sh`，使用唯一package，显式列出全部Datapath RTL和四个test-only模型，顶层 `tb_cpu_datapath`，干净生成到 `build/datapath`，临时目录为 `build/tmp`。最终输出 `PASS: complete CPU datapath with test stubs`，退出码0。

没有SystemVerilog锁存器、多驱动或宽度告警。脚本仅用生成在build目录的精确文件规则豁免既有 `imm_gen.sv` 低7位unused告警，并局部允许共享package未被本测试使用的参数；没有全局关闭lint。剩余输出是Verilator/UCRT生成C++的 `STDOUT_FILENO/STDERR_FILENO` 宏重定义。

最终七项回归记录：

| 脚本 | PASS | 退出码 |
|---|---|---:|
| `run_pkg_tests.sh` | `PASS: cpu_control_pkg compatibility` | 0 |
| `run_base_tests.sh` | `PASS: base datapath modules` | 0 |
| `run_lsu_tests.sh` | `PASS: LSU and address decoder` | 0 |
| `run_fetch_tests.sh` | `PASS: fetch adapter` | 0 |
| `run_dmem_timing_tests.sh` | `PASS: fixed-latency Data SRAM timing` | 0 |
| `run_datapath_tests.sh` | `PASS: complete CPU datapath with test stubs` | 0 |
| `check_control_pkg_compat.sh` | `PASS: M Control compiles with Datapath cpu_control_pkg` | 0 |

其中fetch干净重建的批处理返回通道被执行器截断，但工程日志以PASS结束且新生成可执行文件正常退出；其余脚本均直接取得退出码0。旧回归保留各自文档已经记录的base/package unused类处理，LSU/fetch/dmem/datapath生成C++可能显示同一UCRT宏告警。

当前限制：固定一周期无ready的IMEM/Data SRAM；MMIO必须零等待；非法/非对齐不触发异常而确定性完成；无CSR、异常、中断、乘除法、压缩/原子指令；未验证实体FPGA存储器或时序收敛。

明确声明：当前仅完成Datapath与test-only组件验证，未完成真实M方Control、Z方CNN或三方SoC联调。
