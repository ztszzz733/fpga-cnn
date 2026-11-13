# cpu_control_pkg 兼容性记录

日期：2026-09-15  
范围：仅建立共享 package 兼容候选、验证现有 Datapath 基础模块并检查 M 方生产 Control 的源码兼容性；不属于真实 Control/CNN 联调。

## 1. 原始来源与修改前哈希

| 来源 | 路径 | 修改前 SHA-256 |
|---|---|---|
| Datapath 原 package | `D:\FPGA\CPU\face_recognition_soc\rtl\common\cpu_control_pkg.sv` | `60EF561CF65AB871E263F9F6AF9B57A4F3794C1EEA77DB41A6A26EC98C8BFE4C` |
| M 方生产 package | `D:\FPGA\CPU\incoming\cpu_control\rtl\common\cpu_control_pkg.sv` | `FC0F6CF155299A43B2D44B527D087D726BF4A3F974377A1D7301492CEFED0A3C` |

M 方生产 filelist 为 `D:\FPGA\CPU\incoming\cpu_control\rtl\filelists\cpu_control.f`，依次列出 package、`main_decoder`、`alu_decoder`、`hazard_unit`、`branch_control`、`pipeline_control` 和 `cpu_control`。本次排除了 `build`、backups、`说明文档/原版`、TB 和生成文件。

## 2. 基准选择

兼容候选以 M 方生产 package 为基准，因为 C1/P1 已冻结 M 方的端口、编码、符号和 `decode_t`，且六个生产 Control 模块直接依赖这些名称与字段。原 Datapath package 的同类数值与之完全兼容，没有同名不同值；因此采用“完整保留 M 方定义 + 以正式符号表达 Datapath 别名 + 增加 RV32I load/store 名称”的超集，不改变任何冻结数值。

## 3. 保留的 M 方正式定义

- PC：`PC_NEXT`、`PC_TARGET`、`PC_JALR`
- Forward：`FWD_REG`、`FWD_WB`、`FWD_MEM`
- ALU A/B：`A_REG`、`A_PC`、`A_ZERO`、`B_REG`、`B_IMM`
- WB：`WB_ALU`、`WB_LOAD`、`WB_PC4`
- Immediate：`IMM_NONE`、`IMM_I`、`IMM_S`、`IMM_B`、`IMM_U`、`IMM_J`
- Branch：`BR_NONE`、`BR_EQ`、`BR_NE`、`BR_LT`、`BR_GE`、`BR_LTU`、`BR_GEU`
- Jump：`J_NONE`、`J_JAL`、`J_JALR`
- ALU：`ALU_ADD/SUB/AND/OR/XOR/SLT/SLTU/SLL/SRL/SRA`
- `decode_t`：字段顺序与位宽原样保留，总宽度 28 位；生产 Control 已成功使用它编译。

## 4. Datapath 兼容别名

新增且均引用 M 方正式符号，不维护独立数字：

| Datapath 别名 | M 方基准 |
|---|---|
| `PC_SEQ` | `PC_NEXT` |
| `ALUA_RS1/ALUA_PC/ALUA_ZERO` | `A_REG/A_PC/A_ZERO` |
| `ALUB_RS2/ALUB_IMM` | `B_REG/B_IMM` |
| `BR_BEQ/BR_BNE/BR_BLT/BR_BGE/BR_BLTU/BR_BGEU` | `BR_EQ/BR_NE/BR_LT/BR_GE/BR_LTU/BR_GEU` |
| `JUMP_NONE/JUMP_JAL/JUMP_JALR` | `J_NONE/J_JAL/J_JALR` |

实际 Datapath RTL 未使用上述清单以外的旧名称。

## 5. LOAD/STORE 编码

M 方 `main_decoder.sv` 对 load 直接输出 `instr_d[14:12]`，允许 0、1、2、4、5；对 store 输出 `instr_d[13:12]`，允许 funct3 0、1、2。因此兼容符号为：

| 名称 | 编码 | 名称 | 编码 |
|---|---:|---|---:|
| `LOAD_LB` | `3'b000` | `STORE_SB` | `2'b00` |
| `LOAD_LH` | `3'b001` | `STORE_SH` | `2'b01` |
| `LOAD_LW` | `3'b010` | `STORE_SW` | `2'b10` |
| `LOAD_LBU` | `3'b100` |  |  |
| `LOAD_LHU` | `3'b101` |  |  |

## 6. 唯一 package 编译规则

Datapath 工程内正式 package 只有：

`D:\FPGA\CPU\face_recognition_soc\rtl\common\cpu_control_pkg.sv`

任何 Datapath 或临时 Control 兼容构建必须把它放在所有引用模块之前且只编译一次。禁止同时加入 `D:\FPGA\CPU\incoming\cpu_control\rtl\common\cpu_control_pkg.sv`，否则会产生同名 package 重定义且破坏唯一编码来源。M 方尚未对新候选哈希正式冻结；真实集成前仍须交换文件并确认哈希。

## 7. 测试结果

### 7.1 package 单元测试

命令：

```powershell
& 'C:\msys64\usr\bin\bash.exe' -lc 'export PATH=/ucrt64/bin:/usr/bin:$PATH; cd /d/FPGA/CPU/face_recognition_soc; ./scripts/run_pkg_tests.sh'
```

结果：`PASS: cpu_control_pkg compatibility`；退出码 0。测试显式断言全部 M 方编码、Datapath 别名、LOAD/STORE、`decode_t` 字段读写和常量/结构体位宽。

### 7.2 原有基础回归

命令：

```powershell
& 'C:\msys64\usr\bin\bash.exe' -lc 'export PATH=/ucrt64/bin:/usr/bin:$PATH; cd /d/FPGA/CPU/face_recognition_soc; export TMPDIR="$PWD/build/tmp" TMP="$PWD/build/tmp" TEMP="$PWD/build/tmp"; mkdir -p "$TMPDIR"; ./scripts/run_base_tests.sh'
```

结果：`PASS: base datapath modules`；退出码 0。ALU、立即数、PC、寄存器堆及四组流水寄存器没有因 package 修改发生回归。

### 7.3 M 方 Control 兼容 lint

最终命令：

```powershell
& 'C:\msys64\usr\bin\bash.exe' -lc 'export PATH=/ucrt64/bin:/usr/bin:$PATH; cd /d/FPGA/CPU/face_recognition_soc; ./scripts/check_control_pkg_compat.sh'
```

最终结果：`PASS: M Control compiles with Datapath cpu_control_pkg`；退出码 0。顶层为 M 方 `cpu_control`，输入仅为 Datapath 新 package 加 M 方 filelist 中六个 Control RTL，明确未加入 M 方同名 package。

首次无警告例外的 `-Wall` lint 返回 1，原因仅为 30 个 unused 警告：M 方保留的 `clk`、`mul_busy`、`illegal_d`、`operand_unready` 以及共享 package 中当前 Control 编译未引用的符号。没有语法、未定义符号、类型、宽度或编码错误。最终脚本只对本项兼容检查加入 `-Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM`；其他 lint 类别仍启用且致命，未使用 `-Wno-lint`、`-Wno-fatal` 或 `--bbox-unsup`。

## 8. 当前警告分类

| 警告 | 分类 | 处理 |
|---|---|---|
| package `UNUSEDPARAM` | 共享接口的另一侧使用，预期且无害 | package 不删除符号；仅 Control 兼容 lint 局部屏蔽该类别 |
| Control `clk/mul_busy/illegal_d/operand_unready` `UNUSEDSIGNAL` | M 方保留接口/诊断信号 | 不修改 M 方 RTL；仅兼容 lint 局部屏蔽该类别 |
| `imm_gen.instr[6:0]` 未使用 | 立即数生成器按格式只使用相应高位，既有设计警告 | 基础回归脚本原有 `-Wno-fatal` 允许继续；未修改模块 |
| `STDOUT_FILENO/STDERR_FILENO` 重定义 | Verilator 5.050 与 UCRT C++ 头文件工具链警告 | 不属于 RTL；未掩盖或修改工具链 |
| MSYS2 home 权限提示 | 首次沙箱启动环境提示 | 实际测试改用工程 `build/tmp`，未修改 MSYS2 home |

## 9. 工具、Git 与执行记录

- Verilator：`5.050 2026-07-01 rev vUNKNOWN-built20260702`。
- 预期 Bash `C:\msys64\ucrt64\bin\bash.exe` 不存在；实际使用 `C:\msys64\usr\bin\bash.exe`。
- PowerShell 与 MSYS2 PATH 均未找到 `git`；未安装 Git，因此无法取得 `git status/diff`。已通过允许文件清单、哈希和只读文件枚举控制范围。
- 首次以错误 Bash 路径启动失败，未进入脚本；随后沙箱内启动因不能建立工程 `build/pkg` 返回 1，未编译 RTL；获准在相同限定工程目录执行后，三项最终测试均为 0。

## 10. 修改后哈希与结论

兼容候选 package SHA-256：

`E57746529AB1D6D3FE7D425DE57311EF2CF3F7B45DBEB73C04EE36B42692F2BD`

所有验收项已满足：工程内只有一个正式 package；M 方定义与 `decode_t` 完整保留；Datapath 别名和 LOAD/STORE 齐全；package 单测、基础回归及 M 方 Control 兼容 lint 的最终退出码均为 0；未修改 M/Z 工程或既有 Datapath 模块接口；未全局关闭 lint。本结果是编译兼容证据，不是实际 Control/CNN 联调证据。
