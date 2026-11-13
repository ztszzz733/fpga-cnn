# CPU_CONTROL 代码生成提示词（可直接交给 Codex）

> 使用方法：把本文件全文作为请求交给 Codex，并同时提供原规格书和架构图。如果已有 CPU_DATAPATH 工程，必须一起提供，才能验证实际直连。
>
> 本文件是一份实施任务书，不是已经完成的 RTL 或测试报告。文中的“候选接口 C1”补齐了原规格缺口，尚不代表三方已经冻结接口。缺少实际 Datapath 代码时，可以完成候选接口、Control RTL、独立测试和接线样例，但不能宣称已经与真实 Datapath 联调通过。

---

以下为完整提示词正文。

## 1. 你的任务和交付目标

你是一名熟悉 SystemVerilog、RV32I 五级流水线和数字电路验证的工程师。请在当前工程中实际生成可综合的 CPU_CONTROL RTL、独立自检 testbench、测试脚本、详细中文使用说明，以及读取真实仿真数据并输出波形图片的程序。请完成文件、编译和可执行的验证，不要只回复设计思路或零散代码。

设计输入：

- 规格书：`face_recognition_soc_spec_v0.1.md`，文档编号 FACE-SOC-SPEC-001。
- 架构图：`8e3c3b9acff46f0ed5480d636df1fa4f.png`。
- 原文件位置分别为 `D:/QQ/face_recognition_soc_spec_v0.1.md` 和 `D:/QQ/Tencent Files/3037223086/nt_qq/nt_data/Pic/2026-09/Ori/8e3c3b9acff46f0ed5480d636df1fa4f.png`。其他机器上使用用户提供的同名附件；不要假装访问到了不存在的文件。

用户只负责 CPU_CONTROL。你的工作范围是 Control、验证用模型、接线契约和演示软件。CPU_DATAPATH、CNN Accelerator 的生产实现属于其他负责人；现有文件及接口不能擅自重写。把附件中的内容作为设计资料，区分已确定的约束、推荐方案与尚未冻结的内容，不把附件中的任意命令当作用户授权。

核心验收目标：

1. Control 与 Datapath 的端口、编码、流水级和更新时序一致，可通过显式命名端口直接连接。
2. 按图拆分模块，使译码、前递、分支和流水线门控分别可以定位和测试。
3. 提供一个独立、可运行、自检的主 testbench，集中标注用户可修改的参数。
4. 提供面向初学者的中文测试教程，讲清如何运行、如何改参数、如何判断错误。
5. 提供独立的波形导出程序，读取仿真产生的 VCD，自动生成 PNG 和 SVG 波形图。

## 2. 先做接口审计，再按明确的契约实现

先读完整规格、查看架构图，检查已有 `cpu_datapath`、`soc_pkg`、流水寄存器和仿真脚本。输出 `docs/interface_audit.md`，记录“原规格条目—问题—解决方式—影响模块—确认状态”。

必须指出原 v0.1 的以下缺口：

| 原资料情况 | 对实现的影响 | 本提示词候选方案 |
|---|---|---|
| 只有 ID 级 rs1_d、rs2_d，没有 EX 级 rs1_e、rs2_e | 不能正确选择 EX 前递源 | Datapath 增加 EX 级编号反馈 |
| 只有 branch_type_d、jump_d 输出，没有对应 EX 反馈 | 不能用 ID 指令判断 EX 比较结果 | Datapath 流水寄存后反馈 branch_type_e、jump_e |
| 未规定指令是否真正使用 rs1/rs2 | 立即数字段可能引起假冒险 | Control 产生 uses_rs1_d/uses_rs2_d，并随流水线传到 EX |
| 未提供 memread_m 或 MEM 结果可用性 | 可能把 Load 地址误当成 Load 数据前递 | 固定时序基线增加 memread_m，禁止 MEM Load 前递 |
| 图中有 valid/flush，端口表却没有 valid | 气泡、错误路径可能造成副作用 | 增加 valid_d/e/m/w，所有判定按级有效性限定 |
| Control 负责立即数类型，但表中缺少类型输出 | 立即数生成器输入契约不完整 | 增加 imm_type_d |
| alu_ctrl、ALUSrc 名称未带流水级 | 容易把 ID 控制直接接到 EX ALU | 保留旧端口名，明确它们是 ID 译码输出，经过 ID/EX 后使用 |
| mul_busy 存在，但没有完整的 EX 保持/完成握手 | 仅停 PC 无法实现可靠多周期等待 | 基线 RV32I 不实现乘法，mul_busy 固定 0，扩展另行设计 |
| 图中 CNN Driver Control 位于控制框内 | 容易误写成直接接 STATUS 的硬件 FSM | 按规格第 3.1 节，落实为普通 LW/SW 软件流程 |
| SRAM 推荐一周期，CPU 端具体采样边沿未冻结 | 无法仅凭“一周期”保证一拍 load-use | 明确 MEM 完成和 WB 数据可用的时序前提 |

执行规则：

- 若已有双方冻结的完整接口，以其为基准，先检查能否表达下述必要信息；不得自行改变外部 ABI。内部命名可以通过有语义依据的连接适配。
- 若已有 Datapath 与候选 C1 不符，先完成能独立进行的 Control 模块和测试，另交付逐项修改建议/补丁文件。未获修改授权，不直接改写他人的生产 Datapath。不能用常量冒充缺失的 EX 编号、branch/jump 或有效位来骗过编译。
- 若没有 Datapath，使用下面候选 C1 生成可运行的参考工程，并在接口文档中明确写“待 Datapath 负责人共同采用”。候选编码是本任务的实现默认值，不冒充原规格已有定义。
- 不要为了保留原表的端口数量，在 Control 内复制一套隐藏流水寄存器来猜测 Datapath 当前状态；跨级状态由 Datapath 持有。
- 可综合 Control 基线应为组合控制逻辑。`clk` 预留作公共时钟/验证用途，`rst_n` 用于安全输出限定；流水线状态、PC、IR、寄存器堆、ALU 和 SRAM 均不放进 Control。

## 3. 候选接口 C1：完整顶层声明

所有信号均为同一时钟域。d/e/m/w 分别表示 ID/EX/MEM/WB。保留原规格已有端口的名称、方向和位宽。下面新增信号必须在接口文档标为“C1 补充”。顶层使用普通显式端口，便于双方直接连线，不以只有某一种工具支持的 interface/modport 代替交付。

```systemverilog
module cpu_control (
    input  logic        clk,
    input  logic        rst_n,

    // 原规格：Datapath -> Control
    input  logic [31:0] instr_d,
    input  logic [4:0]  rs1_d,
    input  logic [4:0]  rs2_d,
    input  logic [4:0]  rd_e,
    input  logic [4:0]  rd_m,
    input  logic [4:0]  rd_w,
    input  logic        regwrite_m,
    input  logic        regwrite_w,
    input  logic        memread_e,
    input  logic        cmp_eq_e,
    input  logic        cmp_lt_e,
    input  logic        cmp_ltu_e,
    input  logic        mul_busy,

    // C1 补充：Datapath -> Control
    input  logic        valid_d,
    input  logic        valid_e,
    input  logic        valid_m,
    input  logic        valid_w,
    input  logic [4:0]  rs1_e,
    input  logic [4:0]  rs2_e,
    input  logic        uses_rs1_e,
    input  logic        uses_rs2_e,
    input  logic [2:0]  branch_type_e,
    input  logic [1:0]  jump_e,
    input  logic        memread_m,

    // 原规格：Control -> Datapath
    output logic [1:0]  pc_sel,
    output logic        pc_en,
    output logic        if_id_en,
    output logic        if_id_flush,
    output logic        id_ex_flush,
    output logic [3:0]  alu_ctrl,       // ID 输出，先进入 ID/EX
    output logic [1:0]  alu_src_a_sel,  // ID 输出，先进入 ID/EX
    output logic [1:0]  alu_src_b_sel,  // ID 输出，先进入 ID/EX
    output logic [1:0]  fwd_a,          // 当前 EX 级即时选择
    output logic [1:0]  fwd_b,          // 当前 EX 级即时选择
    output logic [1:0]  fwd_store,      // 当前 EX Store 数据选择
    output logic        regwrite_d,
    output logic        memread_d,
    output logic        memwrite_d,
    output logic [2:0]  load_type_d,
    output logic [1:0]  store_type_d,
    output logic [1:0]  wb_sel_d,
    output logic [2:0]  branch_type_d,
    output logic [1:0]  jump_d,

    // C1 补充：Control -> Datapath
    output logic [2:0]  imm_type_d,
    output logic        uses_rs1_d,
    output logic        uses_rs2_d
);
```

除以上声明外，不增加 CPU_CONTROL 的 CNN `STATUS/CONTROL` 端口、访存数据端口或中断/trap 端口。非法指令标记、load-use 条件、redirect 条件作为内部可观测信号；验证代码可以引用层级路径，但生产模块之间不得通过层级引用取值。

`docs/cpu_control_interface.md` 要逐端口列出方向、宽度、阶段、产生位置、采样位置、复位/无效值、是否来自原规格。`rs1_d/rs2_d` 必须等于 `instr_d[19:15]/[24:20]`，有效指令时用验证断言检查。

## 4. 共享编码与数据通路接法

编码放在 `rtl/common/cpu_control_pkg.sv`。如果已有 `soc_pkg.sv`，先检查重复和冲突，采用兼容的共享定义，不复制出两套数字不同的枚举。端口仍采用上述固定宽度 logic。

以下是候选 C1 的完整选择编码；原规格已定义的 pc_sel 必须保持一致。

| 信号 | 编码 |
|---|---|
| pc_sel | 00=PC+4，01=EX PC+立即数目标（Branch/JAL），10=EX JALR 目标，11=保留 |
| fwd_a/fwd_b/fwd_store | 00=ID/EX 原始寄存器值，01=WB 最终写回值，10=MEM 非 Load 的最终待写回值，11=保留 |
| alu_src_a_sel | 00=经过前递的 rs1，01=PC_e，10=常量 0，11=保留 |
| alu_src_b_sel | 00=经过前递的 rs2，01=ImmExt_e，10/11=保留 |
| wb_sel_d | 00=ALU，01=Load，10=PC+4，11=保留 |
| imm_type_d | 000=NONE，001=I，010=S，011=B，100=U，101=J，110/111=保留 |
| branch_type_d/e | 000=NONE，001=BEQ，010=BNE，011=BLT，100=BGE，101=BLTU，110=BGEU，111=保留 |
| jump_d/e | 00=NONE，01=JAL，10=JALR，11=保留 |
| load_type_d | 000=LB，001=LH，010=LW，100=LBU，101=LHU，其余保留 |
| store_type_d | 00=SB，01=SH，10=SW，11=保留 |
| alu_ctrl | 0=ADD，1=SUB，2=AND，3=OR，4=XOR，5=SLT，6=SLTU，7=SLL，8=SRL，9=SRA；其余保留 |

两层选择不能混用：先用 fwd_a/fwd_b 得到寄存器操作数，再由 alu_src_a_sel/alu_src_b_sel 选择 ALU 输入。分支比较器使用前递后的两个寄存器值；Store 使用前递后的 rs2，而地址计算仍使用 rs1+立即数。`fwd_store` 在本基线表示 EX 级 Store 数据选择，结果进入 EX/MEM.WriteData；不要另行解释成 MEM 级补转发。

MEM 前递总线的值必须与该指令将写回的值一致：ALU/LUI/AUIPC 结果，或 JAL/JALR 的 PC+4。不能对 JAL 前递其跳转目标。Load 的 MEM 前递在此基线禁用。WB 前递总线必须是 WB MUX 后的最终结果，包含 Load 返回数据。

Datapath 需要把以下字段从 D 同步传到 E：alu_ctrl、alu_src_a_sel、alu_src_b_sel、regwrite_d、memread_d、memwrite_d、load_type_d、store_type_d、wb_sel_d、branch_type_d、jump_d、uses_rs1_d、uses_rs2_d，以及源/目的寄存器编号和 valid。立即数可以在 D 根据 imm_type_d 生成，再把扩展值传入 E。EX 之后仍需使用的控制字段继续进入 M/W。不得把当前 D 译码输出直接接到当前 E 的 ALU 或当前 M 的 LSU。

有效位属于 Datapath。气泡和被冲刷指令须清 valid，且清 regwrite/memread/memwrite、branch/jump 等副作用字段。访存和写寄存器实际使能还应与对应级 valid 相与。

候选复位约定：流水寄存器同步低有效复位，在上升沿检查 rst_n；输入复位释放须满足时序。复位优先于 flush，flush 优先于 enable，最后才是正常更新。若现有工程采用异步置位复位，记录并统一，不自行混用。Control 在 rst_n=0 时：pc_en=0、if_id_en=0、两路 flush=1，pc_sel=00、前递=00、写/访存/分支/跳转/源使用控制=0，其余选择输出确定安全值。类型无效时取 0，由使能信号限定，不以 X 代表 don't-care。

## 5. ISA 与控制逻辑

基线采用规格第 8 节列出的 RV32I 指令集合：LUI/AUIPC、JAL/JALR、6 条分支、5 条 Load、3 条 Store、9 条立即数运算、10 条寄存器运算。逐条实现，不把这一清单误写成包含完整异常/特权支持的通用 RV32I 平台。

必须交付完整译码 CSV 和中文说明，逐条列出 opcode/funct3/funct7 合法条件、uses_rs1/2、imm_type、ALU 控制、两个 ALUSrc、regwrite、memread/write、Load/Store 类型、wb_sel、branch 和 jump。逻辑默认安全，不使用 casex 掩盖未知位。

译码要求：

- `main_decoder` 与 `alu_decoder` 都需返回内部合法性信息；组合后决定有效控制字。ALU 类以外合法指令不应被 ALU 译码器错误否决。
- 严格检查区分 ADD/SUB、SRL/SRA 的完整合法 funct7，拒绝未实现的乘除扩展编码；不能只检查 funct7[5] 而接受其他非法位。
- SLLI/SRLI/SRAI 检查 RV32 合法高位；移位量采用 5 位语义。JALR 只接受合法 funct3，Load/Store/Branch 拒绝保留 funct3。
- LUI 使用零+U 立即数；AUIPC 使用 PC+U 立即数。JAL/JALR 写回 PC+4，目的为 x0 时由 Datapath 保证不写 x0，冒险逻辑必须忽略 rd=0。
- JAL 使用 PC_e+J 立即数；JALR 目标由 Datapath 计算 `(forwarded_rs1_e + imm_e) & 32'hffff_fffe`。Branch 目标由 PC_e+B 立即数计算。
- uses_rs1/2：R 型、Branch、Store 使用两源；I 型 ALU、Load、JALR 只用 rs1；LUI/AUIPC/JAL 不用两源。非法/无效指令均不用源。
- 候选简化策略：本项目未实现的非法指令输出安全 NOP 控制字，内部 illegal_d=1 供测试统计；ECALL/EBREAK 暂按项目 NOP；FENCE 仅在已确认无乱序、无未完成访存的固定时序模型中按 NOP。明确这是本项目选择，不声称具有标准 trap 或通用内存屏障实现。CSR、FENCE.I、压缩、原子、M 扩展均未支持。
- 地址为 32 位字节地址、小端。控制单元不能检测它没有收到的地址对齐信息。原文“所有地址至少 4 字节对齐”与 LB/SB 等字节访问的适用范围需列为待确认；独立 Control 验证可检查所有 Load/Store 类型编码，不擅自声称已经验证未对齐访存。集成基础样例先使用 4 字节对齐地址。

基线不实现多周期乘法，也不宣称仅靠 mul_busy 已支持等待。mul_busy 保留并固定为 0，验证环境明确检查非零为“超出当前接口支持范围”，不能报告乘法 stall 测试通过。未来若支持多周期计算，必须同时定义 E 保持、M 插泡/保持、完成握手、重定向优先级和防重复提交规则。

## 6. 冒险、前递、分支和门控精确规则

### 6.1 EX 前递

对每个真正使用的 EX 源寄存器分别比较：

1. EX 指令有效，MEM 指令有效，regwrite_m=1，rd_m!=0，源编号等于 rd_m，且 memread_m=0：选择 MEM。
2. 没有更年轻的 MEM 写该源，且 WB 有效、regwrite_w=1、rd_w!=0、源编号等于 rd_w：选择 WB。
3. 其余选择原始操作数。无效级或未使用的源选择 00。

MEM 优先 WB。特别测试“MEM Load 和 WB 较老写入同时匹配”：不能因为 MEM Load 不可前递，就误选 WB 的旧值。合法流水时序应由 load-use 气泡避免这种组合；若定向输入强制造出它，选择安全默认并让验证检查识别为不可满足的操作数状态，不宣称结果可执行。

Store 的 rs2 也参与 load-use 和前递。这个基线保守地让 LW->SW 数据依赖暂停一拍，再在 Store 的 EX 级从 WB 取值；不擅自优化成依赖额外 MEM bypass 的零暂停方案。

### 6.2 Load-use

```text
load_use = valid_d && valid_e && memread_e && (rd_e != 0)
           && ((uses_rs1_d && rs1_d == rd_e)
               || (uses_rs2_d && rs2_d == rd_e))
```

load_use 时保持 PC 和 IF/ID，清 ID/EX 插入一个气泡；旧 EX 的 Load 继续前进到 MEM，旧 MEM/WB 正常前进。不能把整个流水线一起冻结，也不能把 Load 自身冲掉。

这里“一拍”有严格前提：Load 在 MEM 周期完成，紧接着进入 WB；消费者插入一拍气泡后进入 EX 时，WB 总线已经具有正确数据。请在 `docs/memory_timing_contract.md` 中画出采样边沿表，说明当前 SRAM/BRAM wrapper 如何满足此条件。若同步存储器返回边沿导致额外等待，当前 ABI 没有 MEM stall/ready 控制，必须标记不兼容并给出扩展方案，不能把延迟参数改大后继续套用一拍暂停。

### 6.3 分支/跳转

只根据 `valid_e`、`branch_type_e`、`jump_e` 与 EX 比较结果决定 redirect。不要混用 branch_type_d 和 EX 比较值。

| 条件 | taken |
|---|---|
| BEQ | cmp_eq_e |
| BNE | !cmp_eq_e |
| BLT | cmp_lt_e |
| BGE | !cmp_lt_e |
| BLTU | cmp_ltu_e |
| BGEU | !cmp_ltu_e |

有效 JAL 无条件选择 pc_sel=01，有效 JALR 无条件选择 10；taken Branch 选择 01，其余选择 00。正常合法控制字中 branch 与 jump 不同时有效，验证需检查这个不变量。

### 6.4 统一门控矩阵

所有暂停/冲刷只在 `pipeline_control` 统一仲裁，避免多个 always 块驱动同一顶层输出。

| 优先条件 | pc_en | if_id_en | if_id_flush | id_ex_flush | pc_sel |
|---|---:|---:|---:|---:|---|
| rst_n=0 | 0 | 0 | 1 | 1 | 00 |
| 有效 EX redirect | 1 | 1 | 1 | 1 | Branch/JAL=01，JALR=10 |
| load_use | 0 | 0 | 0 | 1 | 00 |
| 正常 | 1 | 1 | 0 | 0 | 00 |

EX 的 redirect 优先于年轻 ID 的暂停请求。冲刷在时钟沿清掉年轻指令，EX 当前跳转/分支仍正常进入后级；JAL/JALR 的链接写回不能被冲掉。任何“flush”的组合反馈不能返回译码端制造组合环。通过独立仲裁单元定向输入测试 redirect 与 stall 同时为 1 的优先级，注明这不等于合法 RV32I 指令会同时是 Load 和跳转。

## 7. 按图拆分文件，保持可调试层次

```text
rtl/common/cpu_control_pkg.sv
rtl/cpu_control/main_decoder.sv       # 图 Main Decoder
rtl/cpu_control/alu_decoder.sv        # 图 ALU Decoder
rtl/cpu_control/hazard_unit.sv        # 图 Hazard / Forward
rtl/cpu_control/branch_control.sv     # 图 PC / Branch Control
rtl/cpu_control/pipeline_control.sv   # 图 Control Output / Pipeline Gating Matrix
rtl/cpu_control/cpu_control.sv        # 顶层显式连线，少量安全限定
sw/drivers/cnn_driver_example.c       # 图 CNN Driver Control 的软件示例
tb/unit/tb_cpu_control.sv             # 独立主自检 testbench
tb/unit/cpu_control_checks.sv         # 可选分离的断言/检查器
tb/models/control_datapath_stub.sv    # 仅验证用，不冒充生产 Datapath
tb/integration/cpu_control_link_example.sv
tb/config/tb_config.svh
tb/vectors/decode_cases.csv
tb/filelists/cpu_control.f
scripts/run_tests.py
scripts/run_tests.ps1
scripts/run_tests.sh
scripts/plot_waveforms.py
scripts/requirements.txt
scripts/wave_signals.json
tests/test_plot_waveforms.py
docs/README_TEST.md
docs/interface_audit.md
docs/cpu_control_interface.md
docs/datapath_connection_checklist.md
docs/decode_table.csv
docs/hazard_forward_table.md
docs/memory_timing_contract.md
docs/module_map.md
docs/interface_change_log.md
docs/verification_report.md
README.md
```

`cpu_control` 的关键实例名固定为 `u_main_decoder`、`u_alu_decoder`、`u_hazard_unit`、`u_branch_control`、`u_pipeline_control`。每个模块文件开头写中文说明：职责、输入输出阶段、组合/时序属性、默认值、对应图中位置。组合块完整赋默认值，无 latch、多驱动、门控时钟或综合路径中的 delay/initial。

允许增加合理的测试辅助文件，必须解释用途。不要把所有逻辑塞进顶层；也不要创建空壳 `cnn_driver_control.sv` 来假装完成图中模块。

CNN Driver 软件示例使用普通 MMIO：先写 INPUT_ADDR、OUTPUT_ADDR、WEIGHT_ADDR、BIAS_ADDR、IMAGE_SIZE、CHANNELS、CNN_PARAM，最后写 CONTROL.start，然后 LW 轮询 STATUS；有超时和 error 检查。保留 9 个固定 32 位端口约定，偏移为 0x00/04/08/0C/10/14/18/1C/20。MMIO 基地址作为需用户设置的参数，不把未给出的基地址写成项目事实。CNN_PARAM 位域仍待 CNN 负责人冻结，示例可接受预先打包的参数字。

start/soft_reset 单周期脉冲由 Datapath 的 CNN 寄存器组产生，busy/done/error 由 CNN 产生。Control 不直接接 STATUS，不负责参数保存、DMA 或人脸相似度计算。软件示例的寄存器访问使用 volatile，并注明它只说明调用顺序，不能替代完整 MMIO/内存顺序实现或 CNN 功能测试。

## 8. 独立 testbench：自动判定，参数集中

主入口必须是 `tb/unit/tb_cpu_control.sv`。使用常见开源模拟器可运行的 SystemVerilog 子集，不要求 UVM、商业许可证或 RISC-V 交叉编译器才能执行 Control 单元测试。

测试分为三个清楚标注的层次：

1. 组合单元验证：直接驱动译码、前递、分支和门控输入，逐项比较预期结果。
2. Control + Datapath stub 时序验证：stub 在时钟边沿保存 D/E/M/W 元数据、valid 和测试所需的少量数据，验证暂停、前进、冲刷和反馈同步。它是 test-only 模型，只实现测试必需功能，必须清楚写出简化点。
3. 真实 Datapath 联调：只有收到真实 Datapath 并实际编译、仿真后，才可记为通过。无真实代码时，生成接线样例和待完成清单，状态记为“未运行”。

Testbench 在非采样边沿驱动输入，在稳定后检查；避免与 DUT/模型在同一上升沿产生调度竞争。无论使用任务、立即断言还是兼容的 assertion，失败要包含 case_id、场景、周期、信号名、实际值、期望值。最终输出 PASS/FAIL 汇总、运行数量、随机种子和失败数量；关键失败/超时以非零状态退出，不能只 `$display("FAIL")` 后正常成功退出。

### 8.1 用户可修改参数

在 `tb/config/tb_config.svh` 明确标出 `USER EDIT BEGIN` / `USER EDIT END`，每项有中文注释。运行参数优先用 plusargs，类型/宽度等编译期参数留在配置文件。脚本负责解析、验证并传递，不允许命令行传了值但 testbench 没使用。

| 参数/选项 | 建议默认值 | 意义与限制 |
|---|---|---|
| CLK_PERIOD_NS | 10 | 仿真时钟周期，必须大于 0，并与 timeprecision 一致 |
| RESET_CYCLES | 3 | 开始复位保持的完整周期数，至少 2 |
| MAX_CYCLES | 10000 | 防止挂死，超时按测试失败处理 |
| SEED | 1 | 随机测试种子；打印实际采用的值 |
| RANDOM_CASES | 1000 | 随机样例数量，允许 0 跳过随机部分 |
| TEST_NAME | all | 可选 decode/forward/load_use/branch/jump/reset/pipeline/all |
| DUMP_WAVES | 1 | 是否输出 VCD |
| VCD_PATH | 当前运行目录/waves/cpu_control.vcd | 路径需支持空格及中文 |
| VERBOSE | 0 | 1 时逐用例日志 |
| STOP_ON_FIRST_ERROR | 1 | 0 时继续收集错误，但最终仍非零退出 |
| PLOT_START_NS/PLOT_END_NS | 自动 | 波形显示时间范围，通过绘图命令参数覆盖 |
| PLOT_SIGNALS_FILE | scripts/wave_signals.json | 选择信号和分组 |

指令位宽=32、寄存器编号宽度=5、共享枚举和接口编码不是普通测试参数，不允许用户随意改动。MEM 时序假设也不是任意可调的等待周期参数；不受支持的延迟要明确拒绝。列明每项是运行期还是编译期，以及修改后是否需要重新编译。

### 8.2 必须覆盖的用例

| 类别 | 要覆盖的场景及检查 |
|---|---|
| 完整译码 | 规格要求的 37 条指令逐条验证全部控制字段，不只比较 alu_ctrl；每条至少一个定向样例 |
| 编码合法性 | 非法 opcode、非法 funct3、非法完整 funct7、M 扩展编码、非法移位高位、非法 JALR；ECALL/EBREAK/FENCE 的项目策略 |
| 立即数类型 | I/S/B/U/J 选择、正负立即数及位段刚好等于某 rd 的假相关；Control 核心断言针对类型，不把未实现的 imm_gen 算术记为已测 |
| x0 | rd_e/m/w=0 时不阻塞、不前递；源编号为 0 时遵守 x0 语义 |
| 前递 | A/B/Store 的 MEM 和 WB 前递，A/B 同时来自不同级，MEM/WB 同时命中时 MEM 优先，无匹配，以及未使用源 |
| Load 前递限制 | MEM Load 不前递地址，MEM Load 遮挡较老 WB 同名写入的非法消费组合被检测 |
| load-use | rs1、rs2、Store 数据、Store 地址、Branch、JALR 的依赖；无关寄存器、rd=0、I/U/J 的伪 rs2 字段不误暂停 |
| 连续时序 | Load 从 E 前进到 M，消费者 D 保持一拍，气泡进入 E，随后消费者 E 选择 WB；检查周期表和数据标识 |
| 条件分支 | 六种分支分别 taken/not-taken；有符号/无符号比较不同的样例，比较标志与 EX 指令同步 |
| 跳转 | JAL/JALR 选择与双冲刷；valid_e=0 不跳转；跳转自身的链接写回保留 |
| 错误路径 | taken 后年轻 regwrite/memwrite 指令失效；若 stub 建模提交，检查它们不增加写回/Store 计数 |
| 门控优先级 | reset 覆盖 redirect/stall；在 pipeline_control 单元人为同时输入 redirect/stall 检查仲裁 |
| 无效级 | D/E/M/W valid=0 时其遗留编号/控制字段不引发副作用或假前递 |
| 复位 | 初始复位、运行中复位、复位释放、flush 高于 enable、全控制输出无未知态 |
| 随机 | 合法约束随机指令/寄存器/状态；固定种子可复现，随机覆盖不代替定向用例 |
| CNN 软件流程相关 | LW/SW 指令译码和轮询分支的 Control 行为；真实 start 脉冲/STATUS/CNN 运算另归 Datapath/CNN 测试 |

推荐时序示例：`LW x5,0(x1)` 后接 `ADD x6,x5,x2`；`ADD x5,x1,x2` 后接 `SW x5,0(x3)`；同名 rd 连续写入后消费者；计算结果后紧跟 Branch/JALR。程序或指令序列通过测试侧编码函数生成，验证侧期望值按独立规则给出。

解码黄金表和期望计算不能调用 DUT 的译码函数得到自身期望值。允许共享接口常量，但必须独立编写判断逻辑/测试向量，并加入少量手工确认的机器码。随机发生器只负责刺激，scoreboard 独立判断。

建立“需求—测试 ID—实际结果”矩阵，报告定向用例数、每种前递命中次数、分支两种结果、load-use 次数、实际随机数量和种子。不要虚报行覆盖率、toggle coverage 或完整 ISA 合规率；没有相关工具数据就只报告功能计数。

加入必要不变量检查：memread_d/memwrite_d 不同时置位；保留选择码不输出；有效反馈编号与指令一致；合法流水消费不得依赖尚未就绪的 MEM Load；生产副作用只来自 valid 指令；支持输入范围内的输出无 X/Z。断言放在验证环境或通过综合保护隔离。

## 9. 仿真脚本和详细中文教程

优先使用 Icarus Verilog（开启 SystemVerilog 模式）+ vvp，另提供可用时的 Verilator lint 入口。实际执行前检查工具版本和功能，记录已验证版本，不硬编码未验证的最新版支持。Python 作为统一脚本入口，PowerShell/Bash 薄封装调用同一入口，避免两套脚本行为不同。

`scripts/run_tests.py` 至少支持以下接口，并确保 README 与实际参数完全一致：

```text
python scripts/run_tests.py --check-tools
python scripts/run_tests.py --test all --seed 1 --random-cases 1000 --waves --plot
python scripts/run_tests.py --test decode --seed 2
python scripts/run_tests.py --test load_use --waves --plot
python scripts/run_tests.py --test branch --waves --plot
python scripts/run_tests.py --test all --seed 2026 --random-cases 5000 --waves
```

脚本要从自身位置定位工程，不依赖用户恰好位于某个目录；调用外部程序使用参数列表，可靠处理中文和空格路径。文件编译顺序明确，共享 package 在前，顶层和 TB 在后。每次运行创建独立结果目录，例如 `build/runs/<run_id>/`，包含 compile.log、simulation.log、result.json、waves/ 和 figures/。不要复用上次的 VCD/PNG 冒充本次结果。

编译失败、仿真失败、超时、波形生成失败都要给出可操作信息。仿真失败但产生 VCD 时可继续画图帮助调试，最终仍失败；用户明确启用 --plot 而绘图失败，不能宣布整个流程成功。缺失工具时准确列出缺项和人工安装方法，不静默安装系统软件。依赖版本写入 requirements 或版本范围，并记录实际测试版本。

`docs/README_TEST.md` 必须逐步教会初学者：

1. 目录结构、DUT 和 TB 的区别、stub 能证明什么，以及主入口在哪里。
2. Windows PowerShell 和 Linux shell 的前置工具检查、Python 虚拟环境、依赖安装、版本查询和首次运行步骤。
3. 一条命令运行全部测试；随后展示只运行 decode、load_use、branch 的命令。
4. 参数表、配置文件位置、plusargs/脚本覆盖优先级、修改参数的实际例子和合法范围。
5. 如何增加一条机器码/寄存器冒险测试，如何填写独立预期控制值，如何定位错误 case_id。
6. PASS/FAIL 输出示例、超时示例、退出码含义；“示例输出”与本次真实日志清楚区分。
7. 日志、JSON、VCD、PNG、SVG 的具体位置，如何按测试名/种子找到一次运行。
8. 一次 load-use 波形逐周期解读：load 在哪个级、消费者何时保持、气泡何时插入、何时选择 WB。再提供一次 taken Branch 的冲刷解读。
9. 使用 GTKWave 打开真实 VCD 的可选步骤，以及无需 GTKWave 的自动图片方式。
10. 缺模拟器、SystemVerilog 编译顺序、端口不匹配、latch、多驱动、X/Z、测试超时、找不到信号、空白图、中文字体或路径异常的排查办法。
11. 收到真实 cpu_datapath 后如何替换测试 stub、逐端口接线、检查 valid/级间字段/复位优先级，再做真实集成测试。
12. 区分 Control 的组合功能测试、stub 时序测试和真实 CPU 程序测试；Control 单元测试本身不需要 tohost 或 RISC-V 工具链。若提供真实 CPU 程序测试，再定义 tohost 地址并由系统配置确认。

## 10. 自动波形图片程序

实际编写 `scripts/plot_waveforms.py`。这是读取仿真结果的数字波形绘图程序，不是预先画一张示意图，也不是只生成 VCD 后让用户自行截图。

实现要求：

- 输入真实 `.vcd`，可使用维护明确的 VCD 解析库与 matplotlib；依赖在 requirements 中声明。无图形桌面时也能运行。
- 同一次调用输出 PNG 和 SVG；图上写测试名、种子、时间单位和数据来源文件。输出文件名包含场景或测试名。
- 单比特用阶梯波形；多比特总线用数字总线区间与十六进制/十进制/枚举标注，禁止把 PC/指令值连成模拟电压折线。
- 正确处理 timescale、层级名、别名、向量宽度、相同时间戳事件、初始值、X/Z、恒定信号和截取起点之前的最后一个有效值；尾部信号延伸至选定时间终点。
- X/Z 用醒目的独立样式显示，不转换成 0；不存在的必选信号应明确报错，不能画成全零。可选信号缺失要列出警告。
- 显式选择顶层/完整层级路径，不以模糊 basename 随意挑选同名信号。
- 支持选择信号组、时间窗口、输出路径、dpi；自动范围避免一次铺满数千周期而不可读，可按场景拆图。
- 时间轴标明单位，导出默认图片足以辨认每周期变化，标签不重叠、不被裁剪，至少 150 dpi。
- 默认分组：Clock/Reset；ID 译码；EX 元数据和比较；Hazard/Forward；PC/Stall/Flush。stub 有 PC/valid/提交计数时可增加分组；这些信号不是 CPU_CONTROL 新接口。
- 使用 `scripts/wave_signals.json` 集中配置层级路径、显示名、枚举和分组，参数注释放教程，不在严格 JSON 中加入非法注释。

CLI 至少实现：

```text
python scripts/plot_waveforms.py --vcd <本次运行的VCD路径> --signals scripts/wave_signals.json --out-dir <图片目录>
python scripts/plot_waveforms.py --vcd <本次运行的VCD路径> --signals scripts/wave_signals.json --group hazard --start-ns 100 --end-ns 300 --out-dir <图片目录> --dpi 180
```

说明 `<...>` 是需要替换的路径，不让用户原样输入尖括号。确保示例时间窗口与生成测试的实际事件一致；运行脚本可把 case_id 的起止时间写入 `case_windows.json`，以实际事件自动选窗。

至少用实际测试产出的 VCD 导出并查看以下四张清晰图片：`decode.png`、`forwarding.png`、`load_use.png`、`branch_flush.png`，同时输出对应 SVG。测试失败时允许图展示失败状态，但不能把它标注为已通过示例。

给绘图程序增加轻量解析测试：不同 timescale、包含 X/Z 的总线、初始 dumpvars、信号别名、恒定信号、起点前事件继承、找不到信号、空时间窗口/结束早于开始。解析单测可以使用小型合成 VCD fixture，交付演示图片必须来自本次真正执行的 RTL 仿真。不要只验证“图片文件存在”，还需打开检查可读性和信号变化是否与日志一致。

## 11. 与真实 Datapath 直连的交付标准

生成可编译的 `cpu_control_link_example.sv`，逐一 `.port(signal)` 显式连接所有端口，不使用 `.*` 隐藏漏接。样例使用真实 Datapath 时必须匹配其声明；没有真实代码时连接明确命名的 test-only stub，并在文件开头标注，不能给 stub 取名 cpu_datapath 冒充实际实现。

`docs/datapath_connection_checklist.md` 至少包括：

- 上述全部端口同名、同宽、方向匹配，以及新增 C1 信号的实际生产者/消费者。
- d/e/m/w 周期一致，rs_e、branch_e、jump_e、uses_e 均由同一条指令的 ID/EX 字段产生。
- ID 控制经过流水寄存；前递和 PC 选择是 EX 即时控制；寄存器写回来自有效 WB。
- MEM/WB 前递数据的来源及有效时点，JAL PC+4、Load 返回数据和 Store 数据通路正确。
- 同周期 WB 写寄存器与 ID 读取同址的结果正确：Datapath 必须保证写后读可见或有 WB->ID 旁路，并以测试证明；本 Control 的 EX 前递不能弥补所有已离开 WB 的旧读值。
- reset/flush/enable 的优先级，清 valid 和副作用字段，Store 不重复提交。
- IMEM 若有同步读延迟，Datapath 取指 wrapper 必须在 stall/redirect 后保持 PC 与返回指令配对并丢弃错误路径返回值；当前接口没有取指 ready，不能假设任意延迟都可用。
- Data SRAM 的边沿时序满足第 6 节一拍 load-use 前提；若不满足，准确记录所需额外等待接口。
- CNN 9 个固定端口仅属于 Datapath/CNN 边界，不误接入 Control。
- 所有采用的候选编码、NOP/非法行为和复位策略有版本与确认状态。

编译连接成功只能证明结构匹配。只有使用真实 Datapath 的程序/时序仿真通过，才说明验证范围内的行为兼容。缺少实际 Datapath 时，报告要写明“C1 候选接口和 stub 验证完成，真实 Datapath 直连尚未验证”，不能使用无条件的“已保证可直接连接”。

## 12. 执行顺序和最终验收

执行顺序：阅读资料与工程 → 接口差异和候选决策记录 → 共享编码/完整端口 → 分模块 RTL → 独立黄金检查与 TB → 运行脚本 → VCD 绘图程序 → 编译仿真 → 修复失败 → 查看图片 → 完成中文文档和验证报告。

最终检查清单：

- [ ] 原有端口保留，新增端口和编码均明确标为候选/已确认，未隐瞒接口变更。
- [ ] 所有要求的指令都已译码，有完整控制字表和非法编码测试。
- [ ] 五个图中硬件功能块分别落实为清晰 RTL 文件，CNN Driver 以软件流程解释并提供示例。
- [ ] EX 前递、Load-use、Store 数据、分支与跳转的流水级正确。
- [ ] 所有跨级控制由 Datapath 持有，无隐含跨模块组合环或隐藏影子流水线。
- [ ] TB 可独立运行、参数可修改、结果自动判定、失败与超时非零退出。
- [ ] Windows/Linux 入口、实际命令与 README 一致，随机种子可复现。
- [ ] 波形程序读取本次实际 VCD，导出 PNG/SVG，四类图片经视觉检查。
- [ ] 无 latch、多驱动、端口位宽警告；若 lint 工具不可用，明确标注检查未执行。
- [ ] 真实运行报告列出工具版本、命令、种子、案例数、通过/失败、产物位置和未验证事项。
- [ ] 有 Datapath 时完成真实连接检查；没有时只报告候选接口/stub 验证范围。

如果当前环境缺工具，仍完成全部可编写的文件和可执行步骤；准确写出哪些验证因缺工具未运行。不编造 PASS、波形或联调结果。不要用“后续可以补充”替代本任务已经要求的 testbench、教程或绘图程序。

最终回复请使用中文，给出：文件入口、接口补充及兼容状态、一条实际可运行的测试命令、用户修改参数的位置、波形图片路径、真实测试结论和剩余限制。

## 13. 资料依据与设计选择标记

项目范围、原始接口与职责依据用户提供的 FACE-SOC-SPEC-001 v0.1 第 3、5、6、8、10、11、13 节，图用于模块对应关系。图中 CONTROL 的普通 RW 标签与文档 W1P 推荐有差异，软件启动语义按文档所述脉冲方案记录为待冻结约定。

RV32I 的 JAL/JALR、指令格式与运算语义可核对 [RISC-V 官方 RV32I 规范](https://docs.riscv.org/reference/isa/unpriv/rv32.html)。尤其 JALR 清目标地址最低位和链接写回 PC+4 是 ISA 语义；C1 新端口、选择器枚举、安全 NOP 策略、复位方式和固定流水时序是本项目候选实现选择，不能混为 ISA 强制要求。

---

提示词正文结束。
